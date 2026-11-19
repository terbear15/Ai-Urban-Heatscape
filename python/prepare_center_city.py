"""Center City, Philadelphia, as the union of its neighborhood polygons.

Source: Azavea Philadelphia neighborhoods (the boundaries published on
OpenDataPhilly). Writes dist/location/center-city.geojson (the area),
center-city-mask.geojson (everything else, for dimming) and
center-city-names.json (every neighborhood name, to check the selection).
"""
import json
from pathlib import Path
import requests
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "location"
URLS = [
    "https://raw.githubusercontent.com/opendataphilly/open-geo-data/master/philadelphia-neighborhoods/philadelphia-neighborhoods.geojson",
    "https://raw.githubusercontent.com/opendataphilly/open-geo-data/main/philadelphia-neighborhoods/philadelphia-neighborhoods.geojson",
    "https://raw.githubusercontent.com/azavea/geo-data/master/Neighborhoods_Philadelphia/Neighborhoods_Philadelphia.geojson",
]
# Neighborhoods between Vine Street and South Street, river to river.
CENTER_CITY = {"rittenhouse", "logan square", "fitler square", "center city east", "center city west",
               "center city", "washington square", "washington square west", "society hill", "old city",
               "chinatown", "penns landing", "penn's landing", "elfreths alley", "elfreth's alley"}


def label(props):
    return str(props.get("LISTNAME") or props.get("listname") or props.get("NAME") or props.get("name") or "")


def main():
    data = None
    for url in URLS:
        response = requests.get(url, timeout=60)
        print(url, response.status_code)
        if response.ok:
            data = response.json()
            break
    assert data, "no neighborhood source could be downloaded"
    names = sorted({label(f["properties"]) for f in data["features"]})
    (OUT / "center-city-names.json").write_text(json.dumps(names, indent=1), encoding="utf-8")
    chosen = [f for f in data["features"] if label(f["properties"]).lower().replace("_", " ") in CENTER_CITY]
    print("chosen:", sorted(label(f["properties"]) for f in chosen))
    assert chosen, "no Center City neighborhoods matched; see center-city-names.json"
    area = unary_union([shape(f["geometry"]) for f in chosen]).buffer(0)
    west, south, east, north = area.bounds
    outer = box(west - 1, south - 1, east + 1, north + 1)
    def fc(geometry, layer):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"layer": layer,
             "neighborhoods": sorted(label(f["properties"]) for f in chosen)}, "geometry": mapping(geometry)}]}
    (OUT / "center-city.geojson").write_text(json.dumps(fc(area, "land"), separators=(",", ":")), encoding="utf-8")
    (OUT / "center-city-mask.geojson").write_text(json.dumps(fc(outer.difference(area), "mask"), separators=(",", ":")), encoding="utf-8")
    print("bounds:", [round(v, 6) for v in area.bounds])


if __name__ == "__main__":
    main()
