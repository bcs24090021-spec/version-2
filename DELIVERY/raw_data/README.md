# raw_data — NASA FIRMS inputs

Standard Processing country-year CSVs from NASA FIRMS (https://firms.modaps.eosdis.nasa.gov/data/country/), unmodified. Every file's size matches the official FIRMS index (`yearly_summary_files.txt`), so none is truncated.

| Folder | Files | Years | Count |
|---|---|---|---|
| `modis/` | `modis_{year}_{Country}.csv` (Aqua + Terra MODIS C6.1; the code keeps Aqua only) | 2003–2020 | 5 countries × 18 = 90 |
| `viirs-snpp/` | `viirs-snpp_{year}_{Country}.csv` (Suomi NPP VIIRS 375 m) | 2012–2020 | 5 countries × 9 = 45 |

Countries: `Argentina`, `Canada`, `India`, `United_States`, `Malaysia`.

**Roles:** 2012–2020 (both satellites) = training and testing. 2003–2011 MODIS = the years being converted.

Main columns: `latitude`, `longitude`, `acq_date`, `acq_time` (UTC), `satellite`, `scan`, `track`, `brightness` / `bright_ti4`, `frp` (fire radiative power, MW), `confidence` (MODIS 0–100; VIIRS l/n/h), `daynight`, `type` (0 = vegetation fire; the only type used).

To fetch another country: `python ../code/main.py --download --country <FIRMS name>`.
