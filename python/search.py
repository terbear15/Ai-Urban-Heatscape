"""Official Philadelphia place-name matching and AIS address geocoding."""
import asyncio
from functools import lru_cache
import json
import re
import sys
from urllib.parse import quote

LANDMARKS = {
    'Rittenhouse Square': (-75.17175, 39.9497),
    'LOVE Park': (-75.1659, 39.9541),
    'City Hall': (-75.1636, 39.9526),
    'Kimmel Center': (-75.1654, 39.9475),
    'Philadelphia Museum of Art': (-75.1794, 39.9656),
    '30th Street Station': (-75.1821, 39.9556),
    'Reading Terminal Market': (-75.1594, 39.9533),
    'Liberty Bell': (-75.1502, 39.9496),
}


def normalize(value):
    return ' '.join(re.findall(r'[a-z0-9]+', value.lower()))


def find_places(query, places):
    words = normalize(query).split()
    if not words:
        return []
    matches = []
    seen = set()
    for name, point in LANDMARKS.items():
        if all(word in normalize(name) for word in words):
            matches.append({'label': name + ' · landmark', 'point': point, 'address': None})
    for place in places:
        name, address = place['name'], place['address']
        key = (normalize(name), address)
        if key in seen or not all(word in normalize(name) for word in words):
            continue
        seen.add(key)
        matches.append({'label': name + ' · ' + address, 'point': None, 'address': address})
    return sorted(matches, key=lambda item: (normalize(query) not in normalize(item['label']), len(item['label'])))[:8]


async def read_json(url):
    if sys.platform == 'emscripten':
        from pyodide.http import pyfetch
        response = await pyfetch(url)
        if response.status != 200:
            raise ValueError('The city address service could not match this search. Try a full street address.')
        return await response.json()
    import httpx
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise ValueError('The city address service could not match this search. Try a full street address.')
        return response.json()


class AddressSearch:
    def __init__(self):
        self.cache = {}

    async def geocode(self, query):
        query = query.strip()
        if len(query) < 3:
            raise ValueError('Enter a place name or full Philadelphia street address.')
        if query in self.cache:
            return self.cache[query]
        url = 'https://api.phila.gov/ais/v1/search/' + quote(query, safe='')
        data = await asyncio.wait_for(read_json(url), timeout=30)
        matches = []
        for feature in data.get('features', []):
            geometry = feature.get('geometry') or {}
            if geometry.get('type') != 'Point':
                continue
            properties = feature.get('properties', {})
            matches.append({'label': properties.get('street_address', query),
                            'point': geometry['coordinates'][:2], 'address': query})
        if not matches:
            raise ValueError('No address match. Try a house number and street, or select a landmark result.')
        self.cache[query] = matches[:8]
        return self.cache[query]
