"""Patch the qgis2web output in place for things qgis2web cannot configure.

Usage: patch_site.py [site_dir]

1. Lamp post vector tiles: qgis2web writes add/remove handlers that use a
   `label_layer_<name>` variable, but only defines it when the layer has labels.
   Without it, removing the layer (which the zoom limits do at page load) throws a
   ReferenceError that aborts the rest of the script: no layer list, no labels.
   Define an empty one.
2. OneMap basemap: its terms require the OneMap logo and attribution.
3. Regions: qgis2web draws labels as separate tooltips that lag behind their markers
   while zooming and end up in the wrong place. Draw each regional bubble as a marker with
   its name and count inside it, sized by count, so the two move together.
4. Bus stops: same problem for the stop numbers (5,205 tooltips). Draw each stop as a marker
   whose number is part of the marker, and show the numbers only when zoomed in.
5. Layer list: the region bubbles switch on and off with the zoom level and OneMap is the fixed
   background, so neither should be a checkbox or radio button in the list.
6. Tile clicks and startup: a click on a vector-tile point threw a TypeError inside Leaflet (it
   treats a small shape with getLatLng() as a marker, but tile shapes have no lat/lng), so no
   popup ever opened. Remove getLatLng from the tile shapes. Also stop adding the tile layer to
   the map at load: at the start zoom it fetched about 1,200 tiles before the zoom limits
   removed it again, which tripped GitHub's rate limit (429).
   Also fix the marker size past the last tile level: when the tiles are scaled up (zoom 17 and 18)
   the library meant to shrink each circle's radius to compensate, but it sets an `r` attribute that
   a <path> ignores, so circles came out 2x and 4x too big. Rewrite the path's radius instead.
7. Title link: make the map title a link to the GitHub repository. qgis2web also uses the project
   title as the page's <title>, so the link cannot be put in the QGIS project.
8. Debug panel: opening the map with ?debug in the address shows what the lamp post tile layer
   is doing (zoom, on the map or not, tile requests by status, shapes drawn, errors), so a
   report from a browser tells us where it fails. Normal visitors never see it.
9. Unused libraries: qgis2web always includes a set of add-on libraries (pattern fills, address
   search, labels, rotated markers, Font Awesome, expression helpers). Drop each one the page's own
   code does not use, along with its file, so the browser makes fewer requests. A library is only
   removed when nothing in the page's code mentions it, so a future qgis2web feature that needs one
   keeps it.
10. Source map comments: browsers with DevTools open request each library's .map file,
   which is not used by the page and often missing (404) or rate limited (429).
"""
import re
import shutil
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
# the region layers' point factory, e.g. "return L.circleMarker(latlng, style_<name>_0(feature));"
REGION_POINT = re.compile(r"return L\.circleMarker\(latlng, style_(\w*regions\w*)_0\(feature\)\);")
REGION_MARKER = """return L.marker(latlng, {
                    pane: 'pane___NAME__',
                    keyboard: false,
                    icon: (function () {
                        var n = feature.properties['count'];
                        var d = Math.round(52 + 8 * Math.log10(Math.max(n, 1)));
                        return L.divIcon({
                            className: 'region-count',
                            iconSize: [d, d],
                            popupAnchor: [0, -d / 2],
                            html: '<div style="width:' + d + 'px;height:' + d + 'px;box-sizing:border-box;border:2px solid #fff;border-radius:50%;background:__BACKGROUND__;color:__TEXT__;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;font:600 10px/1.2 sans-serif;"><span>' + feature.properties['name'] + '</span><span style="font-size:13px;">' + n.toLocaleString() + '</span></div>'
                        });
                    })()
                });"""
# bubble colours: (background, text) for the bus stop region bubbles, and for the lamp posts
REGION_COLOURS = {"BusStop": ("rgba(28,126,214,0.8)", "#fff")}
REGION_COLOURS_DEFAULT = ("rgba(240,163,10,0.75)", "#000")

REPO_URL = "https://github.com/flamanta/sg-streetpoints"
# qgis2web writes the title as: title.update = function () { this._div.innerHTML = '<h2>TEXT</h2>'; };
TITLE_HEADING = re.compile(r"(title\.update = function \(\) \{\s*this\._div\.innerHTML = ')<h2>(.*?)</h2>(';)", re.DOTALL)


def link_title(match):
    start, text, end = match.groups()
    if "<a " in text:  # already linked: re-runs are fine
        return match.group(0)
    return f'{start}<h2><a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">{text}</a></h2>{end}'


