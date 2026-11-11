import json
from search import AddressSearch, find_places, normalize

with open("places.json", encoding="utf-8") as source:
    places = json.load(source)

# Branch addresses from the official McDonald's location directory.
places.extend([
    {"name": "McDonald's", "address": "2901 Grays Ferry Ave"},
    {"name": "McDonald's", "address": "3935 Walnut Street"},
    {"name": "McDonald's", "address": "3137 N Broad St"},
    {"name": "McDonald's", "address": "2109 N Broad St"},
])
addresses = AddressSearch()


async def lookup(query, address_only, suggest=False):
    normalized = normalize(query)
    if normalized in {"mcd", "mcdo", "mcdon", "mcdonald", "mcdonalds"}:
        query = "McDonald"
    matches = []
    if not address_only and normalized:
        if normalized[0].isdigit():
            if suggest:
                candidates = dict.fromkeys(
                    place["address"] for place in places
                    if normalize(place["address"]).startswith(normalized)
                )
                matches = [
                    {"label": address, "point": None, "address": address}
                    for address in list(candidates)[:8]
                ]
        else:
            matches = find_places(query, places)
    if matches or suggest:
        return json.dumps(matches)
    return json.dumps(await addresses.geocode(query))
