"""Clean satellite thumbnails of each downtown from NASA imagery (explore page).

Imagery: NASA Harmonized Landsat and Sentinel-2 (HLS, 30 m), served by NASA GIBS. For
each city the frame is centered on the downtown area (dist/cities/views.json bounds),
at least 3.5 km across. Several recent summer and autumn dates are tried and the scene
with the least missing data and cloud is kept. No outline or labels are drawn. Output:
dist/thumbs/<slug>.jpg (600 px). Run on GitHub Actions; needs requests and Pillow."""
import datetime as dt
import io
import json
import math
import time
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "thumbs"
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
LAYERS = ["HLS_S30_Nadir_BRDF_Adjusted_Reflectance", "HLS_L30_Nadir_BRDF_Adjusted_Reflectance"]
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}
SIZE = 600
FETCH = 300  # 30 m imagery: ~4.5 km at ~15 m per pixel, then resampled


def merc(lon, lat):
    return math.radians(lon) * 6378137, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137


def dates():
    today = dt.date.today()
    for year in (today.year, today.year - 1, today.year - 2):
        for month, day in [(9, 1), (8, 1), (6, 15), (10, 1), (7, 1), (5, 1)]:
            for offset in range(0, 30, 3):
                d = dt.date(year, month, day) + dt.timedelta(days=offset)
                if d < today - dt.timedelta(days=7):
                    yield d.isoformat()


def score(image):
    """Lower is better. Scenes with missing data or cloud are pushed far back; among clear
    scenes the one with the most contrast wins (haze and smoke flatten the image)."""
    small = image.resize((100, 100))
    px = list(small.getdata())
    missing = sum(1 for r, g, b in px if r + g + b < 25) / len(px)
    cloud = sum(1 for r, g, b in px if min(r, g, b) > 185 and max(r, g, b) - min(r, g, b) < 30) / len(px)
    contrast = ImageStat.Stat(small.convert("L")).stddev[0]
    return missing * 20 + cloud * 10 + max(0.0, 60 - contrast) / 60


def fetch(bbox, layer, date):
    params = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer, "STYLES": "",
              "CRS": "EPSG:3857", "BBOX": ",".join(f"{v:.1f}" for v in bbox), "WIDTH": FETCH, "HEIGHT": FETCH,
              "FORMAT": "image/jpeg", "TIME": date}
    try:
        r = requests.get(WMS, params=params, headers=HEADERS, timeout=60)
    except requests.RequestException:
        time.sleep(3)
        return None
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
        return None
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    views = json.loads((ROOT / "dist" / "cities" / "views.json").read_text())
    report = {}
    for slug, city in views.items():
        (w, s), (e, n) = city["bounds"]
        x1, y1 = merc(w, s)
        x2, y2 = merc(e, n)
        k = 1 / math.cos(math.radians((s + n) / 2))  # web-mercator metres per ground metre
        half = max(max(x2 - x1, y2 - y1) / 2 * 1.08, 1750 * k)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        bbox = (cx - half, cy - half, cx + half, cy + half)
        best = None
        tried = 0
        for date in dates():
            for layer in LAYERS:
                image = fetch(bbox, layer, date)
                tried += 1
                time.sleep(0.2)
                if image is None or ImageStat.Stat(image).mean[0] < 8:
                    continue
                q = score(image)
                if best is None or q < best[0]:
                    best = (q, image, date, layer)
            if tried > 160:
                break
        if not best:
            print(slug, "no NASA scene found")
            continue
        q, image, date, layer = best
        image = image.resize((SIZE, SIZE), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=2))
        image = ImageOps.autocontrast(image, cutoff=(1.5, 0.8), preserve_tone=True)
        image = ImageEnhance.Color(image).enhance(0.9)
        image.save(OUT / f"{slug}.jpg", quality=84, optimize=True, progressive=True)
        report[slug] = {"date": date, "layer": layer, "score": round(q, 3)}
        print(slug, date, layer, f"score {q:.3f}")
    (OUT / "credits.json").write_text(json.dumps({"source": "NASA HLS via GIBS", "scenes": report}, indent=1))


if __name__ == "__main__":
    main()
