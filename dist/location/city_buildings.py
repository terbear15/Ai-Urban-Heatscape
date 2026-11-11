"""Fetch Philadelphia building footprints for a map window and project their shadows."""
import math
from urllib.parse import urlencode

from search import read_json

SOURCE = "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/LI_BUILDING_FOOTPRINTS/FeatureServer/0/query"
CENTER = (-75.176, 39.946, -75.158, 39.957)
MAX_SHADOW = 350
PAGE_SIZE = 2000


def collection(features):
    return {"type": "FeatureCollection", "features": features}


def in_center(x, y):
    west, south, east, north = CENTER
    return west <= x <= east and south <= y <= north


async def fetch_buildings(window, minimum_area=0, include_center=False):
    features = []
    offset = 0
    while True:
        params = {
            "where": f"square_ft >= {int(minimum_area)}" if minimum_area else "1=1", "geometry": ",".join(map(str, window)),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "f": "geojson",
            "outFields": "objectid,address,building_name,approx_hgt,max_hgt",
            "orderByFields": "objectid", "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE, "geometryPrecision": 6,
        }
        response = await read_json(SOURCE + "?" + urlencode(params))
        if "features" not in response:
            raise ValueError("Philadelphia building data could not be loaded.")
        page = response["features"]
        for feature in page:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                continue
            rings = geometry["coordinates"]
            outer = rings[0] if geometry["type"] == "Polygon" else rings[0][0]
            if not outer or (not include_center and all(in_center(*point[:2]) for point in outer)):
                continue
            attrs = feature["properties"]
            feet = attrs.get("approx_hgt")
            basis = "City footprint · approximate height"
            if not feet or feet <= 0:
                feet = attrs.get("max_hgt")
                basis = "City footprint · maximum height"
            if not feet or feet <= 0:
                feet, basis = 39, "assumed 39 ft"
            feature["properties"] = {
                "height": feet * 0.3048,
                "basis": basis,
                "name": (attrs.get("building_name") or "").strip() or attrs.get("address") or "Building",
            }
            features.append(feature)
        offset += len(page)
        if not page or (len(page) < PAGE_SIZE and not response.get("properties", {}).get("exceededTransferLimit")):
            return features


def shadows(features, azimuth, altitude):
    if altitude <= 0:
        return collection([])
    shapes = []
    for feature in features:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        length = min(MAX_SHADOW, feature["properties"]["height"] / math.tan(altitude))
        latitude = polygons[0][0][0][1]
        dx = length * math.sin(azimuth) / (111320 * math.cos(math.radians(latitude)))
        dy = length * math.cos(azimuth) / 111320
        for polygon in polygons:
            for index, ring in enumerate(polygon):
                if len(ring) < 4:
                    continue
                x0, y0 = ring[0][:2]
                area = sum((a[0]-x0)*(b[1]-y0) - (b[0]-x0)*(a[1]-y0)
                           for a, b in zip(ring, ring[1:]))
                # Only walls facing the shadow direction contribute outside the footprint.
                outward = math.copysign(1, area) * (-1 if index else 1)
                for a, b in zip(ring, ring[1:]):
                    if outward * ((b[0]-a[0])*dy - (b[1]-a[1])*dx) >= -1e-14:
                        continue
                    quad = [a, b, [round(b[0]+dx, 7), round(b[1]+dy, 7)],
                            [round(a[0]+dx, 7), round(a[1]+dy, 7)], a]
                    shapes.append({"type": "Feature", "properties": {},
                                   "geometry": {"type": "Polygon", "coordinates": [quad]}})
    return collection(shapes)
