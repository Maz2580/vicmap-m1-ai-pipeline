# `data/` — input/output for the pipeline

This directory is **intentionally empty in the repo**. All spatial data, VicMap
extracts, and pipeline outputs are excluded by `.gitignore` — adopters supply
their own data per the steps below.

## What goes here

```
data/
├── incoming/      # Raw .zip downloaded from the VicMap S3 delivery email
├── extract/       # Unzipped VicMap shapefiles (.shp, .shx, .dbf, .prj, .cpg)
├── processed/     # FME-processed output (M1 candidates)
└── rates/         # Optional: TechnologyOne InfoProd rates export
```

## How to obtain a VicMap extract for your LGA

1. Visit https://datashare.maps.vic.gov.au/ (Datashare).
2. Order the **Vicmap Property** and **Vicmap Address** datasets, filtered to
   your LGA polygon. (You'll need a Datashare account — councils get one for
   free as a Victorian data custodian.)
3. Datashare emails you an S3 pre-signed URL when the extract is ready.
4. The pipeline's email monitor (`email_monitor.py`) picks up that email, or
   you can paste the URL directly into `download_url.json`
   (see `download_url.example.json` for the schema).
5. The Download phase (`download_extract.py`) fetches and unzips the data into
   `data/incoming/` and `data/extract/`.

## Privacy

Do not commit any file under `data/` to git. The `.gitignore` is configured to
block `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`, `.geojson`, `.gpkg`, and any
`.zip` in `data/incoming/`. If you find yourself wanting to commit a sample
extract, generate a synthetic version instead — see `tests/fixtures/sample_m1.csv`.
