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
from PIL import Image, ImageEnhance, ImageFilter, ImageStat

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


def nodata_share(image):
    small = image.resize((100, 100))
    return sum(1 for p in small.getdata() if sum(p) < 30) / 10000


def fill_nodata(image):
    """NAIP has no pixels over open water far from shore (black). Paint those with the
    median colour of the nearby water so the frame stays clean."""
    px = image.load()
    w, h = image.size
    empty = [(x, y) for y in range(h) for x in range(w) if sum(px[x, y]) < 30]
    if not empty:
        return image
    mask = Image.new("L", image.size, 0)
    mp = mask.load()
    for x, y in empty:
        mp[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(3))  # include JPEG fringes at the edge
    mp = mask.load()
    ring = mask.filter(ImageFilter.MaxFilter(25))
    rp = ring.load()
    edge = [px[x, y] for y in range(0, h, 2) for x in range(0, w, 2) if rp[x, y] and not mp[x, y] and sum(px[x, y]) >= 30]
    if not edge:
        return image
    colour = tuple(sorted(c[i] for c in edge)[len(edge) // 2] for i in range(3))
    filled = image.copy()
    filled.paste(colour, mask=mask)
    soft = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(8))
    return Image.composite(filled.filter(ImageFilter.GaussianBlur(6)), image, soft)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    views = json.loads((ROOT / "dist" / "cities" / "views.json").read_text())
    scenes, missing = {}, []
    stamp = time.strftime("%Y%m%d%H%M")
    for slug in views:
        xy = [merc(lon, lat) for lon, lat in land_points(slug)]
        xs, ys = [p[0] for p in xy], [p[1] for p in xy]
        half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 * 1.04
        # The square frame has spare room along the shorter side of the area. Try sliding it
        # to either end and keep the frame with the least missing imagery (open water).
        options = []
        for fx in (0.5, 0.0, 1.0):
            for fy in (0.5, 0.0, 1.0):
                cx = min(xs) + half + (max(xs) - min(xs) - 2 * half) * fx if 2 * half > max(xs) - min(xs) else (min(xs) + max(xs)) / 2
                cy = min(ys) + half + (max(ys) - min(ys) - 2 * half) * fy if 2 * half > max(ys) - min(ys) else (min(ys) + max(ys)) / 2
                options.append((round(cx), round(cy)))
        best = None
        for cx, cy in dict.fromkeys(options):
            image = fetch((cx - half, cy - half, cx + half, cy + half))
            if image is None:
                continue
            gaps = nodata_share(image)
            if best is None or gaps < best[0]:
                best = (gaps, image)
            if gaps < 0.002:
                break
        image = best[1] if best else None
        if image is None or ImageStat.Stat(image).mean[0] < 10:
            print(slug, "no imagery")
            missing.append(slug)
            continue
        image = fill_nodata(image)
        image = ImageEnhance.Contrast(image).enhance(1.05)
        image.save(OUT / f"{slug}.jpg", quality=82, optimize=True, progressive=True)
        scenes[slug] = {"date": stamp}
        print(slug, "ok")
    (OUT / "credits.json").write_text(json.dumps({"source": "USDA NAIP via USGS The National Map", "scenes": scenes}, indent=1))
    if missing:
        raise SystemExit("missing imagery: " + ", ".join(missing))


if __name__ == "__main__":
    main()
