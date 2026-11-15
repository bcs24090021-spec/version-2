# FireAtlas

A local MODIS / VIIRS fire-analysis website for exploring real NASA FIRMS observations. Built from the supplied harmonization brief using React, Vite, TypeScript, Tailwind, MapLibre GL JS, FastAPI, pandas, DuckDB, and Parquet.

## Run the complete system

```sh
docker compose up --build
```

Open **http://localhost:8000**. API documentation: **http://localhost:8000/docs**.
The bundled dataset works without a key or network connection. The initial view is a true 3D globe with Esri satellite imagery, which requires network access. Switch to Map to use the bundled Natural Earth basemap offline; fonts and observations are also bundled. A WebGL-capable browser is required.

### Run locally without Docker (Windows)

```powershell
git clone https://github.com/bcs24090021-spec/harmonization-MODIS-VIIRS.git
cd harmonization-MODIS-VIIRS
npm.cmd install
npm.cmd run build
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For frontend development: `npm.cmd run dev -- --port 5178`. It uses the bundled observations. The production FastAPI server provides `/data/runtime.json`, enabling the same frontend to load the server's ingested records at `/api/dataset`. Vite proxies `/api`; the full local build is the supported way to see added Parquet observations.

## Navigate the local website

### Historical record from FINAL

Open **Historical record** in the main navigation for the supplied Aqua MODIS → S-NPP VIIRS system. This workspace includes:

- The 216-month burning calendar (2003–2020), month-to-map selection, anomaly and point-FRP views, annual trends, and peak-month selection.
- Malaysia / Peninsular Malaysia / Malaysian Borneo, day/night and year selection, drawn or uploaded Polygon/MultiPolygon areas, and a collapsible sidebar.
- Separate observed Aqua, observed S-NPP and synthetic VIIRS map layers, paired/hole origin filters, CSV/GeoJSON exports preserving synthetic flags, and calendar CSV/PNG exports.
- All seven validation methods, each held-out year, exam/tuning/all-year comparisons, the Indonesia check, model-size comparison, and out-of-sample continuity.
- Five-run simulation statistics, control comparisons, figures, original workbooks, English/Chinese explanations, and a downloadable source archive with the Malaysia inputs.
- A local **Run pipeline** screen: feature building, all-method validation, or the complete workflow; 200/800 trees; optional FIRMS downloads and simulation tuning; progress/logs, cancellation, output downloads, and loading completed full runs into the website.

The default historical data come directly from `FINAL/results` and the cleaned `FINAL/code/data/raw` files. The historical scale is **S-NPP VIIRS-equivalent**. The original explorer keeps its separate **MODIS-equivalent** method. National historical estimates are model expectations; regional/day-night historical totals use synthetic run 1. Synthetic locations are always identified as simulations. January 2012 remains partial and excluded from validation and the anomaly baseline. The delivered Malaysia model does **not** reach the ≤15% monthly-error target.

The packaged record is already included in the frontend. To rebuild it after replacing the supplied data or results:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/build_final_data.py
npm.cmd run build
```

The static site supports exploration, reports and downloads. Running new scientific jobs requires FastAPI. Each job writes to `artifacts/final-jobs/<run-id>` and preserves `FINAL/results`. A completed full run can be loaded with its own point files, calendar and workbooks. Its `environment.json` records the Python/package versions and settings. Different scientific-library versions can produce slightly different fitted results.

For development, Vite proxies `/api` to port 8000 by default. If that port is occupied, run this project's API on another port and put `FIREATLAS_API_URL=http://127.0.0.1:8010` in `.env.local`, then restart Vite. This workspace's current local setup uses API port 8010 and website port 5178.

See [the implementation and verification notes](docs/final-integration.md) for the requirement mapping and checks.

### Original fire explorer

The fire explorer opens as a split workspace: an analysis panel on the left occupies 25% of the desktop width, and the map fills the remaining 75% beside it. Both extend from the main navigation to the bottom of the screen. Click the arrow halfway down the panel's right edge to hide it and expand the map to the full width; click the arrow again at the map's left edge to reopen the panel. Your analysis tab and selections are preserved.

