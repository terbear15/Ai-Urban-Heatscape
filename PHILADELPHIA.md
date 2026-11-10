# HeatScape — Philadelphia first version

The main page now demonstrates building-shadow-aware route exploration in a bounded Center City extract. The former synthetic heat grid is preserved at `dist/legacy.html`.

## Run

Serve `dist` with any static HTTP server. For example, `python -m http.server 8766 --directory dist`. No API key, database, paid routing service or build step is required. Background Esri tiles and Google Fonts require internet; analysis data and JS libraries are local.

## Data and provenance

- Source: https://api.openstreetmap.org/api/0.6/map?bbox=-75.176,39.946,-75.158,39.957
- Retrieved November 10, 2026. © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright
- 2,649 closed-way building footprints; 5,588 street/path segments; 4,196 nodes in the largest connected routing component.
- Building height uses a parseable metric OSM height, otherwise floor count multiplied by 3 m, otherwise a 12 m (39 ft) assumption. 974 buildings have assumed heights. Relation/multipolygon buildings are omitted.
- Run `prepare-philly.py` after downloading the extract to `osm-philly.xml` to regenerate `dist/philly-data.js`. Raw XML is excluded from Git; the derived data is included under ODbL.
- MapLibre GL JS 5.6.2 (BSD-3-Clause) renders the map. SunCalc 1.9.0 (BSD-2-Clause) computes solar position. Both are vendored, with licenses in `dist/vendor`.

## Model

Flat-ground shadow polygons combine building footprints with projected wall quads. A 50 m spatial index accelerates point-in-polygon sampling approximately every 10 m along each network edge. Displayed shadow geometry and route scores share this computation. Summer dates use Eastern daylight time (UTC−4). The selected time is held constant for the entire trip.

Dijkstra finds shortest distance. Seven weighted-distance searches (penalties 0.5, 1, 2, 4, 8, 16, 40) find candidate alternatives. The least-exposed candidate inside the additional-time allowance is selected. This is a heuristic candidate search, not a globally optimal constrained route solver. Walking speed is assumed to be 3 mph. Endpoints snap to the nearest node in the largest connected component; snap distances are shown and excluded from trip metrics. Points more than 150 m away are rejected.

## Limitations

This version has no trained AI model, no tree canopy, no current weather, no verified cooling destinations and no turn-by-turn navigation. Road centerlines are not verified sidewalks. Foot access, crossings, stairs, topology, map age, building heights and entrances require validation. Bridges/tunnels and terrain are not represented in the shadow model. OSM ways are treated as bidirectional walking links after basic access filtering; this is not a comprehensive pedestrian routing ruleset. It cannot establish thermal comfort or safety. The imagery-segmentation experiment remains future work.

## Verification

`node check-engine.cjs` checks connectivity, detour limits, exposure bounds, same-point and out-of-area rejection, changing solar time, and a synthetic directional-shadow case. Browser checks covered 2D/3D, destination changes, time changes, zero detour and the methods dialog. No field accuracy has been measured.
