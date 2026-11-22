"""OpenStreetMap download for a study area (official OSM API, tiled) and an .osm writer for OSMnx."""
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

import requests

from .common import RAW, log, parts

API = "https://api.openstreetmap.org/api/0.6/map"
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}


def _get(bbox):
    for attempt in range(6):
        try:
            response = requests.get(API, params={"bbox": ",".join(f"{v:.6f}" for v in bbox)}, headers=HEADERS, timeout=180)
            if response.status_code == 400 and "exceed" in response.text.lower():
                return None  # more than 50,000 nodes: split the tile
            if response.status_code in (429, 509):
                time.sleep(30 * (attempt + 1))
                continue
            response.raise_for_status()
            return ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as error:
            log("OSM API retry", attempt + 1, bbox, error)
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"OSM API failed for {bbox}")


def fetch(geometry, tile=0.006):
    """Nodes, ways and relations touching each part of the geometry.

    nodes[id] = (lon, lat, tags); ways[id] = (node_ids, tags); relations[id] = (members, tags)
    with members = [(type, ref, role)].
    """
    nodes, ways, relations = {}, {}, {}
    queue = []
    for part in parts(geometry):
        west, south, east, north = part.bounds
        x = west
        while x < east:
            y = south
            while y < north:
                queue.append((x, y, min(x + tile, east), min(y + tile, north)))
                y += tile
            x += tile
    done = 0
    while queue:
        box = queue.pop()
        root = _get(box)
        if root is None:
            w, s, e, n = box
            mx, my = (w + e) / 2, (s + n) / 2
            queue += [(w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)]
            continue
        for node in root.iter("node"):
            tags = {t.get("k"): t.get("v") for t in node.iter("tag")}
            nodes[int(node.get("id"))] = (float(node.get("lon")), float(node.get("lat")), tags)
        for way in root.iter("way"):
            ways[int(way.get("id"))] = ([int(nd.get("ref")) for nd in way.iter("nd")],
                                        {t.get("k"): t.get("v") for t in way.iter("tag")})
        for relation in root.iter("relation"):
            relations[int(relation.get("id"))] = (
                [(m.get("type"), int(m.get("ref")), m.get("role")) for m in relation.iter("member")],
                {t.get("k"): t.get("v") for t in relation.iter("tag")})
        done += 1
        if done % 10 == 0 or not queue:
            log(f"  OSM tile {done}: {len(nodes):,} nodes, {len(ways):,} ways, {len(relations):,} relations")
        time.sleep(1)  # be gentle with the public API
    return nodes, ways, relations


def write_osm(path, nodes, ways):
    """Write the given ways (and only the nodes they use) as an .osm XML file for OSMnx."""
    path.parent.mkdir(parents=True, exist_ok=True)
    used = {ref for refs, _ in ways.values() for ref in refs}
    with open(path, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="HeatScape">\n')
        for ref in used:
            lon, lat, _ = nodes[ref]
            out.write(f'<node id="{ref}" lat="{lat:.7f}" lon="{lon:.7f}"/>\n')
        for way_id, (refs, tags) in ways.items():
            out.write(f'<way id="{way_id}">')
            out.write("".join(f'<nd ref="{r}"/>' for r in refs))
            out.write("".join(f"<tag k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in tags.items()))
            out.write("</way>\n")
        out.write("</osm>\n")


def cache_path(slug):
    return RAW / "osm" / f"{slug}.osm"
