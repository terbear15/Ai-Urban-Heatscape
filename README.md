# HeatScape

**Find the shadier way.** HeatScape compares walking routes by how much direct sun they get. In summer it looks for the route that stays in the shade of buildings and trees; in winter, the one that stays in the sunshine. It covers the downtown and main visitor areas of twenty large US cities.

**Website:** https://terbear15.github.io/Ai-Urban-Heatscape/

Geospatial Python course project (MUSA 5500, University of Pennsylvania).

## Using the site

1. **Landing page** — pick Summer or Winter (the choice carries across every page) and press *Explore*.
2. **Choose a city** — twenty cities, searchable by city or area name (for example "Hollywood" or "Back Bay").
3. **City map** — enter where you start and where you are going (a place, landmark or address, or click the map), choose how many extra minutes a better route is worth, and press *Compare routes*. You get three routes: the fastest, a balanced one (about a minute extra) and the shadiest (or sunniest in winter) within your budget, with minutes in direct sun, a street-by-street list, and the best time to leave. Drag the time and date sliders to watch the shadows move. Links can be shared; they reopen the same route.

HeatScape is a model, not a forecast. It shows where buildings and trees cast shadows for a given sun position. It does not measure temperature, clouds, awnings or safety.

## How it works

| Step | Where | What |
|---|---|---|
| Study areas | `python/city_zones.py`, `python/official_zones.py`, `python/prepare_city_views.py` | Each city's downtown and visitor zones use official boundaries: NYC Neighborhood Tabulation Areas, LA County statistical areas, city neighborhood layers (San Francisco, Seattle, Atlanta, Detroit), Philadelphia's Center City neighborhoods, and OpenStreetMap neighborhood and district boundaries elsewhere. The areas are clipped to land using Census place boundaries. |
| Street network | `python/pipeline/osm.py`, `network.py` | OpenStreetMap is downloaded in tiles. **OSMnx** builds the walking graph (`graph_from_xml`), with street counts and basic statistics. Each segment gets a sidewalk offset from its road type, width and lanes, so shade is sampled on the two sidewalks, not on the centerline. |
| Buildings | `python/pipeline/buildings.py` | OSM footprints, including multipolygons. |
| LiDAR | `python/pipeline/lidar.py` | **USGS 3DEP** point clouds (Entwine format on AWS; NOAA for Philadelphia) are gridded at 2 m: ground, highest return, and a **canopy height model**. Building height is the 90th percentile of the CHM inside each footprint. Tree crowns are CHM cells 2.5–45 m tall outside buildings, labeled into connected pieces (`scipy.ndimage`) and polygonized with `rasterio`. |
| Missing heights | `python/pipeline/heights_ml.py` | A **scikit-learn random forest** predicts heights for buildings LiDAR does not cover, from footprint shape, OSM tags and neighboring heights (5-fold cross-validated error reported per city). |
| Places | `python/pipeline/places.py` | Searchable landmarks and streets, plus places to cool off in summer or warm up in winter. |
| Shade and routing | `dist/engine.js` in a Web Worker | For each 15-minute slot after departure the sun position (SunCalc) sweeps every building and crown into a 2 m shade grid. A time-dependent Dijkstra search updates the sun as the walk goes on and takes the better sidewalk on each segment. |
| Site | `dist/` | Plain HTML, CSS and JavaScript with MapLibre; no framework or build step. |

Data processing runs on GitHub Actions: `city-pipeline.yml` builds city data, `city-data.yml` rebuilds the study areas, `thumbnails.yml` makes the city thumbnails, `tests.yml` checks the routing engine, and `stamp-versions.yml` refreshes cache-busting versions after each deploy.

## Run locally

```sh
python -m http.server 8000
# open http://localhost:8000/dist/
```

Engine checks: `node tests/engine.test.cjs`.

To rebuild a city's data, put city slugs (one per line) in `python/pipeline/run.txt` and push, or run the *City shade data* workflow by hand. To run it locally (needs network access and about 4 GB of memory for larger cities):

```sh
pip install -r python/requirements.txt
cd python && python -m pipeline.build_city philadelphia
```

## Data sources

OpenStreetMap contributors (ODbL) · USGS 3D Elevation Program · NOAA Office for Coastal Management · US Census Bureau cartographic boundaries · NYC Department of City Planning · Los Angeles County eGIS · City and County of San Francisco · City of Seattle · City of Atlanta · City of Detroit · City of Philadelphia · Esri basemaps and imagery · Photon geocoder (komoot).

## Limits

Shade comes from mapped buildings and trees only, for a clear sky. Tree crowns come from the LiDAR survey year (2014–2022 depending on the city), so new or removed trees are not reflected. Sidewalks are modeled from street centerlines. Seattle and San Francisco hills are not modeled.
