"""Derive tree canopy heights for Center City, Philadelphia from classified NOAA EPT LiDAR.

Crown outlines come from the city's 2015 tree canopy layer (PPR, via CARTO). For each
crown, the 90th-percentile height of first-return non-ground LiDAR points above the
local bare-earth surface (both rasterized to a 2 m grid with rasterio) gives its height.
Results are written to dist/location/lidar-canopy.geojson and added to dist/philly-data.js
as PHILLY.trees for the in-browser shade engine.
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import laspy
import numpy as np
import requests
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "raw" / "lidar" / "ept"
CACHE.mkdir(parents=True, exist_ok=True)
EPT = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/9848/"
CARTO = "https://phl.carto.com/api/v2/sql"
CENTER_CITY = shape(json.loads((ROOT / "dist" / "location" / "center-city.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
REACH = CENTER_CITY.buffer(.002)  # about 150-200 m around the official area, matching the street data
AREA = tuple(round(v, 5) for v in REACH.bounds)
DEPTH = 10
RESOLUTION = 2


def fetch(url, path, params=None):
    if not path.exists():
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=40)
                response.raise_for_status()
                path.write_bytes(response.content)
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
    return path


def main():
    metadata = json.loads(fetch(EPT + "ept.json", CACHE / "ept.json").read_bytes())
    crs = CRS.from_user_input(metadata["srs"]["wkt"])
    assert crs.axis_info[0].unit_conversion_factor == 1
    to_meters = Transformer.from_crs(4326, crs, always_xy=True).transform
    to_degrees = Transformer.from_crs(crs, 4326, always_xy=True).transform
    west, south, east, north = transform(to_meters, box(*AREA)).bounds
    west, south, east, north = math.floor(west), math.floor(south), math.ceil(east), math.ceil(north)
    grid_shape = (math.ceil((north-south)/RESOLUTION), math.ceil((east-west)/RESOLUTION))
    affine = from_origin(west, north, RESOLUTION, RESOLUTION)

    xmin, ymin, _, xmax, _, _ = metadata["bounds"]
    edge = xmax-xmin
    keys = set()

    def walk(page):
        hierarchy = json.loads(fetch(EPT + f"ept-hierarchy/{page}.json", CACHE / f"{page}.json").read_bytes())
        for key, count in hierarchy.items():
            depth, ix, iy, _ = map(int, key.split("-"))
            size = edge / 2**depth
            x, y = xmin+ix*size, ymin+iy*size
            if depth > DEPTH or x > east or y > north or x+size < west or y+size < south:
                continue
            if count == -1 and key != page:
                walk(key)
            elif count > 0:
                keys.add(key)

    walk("0-0-0-0")
    print(f"Selected {len(keys)} EPT nodes for {AREA}", flush=True)
    assert keys
    area = REACH
    envelope = ",".join(map(str, AREA))
    query = ("SELECT cartodb_id, the_geom FROM ppr_tree_canopy_outlines_2015 "
             f"WHERE the_geom && ST_MakeEnvelope({envelope},4326)")
    raw = fetch(CARTO, CACHE / "canopy.geojson", {"q": query, "format": "geojson"})
    crowns = [(int(f["properties"]["cartodb_id"]), shape(f["geometry"]).intersection(area))
              for f in json.loads(raw.read_bytes())["features"] if f.get("geometry")]
    crowns = [(key, poly) for key, poly in crowns if poly.area > 0]
    crown_ids = rasterize([(transform(to_meters, geom), i) for i, (_, geom) in enumerate(crowns, 1)],
                          out_shape=grid_shape, transform=affine, dtype="int32")
    old_data = (ROOT / "dist" / "philly-data.js").read_text(encoding="utf-8")
    old_buildings = json.loads(old_data[len("window.PHILLY="):].rstrip().rstrip(";"))["buildings"]["features"]
    buildings = rasterize([(transform(to_meters, shape(f["geometry"])), 1)
                           for f in old_buildings if shape(f["geometry"]).intersects(area)],
                          out_shape=grid_shape, transform=affine, dtype="uint8")
    ground = np.full(grid_shape, np.inf)
    vegetation = []
    points = 0
    classes = {}

    def read(key):
        path = fetch(EPT + f"ept-data/{key}.laz", CACHE / f"{key}.laz")
        return laspy.read(path)

    with ThreadPoolExecutor(max_workers=16) as pool:
        for lidar in pool.map(read, sorted(keys)):
            x, y, z = np.asarray(lidar.x), np.asarray(lidar.y), np.asarray(lidar.z)
            assert lidar.header.scales[2] > 0
            row = np.floor((north-y)/RESOLUTION).astype(int)
            col = np.floor((x-west)/RESOLUTION).astype(int)
            valid = (row >= 0) & (col >= 0) & (row < grid_shape[0]) & (col < grid_shape[1])
            row, col, z = row[valid], col[valid], z[valid]
            cls = np.asarray(lidar.classification)[valid]
            for code, count in zip(*np.unique(cls, return_counts=True)):
                classes[int(code)] = classes.get(int(code), 0) + int(count)
            points += len(z)
            bare = cls == 2
            np.minimum.at(ground, (row[bare], col[bare]), z[bare])
            candidates = np.isin(cls, [1, 3, 4, 5]) & (np.asarray(lidar.return_number)[valid] == 1)
            candidates &= (crown_ids[row, col] > 0) & (buildings[row, col] == 0)
            vegetation.append((row[candidates], col[candidates], z[candidates]))
    assert np.isfinite(ground).any()
    gaps, nearest = distance_transform_edt(~np.isfinite(ground), return_indices=True)
    local_ground = ground[tuple(nearest)]
    values = {}
    for row, col, z in vegetation:
        heights = z - local_ground[row, col]
        valid = (gaps[row, col] * RESOLUTION <= 12) & (heights >= 2) & (heights <= 45)
        for key, height in zip(crown_ids[row[valid], col[valid]], heights[valid]):
            values.setdefault(int(key), []).append(float(height))
    features = []
    for i, (key, polygon) in enumerate(crowns, 1):
        heights = values.get(i, [])
        if len(heights) < 5:
            continue
        geometry = transform(to_meters, polygon).simplify(.65, preserve_topology=True)
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        features.append({"type": "Feature", "geometry": mapping(transform(to_degrees, geometry)),
                         "properties": {"canopy_id": key, "height_m": round(float(np.percentile(heights, 90)), 2),
                                        "returns": len(heights)}})
    assert features
    output = {"type": "FeatureCollection", "features": features}
    target = ROOT / "dist" / "location"
    (target / "lidar-canopy.geojson").write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    summary = {"bounds": AREA, "ept_nodes": sorted(keys), "depth_limit": DEPTH,
               "resolution_m": RESOLUTION, "points_in_grid": points, "class_counts": classes,
               "candidate_crowns": len(crowns), "modeled_crowns": len(features),
               "height_range_m": [min(f["properties"]["height_m"] for f in features),
                                  max(f["properties"]["height_m"] for f in features)],
               "lidar_source": EPT, "canopy_query": query, "crs": crs.to_string()}
    (target / "lidar-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # Hand the crowns to the browser engine (rounded to ~1 cm).
    def rounded(value):
        return [rounded(v) for v in value] if isinstance(value, list) else round(value, 7)
    trees = [{"type": "Feature", "properties": {"h": f["properties"]["height_m"]},
              "geometry": {"type": f["geometry"]["type"], "coordinates": rounded(json.loads(json.dumps(f["geometry"]["coordinates"])))}}
             for f in features]
    engine_path = ROOT / "dist" / "philly-data.js"
    engine = json.loads(engine_path.read_text(encoding="utf-8")[len("window.PHILLY="):].rstrip().rstrip(";"))
    engine["trees"] = {"type": "FeatureCollection", "features": trees}
    engine["meta"]["trees"] = len(trees)
    engine["meta"]["tree_source"] = "NOAA NOS coastal LiDAR (EPT 9848, 2022) heights; PPR 2015 canopy outlines"
    engine_path.write_text("window.PHILLY=" + json.dumps(engine, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"Added {len(trees)} tree crowns to philly-data.js", flush=True)
    print({k: v for k, v in summary.items() if k not in {"ept_nodes", "crs"}}, flush=True)


if __name__ == "__main__":
    main()
