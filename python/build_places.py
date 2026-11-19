"""Named places in Center City, Philadelphia, for instant search suggestions.

Downloads named OpenStreetMap features (attractions, museums, parks, restaurants,
shops, stations, offices, notable buildings) inside the Center City area plus a
small margin, and writes dist/location/center-city-places.js as
window.PLACES = [[name, kind, lon, lat], ...].
"""
import json
from pathlib import Path

import requests
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
AREA = shape(json.loads((ROOT / "dist" / "location" / "center-city.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
REACH = AREA.buffer(.0015)
OUT = ROOT / "dist" / "location" / "center-city-places.js"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
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
    bbox = f"{south},{west},{north},{east}"
    parts = "".join(f'nwr["name"]["{k}"]({bbox});' for k in KEYS)
    query = f"[out:json][timeout:180];({parts});out center tags;"
    data = None
    for url in ENDPOINTS:
        try:
            response = requests.post(url, data={"data": query}, timeout=240,
                                     headers={"User-Agent": "HeatScape course project"})
            response.raise_for_status()
            data = response.json()
            print(url, len(data["elements"]), "elements", flush=True)
            break
        except Exception as error:
            print(url, "failed:", error, flush=True)
    assert data, "all Overpass endpoints failed"
    places, seen = [], set()
    for element in data["elements"]:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or any(tags.get(k) in v for k, v in SKIP.items()):
            continue
        lon = element.get("lon", element.get("center", {}).get("lon"))
        lat = element.get("lat", element.get("center", {}).get("lat"))
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
