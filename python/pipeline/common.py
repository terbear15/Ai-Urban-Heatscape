"""Shared paths and geometry helpers for the city pipeline."""
import json
import math
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
DATA = DIST / "data"
RAW = ROOT / "raw"
MARGIN_M = 150  # streets and buildings are kept this far beyond the dashed boundary


def log(*args):
    print(*args, flush=True)


def city_area(slug):
    """The study area (union of downtown and visitor zones) as a shapely geometry in lon/lat."""
    collection = json.loads((DIST / "cities" / f"{slug}.geojson").read_text(encoding="utf-8"))
    land = next(f for f in collection["features"] if f["properties"]["layer"] == "land")
    return shape(land["geometry"])


def views():
    return json.loads((DIST / "cities" / "views.json").read_text(encoding="utf-8"))


class Local:
    """Azimuthal equidistant projection centered on the area, in meters."""

    def __init__(self, geometry):
        c = geometry.centroid
        self.crs = CRS.from_proj4(f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m")
        self.forward = Transformer.from_crs(4326, self.crs, always_xy=True).transform
        self.reverse = Transformer.from_crs(self.crs, 4326, always_xy=True).transform

    def to_m(self, geometry):
        return transform(self.forward, geometry)

    def to_ll(self, geometry):
        return transform(self.reverse, geometry)


def reach(slug):
    """Area plus the margin, in lon/lat, and the projection used to build it."""
    area = city_area(slug)
    local = Local(area)
    return area, local.to_ll(local.to_m(area).buffer(MARGIN_M)), local


def parts(geometry):
    return list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]


def rounded(value, digits=6):
    return [rounded(v, digits) for v in value] if isinstance(value, (list, tuple)) else round(value, digits)


def write_js(path, variable, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.{variable}=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")


def meters_per_degree(lat):
    return 111320 * math.cos(math.radians(lat)), 110540
