"""Walking-route calculation shared by the Panel app and research notebooks."""
from functools import lru_cache
import heapq
import math

import numpy as np

METERS_PER_MILE = 1609.344
METERS_PER_MINUTE = METERS_PER_MILE * 3 / 60


def projected(point):
    """Local distance approximation used only by A* and endpoint matching."""
    return ((point[0] + 75.167) * 85300, (point[1] - 39.9515) * 111320)


def in_ring(point, ring):
    inside = False
    previous = ring[-1]
    for current in ring:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing = (previous[0] - current[0]) * (point[1] - current[1]) / (previous[1] - current[1]) + current[0]
            if point[0] < crossing:
                inside = not inside
        previous = current
    return inside


class RoutingEngine:
    def __init__(self, data):
        self.data = data
        self.nodes = data['nodes']
        self.coordinates = np.array([projected(point) for point in self.nodes])
        self.edges = data['edges']
        self.links = [[] for _ in self.nodes]
        for index, edge in enumerate(self.edges):
            self.links[edge['u']].append(index)

    def inside_city(self, point):
        geometry = self.data['boundary']
        polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
        return any(in_ring(point, polygon[0]) and not any(in_ring(point, hole) for hole in polygon[1:])
                   for polygon in polygons)

    def snap(self, point):
        if not self.inside_city(point):
            raise ValueError('This location is outside Philadelphia. Choose an address inside the city.')
        differences = self.coordinates - np.array(projected(point))
        squared = np.sum(differences * differences, axis=1)
        node = int(np.argmin(squared))
        meters = float(math.sqrt(squared[node]))
        if meters > 150:
            raise ValueError('This point is more than 490 ft from the mapped walking network. Choose a nearby entrance or street.')
        return node, meters

    @lru_cache(maxsize=128)
    def path(self, start, end, hour, penalty):
        """A* on the directed OSMnx graph, preserving parallel edge choices.

        The conservative 0.98 straight-line heuristic is below local network
        distance in the Philadelphia extent. Unknown-shade edges are excluded
        from shade-optimized searches instead of being assigned an invented cost.
        """
        shade = self.data['frames'][str(hour)]['shade']
        destination = self.coordinates[end]
        costs = {start: 0.0}
        previous = {}
        queue = [(0.0, 0.0, start)]
        while queue:
            _, cost, current = heapq.heappop(queue)
            if cost != costs.get(current):
                continue
            if current == end:
                indices = []
                while current != start:
                    index = previous[current]
                    indices.append(index)
                    current = self.edges[index]['u']
                return tuple(reversed(indices))
            for index in self.links[current]:
                edge = self.edges[index]
                if penalty and edge['covered'] < .999:
                    continue
                exposure_fraction = max(0, edge['covered'] - shade.get(str(index), 0))
                value = cost + edge['length'] * (1 + penalty * exposure_fraction)
                neighbor = edge['v']
                if value < costs.get(neighbor, math.inf):
                    costs[neighbor] = value
                    previous[neighbor] = index
                    delta = self.coordinates[neighbor] - destination
                    heuristic = .98 * math.hypot(delta[0], delta[1])
                    heapq.heappush(queue, (value + heuristic, value, neighbor))
        return None

    def summarize(self, indices, hour):
        shade = self.data['frames'][str(hour)]['shade']
        distance = covered = shaded = 0.0
        coordinates = []
        steps = []
        for index in indices:
            edge = self.edges[index]
            distance += edge['length']
            covered += edge['length'] * edge['covered']
            shaded += edge['length'] * min(edge['covered'], shade.get(str(index), 0))
            coordinates.extend(edge['path'] if not coordinates else edge['path'][1:])
            if steps and steps[-1]['street'] == edge['name']:
                steps[-1]['feet'] += edge['length'] * 3.28084
            else:
                steps.append({'street': edge['name'], 'feet': edge['length'] * 3.28084})
        complete = covered >= distance * .999
        return {'edges': indices, 'path': coordinates, 'distance': distance,
                'miles': distance / METERS_PER_MILE, 'minutes': distance / METERS_PER_MINUTE,
                'covered': covered / distance if distance else 0,
                'sun_minutes': max(0, covered - shaded) / METERS_PER_MINUTE,
                'shade_minutes': shaded / METERS_PER_MINUTE, 'complete': complete, 'steps': steps}

    def compare(self, origin, destination, hour=15, allowance=5):
        start, origin_gap = self.snap(origin)
        end, destination_gap = self.snap(destination)
        if start == end:
            raise ValueError('These locations meet the same network point. Choose a farther destination.')
        indices = self.path(start, end, hour, 0)
        if indices is None:
            raise ValueError('No connected walking route was found. Try a nearby public entrance.')
        fastest = self.summarize(indices, hour)
        alternative = None
        if fastest['complete']:
            alternative = fastest
            for penalty in (.5, 1, 2, 4, 8, 16, 40):
                candidate_indices = self.path(start, end, hour, penalty)
                if candidate_indices is None:
                    continue
                candidate = self.summarize(candidate_indices, hour)
                if (candidate['minutes'] <= fastest['minutes'] + allowance + 1e-7
                        and candidate['sun_minutes'] < alternative['sun_minutes']):
                    alternative = candidate
        return {'fastest': fastest, 'alternative': alternative,
                'start': self.nodes[start], 'end': self.nodes[end],
                'origin_gap_ft': origin_gap * 3.28084, 'destination_gap_ft': destination_gap * 3.28084}
