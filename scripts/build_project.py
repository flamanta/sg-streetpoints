"""Build qgis/sg-streetpoints.qgz from data/*.geojson with PyQGIS (no QGIS GUI).

Run inside a QGIS environment (e.g. the qgis/qgis Docker image):
    QT_QPA_PLATFORM=offscreen python3 scripts/build_project.py
"""
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsMarkerSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "qgis" / "sg-streetpoints.qgz"

# Each point layer has five regional count bubbles for when the map is zoomed out and the individual
# points for when it is zoomed in. qgis2web turns a scale into a web zoom level
# (utils.scaleToZoom), so these are chosen to land on adjacent levels with no overlap.
LAMP_SCALE = 18000  # lamp posts from zoom 14 ...
REGION_SCALE = 36000  # ... the lamp post regions up to zoom 13
BUS_SCALE = 12000  # bus stops from zoom 15 ...
BUS_REGION_SCALE = 20000  # ... the bus stop regions up to zoom 14
REGION_ZOOMED_OUT_SCALE = 500000  # must not be 0: qgis2web reads 0 as zoom 19 and would never show the layer

# One size for all three point layers. qgis2web draws a marker with radius = 2 x this many mm, so
# 2.0 mm is an 8 px circle (plus a 1 px white outline). 8 px is also the size that stays exact when
# the lamp post tiles are scaled past their last level (zoom 16): the tile library rounds each shape's
# radius to whole pixels, so other sizes wobble between zoom 17 and 19. patch_site.py makes the bus
# stop dots match.
MARKER_SIZE_MM = 2.0

# name, title, colour, size (mm), popup fields (used by export_web.py), min scale denominator (0 = always)
# Listed top -> bottom as they stack on the map. The region layers have no colour or size here:
# patch_site.py replaces their symbols on the web map.
LAYERS = [
    ("lta_lamp_post", "LTA Lamp Post", "#f0a30a", MARKER_SIZE_MM, ["LAMPPOST_NUM", "UNIQUE_ID", "lat", "lon"], LAMP_SCALE),
    ("sla_lamp_post", "SLA Lamp Post", "#d9480f", MARKER_SIZE_MM, ["LAMPPOST_NUMBER", "STREET_NAME", "lat", "lon"], 50000),
    ("lta_bus_stop", "LTA Bus Stop", "#1c7ed6", MARKER_SIZE_MM, ["BUS_STOP_NUM", "BUS_ROOF_NUM", "UNIQUE_ID", "lat", "lon"], BUS_SCALE),
    ("lta_lamp_post_regions", "LTA Lamp Post (regions)", None, None, ["name", "count"], REGION_SCALE),
    ("lta_bus_stop_regions", "LTA Bus Stop (regions)", None, None, ["name", "count"], BUS_REGION_SCALE),
]

BASEMAP_TITLE = "OneMap"
# %7B / %7D are the { } of the {z}/{x}/{y} template, as QGIS expects them in an XYZ source
BASEMAP_SOURCE = (
    "type=xyz&url=https://www.onemap.gov.sg/maps/tiles/Default/%7Bz%7D/%7Bx%7D/%7By%7D.png"
    "&zmin=11&zmax=19"
)

def style(layer, colour, size, minscale):
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": colour, "outline_color": "#ffffff",
         "outline_width": "0.2", "size": str(size)}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    if minscale:
        layer.setScaleBasedVisibility(True)
        layer.setMinimumScale(minscale)  # hidden when zoomed out beyond 1:minscale
        layer.setMaximumScale(0)


def style_regions(layer, max_scale):
    # One uniform symbol; patch_site.py replaces it on the web map with a bubble sized by
    # count with the number inside. qgis2web's graduated-size styling failed on this layer
    # in CI (IndexError in getSymbolAsStyle), so keep it simple.
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "240,163,10,170", "outline_color": "#ffffff",
         "outline_width": "0.3", "size": "6"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setScaleBasedVisibility(True)
    layer.setMaximumScale(max_scale)  # hidden once zoomed in past this
    layer.setMinimumScale(REGION_ZOOMED_OUT_SCALE)


def main():
    qgs = QgsApplication([], False)
    qgs.initQgis()

    project = QgsProject.instance()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    project.setFilePathStorage(Qgis.FilePathType.Relative)

    basemap = QgsRasterLayer(BASEMAP_SOURCE, BASEMAP_TITLE, "wms")
    if not basemap.isValid():
        raise SystemExit("basemap failed to load")
    project.addMapLayer(basemap)

    for name, title, colour, size, popup_fields, minscale in reversed(LAYERS):
        layer = QgsVectorLayer(str(ROOT / "data" / f"{name}.geojson"), title, "ogr")
        if not layer.isValid():
            raise SystemExit(f"layer failed to load: {name}")
        if name.endswith("_regions"):
            style_regions(layer, minscale)
        else:
            style(layer, colour, size, minscale)
        project.addMapLayer(layer)

    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(
            QgsRectangle(103.60, 1.20, 104.05, 1.48), QgsCoordinateReferenceSystem("EPSG:4326")
        )
    )

    OUT.parent.mkdir(exist_ok=True)
    if not project.write(str(OUT)):
        raise SystemExit("failed to write project")
    print(f"wrote {OUT}")
    qgs.exitQgis()


if __name__ == "__main__":
    main()
