# others

| Folder | What it is |
|---|---|
| `documentation/` | Full explanation of the system: problem, data, theory, workflow and formulas, every test result, limitations. `System_Explanation_EN.pdf` (English, for judges), `系统说明_中文.pdf` (Chinese, same content) |
| `website/` | Burning-calendar web page for Malaysia 2003–2020. Open `index.html`, or serve the folder (`python -m http.server`) and choose a year/month; shows the month vs its historical median and lets you download the CSV. `data/` holds the synthetic VIIRS points it displays. `上台讲稿.md` = presentation script (Chinese) |
| `indonesia_check/` | Second-country check of the method (Indonesia, 9 held-out years, 5 methods) |

## indonesia_check
| File | Content |
|---|---|
| `loyo_indonesia_fixed2012.xlsx` | **Current.** Leave-one-year-out with the complete 2012 VIIRS file. Fusion G1 error for held-out 2012: **9.7%** |
| `loyo_indonesia_old_incomplete2012.xlsx` | Earlier run whose 2012 VIIRS download was truncated (17,956,864 of 25,193,408 bytes), which inflated the 2012 error to 53.5%. Kept only to show why the file-size check was added |

Sheets: `by_year` (one row per method × held-out year), `averages`, `choice`. Columns are explained in `../results/README.md` (Score names).
