"""Build the Philadelphia walking graph and reproducible building-shade scenarios.

Run from the repository root. The heavy GIS dependencies stay in preprocessing;
the published Panel app loads the resulting compact dataset in browser Python.
"""
from datetime import datetime, timezone
import json
import gzip
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
import requests
from shapely import contains_xy
from shapely.geometry import LineString, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'python' / 'data'
OUT.mkdir(parents=True, exist_ok=True)
CRS = 'EPSG:26918'
to_metric = Transformer.from_crs(4326, CRS, always_xy=True).transform
to_lonlat = Transformer.from_crs(CRS, 4326, always_xy=True).transform
ALLOWED = {'footway', 'pedestrian', 'path', 'living_street', 'residential',
           'tertiary', 'secondary', 'primary', 'unclassified', 'service',
           'steps', 'tertiary_link', 'secondary_link', 'primary_link'}


def solar_position(hour):
    """NOAA fractional-year approximation for July 15, 2026, EDT in Philadelphia."""
    day = datetime(2026, 7, 15).timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (day - 1 + (hour - 12) / 24)
    equation = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                        - 0.032077 * math.sin(gamma)
                        - 0.014615 * math.cos(2 * gamma)
                        - 0.040849 * math.sin(2 * gamma))
    declination = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
                   - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
                   - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    solar_minutes = hour * 60 + equation + 4 * -75.167 - 60 * -4
    hour_angle = math.radians(solar_minutes / 4 - 180)
    latitude = math.radians(39.9515)
    elevation = math.asin(math.sin(latitude) * math.sin(declination)
                         + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle))
    azimuth = math.atan2(math.sin(hour_angle), math.cos(hour_angle) * math.sin(latitude)
                         - math.tan(declination) * math.cos(latitude))
    return azimuth, elevation


def prepare_graph(boundary):
    graph_path = OUT / 'walk.graphml'
    if graph_path.exists():
        return ox.load_graphml(graph_path)
    extract = json.loads((ROOT / 'osm-philly-roads.json').read_text(encoding='utf-8'))
    city_buffer = transform(to_metric, boundary).buffer(500)
    ways, nodes = [], {}
    for element in extract['elements']:
        tags = element.get('tags', {})
        if (tags.get('highway') not in ALLOWED or tags.get('area') == 'yes'
                or tags.get('access') in {'no', 'private', 'permit'}
                or tags.get('foot') in {'no', 'private'}
                or tags.get('service') == 'parking_aisle'):
            continue
        coords = [(p['lon'], p['lat']) for p in element.get('geometry', [])]
        if len(coords) < 2 or not transform(to_metric, LineString(coords)).intersects(city_buffer):
            continue
        ways.append(element)
        nodes.update(zip(element['nodes'], coords))
    xml = ET.Element('osm', version='0.6', generator='HeatScape')
    for key, (lon, lat) in nodes.items():
        ET.SubElement(xml, 'node', id=str(key), lon=str(lon), lat=str(lat))
    for item in ways:
        way = ET.SubElement(xml, 'way', id=str(item['id']))
        for key in item['nodes']:
            ET.SubElement(way, 'nd', ref=str(key))
        for key, value in item['tags'].items():
            ET.SubElement(way, 'tag', k=key, v=str(value))
    xml_path = ROOT / 'raw' / 'walk-filtered.osm'
    ET.ElementTree(xml).write(xml_path, encoding='utf-8', xml_declaration=True)
    # Keep pedestrian one-way tags visible through graph simplification.
    ox.settings.useful_tags_way = list(set(ox.settings.useful_tags_way + ['oneway:foot', 'foot:forward', 'foot:backward']))
    graph = ox.graph_from_xml(xml_path, bidirectional=True, simplify=False, retain_all=True)
    for u, v, key, attributes in list(graph.edges(keys=True, data=True)):
        reversed_edge = attributes.get('reversed', False)
        direction = attributes.get('oneway:foot')
        prohibited = (direction in {'yes', '1', 'true'} and reversed_edge) or (direction == '-1' and not reversed_edge)
        prohibited |= attributes.get('foot:backward' if reversed_edge else 'foot:forward') == 'no'
        if prohibited:
            graph.remove_edge(u, v, key)
    graph = ox.simplification.simplify_graph(graph)
    ox.save_graphml(graph, graph_path)
    return graph


def prepare_places():
    """Paginate the official place-name table; geocode only the user's chosen result."""
    url = 'https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/place_names/FeatureServer/0/query'
    places = []
    offset = 0
    while True:
        response = requests.get(url, params={'where': '1=1', 'outFields': 'objectid,alias,address',
            'f': 'json', 'returnGeometry': 'false', 'orderByFields': 'objectid',
            'resultOffset': offset, 'resultRecordCount': 2000}, timeout=90)
        response.raise_for_status()
        page = response.json()
        if 'error' in page:
            raise RuntimeError(page['error'])
        records = page.get('features', [])
        places.extend({'name': f['attributes']['alias'], 'address': f['attributes']['address']}
                      for f in records if f['attributes'].get('alias') and f['attributes'].get('address'))
        if not page.get('exceededTransferLimit'):
            break
        offset += len(records)
    return places


