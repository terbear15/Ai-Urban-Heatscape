"""Build translucent bands outside Philadelphia for the satellite map."""
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

DIST = Path(__file__).resolve().parents[1] / "dist"
LOCATION = DIST / "location"
to_meters = Transformer.from_crs(4326, 26918, always_xy=True).transform
to_degrees = Transformer.from_crs(26918, 4326, always_xy=True).transform

boundary = json.loads((LOCATION / "city-boundary.geojson").read_text(encoding="utf-8"))
city = transform(to_meters, shape(boundary["geometry"]))
features = []


def add_band(geometry, opacity):
    if geometry.is_empty:
        return
    features.append({
        "type": "Feature",
        "properties": {"opacity": opacity},
        "geometry": mapping(geometry),
    })


previous = city
for step in range(1, 13):
    expanded = city.buffer(step * 100).simplify(8, preserve_topology=True).union(previous)
    add_band(transform(to_degrees, expanded.difference(previous)), round(.06 + .04 * (step - 1), 2))
    previous = expanded

# Build the broad outer mask in geographic coordinates so its edges stay straight.
region = box(-82, 33, -68, 47)
add_band(region.difference(transform(to_degrees, previous)), .54)
(LOCATION / "city-fade.geojson").write_text(
    json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
    encoding="utf-8",
)
