"""Pack dist/data/<slug>.js into a compact form and write the map layers.

The pipeline writes readable GeoJSON-style data. Packed (format 3) it is about four
times smaller, which matters for loading on a phone:
  - coordinates become integer offsets from an origin in millionths of a degree
    (about 0.1 m), delta-encoded along each ring;
  - street segments share one node table: [a, b, sidewalk offset * 10, name];
  - tree crowns are stored as their convex hull (the engine sweeps crowns as hulls,
    so the shadow is identical);
  - heights are stored in decimetres.
dist/engine.js unpacks it on load; the map layers are built from it in the browser
(dist/shade-worker.js), so the city is downloaded once. Standard library only; safe to run twice.
Usage: python python/pack_city_data.py [slug ...]"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
Q = 1_000_000


def hull(points):
    pts = sorted(set(points))
    if len(pts) <= 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def outer_rings(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry["type"] == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


def encode_ring(ring, origin):
    ox, oy = origin
    pts = [(round((x - ox) * Q), round((y - oy) * Q)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out, px, py = [], 0, 0
    for x, y in pts:
        out += [x - px, y - py]
        px, py = x, y
    return pts, out


def area_rings(slug):
    """Land polygon rings of the city's area, for keeping map layers inside the boundary."""
    path = DATA.parent / "cities" / f"{slug}.geojson"
    g = json.loads(path.read_text(encoding="utf-8"))
    land = next(f["geometry"] for f in g["features"] if f["properties"].get("layer") == "land")
    polys = [land["coordinates"]] if land["type"] == "Polygon" else land["coordinates"]
    return [(poly[0], poly[1:]) for poly in polys]


def inside(pt, rings):
    def in_ring(ring):
        x, y, hit = pt[0], pt[1], False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
        return hit
    return any(in_ring(outer) and not any(in_ring(h) for h in holes) for outer, holes in rings)


def centroid(ring):
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def write_layers(slug, layers):
    """Map layers keep only objects whose centre lies inside the area (the data itself
    reaches 150 m further so edge streets get the right shade)."""
    area = area_rings(slug)
    for layer, features in layers.items():
        kept = [f for f in features if inside(centroid(f["geometry"]["coordinates"][0][:-1]), area)]
        (DATA / f"{slug}-{layer}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": kept}, separators=(",", ":")), encoding="utf-8")


def decode(flat, origin, key):
    ox, oy = origin
    out, i = [], 0
    while i < len(flat):
        h, n = flat[i] / 10, flat[i + 1]
        x = y = 0
        ring = []
        for k in range(n):
            x += flat[i + 2 + 2 * k]
            y += flat[i + 3 + 2 * k]
            ring.append((ox + x / Q, oy + y / Q))
        out.append(feature(key, round(h, 1), ring))
        i += 2 + 2 * n
    return out


def feature(height_key, height, ring):
    closed = ring + [ring[0]]
    return {"type": "Feature", "properties": {height_key: height},
            "geometry": {"type": "Polygon", "coordinates": [[[round(x, 5), round(y, 5)] for x, y in closed]]}}


def pack(slug):
    path = DATA / f"{slug}.js"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
    if data.get("v") == 3:
        print(slug, "already packed")
        return
    west, south = data["meta"]["bounds"][0], data["meta"]["bounds"][1]
    origin = (round(west, 4), round(south, 4))
    ox, oy = origin
    to_ll = lambda p: (ox + p[0] / Q, oy + p[1] / Q)

    blds, bld_layer = [], []
    for f in data["buildings"]["features"]:
        h = f["properties"].get("height") or 0
        for ring in outer_rings(f["geometry"]):
            pts, enc = encode_ring(ring, origin)
            if len(pts) < 3:
                continue
            blds += [round(h * 10), len(pts)] + enc
            bld_layer.append(feature("height", round(h, 1), [to_ll(p) for p in pts]))

    trees, tree_layer = [], []
    for f in (data.get("trees") or {}).get("features", []):
        props = f["properties"]
        h = props.get("h", props.get("height_m")) or 0
        for ring in outer_rings(f["geometry"]):
            pts, _ = encode_ring(ring, origin)
            pts = hull(pts)
            if len(pts) < 3:
                continue
            if len(pts) > 10:  # at most 10 hull points per crown; the shadow barely changes
                step = len(pts) / 10
                pts = [pts[int(i * step)] for i in range(10)]
            enc, px, py = [], 0, 0
            for x, y in pts:
                enc += [x - px, y - py]
                px, py = x, y
            trees += [round(h * 10), len(pts)] + enc
            tree_layer.append(feature("h", round(h, 1), [to_ll(p) for p in pts]))

    node_index, nodes, edges = {}, [], []
    for e in data["edges"]:
        a, b, x1, y1, x2, y2 = e[:6]
        w = e[6] if len(e) > 6 else 0
        name = e[7] if len(e) > 7 else -1
        ids = []
        for key, x, y in ((a, x1, y1), (b, x2, y2)):
            if key not in node_index:
                node_index[key] = len(nodes) // 2
                nodes += [round((x - ox) * Q), round((y - oy) * Q)]
            ids.append(node_index[key])
        edges += [ids[0], ids[1], round(w * 10), name if name is not None else -1]

    packed = {"v": 3, "origin": [ox, oy], "q": Q, "nodes": nodes, "edges": edges, "buildings": blds,
              "trees": trees, "names": data.get("names", []), "pois": data.get("pois", []), "meta": data["meta"]}
    before = len(text)
    out = "window.CITYDATA=" + json.dumps(packed, separators=(",", ":")) + ";\n"
    path.write_text(out, encoding="utf-8")
    print(f"{slug}: {before / 1e6:.1f} MB -> {len(out) / 1e6:.1f} MB; {len(bld_layer)} buildings, {len(tree_layer)} trees, {len(edges) // 4} segments")


if __name__ == "__main__":
    slugs = sys.argv[1:] or sorted(p.stem for p in DATA.glob("*.js") if not p.stem.endswith("-places"))
    for slug in slugs:
        pack(slug)
