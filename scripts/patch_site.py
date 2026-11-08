"""Patch the qgis2web output in place for things qgis2web cannot configure.

Usage: patch_site.py [site_dir]

1. Lamp post vector tiles: qgis2web draws them with SVG tiles (one DOM element per
   point, slow) and each point is a few pixels wide, so it is hard to click. Use
   canvas tiles with a click tolerance instead.
2. OneMap basemap: its terms require the OneMap logo and attribution.
"""
import re
import sys
from pathlib import Path

SVG_TILES = "rendererFactory: L.svg.tile,"
CANVAS_TILES = "rendererFactory: L.canvas.tile,\n            tolerance: 12,"

ONEMAP_ATTRIBUTION = (
    '<img src="https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png" '
    'style="height:20px;width:20px;"/>&nbsp;'
    '<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener noreferrer">OneMap</a>'
    "&nbsp;&copy;&nbsp;contributors&nbsp;&#124;&nbsp;"
    '<a href="https://www.sla.gov.sg/" target="_blank" rel="noopener noreferrer">'
    "Singapore Land Authority</a>"
)
# the OneMap tile layer's options object, up to its closing "});"
ONEMAP_LAYER = re.compile(
    r"(L\.tileLayer\('https://www\.onemap\.gov\.sg/[^']*',\s*\{)(.*?)(\}\);)", re.DOTALL
)
ATTRIBUTION_OPTION = re.compile(r"attribution:\s*'[^']*',?")


def patch_onemap(match):
    start, options, end = match.groups()
    new_option = f"attribution: '{ONEMAP_ATTRIBUTION}',"
    if ATTRIBUTION_OPTION.search(options):
        options = ATTRIBUTION_OPTION.sub(lambda _: new_option, options, count=1)
    else:
        options = f"\n            {new_option}{options}"
    return start + options + end


def main():
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    tiles = onemap = 0
    for path in sorted(site.rglob("*.html")):
        text = path.read_text()
        patched = text.replace(SVG_TILES, CANVAS_TILES)
        tiles += text.count(SVG_TILES) + text.count("rendererFactory: L.canvas.tile,")  # re-runs are fine
        patched, n = ONEMAP_LAYER.subn(patch_onemap, patched)
        onemap += n
        if patched != text:
            path.write_text(patched)
    print(f"canvas tile layers patched: {tiles}; OneMap attribution patched: {onemap}")
    # fail loudly rather than ship a map that is slow, unclickable or missing a required credit
    if not tiles:
        sys.exit("no vector tile layer found to patch; did the lamp post tile export run?")
    if not onemap:
        sys.exit("OneMap tile layer not found; cannot add its required attribution")


if __name__ == "__main__":
    main()
