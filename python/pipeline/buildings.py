"""Building footprints from OSM (closed ways and multipolygon relations), with any OSM height."""
import math

from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

METERS_PER_LEVEL = 3.3


def parse_height(tags):
    """(meters, source) from OSM tags, or (None, None)."""
    for key in ("height", "building:height"):
        value = tags.get(key)
        if value:
            text = value.lower().replace(" ", "")
            try:
                if text.endswith("ft") or text.endswith("'"):
                    return float(text.rstrip("ft'")) * .3048, "osm"
                return float(text.rstrip("m")), "osm"
            except ValueError:
                pass
    levels = tags.get("building:levels")
    if levels:
        try:
            return float(levels) * METERS_PER_LEVEL, "osm-levels"
        except ValueError:
            pass
    return None, None


def is_building(tags):
    return (tags.get("building", "no") != "no" or "building:part" in tags) and tags.get("building") != "roof"


def extract(nodes, ways, relations, reach_polygon):
    """List of dicts: polygon (lon/lat), height (m or None), source, kind."""
    out = []
    for way_id, (refs, tags) in ways.items():
        if not is_building(tags) or len(refs) < 4 or refs[0] != refs[-1] or any(r not in nodes for r in refs):
            continue
        polygon = Polygon([nodes[r][:2] for r in refs])
        if polygon.is_valid and polygon.area > 0 and polygon.intersects(reach_polygon):
            height, source = parse_height(tags)
            out.append({"id": f"w{way_id}", "polygon": polygon, "height": height, "source": source,
                        "kind": tags.get("building", "part")})
    for rel_id, (members, tags) in relations.items():
        if tags.get("type") != "multipolygon" or not is_building(tags):
            continue
        lines = []
        for kind, ref, role in members:
            if kind == "way" and role in ("outer", "") and ref in ways:
                refs = ways[ref][0]
                if all(r in nodes for r in refs) and len(refs) >= 2:
                    lines.append(LineString([nodes[r][:2] for r in refs]))
        if not lines:
            continue
        shape = unary_union(list(polygonize(unary_union(lines))))
        for polygon in getattr(shape, "geoms", [shape]):
            if polygon.geom_type == "Polygon" and polygon.is_valid and polygon.area > 0 and polygon.intersects(reach_polygon):
                height, source = parse_height(tags)
                out.append({"id": f"r{rel_id}", "polygon": Polygon(polygon.exterior.coords), "height": height,
                            "source": source, "kind": tags.get("building", "yes")})
    return out


def features(building, local):
    """Shape features in meters for the height model."""
    poly = local.to_m(building["polygon"])
    area = poly.area
    perimeter = poly.length
    return {
        "area": area,
        "perimeter": perimeter,
        "compactness": 4 * math.pi * area / perimeter ** 2 if perimeter else 0,
        "vertices": len(poly.exterior.coords),
        "x": poly.centroid.x,
        "y": poly.centroid.y,
    }
