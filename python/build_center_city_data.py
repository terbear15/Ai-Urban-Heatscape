"""Build the Center City, Philadelphia dataset for the in-browser shade engine.

Inputs (downloaded here):
  * dist/location/center-city.geojson: Center City as the union of its official
    neighborhood polygons (python/prepare_center_city.py).
  * OpenStreetMap buildings and walkable ways inside that area plus a 150 m margin,
    from the official OSM API (python/osm_api.py).
Output: dist/philly-data.js (window.PHILLY = {buildings, edges, area, meta}).
Tree crowns are added afterwards by python/prepare_lidar_canopy.py.
"""
import json
import math
from datetime import date
from pathlib import Path

from shapely.geometry import LineString, Polygon, shape

from osm_api import fetch

ROOT = Path(__file__).resolve().parents[1]
AREA_FILE = ROOT / "dist" / "location" / "center-city.geojson"
OUT = ROOT / "dist" / "philly-data.js"
MARGIN_M = 150
WALKABLE = {"footway", "pedestrian", "path", "living_street", "residential", "tertiary", "secondary",
            "primary", "unclassified", "service", "steps", "tertiary_link", "secondary_link",
            "primary_link", "corridor", "cycleway", "track"}
METERS_PER_LEVEL = 3.3
ASSUMED_HEIGHT_M = 12.0


def area():
    feature = json.loads(AREA_FILE.read_text(encoding="utf-8"))["features"][0]
    return shape(feature["geometry"])


def parse_height(tags):
    """Height in meters and how it was obtained."""
    for key in ("height", "building:height"):
        value = tags.get(key)
        if value:
            text = value.lower().replace(" ", "")
            try:
                if text.endswith("ft") or text.endswith("'"):
                    return float(text.rstrip("ft'")) * .3048, "OSM height"
                return float(text.rstrip("m")), "OSM height"
            except ValueError:
                pass
    levels = tags.get("building:levels")
    if levels:
        try:
            return float(levels) * METERS_PER_LEVEL, "OSM levels × 3.3 m"
        except ValueError:
            pass
    return ASSUMED_HEIGHT_M, "assumed 12 m"


def main():
    zone = area()
    lat0 = zone.centroid.y
    pad_lat = MARGIN_M / 111320
    pad_lon = MARGIN_M / (111320 * math.cos(math.radians(lat0)))
    west, south, east, north = zone.bounds
    west, south, east, north = west - pad_lon, south - pad_lat, east + pad_lon, north + pad_lat
    # Margin around the official area, measured roughly in degrees (fine at this scale).
    reach = zone.buffer(max(pad_lat, pad_lon))
    nodes, ways = fetch(west, south, east, north)
    source = "https://api.openstreetmap.org/api/0.6/map"

    buildings, edges, seen = [], [], set()
    for way_id, (ids, tags) in ways.items():
        if any(i not in nodes for i in ids) or len(ids) < 2:
            continue
        coords = [[round(nodes[i][0], 7), round(nodes[i][1], 7)] for i in ids]
        element = {"id": way_id}
        is_building = (tags.get("building", "no") != "no") or ("building:part" in tags)
        if is_building and len(coords) >= 4 and ids[0] == ids[-1]:
            polygon = Polygon(coords)
            if not polygon.is_valid or polygon.area == 0 or not polygon.intersects(reach):
                continue
            height, basis = parse_height(tags)
            base = 0.0
            try:
                base = float(str(tags.get("min_height", "0")).rstrip("m"))
            except ValueError:
                pass
            if tags.get("building") == "roof" or base >= height:
                continue  # canopies and floating parts cast no ground-level street shade worth modelling
            buildings.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]},
                              "properties": {"id": str(element["id"]), "height": round(max(3, min(300, height)), 1),
                                             "basis": basis, "name": tags.get("name", "Building")}})
            continue
        highway = tags.get("highway")
        if (highway not in WALKABLE or tags.get("area") == "yes" or tags.get("access") in {"no", "private"}
                or tags.get("foot") in {"no", "private"} or tags.get("service") == "parking_aisle"):
            continue
        name = tags.get("name") or highway.replace("_", " ")
        for a, b, p, q in zip(ids, ids[1:], coords, coords[1:]):
            if a == b or (min(a, b), max(a, b)) in seen:
                continue
            if not LineString([p, q]).intersects(reach):
                continue
            seen.add((min(a, b), max(a, b)))
            edges.append({"a": str(a), "b": str(b), "p": p, "q": q, "name": name, "kind": highway})

    assumed = sum(f["properties"]["basis"].startswith("assumed") for f in buildings)
    data = {
        "buildings": {"type": "FeatureCollection", "features": buildings},
        "edges": edges,
        "trees": {"type": "FeatureCollection", "features": []},
        "meta": {
            "source": source, "retrieved": date.today().isoformat(),
            "license": "ODbL, © OpenStreetMap contributors",
            "bounds": [round(west, 6), round(south, 6), round(east, 6), round(north, 6)],
            "area": "Center City: Center City East, Chinatown, Fitler Square, Logan Square, Old City, "
                    "Rittenhouse, Society Hill, Washington Square West (OpenDataPhilly neighborhoods), "
                    f"plus a {MARGIN_M} m margin",
            "buildings": len(buildings), "assumed_heights": assumed, "segments": len(edges),
            "limitations": "Street centerlines, not verified sidewalks. Some building heights are assumed. "
                           "Relation (multipolygon) buildings are omitted.",
        },
    }
    OUT.write_text("window.PHILLY=" + json.dumps(data, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"{len(buildings)} buildings ({assumed} assumed heights), {len(edges)} segments, "
          f"{OUT.stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
