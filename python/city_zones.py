"""Downtown and visitor areas for each city.

Each zone is (name, longitude, latitude, radius in km): a circle around the
area's center. A zone given as (name, (west, south, east, north)) is a box.
The union of a city's zones, clipped to the city's land, is the area where
HeatScape works in that city.
"""

ZONES = {
    "new-york": [
        ("Manhattan", -73.971, 40.776, 4.0),
    ],
    "los-angeles": [
        ("Downtown LA", -118.250, 34.048, 1.6),
        ("Westlake and Koreatown", -118.290, 34.062, 1.6),
        ("Larchmont and Little Armenia", -118.300, 34.079, 0.9),
        ("Hollywood", -118.330, 34.101, 1.4),
        ("West Hollywood and Sunset Strip", -118.370, 34.090, 1.2),
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
        ("Art Museum, Spring Garden and Callowhill", (-75.1830, 39.9580, -75.1360, 39.9675)),
        ("Grays Ferry", (-75.2060, 39.9225, -75.1790, 39.9420)),
        ("Delaware River waterfront", (-75.1500, 39.9225, -75.1290, 39.9545)),
        ("University City", -75.195, 39.953, 1.2),
        ("South Philadelphia", -75.165, 39.928, 1.6),
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
    "san-jose": [
        ("Downtown", -121.889, 37.335, 1.3),
    ],
    "charlotte": [
        ("Uptown", -80.843, 35.227, 1.3),
        ("South End", -80.856, 35.212, 0.9),
    ],
    "san-francisco": [
        ("Union Square and Financial District", -122.405, 37.790, 1.4),
        ("Fisherman's Wharf and North Beach", -122.412, 37.805, 1.1),
        ("Embarcadero", -122.394, 37.796, 0.8),
        ("Mission District", -122.418, 37.760, 1.0),
        ("Golden Gate Park", -122.465, 37.770, 1.3),
        ("Hayes Valley and Western Addition", -122.430, 37.778, 0.9),
        ("Haight-Ashbury and Inner Sunset", -122.450, 37.766, 0.9),
        ("Castro and Twin Peaks", -122.440, 37.755, 1.0),
        ("Presidio", -122.466, 37.798, 1.5),
        ("Marina and Pacific Heights", -122.435, 37.797, 1.0),
        ("Richmond, Sea Cliff and Lincoln Park", -122.490, 37.780, 1.5),
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
    "washington": [
        ("National Mall", -77.030, 38.889, 1.6),
        ("Downtown and Penn Quarter", -77.023, 38.899, 1.0),
        ("Dupont Circle", -77.043, 38.910, 0.8),
        ("Georgetown", -77.064, 38.906, 0.9),
    ],
    "boston": [
        ("Downtown and Freedom Trail", -71.059, 42.358, 1.0),
        ("North End", -71.054, 42.365, 0.6),
        ("Back Bay", -71.080, 42.350, 1.0),
        ("Seaport", -71.044, 42.350, 0.8),
        ("MIT, Kendall Square and Harvard", (-71.1240, 42.3540, -71.0770, 42.3790)),
    ],
    "atlanta": [
        ("Downtown", -84.390, 33.757, 1.2),
        ("Midtown", -84.385, 33.781, 1.1),
        ("Old Fourth Ward and BeltLine", -84.365, 33.767, 0.8),
    ],
    "minneapolis": [
        ("Downtown", -93.270, 44.977, 1.2),
        ("Mill District and Riverfront", -93.256, 44.979, 0.7),
    ],
    "detroit": [
        ("Downtown", -83.047, 42.333, 1.2),
        ("Midtown", -83.065, 42.352, 0.9),
        ("Riverwalk", -83.035, 42.330, 0.7),
    ],
    "baltimore": [
        ("Inner Harbor", -76.611, 39.285, 1.0),
        ("Fells Point", -76.594, 39.283, 0.7),
        ("Mount Vernon", -76.616, 39.298, 0.7),
    ],
    "miami": [
        ("Downtown and Bayfront", -80.190, 25.775, 1.2),
        ("Brickell", -80.193, 25.762, 0.9),
        ("Wynwood", -80.199, 25.801, 0.8),
        ("Little Havana", -80.218, 25.766, 0.8),
    ],
    "st-louis": [
        ("Downtown", -90.190, 38.628, 1.1),
        ("Downtown West", -90.205, 38.632, 0.8),
    ],
    "portland": [
        ("Downtown", -122.679, 45.517, 1.0),
        ("Pearl District", -122.683, 45.528, 0.6),
        ("Old Town Chinatown", -122.673, 45.525, 0.5),
    ],
    "nashville": [
        ("Downtown", -86.778, 36.162, 1.1),
        ("The Gulch", -86.786, 36.152, 0.5),
    ],
    "indianapolis": [
        ("Downtown", -86.158, 39.768, 1.3),
    ],
    "cincinnati": [
        ("Downtown", -84.512, 39.102, 0.9),
        ("Over-the-Rhine", -84.516, 39.112, 0.7),
    ],
    "kansas-city": [
        ("Downtown", -94.583, 39.100, 1.1),
        ("Crossroads", -94.581, 39.088, 0.6),
        ("River Market", -94.582, 39.110, 0.5),
    ],
    "pittsburgh": [
        ("Downtown", -79.997, 40.441, 0.9),
        ("Strip District", -79.978, 40.452, 0.7),
    ],
    "cleveland": [
        ("Downtown", -81.690, 41.500, 1.2),
    ],
    "salt-lake-city": [
        ("Downtown", -111.891, 40.763, 1.2),
    ],
    "milwaukee": [
        ("Downtown", -87.909, 43.041, 1.1),
        ("Third Ward", -87.907, 43.033, 0.5),
    ],
}


# Official areas. Each zone above maps to one or more named places whose boundary
# polygon is looked up in OpenStreetMap (neighborhood, district, park or city
# boundaries) by python/official_zones.py. The circles above are used only for a
# zone whose names all fail to resolve. Philadelphia uses the city's own Center City
# neighborhoods (python/prepare_center_city.py).
OFFICIAL = {
    "new-york": {  # NYC Department of City Planning Neighborhood Tabulation Areas (2020), all of Manhattan
        "Manhattan": ["ntaboro:Manhattan"],
    },
    "los-angeles": {  # LA County Countywide Statistical Areas (LA City neighborhoods)
        "Downtown LA": ["lacounty:Los Angeles - Downtown"],
        "Westlake and Koreatown": ["lacounty:Los Angeles - Westlake", "lacounty:Los Angeles - Koreatown", "lacounty:Los Angeles - Wilshire Center"],
        "Larchmont and Little Armenia": [],  # street-bounded connector, python/downtown_boxes.py
        "Hollywood": ["lacounty:Los Angeles - Hollywood", "lacounty:Los Angeles - East Hollywood"],
        "West Hollywood and Sunset Strip": ["lacity:West Hollywood"],
    },
    "chicago": {
        "The Loop": ["Loop, Chicago"],
        "River North and Magnificent Mile": ["Near North Side, Chicago"],
        "Museum Campus": ["Grant Park, Chicago", "Museum Campus, Chicago"],
        "Navy Pier": ["Streeterville, Chicago", "Near North Side, Chicago"],
    },
    "houston": {
        "Downtown": ["Downtown, Houston"],
        "Midtown": ["Midtown, Houston"],
        "Museum District": ["Museum District, Houston"],
    },
    "phoenix": {
        "Downtown": ["Downtown Phoenix", "Downtown, Phoenix"],
        "Roosevelt Row": ["Roosevelt Row, Phoenix", "Evans Churchill, Phoenix", "Roosevelt, Phoenix", "Roosevelt Historic District, Phoenix"],
    },
    "san-diego": {
        "Downtown and Gaslamp Quarter": ["Downtown, San Diego"],
        "Balboa Park": ["Balboa Park, San Diego"],
        "Old Town": ["Old Town, San Diego", "Old Town San Diego", "Old Town San Diego State Historic Park"],
        "La Jolla": ["La Jolla Village, San Diego", "La Jolla, San Diego"],
    },
    "dallas": {
        "Downtown": ["Downtown Dallas", "Downtown, Dallas", "City Center District, Dallas", "Main Street District, Dallas"],
        "Uptown and Arts District": ["Uptown, Dallas", "Arts District, Dallas"],
        "Deep Ellum": ["Deep Ellum, Dallas"],
    },
    "charlotte": {
        "Uptown": ["First Ward, Charlotte", "Second Ward, Charlotte", "Third Ward, Charlotte", "Fourth Ward, Charlotte"],
        "South End": ["South End, Charlotte", "Dilworth, Charlotte"],
    },
    "san-francisco": {  # San Francisco Analysis Neighborhoods
        "Union Square and Financial District": ["layer:sf:nhood=Financial District/South Beach", "layer:sf:nhood=Chinatown", "layer:sf:nhood=Nob Hill", "layer:sf:nhood=Tenderloin"],
        "Fisherman's Wharf and North Beach": ["layer:sf:nhood=North Beach", "layer:sf:nhood=Russian Hill"],
        "Embarcadero": ["layer:sf:nhood=South of Market"],
        "Mission District": ["layer:sf:nhood=Mission"],
        "Golden Gate Park": ["layer:sf:nhood=Golden Gate Park"],
        "Hayes Valley and Western Addition": ["layer:sf:nhood=Hayes Valley", "layer:sf:nhood=Western Addition"],
        "Haight-Ashbury and Inner Sunset": ["layer:sf:nhood=Haight Ashbury", "layer:sf:nhood=Inner Sunset", "layer:sf:nhood=Lone Mountain/USF"],
        "Castro and Twin Peaks": ["layer:sf:nhood=Castro/Upper Market", "layer:sf:nhood=Twin Peaks", "layer:sf:nhood=Noe Valley"],
        "Presidio": ["layer:sf:nhood=Presidio"],
        "Marina and Pacific Heights": ["layer:sf:nhood=Marina", "layer:sf:nhood=Pacific Heights", "layer:sf:nhood=Presidio Heights", "layer:sf:nhood=Japantown"],
        "Richmond, Sea Cliff and Lincoln Park": ["layer:sf:nhood=Seacliff", "layer:sf:nhood=Lincoln Park", "layer:sf:nhood=Outer Richmond", "layer:sf:nhood=Inner Richmond"],
    },
    "seattle": {  # Seattle City Clerk Neighborhood Map Atlas
        "Downtown and Pike Place": ["layer:seattle:S_HOOD=Central Business District", "layer:seattle:S_HOOD=Pike-Market", "layer:seattle:S_HOOD=Pike Market", "layer:seattle:S_HOOD=Belltown"],
        "Pioneer Square": ["layer:seattle:S_HOOD=Pioneer Square", "layer:seattle:S_HOOD=International District"],
        "Seattle Center": ["layer:seattle:S_HOOD=Lower Queen Anne", "Seattle Center"],
        "Capitol Hill": ["layer:seattle:S_HOOD=Broadway", "Capitol Hill, Seattle"],
    },
    "denver": {
        "Downtown and LoDo": ["Central Business District, Denver", "Union Station, Denver", "Auraria, Denver"],
        "Civic Center": ["Civic Center, Denver"],
        "RiNo": ["Five Points, Denver"],
    },
    "washington": {
        "National Mall": ["National Mall, Washington"],
        "Downtown and Penn Quarter": ["Downtown, Washington", "Penn Quarter, Washington", "Chinatown, Washington"],
        "Dupont Circle": ["Dupont Circle, Washington"],
        "Georgetown": ["Georgetown, Washington"],
    },
    "boston": {
        "Downtown and Freedom Trail": ["Downtown, Boston", "Beacon Hill, Boston", "West End, Boston"],
        "North End": ["North End, Boston"],
        "Back Bay": ["Back Bay, Boston"],
        "Seaport": ["Seaport District, Boston", "South Boston Waterfront, Boston"],
        "MIT, Kendall Square and Harvard": [],  # street-bounded band in Cambridge, python/downtown_boxes.py
    },
    "atlanta": {  # City of Atlanta Department of City Planning neighborhoods
        "Downtown": ["layer:atlanta:NAME=Downtown", "Downtown Atlanta"],
        "Midtown": ["layer:atlanta:NAME=Midtown", "Midtown Atlanta"],
        "Old Fourth Ward and BeltLine": ["layer:atlanta:NAME=Old Fourth Ward", "Old Fourth Ward, Atlanta"],
    },
    "minneapolis": {
        "Downtown": ["Downtown West, Minneapolis", "Downtown East, Minneapolis"],
        "Mill District and Riverfront": ["Downtown East, Minneapolis", "Marcy-Holmes, Minneapolis"],
    },
    "san-jose": {
        "Downtown": ["Downtown San Jose", "Downtown, San Jose", "Downtown Core, San Jose"],
    },
    "detroit": {
        "Downtown": ["layer:detroit:NHood_Name=Downtown", "Downtown Detroit"],
        "Midtown": ["layer:detroit:NHood_Name=Midtown", "Midtown, Detroit"],
        "Riverwalk": ["layer:detroit:NHood_Name=Rivertown", "Rivertown, Detroit"],
    },
    "baltimore": {
        "Inner Harbor": ["Inner Harbor, Baltimore", "Downtown, Baltimore"],
        "Fells Point": ["Fells Point, Baltimore", "Fell's Point, Baltimore", "Fells Point Historic District"],
        "Mount Vernon": ["Mount Vernon, Baltimore"],
    },
    "miami": {
        "Downtown and Bayfront": ["Downtown, Miami", "Downtown Miami", "Central Business District, Miami", "Park West, Miami"],
        "Brickell": ["Brickell, Miami"],
        "Wynwood": ["Wynwood, Miami"],
        "Little Havana": ["Little Havana, Miami", "East Little Havana, Miami", "Little Havana"],
    },
    "st-louis": {
        "Downtown": ["Downtown, St. Louis", "Gateway Arch National Park"],
        "Downtown West": ["Downtown West, St. Louis"],
    },
    "portland": {
        "Downtown": ["Downtown, Portland", "Portland Downtown"],
        "Pearl District": ["Pearl, Portland", "Pearl District, Portland"],
        "Old Town Chinatown": ["Old Town, Portland", "Old Town Chinatown, Portland"],
    },
    "nashville": {
        "Downtown": ["Downtown, Nashville", "Downtown Nashville"],
        "The Gulch": ["The Gulch, Nashville", "Gulch, Nashville"],
    },
    "indianapolis": {
        "Downtown": ["Downtown, Indianapolis", "Mile Square, Indianapolis"],
    },
    "cincinnati": {
        "Downtown": ["Downtown, Cincinnati", "Central Business District, Cincinnati"],
        "Over-the-Rhine": ["Over-the-Rhine, Cincinnati"],
    },
    "kansas-city": {
        "Downtown": ["Central Business District, Kansas City", "Downtown, Kansas City"],
        "Crossroads": ["Crossroads, Kansas City", "Crossroads Arts District, Kansas City"],
        "River Market": ["River Market, Kansas City"],
    },
    "pittsburgh": {
        "Downtown": ["Central Business District, Pittsburgh", "Downtown, Pittsburgh"],
        "Strip District": ["Strip District, Pittsburgh"],
    },
    "cleveland": {
        "Downtown": ["Downtown, Cleveland", "Downtown Cleveland"],
    },
    "salt-lake-city": {
        "Downtown": ["Downtown, Salt Lake City", "Central Business District, Salt Lake City"],
    },
    "milwaukee": {
        "Downtown": ["Downtown, Milwaukee", "Westown, Milwaukee", "East Town, Milwaukee"],
        "Third Ward": ["Historic Third Ward, Milwaukee", "Third Ward, Milwaukee"],
    },
    "philadelphia": {  # Philadelphia neighborhoods (OpenDataPhilly)
        "Center City": ["layer:philly:LISTNAME=" + n for n in ("Logan Square", "Rittenhouse", "Fitler Square", "Center City East",
                        "Washington Square West", "Society Hill", "Old City", "Chinatown")],
        "Art Museum, Spring Garden and Callowhill": [],  # street-bounded band, python/downtown_boxes.py
        "Grays Ferry": [],  # street-bounded block, python/downtown_boxes.py
        "Delaware River waterfront": [],  # street-bounded block, python/downtown_boxes.py
        "University City": ["layer:philly:LISTNAME=" + n for n in ("University City", "Powelton", "West Powelton", "Spruce Hill",
                            "Cedar Park", "Walnut Hill")],
        "South Philadelphia": ["layer:philly:LISTNAME=" + n for n in ("Queen Village", "Bella Vista", "Graduate Hospital",
                               "Passyunk Square", "East Passyunk", "Pennsport", "Dickinson Narrows", "Point Breeze",
                               "Newbold", "Whitman", "Lower Moyamensing")],
    },
}
