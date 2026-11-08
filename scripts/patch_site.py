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
6. Debug panel: opening the map with ?debug in the address shows what the lamp post tile layer
   is doing (zoom, on the map or not, tile requests by status, shapes drawn, errors), so a
   report from a browser tells us where it fails. Normal visitors never see it.
7. Source map comments: browsers with DevTools open request each library's .map file,
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

# layer list entries to drop: the "(regions)" layers and the OneMap basemap
LIST_REGIONS = re.compile(r"\s*\{label: '[^']*\(regions\)', layer: \w+\},?")
LIST_ONEMAP = re.compile(r"\s*\{label: \"OneMap\"[^}]*\},?")

# the individual bus stops' point factory; the region layer is "...BusStopregions_N", so
# requiring "_<digits>" right after "BusStop" matches only the individual stops
STOP_POINT = re.compile(r"return L\.circleMarker\(latlng, style_(LTABusStop_\d+)_0\(feature\)\);")
STOP_MARKER = """return L.marker(latlng, {
                    pane: 'pane___NAME__',
                    keyboard: false,
                    icon: L.divIcon({
                        className: 'bus-stop',
                        iconSize: [12, 12],
                        popupAnchor: [0, -6],
                        html: '<span class="bus-stop-dot"></span><span class="bus-stop-label">' + feature.properties['BUS_STOP_NUM'] + '</span>'
                    })
                });"""
SITE_CSS = """<style>
        /* Leaflet positions markers with position:absolute, so do not set position on .bus-stop;
           the label is positioned against the marker itself. */
        .bus-stop-dot { display: block; width: 12px; height: 12px; box-sizing: border-box; border: 2px solid #fff; border-radius: 50%; background: rgba(28,126,214,1); }
        .bus-stop-label { display: none; position: absolute; left: 15px; top: -1px; font: 600 11px sans-serif; color: #000; white-space: nowrap; text-shadow: -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff; pointer-events: none; }
        #map.stop-labels .bus-stop-label { display: block; }
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
    tiles = labels = onemap = grid = stops = listed = 0
    for path in sorted(site.rglob("*.html")):
        text = path.read_text()
        patched, found, defined = define_missing_label_layers(text)
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
        tiles, labels, onemap, grid, stops = tiles + found, labels + defined, onemap + n, grid + g, stops + st
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
    print(f"vector tile layers: {tiles}; label layers defined: {labels}; OneMap attribution patched: {onemap}; region markers: {grid}; bus stop markers: {stops}; layer list entries removed: {listed}")
    # fail loudly rather than ship a map that is broken or missing a required credit
    if not tiles:
        sys.exit("no vector tile layer found; did the lamp post tile export run?")
    # the map still works without the numbers, so warn rather than fail
    if not grid:
        print("::warning::region layers not found; the bubbles will have no names or numbers")
    if not stops:
        print("::warning::bus stop layer not found; the stops will have no numbers")
    if not onemap:
        sys.exit("OneMap tile layer not found; cannot add its required attribution")


if __name__ == "__main__":
    main()
