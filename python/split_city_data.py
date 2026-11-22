"""Split dist/data/<slug>.js into map layers the browser map loads on its own thread:
dist/data/<slug>-buildings.geojson (height per footprint) and dist/data/<slug>-trees.geojson.
Run for every city that has data (no arguments) or for given slugs. Standard library only."""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"


def split(slug):
    text = (DATA / f"{slug}.js").read_text(encoding="utf-8")
    data = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
    for layer in ("buildings", "trees"):
        collection = data.get(layer) or {"type": "FeatureCollection", "features": []}
        (DATA / f"{slug}-{layer}.geojson").write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    print(slug, len(data["buildings"]["features"]), "buildings,", len((data.get("trees") or {}).get("features", [])), "trees")


slugs = sys.argv[1:] or sorted(p.stem for p in DATA.glob("*.js") if not p.stem.endswith("-places"))
for slug in slugs:
    split(slug)
