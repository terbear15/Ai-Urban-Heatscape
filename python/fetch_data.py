"""Acquire the API inputs used by prepare_data.py. Existing files are reused."""
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'raw'
RAW.mkdir(exist_ok=True)
session = requests.Session()
session.headers['User-Agent'] = 'HeatScape-University-Research/0.2 (https://github.com/terbear15/Ai-Urban-Heatscape)'

boundary = RAW / 'boundary.geojson'
if not boundary.exists():
    response = session.get('https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2024/MapServer/28/query',
        params={'where': "STATE='42' AND PLACE='60000'", 'outFields': '*', 'f': 'geojson', 'outSR': 4326}, timeout=90)
    response.raise_for_status()
    assert response.json().get('features'), 'Missing city boundary'
    boundary.write_bytes(response.content)

roads = ROOT / 'osm-philly-roads.json'
if not roads.exists():
    query = '[out:json][timeout:180];way[highway][highway!~"motorway|trunk|proposed|construction"](39.865,-75.285,40.14,-74.955);out body geom;'
    response = session.get('https://overpass.private.coffee/api/interpreter', params={'data': query}, timeout=240)
    response.raise_for_status()
    assert response.json().get('elements'), 'Missing OSM ways'
    roads.write_bytes(response.content)
print('Raw API inputs ready. Run python python/prepare_data.py next.')
