"""Patch the qgis2web output in place for things qgis2web cannot configure.

Usage: patch_site.py [site_dir]

1. Lamp post vector tiles: qgis2web writes add/remove handlers that use a
   `label_layer_<name>` variable, but only defines it when the layer has labels.
   Without it, removing the layer (which the zoom limits do at page load) throws a
   ReferenceError that aborts the rest of the script: no layer list, no labels.
   Define an empty one.
2. OneMap basemap: its terms require the OneMap logo and attribution.
3. Source map comments: browsers with DevTools open request each library's .map file,
   which is not used by the page and often missing (404) or rate limited (429).
"""
import re
import sys
from pathlib import Path

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
# "//# sourceMappingURL=x.map" at the end of a script, "/*# sourceMappingURL=x.map */" in CSS
SOURCE_MAP_COMMENT = re.compile(r"^[ \t]*(?://|/\*)[#@] sourceMappingURL=[^\n]*?(?:\*/)?[ \t]*$", re.MULTILINE)
ATTRIBUTION_OPTION = re.compile(r"attribution:\s*'[^']*',?")
# "var layer_<name> = L.vectorGrid.protobuf(" starts a vector tile layer
TILE_LAYER = re.compile(r"^([ \t]*)var layer_(\w+) = L\.vectorGrid\.protobuf\(", re.MULTILINE)


def patch_onemap(match):
    start, options, end = match.groups()
    new_option = f"attribution: '{ONEMAP_ATTRIBUTION}',"
    if ATTRIBUTION_OPTION.search(options):
        options = ATTRIBUTION_OPTION.sub(lambda _: new_option, options, count=1)
    else:
        options = f"\n            {new_option}{options}"
    return start + options + end


def define_missing_label_layers(text):
    """Return (patched text, tile layers found, label layers defined)."""
    found = defined = 0

    def add(match):
        nonlocal found, defined
        indent, name = match.groups()
        found += 1
        label = f"label_layer_{name}"
        if label not in text or re.search(rf"\bvar {label}\b", text):
            return match.group(0)
        defined += 1
        return f"{indent}var {label} = L.layerGroup();\n{match.group(0)}"

    return TILE_LAYER.sub(add, text), found, defined


def main():
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    tiles = labels = onemap = 0
    for path in sorted(site.rglob("*.html")):
        text = path.read_text()
        patched, found, defined = define_missing_label_layers(text)
        patched, n = ONEMAP_LAYER.subn(patch_onemap, patched)
        tiles, labels, onemap = tiles + found, labels + defined, onemap + n
        if patched != text:
            path.write_text(patched)
    maps = 0
    for path in sorted([*site.rglob("*.js"), *site.rglob("*.css")]):
        text = path.read_text(errors="surrogateescape")
        patched, n = SOURCE_MAP_COMMENT.subn("", text)
        if n:
            path.write_text(patched, errors="surrogateescape")
            maps += n
    print(f"source map comments removed: {maps}")
    print(f"vector tile layers: {tiles}; label layers defined: {labels}; OneMap attribution patched: {onemap}")
    # fail loudly rather than ship a map that is broken or missing a required credit
    if not tiles:
        sys.exit("no vector tile layer found; did the lamp post tile export run?")
    if not onemap:
        sys.exit("OneMap tile layer not found; cannot add its required attribution")


if __name__ == "__main__":
    main()
