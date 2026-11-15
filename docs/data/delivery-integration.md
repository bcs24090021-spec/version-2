# DELIVERY archive integration

The archive supplies observed Aqua MODIS (2003–2020), observed S-NPP VIIRS (2012–2020), and Fusion G1 monthly estimates (2003–2011) for Argentina, Canada, India and the United States. Malaysia's existing historical point simulation remains in `data/final`; the additional delivery archive provides observed Malaysia data back to 2003 in Fire explorer.

## Data contract

`frontend/public/data/delivery/<Country>/manifest.json` indexes gzip JSON point shards by month. Every row retains the 17-field historical point schema. Predicted grid shards contain `[latitude, longitude, daynight, predicted_viirs_count, observed_modis_count]`; coordinates are 0.25° cell centers. Predictions are rendered as polygons, never fabricated point detections. Only observations drive the acquisition-time timeline.

The importer uses the repository's existing `firms_to_pair_frame` and `keep_representatives`: Aqua/S-NPP only, vegetation fires, nominal/high confidence, and same-minute overlapping-footprint duplicate cleanup. Source SHA-256 hashes and cleanup statistics are recorded. January 2012 S-NPP coverage starts on 20 January. Raw archives are not copied into the website. The generated archive contains 13,144,873 cleaned observed points across 1,080 country/month point shards; selected monthly grids are separate assets.

Only the selected country's selected months are fetched. Shards use gzip; the loader handles both raw gzip and HTTP-decoded responses, checks record counts, and cancels stale country/date requests. Archive selection is preserved in explorer share links (`archive`) and historical URLs (`hCountry`).

## Scientific distinctions

- Fire explorer's daily adjustment retains a **MODIS-equivalent** scale. Historical monthly predictions use **S-NPP VIIRS-equivalent** counts.
- New-country calendars and trends are national monthly totals. Day/night and drawn areas filter the current map; the national calendar stays explicitly labeled.
- Grid values are monthly estimates; no precise hotspot location, acquisition time, synthetic FRP or daily prediction is inferred from them.
- New countries use 2018–2020 three-seed screening, which is distinct from Malaysia's nine-year study.
- The corrected Indonesia workbook supersedes earlier PDF/summary figures: Fusion G1 2012 WAPE 9.71%; nine-year mean 11.53%. Original workbooks remain available with a correction notice.
- The source `screen_summary.csv` is empty; use per-country screen.json. No data after 2020 or before 2003 are claimed by this archive.

## Rebuild and verify

With the scientific requirements in `FINAL/code/requirements.txt` installed:

```sh
python scripts/build_delivery_data.py /path/to/DELIVERY.zip
python scripts/verify_delivery_data.py
npm run build
node scripts/verify-delivery.mjs
```

An optional second argument selects one country. Completed manifests are reused; delete that country's generated folder to rebuild it. Existing Malaysia historical results are not appended or duplicated. Keep DELIVERY.zip outside Git.
