# SG Street Points

A web map of Singapore lamp posts and bus stops, built with QGIS and qgis2web from open data on [data.gov.sg](https://data.gov.sg). A GitHub Action refreshes the data monthly and republishes the map to GitHub Pages.

## Data sources and attribution

Contains information from the datasets below, accessed from [data.gov.sg](https://data.gov.sg), which is made available under the terms of the [Singapore Open Data Licence version 1.0](https://data.gov.sg/open-data-licence).

| Dataset | Agency | Dataset ID |
|---|---|---|
| [LTA Lamp Post](https://data.gov.sg/datasets/d_ca109de3e83efdd9a10bc5f3dda70a98/view) | Land Transport Authority | `d_ca109de3e83efdd9a10bc5f3dda70a98` |
| [SLA Lamp Post](https://data.gov.sg/datasets/d_1ad7921e25264140dc361e193c095c52/view) | Singapore Land Authority | `d_1ad7921e25264140dc361e193c095c52` |
| [LTA Bus Stop](https://data.gov.sg/datasets/d_3f172c6feb3f4f92a2f47d93eed2908a/view) | Land Transport Authority | `d_3f172c6feb3f4f92a2f47d93eed2908a` |

The data is retrieved on a monthly schedule, so the access date is the date of the latest run of the workflow. Point locations in the lamp post datasets are indicative only, as stated by the data owners.

This project modifies the source data: unused attributes are dropped, coordinates are rounded to 8 decimal places, and `lat` and `lon` properties are added to each feature. It is not endorsed by or affiliated with LTA, SLA or the Singapore Government.

## How it works

1. `scripts/fetch_geojson.py` downloads each dataset through the data.gov.sg API and skips the run if nothing has changed.
2. `scripts/inject_latlon.py` writes slimmed GeoJSON with `lat` and `lon` properties to `data/`.
3. `scripts/build_project.py` builds the QGIS project, and `scripts/export_web.py` exports it with qgis2web, both inside the QGIS Docker image.
4. The workflow in `.github/workflows/refresh.yml` runs monthly, or on demand, and deploys the map to GitHub Pages.

Dataset IDs and the properties kept for each layer are set in `config/datasets.json`. An optional `DATA_GOV_SG_API_KEY` repository secret raises the API rate limits.
