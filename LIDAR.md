# HeatScape LiDAR tree shade pilot

[Open the map](https://terbear15.github.io/Ai-Urban-Heatscape/dist/) and select **View Rittenhouse pilot**. The teal polygons are projected tree shadows. Change the time of day to move the shadows. The checkbox also enables pilot tree shade in summer route scoring.

## Inputs and provenance

| Dataset | Use |
|---|---|
| [April 2022 City of Philadelphia LiDAR, NOAA InPort 70168](https://www.fisheries.noaa.gov/inport/item/70168) | Classified point returns delivered as NOAA Entwine Point Tiles (EPT 9848) from the Philadelphia aerial survey originally distributed by PASDA. The EPT data are in NAD83(2011) / UTM zone 18N with NAVD88 heights in meters. |
| [PPR 2015 Tree Canopy Outlines](https://opendataphilly.org/datasets/ppr-tree-canopy/) | Canopy footprint mask from the city's CARTO table ppr_tree_canopy_outlines_2015. The project reads polygon geometry and identifiers. The published average-height field is not used. |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | Existing building footprints screen out roof cells in the LiDAR preprocessing. The OSMnx walking graph supplies routes and street centerlines. |
| [Philadelphia building footprints](https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/LI_BUILDING_FOOTPRINTS/FeatureServer/0) | Building height and footprint inputs for the citywide building-shadow model used alongside tree shade. |

## Processing

1. Run the preparation script using Python with laspy, lazrs, NumPy, requests, rasterio, SciPy, pyproj and Shapely. It selects NOAA EPT nodes intersecting the pilot, through depth 10, and caches the downloaded inputs. Run from the repository root with `python python/prepare_lidar_canopy.py`.
2. On a 2 m raster, assign each cell the minimum class-2 ground elevation. Fill empty cells from the closest ground cell and reject canopy samples whose nearest ground cell is more than 12 m away.
3. Within the 2015 crown mask and outside the building mask, take first-return elevations minus local ground. Keep relative elevations from 2 to 45 m and require at least five eligible returns for a crown. Use their 90th percentile as the crown height. The pilot processed 7,980,752 points in the grid, retained 86 of 93 canopy polygons, and estimated heights from 3.82 to 39.47 m.
4. At each selected sun position, Python translates the crown footprint opposite the sun by height divided by the tangent of solar elevation, capped at 350 m. The browser draws the output on the 2D map. The same polygons are used to score candidate routes. Only tree shade outside a building shadow is counted in the tree-only metric.

The pilot uses a flat-ground, opaque crown approximation with one height per crown. Crown outlines and heights come from different survey years. The April 2022 survey was leaf-off; the summer display uses the mapped crown footprint as an approximation for leaf cover. Seasonal foliage, ground slope, and field accuracy have not been validated. Winter routing uses the building model. The route layer combines building estimates and available pilot trees, and outside the pilot there is no tree contribution.

The [processing manifest](dist/location/lidar-summary.json) lists the exact EPT node IDs, query, study bounds, sampling resolution and point counts. The raw LAZ files are cached locally and can be downloaded again by the script.
