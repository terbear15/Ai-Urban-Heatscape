import json
from search import AddressSearch, find_places, normalize
with open("places.json", encoding="utf-8") as source:
    places = json.load(source)
addresses = AddressSearch()

async def lookup(query, address_only):
    words = normalize(query).split()
    matches = [] if address_only or len(query) < 2 or (words and words[0].isdigit()) else find_places(query, places)
    return json.dumps(matches or await addresses.geocode(query))
