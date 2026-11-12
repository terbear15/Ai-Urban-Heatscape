"""Walking alternatives scored against the same building shadows as the map."""
import asyncio
import gzip
import heapq
import json
import math
from functools import lru_cache

from city_buildings import fetch_buildings, shadows
from routing import METERS_PER_MINUTE, RoutingEngine, in_ring, projected

with gzip.open("data/philadelphia.json.gz", "rt", encoding="utf-8") as source:
    network = RoutingEngine(json.load(source))

CELL = 50
WINDOW = .012
building_tasks = {}


def cell(point):
    x, y = projected(point)
    return math.floor(x / CELL), math.floor(y / CELL)


def samples(path, spacing):
    for a, b in zip(path, path[1:]):
        distance = math.hypot((b[0]-a[0])*85300, (b[1]-a[1])*111320)
        if not distance:
            continue
        count = math.ceil(distance / spacing)
        for i in range(count):
            t = (i + .5) / count
            yield (a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])), distance/count


async def corridor_buildings(points):
    tiles = {(math.floor(x/WINDOW), math.floor(y/WINDOW)) for x, y in points}
    features = {}
    for offset in range(0, len(tiles), 3):
        tasks = []
        for ix, iy in sorted(tiles)[offset:offset+3]:
            key = ix, iy
            if key not in building_tasks:
                window = (ix*WINDOW-.007, iy*WINDOW-.006,
                          (ix+1)*WINDOW+.007, (iy+1)*WINDOW+.006)
                building_tasks[key] = asyncio.create_task(fetch_buildings(window, include_center=True))
            tasks.append((key, building_tasks[key]))
        for key, task in tasks:
            try:
                for feature in await task:
                    features[feature["id"]] = feature
            except Exception:
                building_tasks.pop(key, None)
                raise
    while len(building_tasks) > 16:
        building_tasks.pop(next(iter(building_tasks)))
    return list(features.values())


def shadow_index(features, azimuth, altitude):
    bins = {}
    for feature in shadows(features, azimuth, altitude)["features"]:
        ring = feature["geometry"]["coordinates"][0]
        keys = [cell(point) for point in ring]
        for x in range(min(k[0] for k in keys), max(k[0] for k in keys)+1):
            for y in range(min(k[1] for k in keys), max(k[1] for k in keys)+1):
                bins.setdefault((x, y), []).append(ring)
    return bins


def weighted_path(start, end, permitted, exposure, penalty):
    costs = {start: 0}
    previous = {}
    queue = [(0, 0, start)]
    target = projected(network.nodes[end])
    while queue:
        _, cost, node = heapq.heappop(queue)
        if cost != costs[node]:
            continue
        if node == end:
            path = []
            while node != start:
                index = previous[node]
                path.append(index)
                node = network.edges[index]["u"]
            return path[::-1]
        for index in network.links[node]:
            edge = network.edges[index]
            neighbor = edge["v"]
            if not permitted(neighbor):
                continue
            total = cost + edge["length"] + penalty * exposure(index)
            if total < costs.get(neighbor, math.inf):
                costs[neighbor] = total
                previous[neighbor] = index
                x, y = projected(network.nodes[neighbor])
                heapq.heappush(queue, (total + .98*math.hypot(x-target[0], y-target[1]), total, neighbor))
    return []


def winter_budget(minutes):
    """Extra minutes for the whole walk, interpolated between the time targets."""
    if minutes <= 10:
        return minutes / 10
    return min(3, 1 + (minutes - 10) / 5)


def combine_sunny_sections(sections, budget, distance, exposure):
    """Choose compatible sunny detours under a conservative whole-second budget."""
    seconds = math.floor(budget * 60 + 1e-8)
    states = {0: (0, ())}
    for index, (base, detour) in enumerate(sections):
        gain = sum(map(exposure, detour)) - sum(map(exposure, base))
        if gain <= 1e-6:
            continue
        extra = max(0, distance(detour) - distance(base))
        cost = math.ceil(extra / METERS_PER_MINUTE * 60 - 1e-8)
        for spent, (sun, chosen) in list(states.items()):
            total = spent + cost
            if total <= seconds and sun + gain > states.get(total, (0, ()))[0]:
                states[total] = sun + gain, (*chosen, index)
    _, (_, chosen) = max(states.items(), key=lambda item: (item[1][0], -item[0]))
    return [edge for index, (base, detour) in enumerate(sections)
            for edge in (detour if index in chosen else base)]


