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
from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from city_zones import OFFICIAL, ZONES  # noqa: E402

OUT = Path(__file__).resolve().parent / "zones"
URL = "https://nominatim.openstreetmap.org/search"
NTA = "https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson"
LACOUNTY = "https://services1.arcgis.com/AXaYBvnJsB5Q7sDF/ArcGIS/rest/services/eGIS_CountyWSA/FeatureServer/0/query"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
# Kinds of OSM objects that are areas people name: boundaries, places and parks. Shops,
# campuses, buildings and roads are refused even when they share the name.
GOOD_TYPES = {"administrative", "neighbourhood", "neighborhood", "suburb", "quarter", "district", "borough",
              "city", "town", "village", "local_authority", "census", "park", "national_park", "protected_area",
              "historic", "garden", "nature_reserve", "political"}
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


def ok(geom, lon0, lat0, official=False):
    if geom.is_empty:
        return False
    c = geom.representative_point()
    far = GEOD.inv(lon0, lat0, c.x, c.y)[2] / 1000
    return far <= 10 and (0.05 if not official else 0.02) <= km2(geom) <= 60


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


def get_json(url, params, tries=4):
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=90)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as error:
            print("  retry", url, error)
            time.sleep(4 * (attempt + 1))
    return None


def from_dataset(name):
    """'nta:<name>' (NYC), 'lacounty:<label>' or 'lacity:<city>' (LA County CSAs). Returns (geometry, source id) or None."""
    kind, label = name.split(":", 1)
    if kind == "nta":
        data = get_json(NTA, {"ntaname": label})
        src = "NYC DCP NTA 2020"
    else:
        where = f"LABEL='{label}'" if kind == "lacounty" else f"LCITY='{label}' AND CITY_TYPE='City'"
        data = get_json(LACOUNTY, {"where": where, "outFields": "LABEL", "outSR": 4326, "f": "geojson"})
        src = "LA County Countywide Statistical Areas"
    feats = (data or {}).get("features") or []
    geoms = [shape(f["geometry"]).buffer(0) for f in feats if f.get("geometry")]
    return (unary_union(geoms), src) if geoms else None


def overpass(label, lon0, lat0):
    """Named areas within ~12 km, built from way/relation geometry."""
    d = 0.12
    bbox = f"{lat0 - d},{lon0 - d * 1.3},{lat0 + d},{lon0 + d * 1.3}"
    esc = label.replace('"', '\\"')
    q = (f'[out:json][timeout:90];(way["name"="{esc}"]["area"!="no"]({bbox});'
         f'relation["name"="{esc}"]({bbox}););out geom;')
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=45)
            r.raise_for_status()
            elements = r.json().get("elements", [])
            break
        except (requests.RequestException, ValueError) as error:
            print("  overpass retry", url, error)
            time.sleep(3)
    else:
        return []
    out = []
    for el in elements:
        tags = el.get("tags", {})
        kind = tags.get("boundary") or tags.get("place") or tags.get("leisure") or tags.get("historic") or ""
        if kind not in GOOD_TYPES and tags.get("boundary") != "administrative":
            continue
        lines = []
        if el["type"] == "way":
            lines = [el.get("geometry", [])]
        else:
            lines = [m.get("geometry", []) for m in el.get("members", []) if m.get("role") in ("outer", "") and m.get("type") == "way"]
        segs = [LineString([(p["lon"], p["lat"]) for p in g]) for g in lines if len(g) >= 2]
        if not segs:
            continue
        polys = list(polygonize(linemerge(segs)))
        if polys:
            out.append((unary_union(polys).buffer(0), f"{el['type']}/{el['id']}", kind))
    return out


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
                if ":" in name and name.split(":", 1)[0] in ("nta", "lacounty", "lacity"):
                    hit = from_dataset(name)
                    if hit:
                        pick = (hit[0], hit[1], "official dataset")
                else:
                    label = name.split(",")[0].strip()
                    for hit in search(f"{name}, {STATES[slug]}"):
                        g = hit.get("geojson") or {}
                        kind = hit.get("type", "")
                        if g.get("type") not in ("Polygon", "MultiPolygon") or kind not in GOOD_TYPES:
                            continue
                        pick = (shape(g).buffer(0), f"{hit.get('osm_type')}/{hit.get('osm_id')}", kind)
                        if ok(pick[0], lon0, lat0):
                            break
                        pick = None
                    if not pick:
                        for cand in overpass(label, lon0, lat0):
                            if ok(cand[0], lon0, lat0):
                                pick = cand
                                break
                if pick and ok(pick[0], lon0, lat0, official=pick[2] == "official dataset"):
                    geom, source, kind = pick
                    size = km2(geom)
                    found += 1
                    features.append({"type": "Feature", "geometry": mapping(geom), "properties": {
                        "zone": zone, "query": name, "source": source, "type": kind, "km2": round(size, 2)}})
                    print(f"{slug}: {name} -> {source} {kind} {size:.2f} km2")
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
