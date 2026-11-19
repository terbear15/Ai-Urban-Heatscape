"""Downtown and visitor areas for each city.

Each zone is (name, longitude, latitude, radius in km): a circle around the
area's center. A zone given as (name, (west, south, east, north)) is a box.
The union of a city's zones, clipped to the city's land, is the area where
HeatScape works in that city.
"""

ZONES = {
    "new-york": [
        ("Lower Manhattan", -74.010, 40.708, 1.3),
        ("SoHo and Greenwich Village", -74.000, 40.727, 1.2),
        ("Midtown and Times Square", -73.985, 40.756, 1.6),
        ("Central Park", -73.968, 40.782, 1.4),
        ("DUMBO and Brooklyn Bridge", -73.990, 40.703, 0.8),
    ],
    "los-angeles": [
        ("Downtown LA", -118.250, 34.048, 1.6),
        ("Hollywood", -118.330, 34.101, 1.4),
        ("Sunset Strip", -118.380, 34.093, 1.2),
        ("Beverly Hills", -118.400, 34.070, 1.0),
        ("Santa Monica", -118.492, 34.012, 1.5),
        ("Venice", -118.470, 33.988, 1.0),
    ],
    "chicago": [
        ("The Loop", -87.630, 41.881, 1.4),
        ("River North and Magnificent Mile", -87.626, 41.895, 1.2),
        ("Museum Campus", -87.615, 41.866, 1.0),
        ("Navy Pier", -87.605, 41.892, 0.7),
    ],
    "houston": [
        ("Downtown", -95.366, 29.758, 1.3),
        ("Midtown", -95.377, 29.743, 0.9),
        ("Museum District", -95.390, 29.722, 1.2),
    ],
    "phoenix": [
        ("Downtown", -112.074, 33.449, 1.4),
        ("Roosevelt Row", -112.069, 33.459, 0.7),
    ],
    "philadelphia": [
        # Center City: Vine Street to South Street, Schuylkill to Delaware River.
        ("Center City", (-75.1830, 39.9415, -75.1395, 39.9585)),
    ],
    "san-antonio": [
        ("Downtown, River Walk and the Alamo", -98.490, 29.425, 1.4),
        ("The Pearl", -98.480, 29.443, 0.7),
    ],
    "san-diego": [
        ("Downtown and Gaslamp Quarter", -117.160, 32.712, 1.3),
        ("Balboa Park", -117.150, 32.731, 1.2),
        ("Old Town", -117.196, 32.754, 0.7),
        ("La Jolla", -117.273, 32.847, 1.0),
    ],
    "dallas": [
        ("Downtown", -96.800, 32.780, 1.3),
        ("Uptown and Arts District", -96.800, 32.795, 1.0),
        ("Deep Ellum", -96.783, 32.784, 0.7),
    ],
    "jacksonville": [
        ("Downtown", -81.658, 30.327, 1.4),
        ("Riverside", -81.685, 30.311, 0.9),
    ],
    "san-jose": [
        ("Downtown", -121.889, 37.335, 1.3),
    ],
    "austin": [
        ("Downtown", -97.743, 30.268, 1.3),
        ("Capitol and UT", -97.738, 30.284, 1.0),
        ("South Congress", -97.748, 30.250, 0.9),
    ],
    "charlotte": [
        ("Uptown", -80.843, 35.227, 1.3),
        ("South End", -80.856, 35.212, 0.9),
    ],
    "columbus": [
        ("Downtown", -82.999, 39.961, 1.3),
        ("Short North", -83.003, 39.978, 0.9),
        ("German Village", -82.995, 39.950, 0.7),
    ],
    "indianapolis": [
        ("Downtown", -86.158, 39.768, 1.4),
        ("Mass Ave", -86.150, 39.775, 0.6),
    ],
    "san-francisco": [
        ("Union Square and Financial District", -122.405, 37.790, 1.4),
        ("Fisherman's Wharf and North Beach", -122.412, 37.805, 1.1),
        ("Embarcadero", -122.394, 37.796, 0.8),
        ("Mission District", -122.418, 37.760, 1.0),
        ("Golden Gate Park", -122.465, 37.770, 1.3),
    ],
    "seattle": [
        ("Downtown and Pike Place", -122.337, 47.608, 1.4),
        ("Pioneer Square", -122.333, 47.600, 0.7),
        ("Seattle Center", -122.352, 47.621, 0.9),
        ("Capitol Hill", -122.320, 47.623, 0.9),
    ],
    "denver": [
        ("Downtown and LoDo", -104.995, 39.748, 1.4),
        ("Civic Center", -104.985, 39.737, 0.9),
        ("RiNo", -104.982, 39.768, 0.8),
    ],
    "oklahoma-city": [
        ("Downtown and Bricktown", -97.513, 35.467, 1.4),
    ],
    "miami": [
        ("Downtown and Bayfront", -80.190, 25.775, 1.2),
        ("Brickell", -80.193, 25.762, 0.9),
        ("Wynwood", -80.199, 25.801, 0.8),
        ("Little Havana", -80.218, 25.766, 0.8),
    ],
}
