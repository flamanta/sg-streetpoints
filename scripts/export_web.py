"""Export qgis/sg-streetpoints.qgz to a Leaflet web map with qgis2web, headlessly.

Drives qgis2web's LeafletWriter directly (the same call the plugin dialog makes)
with a minimal stand-in for QGIS's `iface`. Run inside a QGIS environment with the
qgis2web plugin installed:
    QT_QPA_PLATFORM=offscreen python3 scripts/export_web.py [out_dir]
"""
import os
import shutil
import sys
import threading
import time
import traceback
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


def rss_mb():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) // 1024
    return -1


def watch(interval=10):
    """Print memory use and where the main thread is, so a killed job shows where it died."""
    main = threading.main_thread().ident

    def run():
        while True:
            time.sleep(interval)
            frame = sys._current_frames().get(main)
            where = " <- ".join(
                f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}"
                for f in reversed(traceback.extract_stack(frame)[-3:])
            ) if frame else "?"
            print(f"[watch] rss={rss_mb()} MB at {where}", flush=True)

    threading.Thread(target=run, daemon=True).start()


class Iface:
    """The bits of QgisInterface that qgis2web's writers use."""

    def __init__(self, canvas):
        self._canvas = canvas

    def mapCanvas(self):
        return self._canvas


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "site").resolve()

    for path in ("/sys/fs/cgroup/memory.max", "/proc/meminfo"):
        try:
            print(path, open(path).read().splitlines()[0], flush=True)
        except OSError:
            pass
    watch()

    qgs = QgsApplication([], True)
    qgs.initQgis()

    # qgis2web imports QGIS's `processing` module and calls native algorithms,
    # neither of which a standalone script gets for free. Processing.initialize()
    # also registers the native algorithms.
    # install_qgis2web.py puts the plugin itself in raw/qgis-plugins.
    sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python" / "plugins"))
    sys.path.insert(0, str(ROOT / "raw" / "qgis-plugins"))
    from processing.core.Processing import Processing

    Processing.initialize()
    from qgis.gui import QgsMapCanvas
    from build_project import BASEMAP_TITLE, LAYERS
    from qgis2web.configparams import getDefaultParams
    from qgis2web.feedbackDialog import Feedback
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
    # The lamp post tiles stop at zoom 16 and the tile library rounds each shape's radius to whole
    # pixels when scaling them, so past zoom 18 the markers double in size. Stop zooming at 18.
    params["Scale/Zoom"]["Max zoom level"] = "18"
    project.setTitle("Singapore street points")
    # qgis2web shows the project abstract as a box under the title; it is inserted as raw HTML
    metadata = project.metadata()
    metadata.setAbstract(
        'by <a href="https://github.com/flamanta" target="_blank" rel="noopener noreferrer">@flamanta</a>'
    )
    project.setMetadata(metadata)
    params["Appearance"]["Abstract"] = "upper right"
    writer.params = params
    writer.layers = layers  # qgis2web expects bottom -> top
    writer.groups = {}
    writer.popup = popup
    writer.visible = [True] * n
    writer.interactive = [True] * n
    writer.json = [True] * n
    # The 126k LTA lamp posts are served as vector tiles (only the tiles in view
    # load). The zoomed-out overview is the small regions layer, so no marker
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
    class LoggingFeedback(Feedback):  # qgis2web's default feedback is silent
        def showFeedback(self, feedback):
            print(f"[qgis2web] rss={rss_mb()} MB {feedback}", flush=True)

    result = writer.write(Iface(canvas), str(tmp), LoggingFeedback())

    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(Path(result.folder), out_dir)
    print(f"exported {result.index_file} -> {out_dir}")
    qgs.exitQgis()


if __name__ == "__main__":
    main()
