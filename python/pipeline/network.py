"""Walking network with OSMnx.

The walkable OSM ways downloaded for the area are written to an .osm file and loaded
with ``osmnx.graph_from_xml``. OSMnx builds the graph, keeps the largest connected
component, and gives network statistics (used in the write-up). Each street segment
also gets a sidewalk offset: how far the walking line sits from the street centerline,
so the browser can test shade on each side of the street (F8).
"""
import re

import networkx as nx
import osmnx as ox

from .common import RAW, log
from .osm import write_osm

WALKABLE = {"footway", "pedestrian", "path", "living_street", "residential", "tertiary", "secondary",
            "primary", "unclassified", "service", "steps", "tertiary_link", "secondary_link",
            "primary_link", "corridor", "cycleway", "track", "trunk_link"}
# Footpaths are already where people walk; streets get a sidewalk on each side.
NO_OFFSET = {"footway", "pedestrian", "path", "steps", "corridor", "cycleway", "track"}
# Half the curb-to-curb width plus about 2 m to the middle of the sidewalk, by street type (meters).
DEFAULT_OFFSET = {"primary": 10.0, "primary_link": 7.0, "secondary": 9.0, "secondary_link": 7.0,
                  "tertiary": 8.0, "tertiary_link": 6.5, "trunk_link": 8.0, "unclassified": 7.0,
                  "residential": 6.5, "living_street": 5.0, "service": 4.5}


def walkable(tags):
    highway = tags.get("highway")
    if highway not in WALKABLE or tags.get("area") == "yes":
        return False
    if tags.get("access") in {"no", "private"} or tags.get("foot") in {"no", "private"}:
        return False
    if highway == "service" and tags.get("service") in {"parking_aisle", "drive-through"}:
        return False
    return True


def _number(value):
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0]
    match = re.match(r"\s*([0-9.]+)", str(value))
    return float(match.group(1)) if match else None


def offset(data):
    """Distance in meters from the centerline to the walking line on each side."""
    highway = data.get("highway")
    highway = highway[0] if isinstance(highway, list) else highway
    footway = data.get("footway")
    if highway in NO_OFFSET or footway in {"sidewalk", "crossing"}:
        return 0.0
    width = _number(data.get("width"))
    if width:
        return round(min(20.0, width / 2 + 2), 1)
    lanes = _number(data.get("lanes"))
    if lanes:
        return round(min(20.0, lanes * 3.3 / 2 + 2), 1)
    return DEFAULT_OFFSET.get(highway, 6.0)


def build(slug, nodes, ways, reach_polygon):
    walk_ways = {i: (refs, tags) for i, (refs, tags) in ways.items()
                 if walkable(tags) and all(r in nodes for r in refs) and len(refs) >= 2}
    path = RAW / "osm" / f"{slug}-walk.osm"
    write_osm(path, nodes, walk_ways)
    ox.settings.useful_tags_way = list(set(ox.settings.useful_tags_way) | {"sidewalk", "footway", "width", "lanes", "name", "highway"})
    graph = ox.graph_from_xml(path, simplify=False, retain_all=False)  # largest weakly connected component
    # Unsimplified graphs lack street counts; OSMnx's statistics need them.
    nx.set_node_attributes(graph, ox.stats.count_streets_per_node(graph), "street_count")
    stats = ox.stats.basic_stats(graph)
    graph = ox.convert.to_undirected(graph)
    log(f"  OSMnx walk graph: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
    names, name_index, edges = [], {}, []
    seen = set()
    sidewalk_m = street_m = 0.0
    for u, v, data in graph.edges(data=True):
        key = (min(u, v), max(u, v))
        if key in seen:
            continue
        seen.add(key)
        a, b = graph.nodes[u], graph.nodes[v]
        name = data.get("name")
        if isinstance(name, list):
            name = name[0]
        highway = data.get("highway")
        highway = highway[0] if isinstance(highway, list) else highway
        if not name:
            name = {"footway": "Footpath", "pedestrian": "Pedestrian street", "steps": "Steps",
                    "path": "Path", "service": "Service lane"}.get(highway, (highway or "street").replace("_", " ").capitalize())
        if name not in name_index:
            name_index[name] = len(names)
            names.append(name)
        w = offset(data)
        length = float(data.get("length", 0))
        if w == 0:
            sidewalk_m += length
        else:
            street_m += length
        # [a, b, lon1, lat1, lon2, lat2, sidewalk offset (m), street name index]
        edges.append([str(u), str(v), round(a["x"], 6), round(a["y"], 6), round(b["x"], 6), round(b["y"], 6), w, name_index[name]])
    summary = {
        "nodes": graph.number_of_nodes(), "edges": len(edges),
        "street_length_km": round(stats.get("street_length_total", 0) / 1000, 2),
        "intersections": stats.get("intersection_count"),
        "streets_per_node_avg": round(stats.get("streets_per_node_avg", 0), 2),
        "footpath_share": round(sidewalk_m / max(1.0, sidewalk_m + street_m), 3),
        "built_with": f"OSMnx {ox.__version__} graph_from_xml, largest connected component",
    }
    return edges, names, summary