- **Location, dates, and Filters:** use the controls in the top-left of the map. Area opens a cascading continent/country menu with regional presets and GeoJSON upload. Dates opens an Apply/Cancel popover with exact years/months and calendar selection. Filters opens a compact drawer; optional Advanced settings over the map applies the same sensor/platform, grid, native MODIS range, and VIIRS category filters immediately.
- **Activity calendar, Satellite trends, and Area summary:** switch views using the three tabs in the left panel. The calendar opens by default and uses a monthly day grid with month/year controls. Select a date to filter the map; use “Show all dates” or clear the date details to restore the date range. Trends are sized to the sidebar; summary figures are stacked vertically. The panel scrolls independently while the map stays visible.
- **Compare satellites:** inspect the raw and adjusted observations, calibration, and fit quality.
- **Read the comparison chart:** MODIS uses a solid blue line, VIIRS a dashed orange line, and the adjusted record a dotted purple line with diamond markers. Tap the legend to hide/show a line and rescale the graph. Hover or use Inspect month/day for separate numerical readouts. Count/FRP updates the graph, scatter plot and calibration parameters together; the monthly table includes slope, intercept, R², bias and RMSE with explanations and units.
- **Fire insights:** explore unusual days and seasonal patterns. Selecting a day takes you back to the map.
- **Current news:** read eight curated satellite, wildfire, regional haze and research stories, reviewed on 15 November 2026. Use topic filters, search, and publication-date sorting. Each story links to its original NASA, FIRMS, NEA or ASMC report; photographs retain source credits. The roundup is bundled for offline reading and does not refresh automatically. Maintain articles in `frontend/src/news-data.ts` and source image records in `frontend/public/news/image-sources.json`.
- **How it works:** read the method and data limitations in plain language.
- **Data & imports / Import data:** add official observations. **Export:** download CSV, GeoJSON, or a calendar image.

On phones and narrow tablets, the map appears above the analysis panel so both remain readable. The six main navigation links stay at the bottom on phones. Filters open as a drawer. Keyboard users can switch analysis tabs with Up/Down, Home, or End and close the filters with Escape.

## What works

- Responsive, light/dark dashboard; Borneo, Malaysia, Southeast Asia, Amazon, California, and Australia presets.
- Real interactive map, rectangle/polygon drawing, Polygon/MultiPolygon GeoJSON uploads with holes, satellite imagery enabled initially, a real navigable 3D globe, and configurable grid rendering. Exit drawn area restores the previous named AOI without changing other settings.
- Daily burning calendars for count, FRP, and anomaly; mouse tooltips, keyboard navigation, and click-to-map filtering.
- Raw MODIS versus merged VIIRS versus harmonized series with descriptive residual bands, daily/monthly aggregation, and sensor visibility controls.
- Month-specific Theil–Sen count/FRP calibration with AOI fallback; actual R², bias, RMSE, transfer coefficients, and scatter plot.
- Other-year seasonal baselines, unusual days, annual activity comparisons, and threshold-based season start/peak/end.
- Browser CSV imports gated by mandatory scope-specific completeness confirmation, CSV/GeoJSON/PNG downloads, shareable URL state, source provenance, empty/error/loading states, and a full Method page.
- FastAPI endpoints, validated AOIs, bounded date ranges, in-memory query caching, archive/API ingestion, partitioned Parquet, Docker, and tests.

## Real sample dataset

**118,940 original NASA FIRMS observations**, Malaysia, 2019–2023, from 15 annual country archive files:

- MODIS (`modis`)
- VIIRS Suomi NPP (`viirs-snpp`)
- VIIRS NOAA-20 (`viirs-jpss1`)

These are complete official country CSVs, not synthetic data. See `data/provenance.json` for source URLs, record counts, and SHA-256 checksums. Rebuild the bundle with:

```sh
python data/download_sample.py
```

**Coverage limits:** Borneo and Southeast Asia show Malaysian territory only. The sample does not cover Indonesian or Bruneian Borneo, other regions, 2000–2018, or 2024 onward. Uncovered intervals remain null. Selecting a global preset does not manufacture a history for it. Browser CSV imports are session-local; imports default to observed dates only and do not establish zero-activity days elsewhere. Confirm complete export coverage only when you know the export is complete for the displayed AOI and dates.

