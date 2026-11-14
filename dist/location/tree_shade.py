"""Project LiDAR-derived crown outlines onto flat ground."""
import json
import math
from pathlib import Path

DATA = json.loads(Path(__file__).with_name("lidar-canopy.geojson").read_text(encoding="utf-8"))


def tree_shadows(azimuth, altitude):
    if altitude <= 0:
        return []
    result = []
    for feature in DATA["features"]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        latitude = polygons[0][0][0][1]
        distance = min(350, feature["properties"]["height_m"] / math.tan(altitude))
        dx = distance * math.sin(azimuth) / (111320 * math.cos(math.radians(latitude)))
        dy = distance * math.cos(azimuth) / 111320
        shifted = [[[[round(x+dx, 7), round(y+dy, 7)] for x, y in ring]
                    for ring in polygon] for polygon in polygons]
        result.append({"type": "Feature", "properties": feature["properties"],
                       "geometry": {"type": geometry["type"],
                                    "coordinates": shifted[0] if geometry["type"] == "Polygon" else shifted}})
    return result


def tree_layer(sun):
    return json.dumps({"type": "FeatureCollection", "features": tree_shadows(*json.loads(sun))})
