"""Export qgis/sg-streetpoints.qgz to a Leaflet web map with qgis2web, headlessly.

Drives qgis2web's LeafletWriter directly (the same call the plugin dialog makes)
with a minimal stand-in for QGIS's `iface`. Run inside a QGIS environment with the
qgis2web plugin installed:
    QT_QPA_PLATFORM=offscreen python3 scripts/export_web.py [out_dir]
"""
import shutil
import sys
from collections import OrderedDict
from pathlib import Path

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsRectangle

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "qgis" / "sg-streetpoints.qgz"
POPUP_SHOWN = "inline label - always visible"
POPUP_HIDDEN = "hidden field"
TILED_LAYER = "LTA Lamp Post"
TILE_MIN_ZOOM, TILE_MAX_ZOOM = 14, 16  # lamp posts only draw from about zoom 15

sys.path.insert(0, str(ROOT / "scripts"))


class Iface:
    """The bits of QgisInterface that qgis2web's writers use."""

    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "site").resolve()

    qgs = QgsApplication([], True)
    qgs.initQgis()

    # qgis2web imports QGIS's `processing` module and calls native algorithms,
    # neither of which a standalone script gets for free.
    # install_qgis2web.py puts the plugin itself in raw/qgis-plugins.
    sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python" / "plugins"))
    sys.path.insert(0, str(ROOT / "raw" / "qgis-plugins"))
    from qgis.analysis import QgsNativeAlgorithms
    from processing.core.Processing import Processing

    Processing.initialize()
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    from qgis.gui import QgsMapCanvas
    from build_project import BASEMAP_TITLE, LAYERS
    from qgis2web.configparams import getDefaultParams
    from qgis2web.leafletWriter import LeafletWriter

    project = QgsProject.instance()
    if not project.read(str(PROJECT)):
        raise SystemExit(f"cannot read {PROJECT}")

    canvas = QgsMapCanvas()
    canvas.resize(1200, 800)
    canvas.setDestinationCrs(project.crs())
    canvas.setExtent(QgsRectangle(103.60, 1.20, 104.05, 1.48))
    canvas.refresh()

    popup_fields = {title: fields for _, title, _, _, fields, _ in LAYERS}
    layers, popup = [], []
    for layer in reversed(project.layerTreeRoot().findLayers()):  # bottom -> top
        layer = layer.layer()
        layers.append(layer)
        if isinstance(layer, QgsRasterLayer):
            popup.append(OrderedDict())  # the basemap has no attributes
            continue
        shown = popup_fields[layer.name()]
        popup.append(OrderedDict(
            (f.name(), POPUP_SHOWN if f.name() in shown else POPUP_HIDDEN)
            for f in layer.fields()
        ))
    n = len(layers)

    writer = LeafletWriter()
    params = getDefaultParams()
    params["Appearance"]["Layers list"] = "Expanded"
    params["Appearance"]["Title"] = "upper right"
    params["Data export"]["Precision"] = "8"
    params["Scale/Zoom"]["Extent"] = "Canvas extent"
    params["Scale/Zoom"]["Min zoom level"] = "11"  # OneMap has no tiles below this
    params["Scale/Zoom"]["Max zoom level"] = "19"
    project.setTitle("Singapore street points")
    writer.params = params
    writer.layers = layers  # qgis2web expects bottom -> top
    writer.groups = {}
    writer.popup = popup
    writer.visible = [True] * n
    writer.interactive = [True] * n
    writer.json = [True] * n
    # The 126k LTA lamp posts are served as vector tiles (only the tiles in view
    # load). The zoomed-out overview is the small grid-count layer, so no marker
    # clustering. Everything else stays plain GeoJSON.
    writer.cluster = [False] * n
    writer.pbfVectorTile = [
        (True, TILE_MIN_ZOOM, TILE_MAX_ZOOM) if layer.name() == TILED_LAYER else (False, None, None)
        for layer in writer.layers
    ]
    writer.getFeatureInfo = [""] * n
    writer.baseMap = [layer.name() == BASEMAP_TITLE for layer in layers]
    writer.collapsedGroup = []

    tmp = ROOT / "raw" / "qgis2web"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    result = writer.write(Iface(canvas), str(tmp))

    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(Path(result.folder), out_dir)
    print(f"exported {result.index_file} -> {out_dir}")
    qgs.exitQgis()


if __name__ == "__main__":
    main()
