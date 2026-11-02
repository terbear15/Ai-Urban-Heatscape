# HeatScape

An interactive urban surface heat research prototype for New York City, Philadelphia, and Los Angeles.

## Current status

All analysis values and geographic grid cells are synthetic demonstration data. No machine-learning model has been trained. Model evaluation is pending. The map basemap is real geographic context; colored cells are schematic, not city boundaries.

## Features

- City selection and interactive Leaflet map
- Illustrative predicted temperature, observed temperature, residual, and canopy layers
- Clickable cell details and overlay opacity control
- City comparison summaries
- CSV export labeled SYNTHETIC_DEMO
- Planned model workflow, evaluation, and data-source documentation

## Run

Serve `dist/` using any static HTTP server, or open `dist/index.html` in a browser. Leaflet, CARTO basemap tiles, and Google Fonts require internet access.

## Planned research

Prepare Landsat temperature and reflectance plus national land-cover data. Compare random forest regression with a linear regression baseline using spatially separated testing and held-out cities. Replace demo values with documented observations and evaluated predictions.

Satellite land surface temperature is not air temperature or personal heat exposure. Predictive relationships are not causal intervention estimates.

## Structure

- `dist/index.html`: interface and methods
- `dist/style.css`: responsive visual design
- `dist/app.js`: demo data, maps, interactions, and exports

