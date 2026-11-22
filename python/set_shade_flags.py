"""Mark cities whose shade data exists (dist/data/<slug>.js) in dist/cities/views.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "dist" / "cities" / "views.json"
views = json.loads(path.read_text(encoding="utf-8"))
for slug, city in views.items():
    city["shade"] = (ROOT / "dist" / "data" / f"{slug}.js").exists()
path.write_text(json.dumps(views, separators=(",", ":")), encoding="utf-8")
print({slug: city["shade"] for slug, city in views.items()})