async def city_route(trip_json):
    origin, destination, azimuth, altitude, extra, *mode = json.loads(trip_json)
    winter = bool(mode and mode[0] == "winter")
    start, start_gap = network.snap(origin)
    end, end_gap = network.snap(destination)
    if start == end:
        raise ValueError("Choose two places farther apart.")
    direct = network.path(start, end, 15, 0)
    if not direct:
        raise ValueError("No connected walking route found. Try a nearby public entrance.")
    baseline = network.summarize(direct, 15)
    fast = {"coords": baseline["path"], "length": baseline["distance"]}
    result = {
        "fast": fast,
        "start": {"coord": network.nodes[start], "meters": start_gap},
        "end": {"coord": network.nodes[end], "meters": end_gap},
    }
    if winter:
        result["winterBudget"] = winter_budget(fast["length"] / METERS_PER_MINUTE)
    if altitude <= 0:
        result["afterSunset"] = True
        fast["exposure"] = 0
        return json.dumps(result)
    points = [point for point, _ in samples(fast["coords"], 25)]
    corridor = {(x+dx, y+dy) for x, y in map(cell, points)
                for dx in range(-4, 5) for dy in range(-4, 5)}
    try:
        features = await corridor_buildings(points)
    except Exception:
        result["shadeUnavailable"] = True
        return json.dumps(result)
    if not features:
        result["shadeUnavailable"] = True
        return json.dumps(result)
    bins = shadow_index(features, azimuth, altitude)

    @lru_cache(maxsize=None)
    def permitted(node):
        return cell(network.nodes[node]) in corridor

    @lru_cache(maxsize=None)
    def exposure(index):
        edge = network.edges[index]
        sun = total = 0
        for point, weight in samples(edge["path"], 10):
            total += weight
            if not any(in_ring(point, ring) for ring in bins.get(cell(point), ())):
                sun += weight
        return edge["length"] * sun / total if total else edge["length"]

    def distance(indices):
        return sum(network.edges[i]["length"] for i in indices)

    positions = {start: 0}
    positions.update({network.edges[i]["v"]: j for j, i in enumerate(direct, 1)})
    fast["exposure"] = sum(map(exposure, direct))
    def shade_cost(index):
        return max(0, network.edges[index]["length"] - exposure(index))

    best = fast["exposure"]
    for penalty in (.5, 1, 2, 4, 8, 16):
        candidate = weighted_path(start, end, permitted, shade_cost if winter else exposure, penalty)
        joins = [(0, 0)] + [(positions[network.edges[i]["v"]], j)
                            for j, i in enumerate(candidate, 1) if network.edges[i]["v"] in positions]
        if not candidate or any(b[0] <= a[0] for a, b in zip(joins, joins[1:])):
            continue
        sections = [(direct[left:right], candidate[a:b])
                    for (left, a), (right, b) in zip(joins, joins[1:])]
        if winter:
            mixed = combine_sunny_sections(sections, result["winterBudget"], distance, exposure)
        else:
            mixed = []
            for base, detour in sections:
                qualifies = (distance(detour) <= distance(base) + extra*METERS_PER_MINUTE + 1e-6
                             and sum(map(exposure, detour)) < sum(map(exposure, base)) - 1e-6)
                mixed.extend(detour if qualifies else base)
        score = sum(map(exposure, mixed))
        improves = score > best + 1e-6 if winter else score < best - 1e-6
        if improves:
            best = score
            route = network.summarize(mixed, 15)
            result["shade"] = {"coords": route["path"], "length": route["distance"], "exposure": score}
    return json.dumps(result)