# layer list entries to drop: the "(regions)" layers and the OneMap basemap
LIST_REGIONS = re.compile(r"\s*\{label: '[^']*\(regions\)', layer: \w+\},?")
LIST_ONEMAP = re.compile(r"\s*\{label: \"OneMap\"[^}]*\},?")

# Libraries qgis2web includes whether or not the map uses them. Each entry: the files that go together,
# and a pattern for code that would use them. A library is removed only if that pattern finds nothing
# in the page's inline code.
OPTIONAL_LIBRARIES = {
    "rotated markers": (["js/leaflet.rotatedMarker.js"], r"rotationAngle|rotationOrigin|rotatedMarker"),
    "pattern fills": (["js/leaflet.pattern.js"], r"Pattern"),
    "labels": (["js/rbush.min.js", "js/labelgun.min.js", "js/labels.js"], r"labelgun|rbush|resetLabels|addLabel\(|totalMarkers|labels\.push"),
    "address search": (["js/leaflet.photon.js", "css/leaflet.photon.css"], r"[Pp]hoton|addressSearch|search-button"),
    "expression helpers": (["js/qgis2web_expressions.js"], r"\bfnc_\w+\(|\bcompile_"),
    "Font Awesome": (["css/fontawesome-all.min.css"], r"\bfas?\b|\bfa[brs]\b|\bfa-"),
}
SCRIPT_TAG = r"[ \t]*<script src=\"{}\"></script>[ \t]*\n?"
STYLE_TAG = r"[ \t]*<link rel=\"stylesheet\" href=\"{}\">[ \t]*\n?"


def strip_unused_libraries(text):
    """Return (text without the unused library tags, the files that are no longer referenced)."""
    inline = "\n".join(re.findall(r"<script>(.*?)</script>", text, re.DOTALL))
    dropped = []
    for _, (files, uses) in OPTIONAL_LIBRARIES.items():
        if re.search(uses, inline):
            continue
        for f in files:
            tag = (SCRIPT_TAG if f.endswith(".js") else STYLE_TAG).format(re.escape(f))
            text, n = re.subn(tag, "", text)
            if n:
                dropped.append(f)
    return text, dropped


# the individual bus stops' point factory; the region layer is "...BusStopregions_N", so
# requiring "_<digits>" right after "BusStop" matches only the individual stops
STOP_POINT = re.compile(r"return L\.circleMarker\(latlng, style_(LTABusStop_\d+)_0\(feature\)\);")
STOP_MARKER = """return L.marker(latlng, {
                    pane: 'pane___NAME__',
                    keyboard: false,
                    icon: L.divIcon({
                        className: 'bus-stop',
                        iconSize: [9, 9],
                        popupAnchor: [0, -4.5],
                        html: '<span class="bus-stop-dot"></span><span class="bus-stop-label">' + feature.properties['BUS_STOP_NUM'] + '</span>'
                    })
                });"""
SITE_CSS = """<style>
        /* Leaflet positions markers with position:absolute, so do not set position on .bus-stop;
           the label is positioned against the marker itself. */
        .bus-stop-dot { display: block; width: 9px; height: 9px; box-sizing: border-box; border: 1px solid #fff; border-radius: 50%; background: rgba(28,126,214,1); }
        .bus-stop-label { display: none; position: absolute; left: 12px; top: -2px; font: 600 11px sans-serif; color: #000; white-space: nowrap; text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff; pointer-events: none; }
        #map.stop-labels .bus-stop-label { display: block; }
        .info h2 a { color: inherit; text-decoration: none; }
        .info h2 a:hover { text-decoration: underline; }
    </style>
    """
