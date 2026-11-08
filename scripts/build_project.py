"""Build qgis/sg-streetpoints.qgz from data/*.geojson with PyQGIS (no QGIS GUI).

Run inside a QGIS environment (e.g. the qgis/qgis Docker image):
    QT_QPA_PLATFORM=offscreen python3 scripts/build_project.py
"""
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsGraduatedSymbolRenderer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsRendererRange,
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
    ("lta_lamp_post", "LTA Lamp Post", "#f0a30a", 1.2, ["LAMPPOST_NUM", "UNIQUE_ID", "lat", "lon"], LAMP_SCALE),
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

# lower, upper, size (mm), label: graduated bubbles for the grid counts
DENSITY_CLASSES = [
    (1, 24, 2.5, "1 - 24"),
    (25, 74, 4.0, "25 - 74"),
    (75, 149, 5.5, "75 - 149"),
    (150, 249, 7.5, "150 - 249"),
    (250, 100000, 10.0, "250+"),
]


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
    ranges = []
    for lower, upper, size, label in DENSITY_CLASSES:
        symbol = QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": "240,163,10,170", "outline_color": "#ffffff",
             "outline_width": "0.3", "size": str(size)}
        )
        ranges.append(QgsRendererRange(lower, upper, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer("count", ranges))
    layer.setScaleBasedVisibility(True)
    layer.setMaximumScale(DENSITY_SCALE)  # hidden once zoomed in past this
    layer.setMinimumScale(DENSITY_ZOOMED_OUT_SCALE)


def label_bus_stops(layer):
    settings = QgsPalLayerSettings()
    settings.fieldName = "BUS_STOP_NUM"
    settings.placement = Qgis.LabelPlacement.OverPoint
    fmt = QgsTextFormat()
    fmt.setSize(8)
    settings.setFormat(fmt)
    settings.scaleVisibility = True
    settings.maximumScale = 5000  # only label when zoomed in
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
            label_bus_stops(layer)
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
