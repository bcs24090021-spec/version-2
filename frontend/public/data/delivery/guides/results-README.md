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
