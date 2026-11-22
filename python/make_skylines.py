"""Downtown skyline photos for the explore page.

For each city, search Wikimedia Commons for a freely licensed skyline photograph (CC BY,
CC BY-SA, CC0 or public domain; landscape, at least 1600 px wide), crop it to a square
around the middle, soften the colour a little so the grid reads calmly, and save
dist/thumbs/<slug>.jpg. Credits (author, licence, source page) go to
dist/thumbs/credits.json and are shown on the page. A file can be pinned per city in
PINNED when the automatic pick is poor. Run on GitHub Actions; needs requests and Pillow."""
import io
import json
import re
import time
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "thumbs"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "HeatScape course project (github.com/terbear15/Ai-Urban-Heatscape)"}
SIZE = 600
FREE = re.compile(r"^(cc[- ]by(-sa)?[- ]?\d|cc0|public domain|pd)", re.I)
BAD = re.compile(r"lights|dusk|evening|car|nissan|gt-r|illustration|render|collage|montage|night|sunset|panorama|aerial|map|logo|drawing|1[89]\d\d|20[01]\d|fog|snow|fireworks", re.I)

QUERIES = {
    "new-york": "Lower Manhattan skyline", "los-angeles": "Downtown Los Angeles skyline",
    "chicago": "Chicago Loop skyline", "san-francisco": "San Francisco skyline from Treasure Island",
    "dallas": "Dallas skyline Trinity River", "houston": "Downtown Houston skyline",
    "washington": "National Mall from Washington Monument", "boston": "Boston skyline Charles River", "atlanta": "Downtown Atlanta skyline",
    "seattle": "Seattle skyline Kerry Park", "philadelphia": "Philadelphia Center City skyline",
    "miami": "Downtown Miami skyline", "san-jose": "Downtown San Jose",
    "phoenix": "Phoenix Arizona downtown skyline daytime", "minneapolis": "Downtown Minneapolis skyline",
    "detroit": "Detroit skyline Detroit River", "san-diego": "San Diego skyline Coronado",
    "denver": "Downtown Denver skyline", "charlotte": "Uptown Charlotte skyline",
    "baltimore": "Baltimore Inner Harbor skyline",
}
PINNED = {}


def api(params):
    for attempt in range(6):
        r = requests.get(API, params=params, headers=HEADERS, timeout=60)
        time.sleep(1.5)
        try:
            return r.json()
        except ValueError:
            print("  throttled, waiting", r.status_code)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Wikimedia Commons did not answer")


def candidates(query):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo", "iiprop": "url|size|extmetadata",
              "iiurlwidth": 1200}
    pages = api(params).get("query", {}).get("pages", {})
    return sorted(pages.values(), key=lambda p: p.get("index", 99))


def pinned(title):
    params = {"action": "query", "format": "json", "titles": title, "prop": "imageinfo",
              "iiprop": "url|size|extmetadata", "iiurlwidth": 1200}
    return list(api(params)["query"]["pages"].values())


def clean(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def daylight(url):
    """Download a small preview; refuse dark (night or dusk) and washed-out pictures."""
    small = url.replace("/1200px-", "/400px-")
    raw = requests.get(small, headers=HEADERS, timeout=60).content
    time.sleep(1.0)
    image = Image.open(io.BytesIO(raw)).convert("L")
    stat = ImageStat.Stat(image)
    return 85 <= stat.mean[0] <= 200 and stat.stddev[0] >= 35


def choose(pages):
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licence = clean(meta.get("LicenseShortName", {}).get("value"))
        w, h = info.get("width", 0), info.get("height", 0)
        if not FREE.match(licence) or w < 1600 or not (1.25 <= w / max(h, 1) <= 2.4) or BAD.search(page["title"].lower()):
            continue
        try:
            if not daylight(info["thumburl"]):
                continue
        except Exception:  # noqa: BLE001 - a broken preview just skips the candidate
            continue
        return page, info, licence, clean(meta.get("Artist", {}).get("value"))[:80]
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    credits = {}
    for slug, query in QUERIES.items():
        pages = pinned(PINNED[slug]) if slug in PINNED else candidates(query)
        pick = choose(pages)
        if not pick:
            print(slug, "no free skyline photo found")
            continue
        page, info, licence, artist = pick
        raw = requests.get(info["thumburl"], headers=HEADERS, timeout=60).content
        time.sleep(1.5)
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        w, h = image.size
        side = min(w, h)
        left = (w - side) // 2
        image = image.crop((left, 0, left + side, side)).resize((SIZE, SIZE), Image.LANCZOS)
        image = ImageEnhance.Color(image).enhance(0.72)
        image.save(OUT / f"{slug}.jpg", quality=80, optimize=True, progressive=True)
        credits[slug] = {"title": page["title"].removeprefix("File:"), "artist": artist or "Unknown",
                         "license": licence, "url": info.get("descriptionurl")}
        print(slug, page["title"], licence, artist)
    (OUT / "credits.json").write_text(json.dumps(credits, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
