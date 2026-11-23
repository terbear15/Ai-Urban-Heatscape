"""Generate city views from Census shoreline-clipped place boundaries."""
import json
from pathlib import Path
import requests
import geopandas as gpd
from shapely.geometry import shape, box, mapping
from shapely.ops import transform, unary_union
from pyproj import CRS, Transformer
from shapely.geometry import Point
from city_zones import ZONES
from downtown_boxes import BOXES
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "dist" / "cities"
OUT.mkdir(exist_ok=True)
CACHE = ROOT / "raw" / "places"
CACHE.mkdir(parents=True, exist_ok=True)
BASE = "https://www2.census.gov/geo/tiger/GENZ2024/shp/"
# Thirty cities. The first twenty: the 20 largest U.S. metro economies (nominal GDP, 2024, from BEA
# county GDP summed to metro areas), stored in that order. The core city of each metro is mapped.
CITIES = {
    "new-york": ("36", "New York"),
    "los-angeles": ("06", "Los Angeles"),
    "chicago": ("17", "Chicago"),
    "san-francisco": ("06", "San Francisco"),
    "dallas": ("48", "Dallas"),
    "houston": ("48", "Houston"),
    "washington": ("11", "Washington"),
    "boston": ("25", "Boston"),
    "atlanta": ("13", "Atlanta"),
    "seattle": ("53", "Seattle"),
    "philadelphia": ("42", "Philadelphia"),
    "miami": ("12", "Miami"),
    "san-jose": ("06", "San Jose"),
    "phoenix": ("04", "Phoenix"),
    "minneapolis": ("27", "Minneapolis"),
    "detroit": ("26", "Detroit"),
    "san-diego": ("06", "San Diego"),
    "denver": ("08", "Denver"),
    "charlotte": ("37", "Charlotte"),
    "baltimore": ("24", "Baltimore"),
    # Ten more large metros with four distinct seasons and a walkable downtown.
    "st-louis": ("29", "St. Louis"),
    "portland": ("41", "Portland"),
    "nashville": ("47", "Nashville"),
    "indianapolis": ("18", "Indianapolis"),
    "cincinnati": ("39", "Cincinnati"),
    "kansas-city": ("29", "Kansas City"),
    "pittsburgh": ("42", "Pittsburgh"),
    "cleveland": ("39", "Cleveland"),
    "salt-lake-city": ("49", "Salt Lake City"),
    "milwaukee": ("55", "Milwaukee"),
}
LA_PLACES = ("Los Angeles", "Santa Monica", "Pasadena", "Inglewood",
             "West Hollywood", "Beverly Hills", "Culver City", "Glendale", "South Pasadena")


def save(path, data):
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def places(state):
    name = f"cb_2024_{state}_place_500k.zip"
    path = CACHE / name
    if not path.exists():
        response = requests.get(BASE + name, timeout=45)
        response.raise_for_status()
        path.write_bytes(response.content)
    return gpd.read_file(path).to_crs(4326)


ACS = "https://api.census.gov/data/2023/acs/acs5"


def tracts(state, city, forward):
    """Census tracts inside the city (projected), with people per km2 (ACS 2023 5-year)."""
    name = f"cb_2024_{state}_tract_500k.zip"
    path = CACHE / name
    if not path.exists():
        response = requests.get(BASE + name, timeout=90)
        response.raise_for_status()
        path.write_bytes(response.content)
    table = gpd.read_file(path).to_crs(4326)
    pops_path = CACHE / f"acs2023_tract_pop_{state}.json"
    if not pops_path.exists():
        r = requests.get(ACS, params={"get": "B01003_001E", "for": "tract:*", "in": f"state:{state} county:*"}, timeout=120)
        if r.status_code != 200 or not r.text.startswith("["):
            raise SystemExit(f"Census API {r.status_code}: {r.text[:300]}")
        rows = r.json()
        pops_path.write_text(json.dumps(rows))
    rows = json.loads(pops_path.read_text())
    head = rows[0]
    pop = {r[head.index("state")] + r[head.index("county")] + r[head.index("tract")]: int(r[0] or 0) for r in rows[1:]}
    w, s_, e, n = transform(reverse_of(forward), city).bounds
    out = []
    for _, row in table.cx[w:e, s_:n].iterrows():
        geom = transform(forward, row.geometry).buffer(0)
        part = geom.intersection(city).buffer(0)
        if part.is_empty or part.area < 0.5 * geom.area:
            continue
        out.append({"id": row.GEOID, "geom": part, "density": pop.get(row.GEOID, 0) / max(geom.area / 1e6, 0.01)})
    return out


def reverse_of(forward):
    return REVERSE[id(forward)]


REVERSE = {}


