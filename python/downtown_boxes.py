"""Street-bounded downtown blocks for zones with no official polygon.

Each block follows the streets and freeways that commonly define the district
(lon, lat ring). Used by prepare_city_views.py only when official_zones.py found
no boundary for that zone; the result is still clipped to land.
"""

BOXES = {
    "san-jose": {
        # Downtown Core: Julian St (north), I-280 (south), SR-87 (west), 7th St / San Jose State (east).
        "Downtown": [(-121.8985, 37.3418), (-121.8793, 37.3418), (-121.8793, 37.3262), (-121.8985, 37.3262)],
    },
    "phoenix": {
        # Downtown Phoenix: Roosevelt St (north), Lincoln St / rail (south), 7th Ave (west), 7th St (east).
        "Downtown": [(-112.0827, 33.4585), (-112.0653, 33.4585), (-112.0653, 33.4423), (-112.0827, 33.4423)],
        # Roosevelt Row arts district: McDowell Rd to Roosevelt St, 7th Ave to 7th St.
        "Roosevelt Row": [(-112.0827, 33.4655), (-112.0653, 33.4655), (-112.0653, 33.4585), (-112.0827, 33.4585)],
    },
    "miami": {
        # Downtown Miami: I-395 (north), Miami River (south), I-95 (west), Biscayne Bay (east).
        "Downtown and Bayfront": [(-80.2005, 25.7895), (-80.1855, 25.7895), (-80.1855, 25.7700), (-80.2005, 25.7700)],
        # Little Havana: W Flagler St (north), SW 13th St (south), SW 27th Ave (west), I-95 (east).
        "Little Havana": [(-80.2378, 25.7740), (-80.2045, 25.7740), (-80.2045, 25.7605), (-80.2378, 25.7605)],
    },
}
