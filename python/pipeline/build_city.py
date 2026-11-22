"""Build one city's HeatScape data.

    cd python && python -m pipeline.build_city boston

Steps: OSM download -> OSMnx walking network -> buildings -> LiDAR (building heights,
tree crowns) -> random-forest heights for the rest -> places. Writes
dist/data/<slug>.js, dist/data/<slug>-places.js and dist/data/<slug>-report.json.
"""
import json
import sys
import time
import traceback
from collections import Counter
from datetime import date

from shapely.geometry import mapping

from . import buildings as building_step
from . import heights_ml, lidar, network, osm, places
from .common import DATA, log, reach, rounded, views, write_js

METHOD_TREES = ("Tree crowns and heights come from airborne LiDAR. Python grids the points at 2 m: the lowest "
                "ground return gives bare earth, the highest other return gives the canopy height model (CHM). "
                "Cells 2.5-45 m tall outside building footprints (vegetation classes where the survey has them) are "
                "split into crowns within 30 m tiles and outlined with rasterio; each crown's height is its "
                "90th-percentile CHM value.")


def main(slug):
    started = time.time()
    city = views()[slug]
    area, reach_ll, local = reach(slug)
    log(f"== {city['name']}: {len(city['zones'])} zone(s)")

    nodes, ways, relations = osm.fetch(reach_ll)
    edges, names, network_summary = network.build(slug, nodes, ways, reach_ll)
    footprints = building_step.extract(nodes, ways, relations, reach_ll)
    log(f"  {len(footprints):,} building footprints")

    trees, lidar_summary = [], []
    try:
        measured, trees, lidar_summary = lidar.survey(slug, reach_ll, footprints)
        for b in footprints:
            # Priority: an OSM height tag, then LiDAR, then OSM floor count, then the model.
            if b["source"] != "osm" and b["id"] in measured:
                b["height"], b["source"] = measured[b["id"]], "lidar"
    except Exception:  # keep going without LiDAR; the report says so
        log("  LiDAR step failed:\n" + traceback.format_exc())
        lidar_summary = [{"error": traceback.format_exc().splitlines()[-1]}]
    model_summary = heights_ml.fill(footprints, local)
    sources = Counter(b["source"] for b in footprints)
    search, pause = places.collect(nodes, ways, reach_ll, edges, names)

    west, south, east, north = reach_ll.bounds
    lidar_url = next((s.get("source") for s in lidar_summary if s.get("source")), None)
    years = sorted({s.get("survey_year") for s in lidar_summary if s.get("survey_year")})
    data = {
        "compact": True,
        "buildings": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"height": round(max(3.0, min(300.0, b["height"])), 1)},
             "geometry": {"type": "Polygon", "coordinates": [rounded(list(b["polygon"].exterior.coords))]}}
            for b in footprints]},
        "edges": edges,
        "names": names,
        "trees": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"h": t["h"]},
             "geometry": {"type": "MultiPolygon", "coordinates": [[rounded(list(p.exterior.coords))]
                                                                  for p in getattr(t["geometry"], "geoms", [t["geometry"]])
                                                                  if p.geom_type == "Polygon"]}}
            for t in trees]},
        "pois": pause,
        "meta": {
            "city": city["name"], "retrieved": date.today().isoformat(),
            "license": "ODbL, © OpenStreetMap contributors",
            "bounds": [round(west, 6), round(south, 6), round(east, 6), round(north, 6)],
            "area": (f"The study area covers {', '.join(city['zones'])}: downtown and the busiest visitor areas, "
                     f"with streets and buildings included up to 150 m beyond the dashed boundary."),
            "network": network_summary,
            "buildings": len(footprints), "height_sources": dict(sources), "height_model": model_summary,
            "trees": len(trees), "tree_method": METHOD_TREES + (f" Survey year: {', '.join(map(str, years))}." if years else ""),
            "lidar_url": lidar_url, "lidar": lidar_summary,
            "limitations": "Street centerlines with modeled sidewalk sides, not surveyed sidewalks. Terrain is not modeled.",
        },
    }
    if slug == "philadelphia":
        data["meta"]["area"] = ("Center City is the union of eight official neighborhood polygons from OpenDataPhilly: "
                                "Center City East, Chinatown, Fitler Square, Logan Square, Old City, Rittenhouse, "
                                "Society Hill and Washington Square West.")
    write_js(DATA / f"{slug}.js", "CITYDATA", data)
    write_js(DATA / f"{slug}-places.js", "PLACES", search)
    report = {"city": city["name"], "slug": slug, "zones": city["zones"], "area_km2": round(local.to_m(area).area / 1e6, 2),
              "network": network_summary, "buildings": len(footprints), "height_sources": dict(sources),
              "height_model": model_summary, "trees": len(trees), "places": len(search), "pause_places": len(pause),
              "pause_by_kind": dict(Counter(p[1] for p in pause)), "lidar": lidar_summary,
              "data_mb": round((DATA / f"{slug}.js").stat().st_size / 1e6, 2), "minutes": round((time.time() - started) / 60, 1)}
    (DATA / f"{slug}-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(f"== {city['name']} done in {report['minutes']} min: {report['data_mb']} MB, {len(edges):,} segments, "
        f"{len(footprints):,} buildings {dict(sources)}, {len(trees):,} crowns, {len(search):,} places, {len(pause)} pause places")


if __name__ == "__main__":
    main(sys.argv[1])
