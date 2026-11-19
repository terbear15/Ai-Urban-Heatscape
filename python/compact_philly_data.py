"""Shrink dist/philly-data.js for the browser (run after the data and LiDAR steps).

* coordinates rounded to 6 decimals (about 10 cm)
* buildings keep only height; walking segments become [a, b, lon1, lat1, lon2, lat2]
* tree crowns keep their outer ring(s) and height
The engine (dist/engine.js) accepts both this compact form and the full one.
"""
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "dist" / "philly-data.js"


def r(value):
    return [r(v) for v in value] if isinstance(value, list) else round(value, 6)


def main():
    text = PATH.read_text(encoding="utf-8")
    data = json.loads(text[len("window.PHILLY="):].rstrip().rstrip(";"))
    if data.get("compact"):
        print("already compact")
        return
    buildings = [{"type": "Feature", "properties": {"height": f["properties"]["height"]},
                  "geometry": {"type": "Polygon", "coordinates": [r(f["geometry"]["coordinates"][0])]}}
                 for f in data["buildings"]["features"]]
    edges = [[e["a"], e["b"], *r(e["p"]), *r(e["q"])] for e in data["edges"]]
    trees = []
    for f in data.get("trees", {}).get("features", []):
        g = f["geometry"]
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        trees.append({"type": "Feature", "properties": {"h": f["properties"].get("h", f["properties"].get("height_m"))},
                      "geometry": {"type": "MultiPolygon", "coordinates": [[r(ring)] for ring in rings]}})
    data.update(compact=True, buildings={"type": "FeatureCollection", "features": buildings}, edges=edges,
                trees={"type": "FeatureCollection", "features": trees})
    PATH.write_text("window.PHILLY=" + json.dumps(data, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"{len(text) / 1e6:.1f} MB -> {PATH.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
