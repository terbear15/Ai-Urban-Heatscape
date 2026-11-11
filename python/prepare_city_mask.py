"""Build the white satellite mask outside Philadelphia's municipal boundary."""
import json
from pathlib import Path

from shapely.geometry import box, mapping, shape

LOCATION = Path(__file__).resolve().parents[1] / "dist" / "location"
boundary = json.loads((LOCATION / "city-boundary.geojson").read_text(encoding="utf-8"))
city = shape(boundary["geometry"])
region = box(-82, 33, -68, 47)
mask = region.difference(city)
(LOCATION / "city-mask.geojson").write_text(
    json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(mask)},
               separators=(",", ":")),
    encoding="utf-8",
)