## Extend with FIRMS data

Copy `.env.example` to `.env` and add your free `FIRMS_MAP_KEY` from https://firms.modaps.eosdis.nasa.gov/api/map_key/ . Never commit `.env` or put the key in browser code.

```powershell
.\.venv\Scripts\python.exe data/ingest.py --year 2023 --source MODIS_SP --bbox "108,-5,120,8"
.\.venv\Scripts\python.exe data/ingest.py --year 2023 --source VIIRS_SNPP_SP --bbox "108,-5,120,8"
.\.venv\Scripts\python.exe data/ingest.py --year 2023 --source VIIRS_NOAA20_SP --bbox "108,-5,120,8"
```

The script checks product availability, downloads at most five days per request, retries safely, caches raw CSVs by source/bbox/date, and writes `data/parquet/year=YYYY/SOURCE.parquet` plus coverage metadata. Rerunning replaces a partition rather than appending duplicates. Run one AOI per product/year; changing the AOI replaces that product/year partition. Restart FastAPI to reload records and clear its cache. The server reads partitions through DuckDB and exposes them to both API users and the browser.

An existing official FIRMS export can be imported without a key:

```powershell
.\.venv\Scripts\python.exe data/ingest.py --year 2023 --source MODIS_SP --bbox "108,-5,120,8" --csv path/to/archive.csv
```

Imported files establish coverage on observed dates only. For a complete, gap-aware time series use API ingestion, whose metadata captures the full queried intervals. Standard-processing and NRT availability differ; the script respects NASA's product date limits. S-NPP ended on 2 November 2026; use supported NOAA products for newer observations.

## API

All analysis endpoints accept `aoi` (preset slug or `west,south,east,north`), `start`, `end`, `sensors=MODIS,VIIRS`, `confidence=30..100`, `grid=0.1|0.25|0.5`, and optional JSON `geometry` (Polygon/MultiPolygon). `/api/calibration` takes `region` instead of `aoi`.

| Endpoint | Output |
| --- | --- |
| `/api/calendar?metric=count` | Daily harmonized count/FRP, sources, residual bands, baseline, percentile, z-score |
| `/api/timeseries` | Daily raw/calibrated/harmonized series and annual summaries |
| `/api/anomalies` | Days above the historical 95th percentile |
| `/api/critical-periods` | Season start, rolling peak, end, ranked by intensity |
| `/api/hotspots?date=2023-07-31` | Accepted observations as GeoJSON |
| `/api/calibration?region=borneo` | Count/FRP global and monthly fit diagnostics |
| `/api/grid` | Per sensor, cell, and day: detection count, unique pixels, FRP |
| `/api/health` | Dataset size and coverage |

First-query analysis includes cleaning and calibration. Repeated identical queries use a bounded 32-entry cache. This is a regional research implementation; global-scale preaggregation, job queues, and spatial indexing should precede production-scale ingestion.

## Science and validation

See `docs/method.md`, `docs/validation.json`, `docs/validation.svg`, and `docs/demo.md`. Run `python scripts/validate_data.py` to regenerate diagnostics, grid Parquet, and the plot. The TypeScript browser and Python API apply the same equations; a browser/API parity check compares the real series.

