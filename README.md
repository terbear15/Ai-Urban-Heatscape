# HeatScape

An interactive urban surface heat research prototype for New York City, Philadelphia, and an expanded Los Angeles study region.

## Current status

All temperature and land-cover values are synthetic demonstration data. Grid geometry is real: 500 m UTM cells clipped to mapped land. No machine-learning model has been trained. Model evaluation is pending. The map basemap is real geographic context; Census ACS 2024 boundaries and TIGERweb Areal Hydrography define the land mask. NYC and Philadelphia use city limits; LA uses a custom expanded region of 42 municipalities plus enclosed land gaps. See dist/map-provenance.json for the full definition.

## Features

- City selection and interactive Leaflet map
- Illustrative predicted temperature, observed temperature, residual, and canopy layers
- Clean Esri light-gray and Esri satellite basemap toggle
- Land-only cells, hover tooltips, clickable details, and overlay opacity
- In-map legend and explicit non-live observation status
- City comparison summaries
- CSV export labeled SYNTHETIC_DEMO
- Planned model workflow, evaluation, and data-source documentation

## Run

Serve `dist/` using any static HTTP server, or open `dist/index.html` in a browser. Leaflet is bundled locally. Esri map tiles and Google Fonts require internet access.

## Planned research

Prepare Landsat temperature and reflectance plus national land-cover data. Compare random forest regression with a linear regression baseline using spatially separated testing and held-out cities. Replace demo values with documented observations and evaluated predictions.

Satellite land surface temperature is not air temperature or personal heat exposure. Predictive relationships are not causal intervention estimates.

## Structure

- `dist/index.html`: interface and methods
- `dist/style.css`: responsive visual design
- `dist/app.js`: demo data, maps, interactions, and exports


