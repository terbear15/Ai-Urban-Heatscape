"""LiDAR: bare earth, canopy height model, building heights and tree crowns.

For each part of a city's study area:
  1. find an Entwine (EPT) point cloud that covers it: USGS 3DEP on AWS (newest survey
     first), or a configured source such as NOAA for Philadelphia;
  2. pick the shallowest EPT depth whose points reach about 8 per square meter;
  3. grid points at 2 m: lowest ground return (class 2) and highest non-ground return;
  4. canopy height model (CHM) = highest return minus interpolated ground;
  5. building height = 90th percentile of the CHM inside each footprint (at least 3 cells);
  6. tree crowns = CHM 2.5-45 m outside buildings (vegetation classes when the survey has
     them), split into connected pieces within 30 m tiles, polygonized with rasterio.
"""
import io
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor

import laspy
import numpy as np
import requests
from pyproj import CRS, Transformer
from rasterio.features import rasterize, shapes
from rasterio.transform import from_origin
from scipy import ndimage
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

from .common import RAW, log, parts

RESOLUTION = 2.0
TARGET_DENSITY = 8.0  # points per square meter
USGS_INDEX = [
    "https://raw.githubusercontent.com/hobu/usgs-lidar/master/boundaries/resources.geojson",
    "https://raw.githubusercontent.com/hobu/usgs-lidar/main/boundaries/resources.geojson",
]
USGS_BUCKET = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/"
# Sources chosen by hand where a better survey than 3DEP exists.
OVERRIDES = {
    "philadelphia": ["https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/entwine/geoid18/9848/"],
}
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "HeatScape course project"


def get(url, timeout=60, retries=4):
    for attempt in range(retries):
        try:
            response = SESSION.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            if attempt == retries - 1:
                raise
            log("  retry", url, error)


def usgs_resources():
    """[(ept url, name, count, lon/lat footprint)] for USGS 3DEP point clouds."""
    cache = RAW / "lidar" / "usgs-resources.geojson"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        for url in USGS_INDEX:
            try:
                cache.write_bytes(get(url, timeout=120).content)
                break
            except requests.RequestException:
                continue
    out = []
    if cache.exists():
        for f in json.loads(cache.read_text())["features"]:
            p = f["properties"]
            url = p.get("url") or (USGS_BUCKET + p["name"] + "/ept.json")
            out.append((url.rsplit("ept.json", 1)[0], p["name"], p.get("count", 0), shape(f["geometry"])))
    return out


def survey_year(name):
    years = [int(y) for y in re.findall(r"(?:19|20)\d\d", name)]
    return max(years) if years else 0


def choose_source(slug, part):
    """The EPT base URL that best covers this part (lon/lat polygon)."""
    if slug in OVERRIDES:
        return OVERRIDES[slug][0]
    covering = [(survey_year(name), count, url, name) for url, name, count, footprint in usgs_resources()
                if footprint.buffer(0).contains(part.buffer(0).envelope)]
    if not covering:
        covering = [(survey_year(name), count, url, name) for url, name, count, footprint in usgs_resources()
                    if footprint.buffer(0).intersects(part)]
    if not covering:
        return None
    covering.sort(reverse=True)
    log(f"  LiDAR source: {covering[0][3]} ({covering[0][0] or 'year unknown'})")
    return covering[0][2]


def nodes_for(base, metadata, bounds_native):
    """EPT node keys intersecting the bounds, up to the depth that reaches TARGET_DENSITY."""
    xmin, ymin, _, xmax, _, _ = metadata["bounds"]
    edge = xmax - xmin
    west, south, east, north = bounds_native
    area = max(1.0, (east - west) * (north - south))
    by_depth = {}

    def walk(page):
        hierarchy = get(base + f"ept-hierarchy/{page}.json").json()
        for key, count in hierarchy.items():
            depth, ix, iy, _ = map(int, key.split("-"))
            size = edge / 2 ** depth
            x, y = xmin + ix * size, ymin + iy * size
            if x > east or y > north or x + size < west or y + size < south or depth > 14:
                continue
            if count == -1 and key != page:
                walk(key)
            elif count > 0:
                by_depth.setdefault(depth, []).append((key, count))

    walk("0-0-0-0")
    chosen, total = [], 0
    for depth in sorted(by_depth):
        for key, count in by_depth[depth]:
            # Count only the share of each node that overlaps the area.
            d, ix, iy, _ = map(int, key.split("-"))
            size = edge / 2 ** d
            x, y = xmin + ix * size, ymin + iy * size
            overlap = max(0, min(x + size, east) - max(x, west)) * max(0, min(y + size, north) - max(y, south))
            total += count * overlap / (size * size)
            chosen.append(key)
        if total / area >= TARGET_DENSITY:
            break
    return chosen, total / area


