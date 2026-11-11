"""Check real routes against an independent shortest-path solver and exercise UI callbacks."""
import asyncio
import gzip
import json
from pathlib import Path
import sys

import networkx as nx
from bokeh.document import Document
from routing import RoutingEngine
from search import LANDMARKS

HERE = Path(__file__).resolve().parent
with gzip.open(HERE / 'data' / 'philadelphia.json.gz', 'rt', encoding='utf-8') as source:
    data = json.load(source)
engine = RoutingEngine(data)
reference = nx.DiGraph()
for edge in data['edges']:
    u, v, length = edge['u'], edge['v'], edge['length']
    if not reference.has_edge(u, v) or reference[u][v]['weight'] > length:
        reference.add_edge(u, v, weight=length)

cases = [('Rittenhouse Square', 'LOVE Park'), ('City Hall', 'Kimmel Center'),
         ('30th Street Station', 'Reading Terminal Market'),
         ('Philadelphia Museum of Art', 'Liberty Bell')]
results = []
for origin, destination in cases:
    start, end = LANDMARKS[origin], LANDMARKS[destination]
    route = engine.compare(start, end)
    fastest, alternate = route['fastest'], route['alternative']
    source, _ = engine.snap(start)
    target, _ = engine.snap(end)
    expected = nx.shortest_path_length(reference, source, target, weight='weight')
    assert abs(fastest['distance'] - expected) < .01, 'A* disagrees with Dijkstra'
    assert 0 <= fastest['shade_minutes'] + fastest['sun_minutes'] <= fastest['minutes'] + 1e-6
    if alternate:
        assert alternate['complete']
        assert alternate['minutes'] <= fastest['minutes'] + 5 + 1e-6
        assert alternate['sun_minutes'] <= fastest['sun_minutes'] + 1e-6
    else:
        assert not fastest['complete']
    summary = {'from': origin, 'to': destination, 'miles': round(fastest['miles'], 2),
               'coverage': round(fastest['covered'], 3),
               'sun_minutes_saved': round(fastest['sun_minutes'] - alternate['sun_minutes'], 2) if alternate else None}
    results.append(summary)
    print(summary, flush=True)

for a, b in [(LANDMARKS['City Hall'], LANDMARKS['City Hall']),
             ((-74.0, 40.7), LANDMARKS['City Hall'])]:
    try:
        engine.compare(a, b)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid endpoints should be rejected')

import app
print('Panel app imported', flush=True)
doc = Document()
app.template.server_doc(doc)
print('Panel document built', flush=True)
doc.to_json()
print('Panel document serialized', flush=True)
assert app.state['result'] is not None
app.perspective.value = '2D map'
app.route_choice.value = 'Shortest'
app.hour.value = 9
app.calculate()
doc.to_json()
assert app.state['result'] is not None

async def check_search():
    async def geocode(query):
        if query == 'unmatched':
            raise ValueError('No match')
        return [{'label': '1234 MARKET ST', 'point': (-75.160975, 39.951663), 'address': query}]
    app.address_search.geocode = geocode
    controls = app.controls['start']
    controls['field'].value = '1234 Market St'
    print('Address edit callback checked', flush=True)
    assert app.compare_button.disabled and app.state['result'] is None
    await controls['search'](None)
    print('Address success callback checked', flush=True)
    assert not app.compare_button.disabled and app.state['result'] is not None
    assert app.state['start_label'] == '1234 MARKET ST'
    controls['field'].value = 'unmatched'
    await controls['search'](None)
    assert app.compare_button.disabled and app.state['result'] is None
    assert 'Could not resolve' in controls['message'].object

asyncio.run(check_search())
doc.to_json()
(HERE / 'data' / 'checks.json').write_text(json.dumps({'routes': results,
    'checks': ['A* agrees with NetworkX Dijkstra on four trips', 'detour and exposure bounds',
               'same-point and outside-city rejection', 'Panel document serialization',
               'search success and failure callbacks; stale route cleared'],
    'browser_verified': False}, indent=2), encoding='utf-8')
print('PASS: Python routing, Panel serialization, and address-search callback checks.')
