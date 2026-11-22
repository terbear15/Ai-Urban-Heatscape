"""Aerial thumbnails of each city's mapped area (explore page).

Imagery: USDA National Agriculture Imagery Program (NAIP), about 0.6 m per pixel,
public domain, served by the USGS National Map. The frame is the square around the
city's own area (the land polygon in dist/cities/<slug>.geojson) with a small margin,
so the picture shows exactly what the map covers; no outline is drawn. Output:
dist/thumbs/<slug>.jpg (800 px). Run on GitHub Actions; needs requests and Pillow."""
import io
import json
import math
import time
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "thumbs"
NAIP = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}
SIZE = 800


def merc(lon, lat):
    return math.radians(lon) * 6378137, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137


def land_points(slug):
    g = json.loads((ROOT / "dist" / "cities" / f"{slug}.geojson").read_text())
    land = next(f["geometry"] for f in g["features"] if f["properties"].get("layer") == "land")
    polys = [land["coordinates"]] if land["type"] == "Polygon" else land["coordinates"]
    return [p for poly in polys for p in poly[0]]


def fetch(bbox):
    params = {"bbox": ",".join(f"{v:.1f}" for v in bbox), "bboxSR": 3857, "imageSR": 3857,
              "size": f"{SIZE},{SIZE}", "format": "jpg", "f": "image"}
    for attempt in range(5):
        try:
            r = requests.get(NAIP, params=params, headers=HEADERS, timeout=120)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            print("  status", r.status_code, r.text[:120])
        except requests.RequestException as error:
            print("  retry", error)
        time.sleep(5 * (attempt + 1))
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    views = json.loads((ROOT / "dist" / "cities" / "views.json").read_text())
    scenes, missing = {}, []
    stamp = time.strftime("%Y%m%d%H%M")
    for slug in views:
        xy = [merc(lon, lat) for lon, lat in land_points(slug)]
        xs, ys = [p[0] for p in xy], [p[1] for p in xy]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 * 1.04
        image = fetch((cx - half, cy - half, cx + half, cy + half))
        if image is None or ImageStat.Stat(image).mean[0] < 10:
            print(slug, "no imagery")
            missing.append(slug)
            continue
        image = ImageEnhance.Contrast(image).enhance(1.05)
        image.save(OUT / f"{slug}.jpg", quality=82, optimize=True, progressive=True)
        scenes[slug] = {"date": stamp}
        print(slug, "ok")
    (OUT / "credits.json").write_text(json.dumps({"source": "USDA NAIP via USGS The National Map", "scenes": scenes}, indent=1))
    if missing:
        raise SystemExit("missing imagery: " + ", ".join(missing))


if __name__ == "__main__":
    main()
