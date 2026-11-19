"""Download OpenStreetMap data for a bounding box from the official OSM API.

The /api/0.6/map call is limited to 50,000 nodes per request, so the box is split
into tiles; nodes and ways are merged by id. Ways that cross a tile edge come back
complete (the API returns every node of every way touching the tile).
"""
import time
import xml.etree.ElementTree as ET

import requests

API = "https://api.openstreetmap.org/api/0.6/map"
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}


def _get(bbox):
    for attempt in range(5):
        try:
            response = requests.get(API, params={"bbox": ",".join(f"{v:.6f}" for v in bbox)}, headers=HEADERS, timeout=180)
            if response.status_code == 400 and "exceed" in response.text.lower():
                return None  # too many nodes: caller splits the tile
            response.raise_for_status()
            return ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as error:
            print("OSM API retry", attempt + 1, bbox, error, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"OSM API failed for {bbox}")


def fetch(west, south, east, north, tile=0.006):
    """Return (nodes, ways): nodes[id] = (lon, lat, tags); ways[id] = (node_ids, tags)."""
    nodes, ways = {}, {}
    queue = []
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
            refs = [int(nd.get("ref")) for nd in way.iter("nd")]
            tags = {t.get("k"): t.get("v") for t in way.iter("tag")}
            ways[int(way.get("id"))] = (refs, tags)
        done += 1
        print(f"tile {done}: {len(nodes):,} nodes, {len(ways):,} ways so far", flush=True)
        time.sleep(1)  # be gentle with the public API
    return nodes, ways
