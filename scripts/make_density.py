"""Bin the LTA lamp posts into a coarse grid and write data/lta_lamp_post_density.geojson.

The web map shows these cell counts when zoomed out (like clusters) and swaps to the
individual lamp posts when zoomed in.

Usage: make_density.py [--src data/lta_lamp_post.geojson] [--out data/lta_lamp_post_density.geojson]
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

CELL = 0.02  # degrees, about 2.2 km: 160 bubbles, so the zoomed-out map stays fast


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/lta_lamp_post.geojson")
    ap.add_argument("--out", default="data/lta_lamp_post_density.geojson")
    args = ap.parse_args()

    features = json.loads(Path(args.src).read_text())["features"]
    if not features:
        sys.exit("no lamp posts to bin")
    counts = Counter()
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        counts[(math.floor(lon / CELL), math.floor(lat / CELL))] += 1

    out = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"count": n},
                "geometry": {
                    "type": "Point",
                    "coordinates": [round((i + 0.5) * CELL, 6), round((j + 0.5) * CELL, 6)],
                },
            }
            for (i, j), n in sorted(counts.items())
        ],
    }
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"{len(out['features']):,} cells, {sum(counts.values()):,} lamp posts, max {max(counts.values())} per cell")


if __name__ == "__main__":
    main()
