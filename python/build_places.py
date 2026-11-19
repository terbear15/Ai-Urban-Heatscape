"""Named places in Center City, Philadelphia, for instant search suggestions.

Downloads named OpenStreetMap features (attractions, museums, parks, restaurants,
shops, stations, offices, notable buildings) inside the Center City area plus a
small margin, and writes dist/location/center-city-places.js as
window.PLACES = [[name, kind, lon, lat], ...].
"""
import json
from pathlib import Path

from shapely.geometry import Point, shape

from osm_api import fetch

ROOT = Path(__file__).resolve().parents[1]
AREA = shape(json.loads((ROOT / "dist" / "location" / "center-city.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
REACH = AREA.buffer(.0015)
OUT = ROOT / "dist" / "location" / "center-city-places.js"
KEYS = ["tourism", "historic", "leisure", "amenity", "shop", "railway", "public_transport", "office", "building", "place"]
SKIP = {"amenity": {"bench", "waste_basket", "bicycle_parking", "parking_entrance", "vending_machine", "atm",
                    "post_box", "telephone", "drinking_water", "charging_station", "parking_space", "recycling"}}


def kind(tags):
    for key in KEYS:
        if key in tags:
            value = tags[key]
            return value.replace("_", " ") if key != "building" else "building"
    return "place"


def main():
    west, south, east, north = REACH.bounds
    nodes, ways = fetch(west, south, east, north)
    elements = [{"lon": lon, "lat": lat, "tags": tags} for lon, lat, tags in nodes.values() if tags.get("name")]
    for refs, tags in ways.values():
        if tags.get("name") and any(k in tags for k in KEYS):
            points = [nodes[r] for r in refs if r in nodes]
            if points:
                elements.append({"lon": sum(p[0] for p in points) / len(points),
                                 "lat": sum(p[1] for p in points) / len(points), "tags": tags})
    data = {"elements": [e for e in elements if any(k in e["tags"] for k in KEYS)]}
    places, seen = [], set()
    for element in data["elements"]:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or any(tags.get(k) in v for k, v in SKIP.items()):
            continue
        lon, lat = element["lon"], element["lat"]
        if lon is None or not REACH.contains(Point(lon, lat)):
            continue
        k = kind(tags)
        key = (name.lower(), round(lon, 3), round(lat, 3))
        if key in seen:
            continue
        seen.add(key)
        # Well-known landmarks first in ties.
        rank = 0 if ("tourism" in tags or "historic" in tags or tags.get("leisure") == "park") else 1
        places.append([name, k, round(lon, 6), round(lat, 6), rank])
    places.sort(key=lambda p: (p[4], p[0].lower()))
    OUT.write_text("window.PLACES=" + json.dumps([p[:4] for p in places], separators=(",", ":"), ensure_ascii=False) + ";",
                   encoding="utf-8")
    print(len(places), "places", f"{OUT.stat().st_size / 1e3:.0f} kB", flush=True)


if __name__ == "__main__":
    main()
