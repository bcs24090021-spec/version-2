# code

```bash
pip install -r requirements.txt
python main.py
```

Reads `../raw_data/`, writes `output/{country}/` (results) and `work/{country}/` (intermediate files). Runs offline. All five countries take about 1–2 hours on a laptop.

## Commands

| Command | What it does |
|---|---|
| `python main.py` | All five countries |
| `python main.py --country India` | One country |
| `python main.py --country India --steps predict` | Only some steps |
| `python main.py --download --country Brazil` | Download FIRMS files for any country first (no login), then run |
| `python main.py --country Malaysia --quick` | Skip the simulation settings search (K=5, α=0, jitter 0.375 km) |
| `--trees 800`, `--raw <dir>`, `--out <dir>` | Bigger forests / other folders |

## Steps

| Step | Default for | What it does | Output |
|---|---|---|---|
| `download` | (on request) | FIRMS country-year CSVs; each file's size is checked against the FIRMS index | `raw_data/` |
| `screen` | all | Leave-one-year-out test on 2018–2020, Fusion G1, seeds 11/22/42. Pass = every seed's mean monthly error ≤ 20% | `screen.json`, `screen/screen_seed*.xlsx` |
| `predict` | Argentina, Canada, India, United States (only if screen passed) | Retrain one Fusion G1 forest on 2012–2020 (seed 42, 200 trees), predict 2003–2011 | `pred_2003_2011_monthly.csv`, `pred_2003_2011_cells.parquet`, `retrain.json` |
| `full` | Malaysia | 7 methods × 9 held-out years, point-level synthetic VIIRS 2003–2011, burning calendar | `loyo_*.xlsx`, `sim_eval_*.xlsx`, `handover_*.xlsx`, `synthetic_viirs/`, `calendar_*.csv`, `figures/` |

## Files

| File | Job |
|---|---|
| `main.py` | Entry point: download, screen, predict, full, calendar |
| `config.py` | Paths and fixed settings (years, trees) |
| `build_features.py` | Clean (vegetation fires, nominal/high confidence, duplicate removal), grid to 0.25° × month × day/night, MODIS-only features |
| `loyo.py` | Methods (multipliers, Fusion G1 random forest) and the leave-one-year-out test |
| `pair_v2.py` | MODIS–VIIRS footprint pairing and duplicate detection |
| `sim_viirs.py` | Point-level synthetic VIIRS (`points`, `check`, `full` steps) |
| `spread_model.py` | Separate tool: next-day fire spread forecast. `python spread_model.py --country Malaysia` (≈3 min) → `output/Malaysia/spread/` |
| `models/` | `{Country}_spread.joblib` (trained spread model) + `{Country}_cells.csv` (0.25° cells of that country): all a daily forecast needs, no raw data |
| `github/forecast_daily.yml` | GitHub Actions workflow: every day at 22:00 UTC downloads the FIRMS 7-day NOAA-20 file, writes tomorrow's forecast for Malaysia and Argentina, commits it for the website |
| `requirements.txt` | Python packages |

## Method in one paragraph
Each 0.25° cell × month × day/night gets a base estimate = MODIS count × day/night multiplier (VIIRS ÷ MODIS on the training years). A random forest (200 trees, max_features 0.33, min_samples_leaf 20, max_depth 24) learns the remaining correction from MODIS-only features: fire radiative power, pixel size, confidence, neighbouring cells, the other day/night pass, previous months and a 2003–2011 "normal fire" mean that leaves out the year being predicted. Fusion G1 adds fire to an empty cell only when MODIS saw fire next to it or at the other time of day.

## Rules built into the code
- Inputs are MODIS-only; year, cell ID and anything from VIIRS are never features.
- Training years 2012–2020 (before Aqua's orbit drift). January 2012 is never scored (S-NPP starts 20 Jan 2012).
- Fixed random seeds: the same numbers on every run.

## Daily forecast (next-day fire spread)
```bash
curl -o J1_7d.csv https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv
python spread_model.py --country Malaysia --forecast J1_7d.csv     # -> output/Malaysia/spread/forecast_{date}.csv
```
To publish it on a GitHub Pages site, copy `github/forecast_daily.yml` to `.github/workflows/` (GitHub Pages itself cannot run Python; the workflow runs it once a day and commits the CSV).