def survey(slug, area_ll, buildings):
    """Run the LiDAR steps. Returns (building heights by id, tree crowns, summary)."""
    heights, trees, summaries = {}, [], []
    for index, part in enumerate(parts(area_ll)):
        base = choose_source(slug, part)
        if not base:
            log(f"  part {index}: no LiDAR coverage found")
            summaries.append({"part": index, "source": None})
            continue
        metadata = get(base + "ept.json").json()
        crs = CRS.from_user_input(metadata["srs"].get("wkt") or f"EPSG:{metadata['srs']['horizontal']}")
        to_native = Transformer.from_crs(4326, crs, always_xy=True).transform
        to_ll = Transformer.from_crs(crs, 4326, always_xy=True).transform
        native_part = transform(to_native, part)
        unit = crs.axis_info[0].unit_conversion_factor or 1.0  # survey feet -> meters where needed
        cell = RESOLUTION / unit
        west, south, east, north = native_part.bounds
        west, south, east, north = math.floor(west), math.floor(south), math.ceil(east), math.ceil(north)
        keys, density = nodes_for(base, metadata, (west, south, east, north))
        grid = (math.ceil((north - south) / cell), math.ceil((east - west) / cell))
        affine = from_origin(west, north, cell, cell)
        log(f"  part {index}: {len(keys)} EPT nodes, ~{density * unit * unit:.1f} pts/m², grid {grid}")
        ground = np.full(grid, np.inf, dtype="float32")
        top = np.full(grid, -np.inf, dtype="float32")
        veg = np.zeros(grid, dtype="uint16")
        bld = np.zeros(grid, dtype="uint16")
        points = 0
        classes = {}

        def read(key):
            return laspy.read(io.BytesIO(get(base + f"ept-data/{key}.laz", timeout=120).content))

        with ThreadPoolExecutor(max_workers=16) as pool:
            for cloud in pool.map(read, keys):
                x, y, z = np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z)
                row = np.floor((north - y) / cell).astype(np.int64)
                col = np.floor((x - west) / cell).astype(np.int64)
                ok = (row >= 0) & (col >= 0) & (row < grid[0]) & (col < grid[1])
                row, col, z = row[ok], col[ok], (z[ok] * unit).astype("float32")
                cls = np.asarray(cloud.classification)[ok]
                for code, count in zip(*np.unique(cls, return_counts=True)):
                    classes[int(code)] = classes.get(int(code), 0) + int(count)
                points += len(z)
                g = cls == 2
                np.minimum.at(ground, (row[g], col[g]), z[g])
                above = ~np.isin(cls, [2, 7, 9, 17, 18])
                np.maximum.at(top, (row[above], col[above]), z[above])
                v = np.isin(cls, [3, 4, 5])
                np.add.at(veg, (row[v], col[v]), 1)
                b = cls == 6
                np.add.at(bld, (row[b], col[b]), 1)
        if not np.isfinite(ground).any():
            log(f"  part {index}: no ground returns")
            continue
        gaps, nearest = ndimage.distance_transform_edt(~np.isfinite(ground), return_indices=True)
        ground_filled = ground[tuple(nearest)]
        chm = np.where(np.isfinite(top) & (gaps * RESOLUTION <= 30), top - ground_filled, np.nan).astype("float32")

        # Building heights from the CHM inside each footprint.
        native = [(i, transform(to_native, b["polygon"])) for i, b in enumerate(buildings)]
        native = [(i, g) for i, g in native if g.intersects(native_part.buffer(200 / unit))]
        footprint = rasterize([(g, i + 1) for i, g in native], out_shape=grid, transform=affine, dtype="int32") if native else np.zeros(grid, "int32")
        ids = footprint.ravel()
        values = chm.ravel()
        good = (ids > 0) & np.isfinite(values) & (values > 1.5)
        order = np.argsort(ids[good], kind="stable")
        sorted_ids, sorted_vals = ids[good][order], values[good][order]
        starts = np.flatnonzero(np.r_[True, sorted_ids[1:] != sorted_ids[:-1]])
        ends = np.r_[starts[1:], len(sorted_ids)]
        for s, e in zip(starts, ends):
            if e - s >= 3:
                heights[buildings[sorted_ids[s] - 1]["id"]] = float(np.percentile(sorted_vals[s:e], 90))

        # Tree crowns.
        has_veg = classes and sum(classes.get(c, 0) for c in (3, 4, 5)) > .01 * max(1, points)
        near_building = ndimage.binary_dilation(footprint > 0, iterations=1)
        mask = np.isfinite(chm) & (chm >= 2.5) & (chm <= 45) & ~near_building
        mask &= (veg > 0) if has_veg else (bld == 0)
        mask = ndimage.binary_opening(mask, iterations=1)
        labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
        if count:
            tile = 15  # 15 cells x 2 m = 30 m: long canopies become several crowns
            rows, cols = np.indices(grid)
            tile_id = (rows // tile) * (grid[1] // tile + 1) + cols // tile
            combined = np.where(labels > 0, labels.astype(np.int64) * 100000 + tile_id, 0)
            uniq, inverse = np.unique(combined, return_inverse=True)
            crowns = inverse.reshape(grid).astype("int32")  # 0 stays 0 (smallest value)
            sizes = np.bincount(crowns.ravel())
            crown_h = ndimage.labeled_comprehension(chm, crowns, np.arange(1, len(uniq)), lambda a: np.nanpercentile(a, 90), float, np.nan)
            polygons = {}
            for geom, value in shapes(crowns, mask=crowns > 0, transform=affine):
                polygons.setdefault(int(value), []).append(shape(geom))
            for value, pieces in polygons.items():
                if sizes[value] < 3 or not np.isfinite(crown_h[value - 1]):
                    continue
                geom = unary_union(pieces).simplify(1.0 / unit, preserve_topology=True)
                geom_ll = transform(to_ll, geom)
                if geom_ll.intersects(part.buffer(.002)):
                    trees.append({"h": round(float(crown_h[value - 1]), 1), "geometry": geom_ll})
        summaries.append({"part": index, "source": base, "survey_year": survey_year(base), "points": points,
                          "density_pts_m2": round(density * unit * unit, 1), "classes": classes,
                          "vegetation_classes": bool(has_veg)})
        log(f"  part {index}: {points:,} points, {len(heights):,} building heights, {len(trees):,} crowns so far")
    return heights, trees, summaries
