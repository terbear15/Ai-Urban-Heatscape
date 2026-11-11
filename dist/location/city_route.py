"""Adapt the Python walking network to the original HeatScape map."""
import gzip
import json
from routing import RoutingEngine

with gzip.open("data/philadelphia.json.gz", "rt", encoding="utf-8") as source:
    network = RoutingEngine(json.load(source))


def city_route(trip_json):
    origin, destination = json.loads(trip_json)
    start, start_gap = network.snap(origin)
    end, end_gap = network.snap(destination)
    if start == end:
        raise ValueError("Choose two places farther apart.")
    edges = network.path(start, end, 15, 0)
    if edges is None:
        raise ValueError("No connected walking route found. Try a nearby public entrance.")
    route = network.summarize(edges, 15)
    return json.dumps({
        "fast": {"coords": route["path"], "length": route["distance"]},
        "start": {"coord": network.nodes[start], "meters": start_gap},
        "end": {"coord": network.nodes[end], "meters": end_gap},
    })