**Known scientific limits:** active hotspots are not burned area; no detection does not prove no fire. A 0.01° matching lattice is an approximate 1 km comparison and can merge neighboring fires. Max-per-pixel FRP avoids repeat sampling but is not integrated energy. Monthly regression uses in-sample overlap observations; residual shading is not a validated confidence interval. Baselines depend on the selected years. A sensor-transition discontinuity is neither forced away nor claimed to be absent. The bundled years cannot validate the 2012 transition. Full 2000–present coverage requires ingesting those archives. Quantile mapping and independent ground-truth validation are not implemented.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd run build
npm.cmd run dev -- --port 5178
# Keep the local API running on port 8000, then in another terminal:
node scripts/verify.mjs
```

Browser verification uses Playwright. Set `CHROME_PATH` if your browser is installed elsewhere; otherwise install its matching Chromium with `npx.cmd playwright install chromium`. Test artifacts are written to ignored `artifacts/` (screenshots, real exports, accessibility report).

## Structure

```text
data/       Official sample, source provenance, download and ingestion scripts
pipeline/   Scientific cleaning, matching, gridding, calibration, analytics
backend/    FastAPI, Parquet queries, API documentation, local frontend serving
frontend/   React/TypeScript dashboard, local assets and equivalent browser engine
docs/       Method, measured validation, presentation script
tests/      Scientific-function and API tests
scripts/    Browser verification and dataset validation
```

The private Sites deployment is the portable frontend with browser-side analysis and the bundled archive. Python, DuckDB, secrets, and persistent ingestion run in the supplied local/Docker service. The hosted frontend supports session-local CSV imports; it does not claim to host the Python API.

## Full system report

[Read the complete system report](output/reports/FireAtlas_Complete_System_Report.pdf) for feature explanations, usage instructions, methodology, measured results, and limitations.

## Globe and selection checks

```sh
npm run build
npm test
npm run test:selection
# In a separate terminal, start the production preview:
npm run preview -- --port 5174
# Against that preview (PowerShell: set $env:BASE_URL first):
BASE_URL=http://127.0.0.1:5174 npm run test:ui
BASE_URL=http://127.0.0.1:5174 npm run test:interactions
BASE_URL=http://127.0.0.1:5174 npm run test:globe
BASE_URL=http://127.0.0.1:5174 npm run test:popovers
```

Browser checks use Playwright Chromium, or `CHROME_PATH` when set. Linux system Chromium is detected automatically. Shared URLs include exact selected date intervals and the globe camera, but never browser-session datasets or credentials. Country/continent identifiers reconstruct their real boundaries from the bundled Natural Earth atlas; see [geography and coverage notes](docs/geography.md).

Complete country coverage applies to the actual Malaysia country selection. Larger regions show observed data while leaving unobserved spatial coverage missing. Confirmed CSV coverage applies only to its explicit geometry and exact selected dates. Switching to a different geometry conservatively preserves observed days without inferring completeness from bounding boxes.

## Host a test website on GitHub Pages

This repository includes `.github/workflows/pages.yml`, which builds and publishes the static browser app on pushes to `main` or a manual workflow run.

1. Open your repository's **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. Merge the GitHub Pages setup PR into `main`.
4. Open **Actions → Deploy FireAtlas to GitHub Pages** and wait for build/deploy to pass. If the commit is already on main, choose **Run workflow** on `main`.
5. Open the URL shown in the deployment or Pages settings. For this repository it is normally `https://alexislim01.github.io/harmonization-MODIS-VIIRS/`.

The Pages site is public. Bundled NASA observations, globe/map navigation, analysis, CSV imports and exports run in the browser. Python/FastAPI endpoints, scheduled ingestion and server-side storage do not run on Pages. CSV imports remain browser-session data and are not uploaded to GitHub. Satellite tiles require an internet connection.

The workflow derives its base path from the repository name. To test the same repository subpath locally:

```sh
FIREATLAS_BASE_PATH=/harmonization-MODIS-VIIRS/ npm run build
FIREATLAS_BASE_PATH=/harmonization-MODIS-VIIRS/ npm run preview -- --port 5175
```

Then visit `http://127.0.0.1:5175/harmonization-MODIS-VIIRS/`. Normal local and FastAPI builds omit `FIREATLAS_BASE_PATH` and continue to use `/`.

## Five-country Delivery archive

Fire explorer now includes a **Data archive** selector for observed Aqua MODIS / S-NPP data from Malaysia, Argentina, Canada, India and the United States (2003–2020; S-NPP from 2012). Historical record has a **Historical archive** country selector, with delivered monthly estimates on a 0.25° grid for the four additional countries. Observations and estimated cells remain separate, including in exports and the timeline.

Data are compressed and fetched by country and month. See [Delivery integration and rebuild instructions](docs/data/delivery-integration.md) for provenance, scientific limits and verification commands. The corrected Indonesia validation workbook supersedes the older PDF/summary figures.
