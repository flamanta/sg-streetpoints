"""Bin the point layers into coarse grids and write data/<name>_density.geojson.

The web map shows these cell counts when zoomed out (like clusters) and swaps to the
individual points when zoomed in.

Usage: make_density.py [--data-dir data]
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

# layer name, cell size in degrees
GRIDS = [
    ("lta_lamp_post", 0.02),  # about 2.2 km: 160 bubbles, so the zoomed-out map stays fast
    ("lta_bus_stop", 0.015),  # about 1.7 km: 218 bubbles
]


def build(src, out, cell):
    features = json.loads(src.read_text())["features"]
    if not features:
        sys.exit(f"{src}: no points to bin")
    counts = Counter()
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        counts[(math.floor(lon / cell), math.floor(lat / cell))] += 1

    out.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"count": n},
                "geometry": {
                    "type": "Point",
                    "coordinates": [round((i + 0.5) * cell, 6), round((j + 0.5) * cell, 6)],
                },
            }
            for (i, j), n in sorted(counts.items())
        ],
    }, separators=(",", ":")) + "\n")
    print(f"{out.name}: {len(counts):,} cells, {sum(counts.values()):,} points, max {max(counts.values())} per cell")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    data = Path(ap.parse_args().data_dir)
    for name, cell in GRIDS:
        build(data / f"{name}.geojson", data / f"{name}_density.geojson", cell)


if __name__ == "__main__":
    main()
