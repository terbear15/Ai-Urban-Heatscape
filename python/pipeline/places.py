"""Named places for search (U9) and places to pause (F9), from the same OSM download."""
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point

SEARCH_KEYS = ["tourism", "historic", "leisure", "amenity", "shop", "railway", "public_transport", "office", "building", "place"]
SKIP = {"amenity": {"bench", "waste_basket", "bicycle_parking", "parking_entrance", "vending_machine", "atm",
                    "post_box", "telephone", "drinking_water", "charging_station", "parking_space", "recycling",
                    "loading_dock", "grit_bin", "bicycle_rental", "motorcycle_parking"}}
# Places to pause. Summer: drinking water and shade or cool indoor public rooms. Winter: warm indoor public rooms.
PAUSE = [
    ("water", lambda t: t.get("amenity") == "drinking_water" or (t.get("amenity") == "fountain" and t.get("drinking_water") == "yes")),
    ("park", lambda t: t.get("leisure") in {"park", "garden"} and t.get("access") not in {"private", "no"}),
    ("library", lambda t: t.get("amenity") == "library"),
    ("community", lambda t: t.get("amenity") in {"community_centre", "social_centre"}),
    ("mall", lambda t: t.get("shop") == "mall"),
    ("station", lambda t: t.get("public_transport") == "station" or t.get("railway") == "station"),
]


def kind_label(tags):
    for key in SEARCH_KEYS:
        if key in tags:
            return "building" if key == "building" else tags[key].replace("_", " ")
    return "place"


def collect(nodes, ways, reach_polygon, edges, street_names):
    """Return (search places, pause places). Each search place: [name, kind, lon, lat, street]."""
    elements = []
    for lon, lat, tags in nodes.values():
        if tags:
            elements.append((lon, lat, tags))
    for refs, tags in ways.values():
        if tags.get("name") or any(test(tags) for _, test in PAUSE):
            pts = [nodes[r] for r in refs if r in nodes]
            if pts:
                elements.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), tags))
    # Nearest street name for each place (edge midpoints), so same-name places can be told apart.
    mids = np.array([[(e[2] + e[4]) / 2, (e[3] + e[5]) / 2] for e in edges]) if edges else np.zeros((0, 2))
    street_tree = cKDTree(mids) if len(mids) else None

    def street_for(lon, lat, tags):
        if tags.get("addr:street"):
            return tags["addr:street"]
        if street_tree is None:
            return ""
        _, i = street_tree.query([lon, lat])
        name = street_names[edges[i][7]]
        return name if name[:1].isupper() and name not in {"Footpath", "Path", "Service lane", "Steps"} else ""

    search, pause, seen, seen_pause = [], [], set(), set()
    for lon, lat, tags in elements:
        if not reach_polygon.contains(Point(lon, lat)):
            continue
        name = (tags.get("name") or "").strip()
        for category, test in PAUSE:
            if test(tags):
                key = (category, round(lon, 4), round(lat, 4))
                if key not in seen_pause:
                    seen_pause.add(key)
                    pause.append([name or {"water": "Drinking water", "park": "Park"}.get(category, category.capitalize()),
                                  category, round(lon, 6), round(lat, 6)])
                break
        if not name or not any(k in tags for k in SEARCH_KEYS) or any(tags.get(k) in v for k, v in SKIP.items()):
            continue
        key = (name.lower(), round(lon, 4), round(lat, 4))
        if key in seen:
            continue
        seen.add(key)
        landmark = 0 if ("tourism" in tags or "historic" in tags or tags.get("leisure") == "park") else 1
        search.append([name, kind_label(tags), round(lon, 6), round(lat, 6), street_for(lon, lat, tags), landmark])
    search.sort(key=lambda p: (p[5], p[0].lower()))
    return [p[:5] for p in search], pause
