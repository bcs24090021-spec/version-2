"""MODIS -> S-NPP VIIRS hotspot harmonization. One entry point for everything.

    python main.py                          # all five countries (about 1-2 h)
    python main.py --country Malaysia       # one country
    python main.py --country India --steps screen,predict
    python main.py --download --country Brazil   # fetch FIRMS files first (no login)

Steps
  download  FIRMS country-year CSVs: Aqua MODIS 2003-2020, S-NPP VIIRS 2012-2020 (size-checked)
  screen    2018-2020 leave-one-year-out test of fusion_G1 with seeds 11, 22, 42 (pass = every mean <= 20%)
  predict   retrain fusion_G1 on 2012-2020 (seed 42), predict monthly / per-cell VIIRS counts for 2003-2011
  full      Malaysia study: 7-method 9-year test, point-level synthetic VIIRS 2003-2011, burning calendar

Default steps: Malaysia -> screen,full ; other countries -> screen,predict (predict only if screen passed).
Inputs: ../raw_data/modis/, ../raw_data/viirs-snpp/.  Outputs: output/{country}/.  Scratch: work/{country}/.
Needs Python 3.10+: pandas numpy scipy scikit-learn pyproj matplotlib openpyxl pyarrow
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

import config

COUNTRIES = ["Malaysia", "Argentina", "Canada", "India", "United_States"]
SEEDS = [11, 22, 42]
SCREEN_YEARS = (2018, 2020)
LIMIT = 20.0  # screen pass line, mean monthly WAPE %
QUICK_CHOICE = {"K": 5, "alpha": 0.0, "jitter_km": 0.375}
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/country"


# ---------------------------------------------------------------- download
def download(country: str) -> None:
    with urllib.request.urlopen(f"{FIRMS}/yearly_summary_files.txt", timeout=120) as r:
        sizes = {p[0]: int(p[1]) for p in (l.split(",") for l in r.read().decode().splitlines()[1:])
                 if len(p) >= 2 and p[1].isdigit()}
    wanted = [("modis", y) for y in range(config.EARLY_YEARS.start, config.TRAIN_YEARS.stop)]
    wanted += [("viirs-snpp", y) for y in config.TRAIN_YEARS]
    for product, year in wanted:
        name = f"{product}_{year}_{country}.csv"
        dest, expected = config.RAW / product / name, sizes.get(name)
        if expected is None:
            print(f"not in FIRMS index (no fires that year?): {name}")
            continue
        if dest.exists() and dest.stat().st_size == expected:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        print(f"get {name}", flush=True)
        urllib.request.urlretrieve(f"{FIRMS}/{product}/{year}/{name}", tmp)
        if tmp.stat().st_size != expected:  # never keep a truncated file
            tmp.unlink()
            raise RuntimeError(f"size mismatch for {name}: expected {expected}")
        tmp.replace(dest)


def check_files(country: str) -> None:
    need = [config.RAW / "modis" / f"modis_{y}_{country}.csv" for y in range(2003, 2021)]
    need += [config.RAW / "viirs-snpp" / f"viirs-snpp_{y}_{country}.csv" for y in config.TRAIN_YEARS]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        raise SystemExit(f"{country}: missing {missing}; run with --download")


# ---------------------------------------------------------------- shared
def set_country(country: str, sub: str = "") -> tuple[Path, Path]:
    config.COUNTRY = country
    config.WORK = WORK / country / sub if sub else WORK / country
    config.OUT = OUT / country / sub if sub else OUT / country
    for d in (config.WORK, config.OUT):
        d.mkdir(parents=True, exist_ok=True)
    return config.WORK, config.OUT


def bind_seed(seed: int) -> None:
    import loyo

    loyo.forest = lambda: RandomForestRegressor(
        n_estimators=config.TREES, criterion="squared_error", max_features=0.33,
        min_samples_leaf=20, max_depth=24, n_jobs=-1, random_state=seed)


# ---------------------------------------------------------------- screen
def screen(country: str) -> bool:
    import build_features, loyo

    work, out = set_country(country, "screen")
    if not (work / f"feature_table_{country}.parquet").exists():
        build_features.build(config.RAW, work, *SCREEN_YEARS, country)
    scores = []
    for seed in SEEDS:
        done = out / f"screen_seed{seed}.xlsx"
        if not done.exists():
            bind_seed(seed)
            loyo.main(country, config.TREES, "fusion_G1")
            (out / f"loyo_{country.lower()}_t{config.TREES}_fusion_G1.xlsx").replace(done)
        by = pd.read_excel(done, sheet_name="by_year")
        scores.append({"seed": seed, "mean_wape": round(float(by["month_wape"].mean()), 2),
                       "worst_year": int(by.loc[by["month_wape"].idxmax(), "year"]),
                       "worst_year_wape": float(by["month_wape"].max())})
    passed = all(s["mean_wape"] <= LIMIT for s in scores)
    (OUT / country / "screen.json").write_text(json.dumps(
        {"screen_years": list(range(SCREEN_YEARS[0], SCREEN_YEARS[1] + 1)), "seeds": scores,
         "screen_pass": passed, "limit": LIMIT}, indent=2), encoding="utf-8")
    print(("PASS " if passed else "FAIL ") + f"{country} {[s['mean_wape'] for s in scores]}", flush=True)
    return passed


# ---------------------------------------------------------------- predict
def early_frame(country: str) -> pd.DataFrame:
    """2003-2011 MODIS-only features; climate mean leaves out the year being predicted."""
    import build_features as bf, loyo

    modis = pd.concat([bf.aggregate_modis(bf.read_aqua_year(config.RAW / "modis" / f"modis_{y}_{country}.csv"))
                       for y in config.EARLY_YEARS], ignore_index=True)
    years = sorted(int(y) for y in modis["year"].unique())
    feat = bf.dense_panel(modis[["cell_id", "lat", "lon"]].drop_duplicates("cell_id"), years)
    feat = feat.merge(modis.drop(columns=["lat", "lon"]), on=["cell_id", "year", "month", "daynight"], how="left")
    for col in ["m_count", "m_frp_sum", "m_frp_mean", "m_frp_max", "m_scan_mean", "m_track_mean",
                "m_frac_high", "m_frac_nominal"]:
        feat[col] = feat[col].fillna(0.0)
    feat = bf.add_other_dn(feat)
    feat["m_count_other_dn"] = feat["m_count_other_dn"].fillna(0.0)
    feat["nb_adj"] = loyo.adjacent(feat)
    feat["pixel_area"] = feat["m_scan_mean"] * feat["m_track_mean"]
    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)
    feat["is_night"] = (feat["daynight"] == "N").astype(int)
    fires, keys, pieces = modis[modis["m_count"] > 0], ["cell_id", "month", "daynight"], []
    for year in years:
        block = feat[feat["year"] == year].drop(columns=["m_clim_mean", "m_clim_frp"], errors="ignore")
        others = fires[fires["year"] != year]
        clim = others.groupby(keys, as_index=False).agg(m_clim_mean=("m_count", "mean"),
                                                        m_clim_frp=("m_frp_mean", "mean"))
        block = block.merge(clim, on=keys, how="left")
        block[["m_clim_mean", "m_clim_frp"]] = block[["m_clim_mean", "m_clim_frp"]].fillna(0.0)
        pieces.append(block)
    return pd.concat(pieces, ignore_index=True)


def predict(country: str) -> None:
    import build_features as bf, loyo

    work, out = set_country(country)
    table = work / f"feature_table_{country}.parquet"
    if not table.exists():
        bf.build(config.RAW, work, config.TRAIN_YEARS.start, config.TRAIN_YEARS.stop - 1, country)
    train = pd.read_parquet(table)
    train = train[train["year"].between(config.TRAIN_YEARS.start, config.TRAIN_YEARS.stop - 1)].copy()
    train["pixel_area"] = train["m_scan_mean"] * train["m_track_mean"]
    train["nb_adj"] = loyo.adjacent(train)
    bind_seed(42)
    pred, tested = loyo.fit_fusion(train, early_frame(country))
    pred = pred.copy()
    # fusion_G1: no fire where neither the cell, its neighbours nor the other day/night pass saw MODIS fire
    isolated = ((tested["m_count"].to_numpy(float) <= 0) & (tested["nb_adj"].to_numpy(float) <= 0)
                & (tested["m_count_other_dn"].to_numpy(float) <= 0))
    pred[isolated] = 0.0
    tested = tested.assign(pred=pred)
    monthly = tested.groupby(["year", "month"], as_index=False)["pred"].sum()
    monthly["pred_viirs_count"] = monthly["pred"].round(1)
    monthly[["year", "month", "pred_viirs_count"]].to_csv(out / "pred_2003_2011_monthly.csv", index=False)
    tested[["cell_id", "lat", "lon", "year", "month", "daynight", "m_count", "pred"]].to_parquet(
        out / "pred_2003_2011_cells.parquet", index=False)
    (out / "retrain.json").write_text(json.dumps({
        "method": "fusion_G1", "train_years": "2012-2020", "predict_years": "2003-2011", "seed": 42,
        "trees": config.TREES, "climate": "2003-2011 mean of fire years, excluding the predicted year"},
        indent=2), encoding="utf-8")
    print(monthly.groupby("year")["pred_viirs_count"].sum().round(0).to_string(), flush=True)


# ---------------------------------------------------------------- full (Malaysia study)
def calendar(country: str) -> None:
    cache = config.paths()["cache"]
    early = pd.read_csv(cache / "early_monthly.csv").rename(columns={"pred": "value"}).assign(source="estimated")
    obs = pd.read_parquet(cache / "viirs.parquet").groupby(["year", "month"]).size().rename("value").reset_index()
    obs["source"] = "observed"
    obs.loc[(obs["year"] == 2012) & (obs["month"] == 1), "source"] = "observed_partial"  # S-NPP starts 20 Jan 2012
    full = pd.MultiIndex.from_product([range(2003, 2021), range(1, 13)], names=["year", "month"]).to_frame(index=False)
    cal = full.merge(pd.concat([early, obs], ignore_index=True), on=["year", "month"], how="left")
    cal["value"] = cal["value"].fillna(0.0).round(1)
    cal["source"] = cal["source"].fillna("estimated")
    med = cal[cal["source"] != "observed_partial"].groupby("month")["value"].median().rename("median")
    cal = cal.merge(med, on="month")
    cal["median"] = cal["median"].round(1)
    cal["anomaly_pct"] = ((cal["value"] - cal["median"]) / cal["median"].clip(lower=1) * 100).round(1)
    cal.sort_values(["year", "month"]).to_csv(config.OUT / f"calendar_2003_2020_{country}.csv", index=False)


def point_sim():
    import sim_viirs

    p = config.paths()  # sim_viirs reads its paths at import time, so point them here
    sim_viirs.RAW, sim_viirs.TABLE, sim_viirs.PRED, sim_viirs.CACHE = config.RAW, p["table"], p["loyo_pred"], p["cache"]
    sim_viirs.RESULT, sim_viirs.FIG, sim_viirs.SYN = config.OUT, p["figures"], p["synthetic"]
    p["cache"].mkdir(parents=True, exist_ok=True)
    return sim_viirs, p


def points(country: str) -> None:
    """Point-level synthetic VIIRS 2003-2011 (every detection: date, time, lat, lon, FRP...), Malaysia settings."""
    set_country(country)
    if not config.paths()["table"].exists():
        predict(country)
    bind_seed(42)
    config.HIST_EXTRA_YEARS = []  # no 2012-2014 in-sample handover for these countries
    config.SIM_RUNS = 1  # one run per year (Malaysia full study uses 5)
    sim_viirs, p = point_sim()
    (p["cache"] / "chosen_sim.json").write_text(json.dumps(QUICK_CHOICE), encoding="utf-8")
    # pairing is cached in work/; main("hist") builds it only when missing
    sim_viirs.main("hist")


def check(country: str) -> None:
    """Hidden-year test of the point simulation (exam years 2012/2019/2020) -> sim_eval_{country}.xlsx."""
    import loyo

    set_country(country)
    if not config.paths()["table"].exists():
        predict(country)
    bind_seed(42)
    if not config.paths()["loyo_pred"].exists():
        loyo.main(country, config.TREES, "fusion_G1")  # 9-year leave-one-year-out counts feed the simulation
        side = config.WORK / f"loyo_{country.lower()}_t{config.TREES}_fusion_G1_predictions.parquet"
        side.replace(config.paths()["loyo_pred"])
    config.SIM_RUNS = 1
    sim_viirs, p = point_sim()
    (p["cache"] / "chosen_sim.json").write_text(json.dumps(QUICK_CHOICE), encoding="utf-8")
    sim_viirs.main("exam")


def full(country: str, quick: bool) -> None:
    import build_features, loyo

    work, out = set_country(country)
    build_features.build(config.RAW, work, config.TRAIN_YEARS.start, config.TRAIN_YEARS.stop - 1, country)
    bind_seed(42)
    loyo.main(country, config.TREES, None)
    sim_viirs, p = point_sim()
    if quick:
        (p["cache"] / "chosen_sim.json").write_text(json.dumps(QUICK_CHOICE), encoding="utf-8")
        for stage in ("pair", "exam", "hist"):
            sim_viirs.main(stage)
    else:
        sim_viirs.main("all")
    calendar(country)


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    global WORK, OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", help="one FIRMS country name; default = the five study countries")
    ap.add_argument("--steps", help="comma list of download,screen,predict,full")
    ap.add_argument("--download", action="store_true", help="add the download step")
    ap.add_argument("--quick", action="store_true", help="full: skip the simulation settings search")
    ap.add_argument("--trees", type=int, default=config.TREES)
    ap.add_argument("--raw", type=Path, default=config.RAW)
    ap.add_argument("--out", type=Path, default=config.BASE / "output")
    a = ap.parse_args(argv)
    config.RAW, config.TREES = a.raw, a.trees
    WORK, OUT = config.BASE / "work", a.out
    sys.path.insert(0, str(config.BASE))

    log = []
    for country in [a.country] if a.country else COUNTRIES:
        steps = a.steps.split(",") if a.steps else (["screen", "full"] if country == "Malaysia" else ["screen", "predict", "points"])
        if a.download:
            steps.insert(0, "download")
        bad = set(steps) - {"download", "screen", "predict", "points", "check", "full"}
        if bad:
            ap.error(f"unknown steps {sorted(bad)}")
        passed = True
        for step in steps:
            t0 = time.time()
            print(f"\n===== {country}: {step} =====", flush=True)
            if step == "download":
                download(country)
                continue
            check_files(country)
            if step == "screen":
                passed = screen(country)
            elif step in ("predict", "points") and not passed and not a.steps:
                print(f"{country} failed the screen; no 2003-2011 output", flush=True)
                continue
            elif step == "predict":
                predict(country)
            elif step == "points":
                points(country)
            elif step == "check":
                check(country)
            elif step == "full":
                full(country, a.quick)
            log.append({"country": country, "step": step, "seconds": round(time.time() - t0, 1)})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print("\nall done ->", OUT)
    return 0


WORK = OUT = None
if __name__ == "__main__":
    raise SystemExit(main())
