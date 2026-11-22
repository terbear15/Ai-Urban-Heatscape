"""Stamp local CSS/JS references in dist/*.html with the current commit, so browsers
fetch fresh files after every deploy (run by .github/workflows/stamp-versions.yml)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout.strip()
LOCAL = re.compile(r'((?:src|href)=")((?!https?:|//)[^"?#]+\.(?:js|css))(?:\?[^"]*)?(")')
changed = 0
for page in sorted((ROOT / "dist").glob("*.html")):
    text = page.read_text(encoding="utf-8")
    new = LOCAL.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={version}{m.group(3)}", text)
    new = re.sub(r"const V = '[^']*';", f"const V = 'v={version}';", new)  # shade.html data loader
    if new != text:
        page.write_text(new, encoding="utf-8")
        changed += 1
print(f"stamped {changed} pages with {version}")