def largest_parts(geom):
    return sorted(getattr(geom, "geoms", [geom]), key=lambda g: -g.area)


def fill_small_holes(geom, max_area=300_000):
    polys = []
    for p in getattr(geom, "geoms", [geom]):
        holes = [h for h in p.interiors if Polygon(h).area > max_area]
        polys.append(Polygon(p.exterior, holes))
    return unary_union(polys)


# Daylight / standard UTC offsets and abbreviations by time zone.
TIME_ZONES = {
    "eastern": ("-04:00", "EDT", "-05:00", "EST"), "central": ("-05:00", "CDT", "-06:00", "CST"),
    "mountain": ("-06:00", "MDT", "-07:00", "MST"), "arizona": ("-07:00", "MST", "-07:00", "MST"),
    "pacific": ("-07:00", "PDT", "-08:00", "PST"),
}
CITY_ZONE = {
    **dict.fromkeys(["new-york", "washington", "boston", "atlanta", "philadelphia", "miami", "detroit", "charlotte", "baltimore", "indianapolis", "cincinnati", "pittsburgh", "cleveland"], "eastern"),
    **dict.fromkeys(["chicago", "dallas", "houston", "minneapolis", "st-louis", "nashville", "kansas-city", "milwaukee"], "central"),
    "denver": "mountain", "salt-lake-city": "mountain", "phoenix": "arizona",
    **dict.fromkeys(["los-angeles", "san-francisco", "san-jose", "seattle", "san-diego", "portland"], "pacific"),
}
CENTER_CITY = ROOT / "dist" / "location" / "center-city.geojson"
ZONE_DIR = ROOT / "python" / "zones"
# Cities whose connected center runs further than 8 km (Manhattan up to the Upper
# West and East Sides, Downtown LA to Hollywood).
REACH = {"new-york": 14000, "los-angeles": 14000}
# Each area grows by census tracts to about twice its connected center (NYC is all of Manhattan).
GROW = 2.0
NO_GROW = {"new-york"}


