# MODIS → VIIRS hotspot harmonization — NASA Space Apps 2026

Converts Aqua MODIS active-fire detections (2003–2011, before VIIRS existed) into S-NPP VIIRS-equivalent counts, so one consistent fire record runs from 2003 to 2020. Learned from the years both satellites flew (2012–2020). All data come from NASA FIRMS.

| Folder | What is inside |
|---|---|
| `code/` | The system. `python main.py` runs everything |
| `raw_data/` | NASA FIRMS input CSVs for the five countries |
| `results/` | Outputs: 2003–2011 predictions (Argentina, Canada, India, United States), the full Malaysia study, and a next-day fire spread forecast for Malaysia |
| `reference/` | Data sources and papers the method is based on |
| `others/` | Explanation PDFs, the burning-calendar website, the Indonesia check |

Every folder has its own README.

**Countries:** Argentina, Canada, India, United States, Malaysia.

**Accuracy (monthly national error, model never saw the test year):**

| Country | Test | Error |
|---|---|---|
| Argentina | 2018–2020, 3 seeds | 11.1% |
| Canada | 2018–2020, 3 seeds | 11.7–12.5% |
| India | 2018–2020, 3 seeds | 9.4% |
| United States | 2018–2020, 3 seeds | 15.6–15.8% |
| Malaysia | all 9 years 2012–2020 | 17.1% (84.8% without conversion) |

Large fire years tend to be under-estimated by about 15–24% (Malaysia). Predicted values are estimates, not observations.

**In this repository:** the FIRMS input CSVs (1.5 GB) are not committed — `python code/main.py --download --country <Name>` fetches them into `raw_data/`. The 2003–2011 synthetic VIIRS point files are served to the website as monthly shards in `frontend/public/data/delivery/{Country}/synthetic/` (built by `scripts/add_synthetic_points.py`). The daily fire forecast runs from `forecast/` via `.github/workflows/forecast_daily.yml`.
