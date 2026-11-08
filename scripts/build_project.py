"""Build qgis/sg-streetpoints.qgz from data/*.geojson with PyQGIS (no QGIS GUI).

Run inside a QGIS environment (e.g. the qgis/qgis Docker image):
    QT_QPA_PLATFORM=offscreen python3 scripts/build_project.py
"""
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "qgis" / "sg-streetpoints.qgz"

# name, title, colour, size (mm), popup fields (used by export_web.py), min scale denominator (0 = always)
LAYERS = [
    ("lta_lamp_post", "LTA Lamp Post", "#f0a30a", 1.2, ["LAMPPOST_NUM", "UNIQUE_ID", "lat", "lon"], 50000),
    ("sla_lamp_post", "SLA Lamp Post", "#d9480f", 1.6, ["LAMPPOST_NUMBER", "STREET_NAME", "lat", "lon"], 50000),
    ("lta_bus_stop", "LTA Bus Stop", "#1c7ed6", 2.4, ["BUS_STOP_NUM", "BUS_ROOF_NUM", "UNIQUE_ID", "lat", "lon"], 0),
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


def label_bus_stops(layer):
    settings = QgsPalLayerSettings()
    settings.fieldName = "BUS_STOP_NUM"
    settings.placement = QgsPalLayerSettings.OverPoint
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
    project.setFilePathStorage(project.FilePathType.Relative)

    for name, title, colour, size, popup_fields, minscale in reversed(LAYERS):
        layer = QgsVectorLayer(str(ROOT / "data" / f"{name}.geojson"), title, "ogr")
        if not layer.isValid():
            raise SystemExit(f"layer failed to load: {name}")
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
