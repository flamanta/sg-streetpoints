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
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "qgis" / "sg-streetpoints.qgz"

# Switch point: lamp posts draw at 1:LAMP_SCALE or closer, the grid counts draw when zoomed out.
# qgis2web turns each scale into a web zoom level (utils.scaleToZoom), so these are chosen to land
# on adjacent levels: lamp posts from zoom 14, the grid up to zoom 13, with no overlap.
LAMP_SCALE = 18000
DENSITY_SCALE = 36000
DENSITY_ZOOMED_OUT_SCALE = 500000  # must not be 0: qgis2web reads 0 as zoom 19 and would never show the layer

# name, title, colour, size (mm), popup fields (used by export_web.py), min scale denominator (0 = always)
# Listed top -> bottom as they stack on the map.
LAYERS = [
    ("lta_lamp_post", "LTA Lamp Post", "#f0a30a", 2.0, ["LAMPPOST_NUM", "UNIQUE_ID", "lat", "lon"], LAMP_SCALE),
    ("sla_lamp_post", "SLA Lamp Post", "#d9480f", 1.6, ["LAMPPOST_NUMBER", "STREET_NAME", "lat", "lon"], 50000),
    ("lta_bus_stop", "LTA Bus Stop", "#1c7ed6", 2.4, ["BUS_STOP_NUM", "BUS_ROOF_NUM", "UNIQUE_ID", "lat", "lon"], 0),
    ("lta_lamp_post_density", "LTA Lamp Post (grid counts)", None, None, ["count"], 0),
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


def style_density(layer):
    # One uniform symbol; patch_site.py replaces it on the web map with a bubble sized by
    # count with the number inside. qgis2web's graduated-size styling failed on this layer
    # in CI (IndexError in getSymbolAsStyle), so keep it simple.
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "240,163,10,170", "outline_color": "#ffffff",
         "outline_width": "0.3", "size": "6"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setScaleBasedVisibility(True)
    layer.setMaximumScale(DENSITY_SCALE)  # hidden once zoomed in past this
    layer.setMinimumScale(DENSITY_ZOOMED_OUT_SCALE)
    # No QGIS label: qgis2web draws labels as separate tooltips that lag behind the
    # bubbles while zooming. patch_site.py puts the count inside the marker instead.


def label_layer(layer, field, size, max_scale=0):
    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.placement = Qgis.LabelPlacement.OverPoint
    fmt = QgsTextFormat()
    fmt.setSize(size)
    settings.setFormat(fmt)
    if max_scale:
        settings.scaleVisibility = True
        settings.maximumScale = max_scale  # only label when zoomed in
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


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
        if name == "lta_lamp_post_density":
            style_density(layer)
        else:
            style(layer, colour, size, minscale)
        if name == "lta_bus_stop":
            label_layer(layer, "BUS_STOP_NUM", 8, max_scale=5000)
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
