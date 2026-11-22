"""Look up official boundary polygons for every downtown and visitor zone.

For each zone in city_zones.OFFICIAL, each named place is searched in OpenStreetMap
through Nominatim (one request per second, as its usage policy asks). The first result
that is a polygon of a sensible size (0.02-60 km²) and lies within 10 km of the zone's
old circle center is kept. Output: python/zones/<slug>.geojson with one feature per
place (zone, query, OSM id, class/type) and python/zones/report.json listing anything
that did not resolve. Run on GitHub Actions; needs requests, shapely and pyproj."""
import json
import math
import sys
import time
from pathlib import Path

import requests
from pyproj import Geod
from shapely.geometry import mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from city_zones import OFFICIAL, ZONES  # noqa: E402

OUT = Path(__file__).resolve().parent / "zones"
URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}
GEOD = Geod(ellps="WGS84")
STATES = {"new-york": "New York", "los-angeles": "California", "chicago": "Illinois", "houston": "Texas",
          "phoenix": "Arizona", "san-diego": "California", "dallas": "Texas", "charlotte": "North Carolina",
          "san-francisco": "California", "seattle": "Washington", "denver": "Colorado",
          "washington": "District of Columbia", "boston": "Massachusetts", "atlanta": "Georgia",
          "minneapolis": "Minnesota", "san-jose": "California", "detroit": "Michigan",
          "baltimore": "Maryland", "miami": "Florida"}


def km2(geom):
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def center_of(zone):
    if len(zone) == 4:
        return zone[1], zone[2]
    w, s, e, n = zone[1]
    return (w + e) / 2, (s + n) / 2


def search(query):
    for attempt in range(4):
        try:
            r = requests.get(URL, params={"q": query, "format": "jsonv2", "polygon_geojson": 1, "limit": 8,
                                          "countrycodes": "us", "polygon_threshold": 0.00002},
                             headers=HEADERS, timeout=60)
            time.sleep(1.1)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as error:
            print("  retry", query, error)
            time.sleep(5 * (attempt + 1))
    return []


def main():
    OUT.mkdir(exist_ok=True)
    report = {}
    for slug, zones in OFFICIAL.items():
        circles = {z[0]: z for z in ZONES[slug]}
        features, missing = [], []
        for zone, names in zones.items():
            lon0, lat0 = center_of(circles[zone])
            found = 0
            for name in names:
                pick = None
                for hit in search(f"{name}, {STATES[slug]}"):
                    g = hit.get("geojson") or {}
                    if g.get("type") not in ("Polygon", "MultiPolygon"):
                        continue
                    geom = shape(g).buffer(0)
                    c = geom.representative_point()
                    far = GEOD.inv(lon0, lat0, c.x, c.y)[2] / 1000
                    size = km2(geom)
                    if far <= 10 and 0.02 <= size <= 60:
                        pick = (hit, geom, size)
                        break
                if pick:
                    hit, geom, size = pick
                    found += 1
                    features.append({"type": "Feature", "geometry": mapping(geom), "properties": {
                        "zone": zone, "query": name, "osm": f"{hit.get('osm_type')}/{hit.get('osm_id')}",
                        "class": hit.get("category") or hit.get("class"), "type": hit.get("type"),
                        "label": hit.get("display_name", "")[:120], "km2": round(size, 2)}})
                    print(f"{slug}: {name} -> {hit.get('osm_type')}/{hit.get('osm_id')} {hit.get('type')} {size:.2f} km2")
                else:
                    print(f"{slug}: {name} -> not found")
                    missing.append(name)
            if not found:
                missing.append(f"ZONE {zone} (circle kept)")
        (OUT / f"{slug}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
        report[slug] = {"places": len(features), "missing": missing}
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
