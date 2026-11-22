"""Square aerial thumbnails for the explore page (U3).

For every city in dist/cities/views.json: download an Esri World Imagery crop around the
covered area, desaturate it so the grid reads calmly, draw the covered area as a dashed
outline, and save dist/thumbs/<slug>.jpg (480 px, ~40 kB). Run on GitHub Actions; needs
requests and Pillow."""
import io
import json
import math
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[1]
CITIES = ROOT / "dist" / "cities"
OUT = ROOT / "dist" / "thumbs"
EXPORT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
SIZE = 480


def merc(lon, lat):
    x = math.radians(lon) * 6378137
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137
    return x, y


def rings(geojson):
    for feature in geojson.get("features", []):
        if (feature.get("properties") or {}).get("layer") != "land":
            continue
        geom = feature.get("geometry") or {}
        polys = [geom["coordinates"]] if geom.get("type") == "Polygon" else geom.get("coordinates", []) if geom.get("type") == "MultiPolygon" else []
        for poly in polys:
            if poly:
                yield poly[0]


def dashed(draw, points, color, width=3, dash=9, gap=6):
    on, left = True, dash
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        pos = 0.0
        while pos < seg:
            step = min(left, seg - pos)
            if on:
                a, b = pos / seg, (pos + step) / seg
                draw.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a), (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)], fill=color, width=width)
            pos += step
            left -= step
            if left <= 0:
                on = not on
                left = dash if on else gap


def thumb(slug, city):
    (w, s), (e, n) = city["bounds"]
    x1, y1 = merc(w, s)
    x2, y2 = merc(e, n)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) / 2 * 1.12
    bbox = (cx - half, cy - half, cx + half, cy + half)
    params = {"bbox": ",".join(f"{v:.1f}" for v in bbox), "bboxSR": 3857, "imageSR": 3857,
              "size": f"{SIZE},{SIZE}", "format": "jpg", "f": "image"}
    response = requests.get(EXPORT, params=params, timeout=60)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB").resize((SIZE, SIZE))
    # Desaturate to ~25% colour and lift the shadows slightly so text and marks read on top.
    image = ImageEnhance.Color(image).enhance(0.25)
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(0.8)
    # Wash toward the page colour so the grid stays light; black no-data tiles become paper.
    image = Image.blend(image, Image.new("RGB", image.size, (246, 243, 236)), 0.28)
    draw = ImageDraw.Draw(image)
    area = CITIES / f"{slug}.geojson"
    if area.exists():
        for ring in rings(json.loads(area.read_text())):
            pts = []
            for lon, lat in ring:
                mx, my = merc(lon, lat)
                pts.append(((mx - bbox[0]) / (bbox[2] - bbox[0]) * SIZE, (bbox[3] - my) / (bbox[3] - bbox[1]) * SIZE))
            if len(pts) > 2:
                dashed(draw, pts, (255, 255, 255), width=5)
                dashed(draw, pts, (45, 45, 45), width=2)
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / f"{slug}.jpg", quality=78, optimize=True, progressive=True)
    print(slug, (OUT / f"{slug}.jpg").stat().st_size // 1024, "kB")


views = json.loads((CITIES / "views.json").read_text())
for slug, city in views.items():
    thumb(slug, city)