# Installed in <head>, before any script runs, so the tile fetches at page load are counted.
DEBUG_SCRIPT = """<script id="lamp-debug">
        (function () {
            if (location.search.indexOf('debug') < 0) return;
            var pbf = {}, errors = [];
            var realFetch = window.fetch;
            window.fetch = function (input) {
                var url = typeof input === 'string' ? input : ((input && input.url) || '');
                var p = realFetch.apply(this, arguments);
                if (url.indexOf('.pbf') > -1) {
                    p.then(function (r) { pbf[r.status] = (pbf[r.status] || 0) + 1; },
                           function (e) { pbf.failed = (pbf.failed || 0) + 1; errors.push('fetch: ' + e); });
                }
                return p;
            };
            window.addEventListener('error', function (e) {
                errors.push((e.message || 'error') + ' @' + String(e.filename || '').split('/').pop() + ':' + e.lineno);
            });
            window.addEventListener('unhandledrejection', function (e) {
                var r = e.reason;
                errors.push('promise: ' + ((r && (r.stack || r.message)) || r));
            });
            function lines() {
                var out = [];
                try {
                    out.push('zoom: ' + map.getZoom() + '  center: ' + map.getCenter().lat.toFixed(4) + ', ' + map.getCenter().lng.toFixed(4));
                    Object.keys(window).filter(function (k) { return /^layer_LTALampPost_\\d+$/.test(k); }).forEach(function (k) {
                        var layer = window[k], pane = map.getPane('pane_' + k.slice(6));
                        var box = pane ? pane.getBoundingClientRect() : null;
                        out.push(k + ' on map: ' + map.hasLayer(layer) + '  tiles: ' + Object.keys(layer._tiles || {}).length +
                                 '  shapes drawn: ' + (pane ? pane.querySelectorAll('path').length : 'no pane') +
                                 '  tile z: ' + layer._tileZoom);
                        out.push('pane z-index: ' + (pane && pane.style.zIndex) + '  size: ' + (box ? Math.round(box.width) + 'x' + Math.round(box.height) : '-'));
                    });
                    out.push('.pbf requests by status: ' + JSON.stringify(pbf));
                    out.push('errors (' + errors.length + '): ' + (errors.slice(-3).join(' | ') || 'none'));
                } catch (e) { out.push('debug panel error: ' + e); }
                return out.join('\\n');
            }
            setInterval(function () {
                var box = document.getElementById('lamp-debug-box');
                if (!box && document.body) {
                    box = document.createElement('pre');
                    box.id = 'lamp-debug-box';
                    box.style.cssText = 'position:fixed;left:8px;bottom:24px;z-index:99999;max-width:92vw;margin:0;padding:6px 8px;background:rgba(255,255,255,.92);border:1px solid #888;font:11px/1.3 monospace;white-space:pre-wrap;pointer-events:none;';
                    document.body.appendChild(box);
                }
                if (box) box.textContent = lines();
            }, 1000);
        })();
    </script>
    """
# stop numbers show from this zoom level
STOP_LABEL_ZOOM = 16
SITE_SCRIPT = """<script>
        (function () {
            var el = document.getElementById('map');
            function update() { el.classList.toggle('stop-labels', map.getZoom() >= %d); }
            map.on('zoomend', update);
            update();
        })();
    </script>
    """ % STOP_LABEL_ZOOM
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


TILE_CLICK_FIX = """// Leaflet treats a small shape that has getLatLng() as a marker and reads its lat/lng when it is
        // clicked. Tile shapes only have a position inside their tile, so that threw a TypeError and no
        // popup opened. Without getLatLng() Leaflet uses the click position instead.
        (function (grid) {
            var create = grid._createLayer;
            grid._createLayer = function () {
                var shape = create.apply(this, arguments);
                shape.getLatLng = undefined;
                return shape;
            };
        })(layer___NAME__);
        """


TILE_SCALE_FIX = """// Past the last tile level the tiles are CSS-scaled, and VectorGrid compensates by setting an `r`
        // attribute, which a <path> ignores: the outline shrank but the circle came out 2x and 4x too big.
        // Rewrite the circle's radius in the path data instead, and keep the outline compensation.
        layer___NAME__._onZoomEnd = function () {
            if (!this._map || this._tileZoom === undefined) { return; }
            var mapZoom = this._map.getZoom();
            var scale = this._tileZoom === mapZoom ? 1 : this._map.getZoomScale(this._tileZoom, mapZoom);
            var pane = this._map.getPane(this.options.pane || 'tilePane');
            if (!pane) { return; }
            var paths = pane.querySelectorAll('path');
            for (var i = 0; i < paths.length; i++) {
                var p = paths[i];
                if (p._leaflet_origWeight !== undefined) { p.setAttribute('stroke-width', p._leaflet_origWeight * scale); }
                if (p._leaflet_origRadius === undefined) { continue; }
                var m = /^M([-\\d.]+),([-\\d.]+)a([\\d.]+),/.exec(p.getAttribute('d') || '');
                if (!m) { continue; }
                var r = p._leaflet_origRadius * scale;
                var cx = parseFloat(m[1]) + parseFloat(m[3]), cy = parseFloat(m[2]);
                p.setAttribute('d', 'M' + (cx - r) + ',' + cy + 'a' + r + ',' + r + ' 0 1,0 ' + (2 * r) + ',0 a' + r + ',' + r + ' 0 1,0 ' + (-2 * r) + ',0 ');
            }
        };
        """