def main():
    tables = {state: places(state) for state in {value[0] for value in CITIES.values()}}
    views = {}
    for key, (state, name) in CITIES.items():
        table = tables[state]
        members = LA_PLACES if key == "los-angeles" else (name,)
        selection = table[table.NAME.isin(members)]
        if selection.empty:
            # Consolidated cities (e.g. Indianapolis) are listed as "<name> city (balance)".
            selection = table[table.NAME.str.startswith(name) & table.NAME.str.contains("balance")]
            assert len(selection) == 1, (name, list(selection.NAME))
        else:
            assert set(selection.NAME) == set(members)
        land = unary_union(selection.geometry)
        if key == "los-angeles":
            # Omit the harbor corridor and southern harbor neighborhoods from this study extent.
            land = land.intersection(box(-119, 33.88, -117, 35))
            assert not land.intersects(unary_union(table[table.NAME == "Long Beach"].geometry).buffer(-.00001))
        if key == "san-francisco":
            # Keep the urban peninsula and nearby islands, excluding offshore Farallon Islands.
            land = land.intersection(box(-122.56, 37.68, -122.30, 37.89))
        assert land.is_valid and not land.is_empty
        city_land = land
        zones = ZONES[key]
        lon0 = sum(z[1] if len(z) == 4 else (z[1][0] + z[1][2]) / 2 for z in zones) / len(zones)
        lat0 = sum(z[2] if len(z) == 4 else (z[1][1] + z[1][3]) / 2 for z in zones) / len(zones)
        local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84")
        forward = Transformer.from_crs(4326, local, always_xy=True).transform
        reverse = Transformer.from_crs(local, 4326, always_xy=True).transform
        REVERSE[id(forward)] = reverse
        shapes = []
        official = ZONE_DIR / f"{key}.geojson"
        polygons = {}
        if official.exists():
            for f in json.loads(official.read_text(encoding="utf-8"))["features"]:
                polygons.setdefault(f["properties"]["zone"], []).append(shape(f["geometry"]).buffer(0))
        for zone in zones:
            if zone[0] in polygons:
                # Official boundary (OpenStreetMap neighborhood, district, park or city).
                shapes.append(unary_union(polygons[zone[0]]))
                continue
            if zone[0] in BOXES.get(key, {}):
                # Street-bounded downtown block (python/downtown_boxes.py).
                shapes.append(Polygon(BOXES[key][zone[0]]))
                continue
            if len(zone) == 4:
                _, lon, lat, km = zone
                shapes.append(transform(reverse, transform(forward, Point(lon, lat)).buffer(km * 1000, quad_segs=32)))
            else:
                shapes.append(box(*zone[1]))
        # HeatScape works only in the downtown and visitor areas, on land.
        if key == "philadelphia" and CENTER_CITY.exists():
            # Philadelphia uses the official Center City neighborhoods (python/prepare_center_city.py).
            land = shape(json.loads(CENTER_CITY.read_text(encoding="utf-8"))["features"][0]["geometry"])
        else:
            # One connected downtown: start from the downtown zone and keep only visitor zones
            # within ~1 km of what is already kept (far-off zones are dropped). Gaps of up to
            # ~700 m between kept zones are filled so the area reads as one piece.
            flat = [transform(forward, g) for g in shapes]
            core = next((i for i, z in enumerate(zones) if any(w in z[0] for w in ("Downtown", "Loop", "Lower Manhattan", "Union Square"))), 0)
            kept, grown = [core], True
            while grown:
                grown = False
                for i, g in enumerate(flat):
                    if i not in kept and unary_union([flat[k] for k in kept]).distance(g) <= 1000 \
                            and g.centroid.distance(flat[core].centroid) <= REACH.get(key, 8000):
                        kept.append(i)
                        grown = True
            kept.sort()
            dropped = [zones[i][0] for i in range(len(zones)) if i not in kept]
            if dropped:
                print(name, "drops far zones:", ", ".join(dropped))
            zones = [zones[i] for i in kept]
            city = transform(forward, city_land).buffer(0)
            base = unary_union([flat[i] for i in kept]).intersection(city).buffer(0)
            pool = tracts(CITIES[key][0], city, forward)
            used = set()
            touches = lambda geom, t: t["id"] not in used and geom.distance(t["geom"]) < 5

            def main_part(geom):
                return max(getattr(geom, "geoms", [geom]), key=lambda g: g.intersection(flat[core]).area + g.area * 1e-9)
            # 1. Join the kept zones with whole census tracts (government units that follow streets).
            for _ in range(400):
                main = main_part(base)
                others = [g for g in getattr(base, "geoms", [base]) if not g.equals(main) and g.distance(main) > 5]
                if not others:
                    break
                rest = unary_union(others)
                cands = [t for t in pool if touches(main, t)]
                if not cands:
                    break
                best = min(cands, key=lambda t: t["geom"].distance(rest))
                if best["geom"].distance(rest) >= main.distance(rest):
                    break  # no tract brings the pieces closer (open water between them)
                used.add(best["id"])
                base = unary_union([base, best["geom"]]).buffer(0)
            base = main_part(base)
            core_area = base.area
            # 2. Grow by the most densely populated neighbouring tract until the area doubles.
            if key not in NO_GROW:
                while base.area < GROW * core_area:
                    cands = [t for t in pool if touches(base, t)]
                    if not cands:
                        break
                    best = max(cands, key=lambda t: t["density"])
                    used.add(best["id"])
                    base = main_part(unary_union([base, best["geom"]]).buffer(0))
                print(name, f"{len(used)} census tracts added; {core_area / 1e6:.1f} -> {base.area / 1e6:.1f} km2")
            final = fill_small_holes(base.buffer(0.5, join_style=2).buffer(-0.5, join_style=2)).intersection(city).buffer(0)
            final = main_part(final)
            # List only zones that really ended up inside the area (a zone across a wide river is lost).
            zones = [z for z, i in zip(zones, kept) if flat[i].intersection(final).area >= 0.25 * flat[i].area]
            land = transform(reverse, final).buffer(0)
        assert land.is_valid and not land.is_empty, key
        west, south, east, north = land.bounds
        # Camera envelope with about 15 miles of context around the areas.
        scope = transform(reverse, transform(forward, land).buffer(15*1609.344, quad_segs=48)).bounds
        outer = box(scope[0]-3, scope[1]-3, scope[2]+3, scope[3]+3)
        features = [{"type": "Feature", "properties": {"layer": role}, "geometry": mapping(geometry)}
                    for role, geometry in [("land", land), ("mask", outer.difference(land))]]
        save(OUT / f"{key}.geojson", {"type": "FeatureCollection", "features": features})
        views[key] = {"name": name, "bounds": [[west, south], [east, north]],
                      "limit": [[scope[0], scope[1]], [scope[2], scope[3]]],
                      "custom": False, "zones": [z[0] for z in zones]}
        summer, summer_name, winter, winter_name = TIME_ZONES[CITY_ZONE[key]]
        views[key].update(
            tz={"summer": summer, "summerName": summer_name, "winter": winter, "winterName": winter_name},
            areaName="Center City" if key == "philadelphia" else "Downtown",
            # The shade map opens for a city once its data file exists.
            shade=(ROOT / "dist" / "data" / f"{key}.js").exists(),
        )
        print(name, land.geom_type, land.bounds)
    save(OUT / "views.json", views)


if __name__ == "__main__":
    main()
