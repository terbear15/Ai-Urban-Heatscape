"""Generate city views from Census shoreline-clipped place boundaries."""
import json
from pathlib import Path
import requests
import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import transform, unary_union
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "cities"
OUT.mkdir(exist_ok=True)
CACHE = ROOT / "raw" / "places"
CACHE.mkdir(parents=True, exist_ok=True)
BASE = "https://www2.census.gov/geo/tiger/GENZ2024/shp/"
CITIES = {
    "new-york": ("36", "New York"),
    "san-francisco": ("06", "San Francisco"),
    "los-angeles": ("06", "Los Angeles"),
    "seattle": ("53", "Seattle"),
    "houston": ("48", "Houston"),
    "phoenix": ("04", "Phoenix"),
    "miami": ("12", "Miami"),
    "chicago": ("17", "Chicago"),
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


def main():
    tables = {state: places(state) for state in {value[0] for value in CITIES.values()}}
    views = {}
    for key, (state, name) in CITIES.items():
        table = tables[state]
        members = LA_PLACES if key == "los-angeles" else (name,)
        selection = table[table.NAME.isin(members)]
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
        west, south, east, north = land.bounds
        center = [(west+east)/2, (south+north)/2]
        local = CRS.from_proj4(f"+proj=aeqd +lat_0={center[1]} +lon_0={center[0]} +datum=WGS84")
        forward = Transformer.from_crs(4326, local, always_xy=True).transform
        reverse = Transformer.from_crs(local, 4326, always_xy=True).transform
        # Rectangular camera envelope with roughly 200 miles of context on each side.
        scope = transform(reverse, transform(forward, land).buffer(200*1609.344, quad_segs=48)).bounds
        outer = box(scope[0]-3, scope[1]-3, scope[2]+3, scope[3]+3)
        features = [{"type": "Feature", "properties": {"layer": role}, "geometry": mapping(geometry)}
                    for role, geometry in [("land", land), ("mask", outer.difference(land))]]
        save(OUT / f"{key}.geojson", {"type": "FeatureCollection", "features": features})
        views[key] = {"name": name, "bounds": [[west, south], [east, north]],
                      "limit": [[scope[0], scope[1]], [scope[2], scope[3]]],
                      "custom": key == "los-angeles"}
        print(name, land.geom_type, land.bounds)
    save(OUT / "views.json", views)


if __name__ == "__main__":
    main()
