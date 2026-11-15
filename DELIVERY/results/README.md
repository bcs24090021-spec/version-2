# results

Produced by `../code/main.py`. Values are S-NPP VIIRS-equivalent vegetation-fire detection counts.

## `screen_summary.csv` — does the method work in this country?
One row per country. Test: leave-one-year-out on 2018–2020 (train on two years, test on the third), Fusion G1, three random seeds.

| Column | Meaning |
|---|---|
| `screen_pass` | True if every seed's mean monthly error ≤ 20% |
| `kept` | Country used in this delivery |
| `mean_wape_max` | Worst of the three seed means (%) |
| `seeds` | Per seed: `mean_wape`, `worst_year`, `worst_year_wape` |
| `note` | Malaysia: screen 21% (just over the line) but kept, because its full 9-year test (below) gives 17.1% |

## `Argentina/`, `Canada/`, `India/`, `United_States/` — converted 2003–2011
| File | Content |
|---|---|
| `pred_2003_2011_monthly.csv` | `year`, `month`, `pred_viirs_count` = predicted national VIIRS detections that month |
| `pred_2003_2011_cells.parquet` | Per 0.25° cell × month × day/night: `cell_id`, `lat`, `lon` (cell centre), `year`, `month`, `daynight` (D/N), `m_count` (MODIS detections), `pred` (predicted VIIRS detections) |
| `retrain.json` | Method, training years, seed, trees, climate rule |
| `screen.json` | The 2018–2020 three-seed screen scores |
| `synthetic_viirs/viirs-sim_{year}_{Country}.csv` | **Every synthetic VIIRS detection 2003–2011** (Argentina, Canada, India; United States only if finished): date, time, lat, lon, FRP… — same 19 columns as Malaysia (below). One run per year; yearly totals agree with `pred_2003_2011_monthly.csv` within 0.4% |
| `synthetic_viirs/sim_runs_summary.csv` | Point count per year (`n_paired` = copied from a MODIS detection's matched VIIRS group, `n_hole` = added where MODIS saw nothing) |
| `point_check_exam.csv` (Argentina) | Hidden-year test of the point simulation, see below |

Model: one Fusion G1 forest trained on all of 2012–2020 (seed 42, 200 trees). Cells where neither the cell, its neighbours nor the other day/night pass had MODIS fire are set to 0.

Yearly totals (predicted VIIRS detections):

| Country | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 |
|---|---|---|---|---|---|---|---|---|---|
| Argentina | 306,084 | 255,986 | 172,050 | 192,133 | 191,317 | 272,823 | 211,678 | 152,518 | 189,458 |
| Canada | 206,043 | 294,016 | 103,045 | 122,564 | 112,681 | 117,462 | 88,482 | 194,977 | 137,042 |
| India | 243,241 | 280,428 | 280,027 | 269,383 | 312,602 | 310,902 | 399,919 | 338,527 | 316,634 |
| United States | 266,889 | 403,443 | 414,523 | 296,091 | 337,725 | 277,600 | 274,897 | 198,869 | 288,308 |

## `Malaysia/` — full study
| File | Content |
|---|---|
| `RESULTS_SUMMARY.xlsx` | **Start here.** All tests side by side (sheet `README` explains each sheet) |
| `loyo_malaysia.xlsx` | 7 methods × 9 held-out years (`by_year`, `averages`, `choice`) |
| `loyo_malaysia_800trees.xlsx` | Same test with 800 trees (same score as 200) |
| `sim_eval_malaysia.xlsx` | Synthetic VIIRS points vs real VIIRS on held-out years, vs a random control |
| `handover_malaysia.xlsx` | Yearly totals 2003–2014; predicted vs real for never-seen years |
| `calendar_2003_2020_Malaysia.csv` | Burning calendar: `value` (VIIRS-equivalent count), `source` (estimated / observed / observed_partial = Jan 2012), `median` of that calendar month, `anomaly_pct` |
| `synthetic_viirs/viirs-sim_{year}_Malaysia.csv` | Point-level synthetic VIIRS 2003–2011: the 15 FIRMS VIIRS columns plus `is_synthetic`, `sim_source` (paired/hole), `sim_parent_modis`, `sim_run`; `version = SIM1.0`. A simulation, not observations |
| `synthetic_viirs/sim_runs_summary.csv` | Point count of each of 5 runs per year |
| `screen.json` | 2018–2020 three-seed screen (≈21%) |
| `figures/` | Yearly timeline, real vs synthetic map, distribution of each column |
| `spread/` | **Next-day fire spread model** (see below) |

### Score names
| Name | Meaning | Good |
|---|---|---|
| `month_wape` | **Main score.** Σ\|predicted − actual\| ÷ Σ actual × 100 over the 12 months of the held-out year | Lower |
| `year_abs_pct` | Error of the yearly total, % | Lower |
| `month_r` | Correlation of predicted vs real monthly totals | Near 1 |
| `peak_hit` | Share of years whose busiest month was predicted right | 1 |
| `anomaly_sign_pct` | % of months where above/below normal was called right | Higher |
| `interannual_ratio` | Spread of predicted yearly totals ÷ real spread | Near 1 |
| `cell_mae` | Mean error per 0.25° cell per month | Lower |
| `frp_month_wape` | `month_wape` for fire radiative power | Lower |

Malaysia headline: monthly error 17.1% over nine never-seen years (15.5% on the exam years 2012/2019/2020), down from 84.8% without conversion. Big fire years are under-estimated by 15–24%.

## `Malaysia/spread/` — next-day fire spread forecast
Model (`../code/spread_model.py`): for each day, every 0.01° (~1 km) cell within 5 km of a VIIRS fire gets a probability of having a VIIRS fire **the next day**. Gradient-boosted trees on features from that day and earlier only (distance to nearest fire, fires within 1/3/5 km, FRP within 3 km, fires nearby 1, 2 and 7 days before, days since the cell last burned, month). Trained 2012–2018, tested on 2019–2020 (never seen).

| File | Content |
|---|---|
| `forecast_2019_2020.csv` | `forecast_for` (date), `lat`, `lon` (cell centre), `fire_probability` (0–1), `fire_observed` (1 = VIIRS really saw fire there that day) |
| `scores.csv` | Per test day: `set` (all = every next-day fire cell; new = > 1 km from any fire the day before), `n_pos`, `auc_model`, `auc_persistence` |
| `summary.json` | Means, model − persistence difference with 95% bootstrap interval, share of days the model wins |
| `model.joblib` | The trained model (scikit-learn) |

Baseline "persistence" = tomorrow's fire is wherever today's fire is closest. AUC: 1 = perfect ranking, 0.5 = random.

| Test 2019–2020 | Model AUC | Persistence AUC | Model wins on | Difference, 95% interval |
|---|---|---|---|---|
| All next-day fires (264 days) | **0.908** | 0.874 | 78% of days | +0.027 to +0.042 |
| New fires > 1 km away (126 days) | **0.763** | 0.668 | 84% of days | +0.077 to +0.112 |

| **Argentina** (`Argentina/spread/`), all next-day fires (672 days) | **0.870** | 0.833 | 85% of days | +0.033 to +0.040 |
| **Argentina**, new fires > 1 km away (554 days) | **0.743** | 0.667 | 89% of days | +0.069 to +0.082 |

It beats the baseline in both countries, most for new spread. `Argentina/spread/` holds `scores.csv`, `summary.json`, `model.joblib` (no forecast CSV: it would be ~13 million rows; rerun `spread_model.py --country Argentina` to write it).

## Argentina point-level check (`Argentina/point_check_exam.csv`)
The point simulation was trained on 2013–2018 and run for hidden years, then compared with real S-NPP VIIRS and with a control (the same number of real points drawn at random from the same month of the training years).

| Hidden year | Monthly error | Cell error (model / control) | Cell correlation (model / control) | Synthetic points with a real VIIRS fire within 1 km the same day |
|---|---|---|---|---|
| 2012 (Jan excluded) | **6.5%** | 1.65 / 3.35 | 0.92 / 0.51 | 68% |
| 2019 | **7.4%** | 1.46 / 2.75 | 0.91 / 0.47 | 68% |

Pass rule set before the test: monthly error < 30%. 2020 was not run (time). Canada, India and the United States use the same settings without their own point check; their monthly counts were checked by the 2018–2020 screen.

## Forecast for now (November 2026)
`Malaysia/spread/forecast_2026-11-16.csv`, `Argentina/spread/forecast_2026-11-15.csv`: tomorrow's fire probability per ~1 km cell, from the latest NASA FIRMS near-real-time NOAA-20 VIIRS 7-day file (S-NPP stopped on 2 Nov 2026). Columns: `forecast_for`, `lat`, `lon`, `fire_probability`, `km_to_nearest_fire_today`; sorted, most likely first.
Run again any day: download `https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv`, then `python spread_model.py --country Malaysia --forecast J1_VIIRS_C2_Global_7d.csv`.
Limits: the model was trained on S-NPP (same 375 m sensor type as NOAA-20); with only 7 days of history, "days since the cell last burned" cannot see further back than a week; country = cells where that country had fires in 2012–2020, so border cells may include a neighbour.
