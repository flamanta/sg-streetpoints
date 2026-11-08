"""Install the latest qgis2web plugin compatible with the running QGIS into raw/qgis-plugins.

Run inside a QGIS environment: python3 scripts/install_qgis2web.py
"""
import io
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from qgis.core import Qgis

PLUGIN = "qgis2web"
# fixed location in the workspace, so it does not depend on $HOME or the QGIS profile
PLUGIN_DIR = Path(__file__).resolve().parent.parent / "raw" / "qgis-plugins"
REPO = "https://plugins.qgis.org/plugins/plugins.xml?qgis={}"


def fetch(url):
    # plugins.qgis.org returns 403 to urllib's default user agent
    req = urllib.request.Request(url, headers={"User-Agent": "sg-streetpoints"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main():
    version = ".".join(Qgis.QGIS_VERSION.split(".")[:2])
    root = ET.fromstring(fetch(REPO.format(version)))
    entries = [p for p in root.iter("pyqgis_plugin") if p.get("name") == PLUGIN]
    if not entries:
        sys.exit(f"{PLUGIN} not available for QGIS {version}")
    url = entries[0].findtext("download_url")
    print(f"installing {PLUGIN} {entries[0].get('version')} for QGIS {version}")

    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(fetch(url))).extractall(PLUGIN_DIR)
    print(f"installed to {PLUGIN_DIR / PLUGIN}")


if __name__ == "__main__":
    main()