def main():
    boundary = shape(json.loads((ROOT / 'raw' / 'boundary.geojson').read_text())['features'][0]['geometry'])
    graph = prepare_graph(boundary)
    nodes, edge_frame = ox.graph_to_gdfs(graph)
    print(f'OSMnx graph: {len(nodes):,} nodes / {len(edge_frame):,} directed edges', flush=True)
    node_keys = list(nodes.index)
    node_indices = {key: index for index, key in enumerate(node_keys)}
    edges = []
    edge_shapes = []
    for (u, v, key), record in edge_frame.iterrows():
        geometry = record.geometry
        coords = list(geometry.coords)
        if abs(coords[0][0] - nodes.loc[u, 'x']) + abs(coords[0][1] - nodes.loc[u, 'y']) > 1e-6:
            coords.reverse()
        metric = transform(to_metric, LineString(coords))
        name = record.get('name')
        if isinstance(name, list):
            name = ' / '.join(map(str, name))
        if not isinstance(name, str):
            name = str(record.get('highway', 'Walking path'))
        edges.append({'u': node_indices[u], 'v': node_indices[v], 'length': round(metric.length, 2),
                      'name': name, 'path': [[round(x, 6), round(y, 6)] for x, y in coords]})
        edge_shapes.append(metric)
    source = (ROOT / 'dist' / 'philly-data.js').read_text(encoding='utf-8')
    old = json.loads(source[len('window.PHILLY='):].rstrip(';'))
    buildings = old['buildings']['features']
    coverage = box(-75.176, 39.946, -75.158, 39.957)
    coverage_metric = transform(to_metric, coverage)
    sample_x, sample_y, sample_edges, sample_weights = [], [], [], []
    for index, geometry in enumerate(edge_shapes):
        if not geometry.intersects(coverage_metric):
            edges[index]['covered'] = 0
            continue
        count = max(1, math.ceil(geometry.length / 10))
        known = 0
        for step in range(count):
            point = geometry.interpolate((step + .5) / count, normalized=True)
            if coverage_metric.covers(point):
                sample_x.append(point.x)
                sample_y.append(point.y)
                sample_edges.append(index)
                sample_weights.append(geometry.length / count)
                known += 1
        edges[index]['covered'] = round(known / count, 4)
    sample_edges = np.asarray(sample_edges)
    sample_weights = np.asarray(sample_weights)
    frames = {}
    for hour in range(8, 20):
        azimuth, elevation = solar_position(hour)
        parts = []
        for feature in buildings:
            polygon = transform(to_metric, shape(feature['geometry']))
            coords = list(polygon.exterior.coords)
            length = feature['properties']['height'] / math.tan(elevation)
            dx, dy = math.sin(azimuth) * length, math.cos(azimuth) * length
            parts.append(polygon)
            for first, second in zip(coords, coords[1:]):
                quad = Polygon([first, second, (second[0] + dx, second[1] + dy),
                                (first[0] + dx, first[1] + dy)])
                if quad.is_valid and quad.area > .001:
                    parts.append(quad)
        shadow = unary_union(parts)
        hits = contains_xy(shadow, np.asarray(sample_x), np.asarray(sample_y))
        shade_lengths = np.bincount(sample_edges, weights=hits * sample_weights, minlength=len(edges))
        fractions = {str(i): round(float(value) / edges[i]['length'], 4)
                     for i, value in enumerate(shade_lengths) if value > 0 and edges[i]['length'] > 0}
        display = transform(to_lonlat, shadow.intersection(coverage_metric).simplify(.7))
        frames[str(hour)] = {'shade': fractions, 'geometry': mapping(display),
                             'elevation': round(math.degrees(elevation), 1)}
        print(f'Shadow scenario {hour}:00 ready', flush=True)
    places = prepare_places()
    boundary_display = transform(to_lonlat, transform(to_metric, boundary).simplify(8))
    data = {'nodes': [[round(row.x, 6), round(row.y, 6)] for row in nodes.itertuples()],
            'edges': edges, 'buildings': old['buildings'], 'frames': frames,
            'coverage': mapping(coverage), 'boundary': mapping(boundary_display), 'places': places,
            'meta': {'prepared': datetime.now(timezone.utc).isoformat(), 'date': '2026-07-15',
                     'network': 'OSMnx 2.1.1 / OpenStreetMap, downloaded 2026-11-10',
                     'buildings': len(buildings), 'assumed_heights': 974, 'places': len(places),
                     'crs': CRS, 'sample_spacing_m': 10, 'source': 'https://overpass.private.coffee/api/interpreter',
                     'place_source': 'https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/place_names/FeatureServer'}}
    (OUT / 'philadelphia.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    with gzip.open(OUT / 'philadelphia.json.gz', 'wt', encoding='utf-8', compresslevel=9) as target:
        json.dump(data, target, separators=(',', ':'))
    print(f'Prepared {len(places)} place names; data size {(OUT / "philadelphia.json").stat().st_size / 1e6:.1f} MB', flush=True)


if __name__ == '__main__':
    main()