def fix_tile_layers(text):
    """Fix clicks on vector-tile points and do not add the tile layer at load.

    Returns (patched text, number of tile layers handled)."""
    handled = 0
    for name in {m.group(2) for m in TILE_LAYER.finditer(text)}:
        handled += 1
        added = rf"(bounds_group\.addLayer\(layer_{name}\);\n)[ \t]*map\.addLayer\(layer_{name}\);\n"
        # the zoom limits add the layer once the map is zoomed in far enough
        text = re.sub(added, lambda m: m.group(1), text, count=1)
        fixes = ""
        if "grid._createLayer = " not in text:
            fixes += TILE_CLICK_FIX.replace("__NAME__", name)
        if f"layer_{name}._onZoomEnd = " not in text:
            fixes += TILE_SCALE_FIX.replace("__NAME__", name)
        anchor = re.search(rf"^([ \t]*)bounds_group\.addLayer\(layer_{name}\);", text, re.MULTILINE)
        if fixes and anchor:
            text = text[:anchor.start()] + anchor.group(1) + fixes + text[anchor.start() + len(anchor.group(1)):]
    return text, handled


def region_marker(match):
    name = match.group(1)
    background, text = next((c for key, c in REGION_COLOURS.items() if key in name), REGION_COLOURS_DEFAULT)
    return REGION_MARKER.replace("__NAME__", name).replace("__BACKGROUND__", background).replace("__TEXT__", text)


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
    tiles = labels = onemap = grid = stops = listed = fixed_tiles = title_links = 0
    removed_libs = set()
    for path in sorted(site.rglob("*.html")):
        text = path.read_text()
        patched, found, defined = define_missing_label_layers(text)
        patched, dropped = strip_unused_libraries(patched)
        removed_libs.update(dropped)
        patched, titled = TITLE_HEADING.subn(link_title, patched)
        patched, fixed = fix_tile_layers(patched)
        patched, n = ONEMAP_LAYER.subn(patch_onemap, patched)
        patched, g = REGION_POINT.subn(region_marker, patched)
        g += patched.count("className: 'region-count'") if not g else 0  # already patched: re-runs are fine
        patched, st = STOP_POINT.subn(lambda m: STOP_MARKER.replace("__NAME__", m.group(1)), patched)
        st += patched.count("className: 'bus-stop'") if not st else 0
        if st and "bus-stop-label" not in text:  # first patch of this page: add the CSS and the zoom switch
            patched = patched.replace("</head>", SITE_CSS + "</head>", 1).replace("</body>", SITE_SCRIPT + "</body>", 1)
        if 'id="lamp-debug"' not in patched:
            patched = patched.replace("</head>", DEBUG_SCRIPT + "</head>", 1)
        patched, r1 = LIST_REGIONS.subn("", patched)
        patched, r2 = LIST_ONEMAP.subn("", patched)
        listed += r1 + r2
        fixed_tiles += fixed
        title_links += titled
        tiles, labels, onemap, grid, stops = tiles + found, labels + defined, onemap + n, grid + g, stops + st
        if patched != text:
            path.write_text(patched)
    for name in removed_libs:
        (site / name).unlink(missing_ok=True)
    if "css/fontawesome-all.min.css" in removed_libs:
        shutil.rmtree(site / "webfonts", ignore_errors=True)  # only that stylesheet refers to them
    print(f"unused library files removed: {len(removed_libs)}")
    maps = 0
    for path in sorted([*site.rglob("*.js"), *site.rglob("*.css")]):
        text = path.read_text(errors="surrogateescape")
        patched, n = SOURCE_MAP_COMMENT.subn("", text)
        if n:
            path.write_text(patched, errors="surrogateescape")
            maps += n
    print(f"source map comments removed: {maps}")
    print(f"vector tile layers: {tiles}; label layers defined: {labels}; OneMap attribution patched: {onemap}; region markers: {grid}; bus stop markers: {stops}; layer list entries removed: {listed}; tile layers click-fixed: {fixed_tiles}; title links: {title_links}")
    # fail loudly rather than ship a map that is broken or missing a required credit
    if not tiles:
        sys.exit("no vector tile layer found; did the lamp post tile export run?")
    # the map still works without the numbers, so warn rather than fail
    if not grid:
        print("::warning::region layers not found; the bubbles will have no names or numbers")
    if not stops:
        print("::warning::bus stop layer not found; the stops will have no numbers")
    if not title_links:
        print("::warning::map title not found; it will not link to the repository")
    if not onemap:
        sys.exit("OneMap tile layer not found; cannot add its required attribution")


if __name__ == "__main__":
    main()
