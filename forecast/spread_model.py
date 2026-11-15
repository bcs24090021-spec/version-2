"""Next-day fire spread model: which 1 km cells will have a VIIRS fire tomorrow?

    python spread_model.py --country Malaysia            # train 2012-2018, test 2019-2020

For every day D, candidate cells = all 0.01 deg cells within 5 km of a day-D VIIRS fire.
Features come only from fires seen on day D and earlier; target = VIIRS fire in the cell on D+1.
Scored per test day by AUC, against the persistence baseline (closer to today's fire = more likely),
on all next-day fire cells and on "new" ones (> 1 km from any day-D fire).
Output: output/{country}/spread/ (scores.csv, summary.json, model.joblib)
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

import config

from pathlib import Path

CELL = 0.01           # deg, ~1 km
R = 5                 # candidate radius in cells (~5 km)
NEG_PER_DAY = 4000    # cap on negative cells kept per training day (all kept on test days)
FEATS = ["d0_km", "n1", "n3", "n5", "frp3", "prev1_3", "prev2_3", "prev7_3", "days_since", "m_sin", "m_cos"]
OFFS = np.array([(a, b) for a in range(-R, R + 1) for b in range(-R, R + 1) if a * a + b * b <= R * R])


def load(country: str, years, files=None) -> pd.DataFrame:
    parts = []
    for path in files or [config.RAW / "viirs-snpp" / f"viirs-snpp_{y}_{country}.csv" for y in years]:
        df = pd.read_csv(path)
        if "type" in df.columns:  # standard archive only; near-real-time files have no type column
            df = df[df["type"] == 0]
        df = df[df["confidence"].astype(str).str.lower().str[0].isin(["n", "h"])]
        t = pd.to_datetime(df["acq_date"] + df["acq_time"].astype(str).str.zfill(4), format="%Y-%m-%d%H%M")
        local = t + pd.to_timedelta(df["longitude"] / 15.0, unit="h")  # solar local day, works in any country
        parts.append(pd.DataFrame({"day": (local.dt.normalize() - pd.Timestamp("2000-01-01")).dt.days,
                                   "lat": df["latitude"].to_numpy(), "lon": df["longitude"].to_numpy(),
                                   "frp": df["frp"].to_numpy()}))
    v = pd.concat(parts, ignore_index=True)
    v["ix"] = np.floor(v["lon"] / CELL).astype(np.int64)
    v["iy"] = np.floor(v["lat"] / CELL).astype(np.int64)
    return v


def km_xy(ix, iy, lat0):
    return np.column_stack([(ix + .5) * CELL * 111.32 * np.cos(np.radians(lat0)), (iy + .5) * CELL * 110.57])


def build(v: pd.DataFrame, rng, sample_neg: bool) -> pd.DataFrame:
    lat0 = float(v["lat"].mean())
    by_day = {d: g for d, g in v.groupby("day")}
    cells_by_day = {d: set(zip(g["ix"], g["iy"])) for d, g in by_day.items()}
    last = {}  # cell -> last day it burned (before D)
    rows = []
    for d in sorted(by_day):
        g = by_day[d]
        fc = np.array(sorted(cells_by_day[d]))
        cand = np.unique((fc[:, None, :] + OFFS[None, :, :]).reshape(-1, 2), axis=0)
        tomorrow = cells_by_day.get(d + 1, set())
        y = np.array([(a, b) in tomorrow for a, b in cand])
        if sample_neg and (~y).sum() > NEG_PER_DAY:
            keep = y.copy()
            keep[rng.choice(np.flatnonzero(~y), NEG_PER_DAY, replace=False)] = True
            cand, y = cand[keep], y[keep]
        xy = km_xy(cand[:, 0], cand[:, 1], lat0)
        pts = np.column_stack([g["lon"] * 111.32 * np.cos(np.radians(lat0)), g["lat"] * 110.57])
        tree = cKDTree(pts)
        frp = g["frp"].to_numpy()
        f = {"day": d, "ix": cand[:, 0], "iy": cand[:, 1], "y": y}
        f["d0_km"] = tree.query(xy)[0]
        for r in (1, 3, 5):
            f[f"n{r}"] = tree.query_ball_point(xy, r, return_length=True)
        f["frp3"] = np.array([frp[j].sum() for j in tree.query_ball_point(xy, 3)])
        for lag, name in ((1, "prev1_3"), (2, "prev2_3")):
            p = by_day.get(d - lag)
            f[name] = 0 if p is None else cKDTree(np.column_stack(
                [p["lon"] * 111.32 * np.cos(np.radians(lat0)), p["lat"] * 110.57])).query_ball_point(xy, 3, return_length=True)
        f["prev7_3"] = sum(np.asarray(f[n]) for n in ("prev1_3", "prev2_3")) + sum(
            cKDTree(np.column_stack([p["lon"] * 111.32 * np.cos(np.radians(lat0)), p["lat"] * 110.57])).query_ball_point(xy, 3, return_length=True)
            for p in (by_day.get(d - k) for k in range(3, 8)) if p is not None)
        f["days_since"] = np.array([min(d - last.get((a, b), d - 999), 999) for a, b in cand])
        month = (pd.Timestamp("2000-01-01") + pd.Timedelta(days=int(d))).month
        f["m_sin"], f["m_cos"] = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
        rows.append(pd.DataFrame(f))
        for c in cells_by_day[d]:
            last[c] = d
    return pd.concat(rows, ignore_index=True)


def score(test: pd.DataFrame) -> pd.DataFrame:
    out = []
    for d, g in test.groupby("day"):
        neg = ~g["y"]  # candidate cells without fire tomorrow
        for tag, pos in (("all", g["y"]), ("new", g["y"] & (g["d0_km"] > 1.0))):
            if pos.sum() < 5 or neg.sum() < 5:
                continue
            sel = pos | (~g["y"])
            yt = pos[sel].astype(int)
            out.append({"day": d, "set": tag, "n_pos": int(pos.sum()),
                        "auc_model": roc_auc_score(yt, g.loc[sel, "p"]),
                        "auc_persistence": roc_auc_score(yt, -g.loc[sel, "d0_km"])})
    return pd.DataFrame(out)


MODELS = config.BASE / "models"  # {country}_spread.joblib + {country}_cells.csv: all a daily forecast needs


def country_mask(country: str) -> set:
    """0.25 deg cells where the country had any S-NPP fire 2012-2020 (NRT files carry no country name)."""
    path = MODELS / f"{country}_cells.csv"
    if not path.exists():
        v = load(country, range(2012, 2021))
        cells = pd.DataFrame({"iy": np.floor(v["lat"] / .25).astype(int), "ix": np.floor(v["lon"] / .25).astype(int)})
        MODELS.mkdir(exist_ok=True)
        cells.drop_duplicates().to_csv(path, index=False)
    c = pd.read_csv(path)
    return set(zip(c["iy"], c["ix"]))


def forecast(country: str, path: Path) -> int:
    import joblib

    out = config.BASE / "output" / country / "spread"
    out.mkdir(parents=True, exist_ok=True)
    saved = MODELS / f"{country}_spread.joblib"
    model = joblib.load(saved if saved.exists() else out / "model.joblib")
    v = load(country, [], files=[path])
    mask = country_mask(country)
    v = v[[(a, b) in mask for a, b in zip(np.floor(v["lat"] / .25).astype(int), np.floor(v["lon"] / .25).astype(int))]]
    now_local = pd.Timestamp.now(tz="UTC").tz_localize(None) + pd.Timedelta(hours=float(v["lon"].mean()) / 15)
    today = (now_local.normalize() - pd.Timestamp("2000-01-01")).days
    d = today if now_local.hour >= 15 else today - 1  # last local day with both day and night passes in
    f = build(v[v["day"] <= d], np.random.default_rng(0), sample_neg=False)
    f = f[f["day"] == d].copy()
    f["p"] = model.predict_proba(f[FEATS])[:, 1]
    date = lambda k: (pd.Timestamp("2000-01-01") + pd.Timedelta(days=int(k))).date()
    res = pd.DataFrame({"forecast_for": date(d + 1), "lat": ((f["iy"] + .5) * CELL).round(3),
                        "lon": ((f["ix"] + .5) * CELL).round(3), "fire_probability": f["p"].round(4),
                        "km_to_nearest_fire_today": f["d0_km"].round(2)}).sort_values("fire_probability", ascending=False)
    name = f"forecast_{date(d + 1)}.csv"
    res.to_csv(out / name, index=False)
    print(f"{country}: fires on {date(d)} = {int((v['day'] == d).sum())}, cells scored = {len(res)}, "
          f"cells p>=0.5 = {int((res.fire_probability >= .5).sum())}, p>=0.2 = {int((res.fire_probability >= .2).sum())} -> {out / name}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default="Malaysia")
    ap.add_argument("--train", default="2012-2018")
    ap.add_argument("--test", default="2019-2020")
    ap.add_argument("--forecast", help="FIRMS near-real-time VIIRS CSV (e.g. 7-day global): forecast tomorrow with the saved model")
    a = ap.parse_args(argv)
    if a.forecast:
        return forecast(a.country, Path(a.forecast))
    span = lambda s: range(int(s.split("-")[0]), int(s.split("-")[1]) + 1)
    rng = np.random.default_rng(42)
    tr = build(load(a.country, span(a.train)), rng, sample_neg=True)
    te = build(load(a.country, span(a.test)), rng, sample_neg=False)
    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, random_state=42)
    model.fit(tr[FEATS], tr["y"])
    te["p"] = model.predict_proba(te[FEATS])[:, 1]
    sc = score(te)
    out = config.BASE / "output" / a.country / "spread"
    out.mkdir(parents=True, exist_ok=True)
    sc.to_csv(out / "scores.csv", index=False)
    pd.DataFrame({  # every candidate cell of every test day: the forecast for the next day
        "forecast_for": (pd.Timestamp("2000-01-01") + pd.to_timedelta(te["day"] + 1, unit="D")).dt.date,
        "lat": ((te["iy"] + .5) * CELL).round(3), "lon": ((te["ix"] + .5) * CELL).round(3),
        "fire_probability": te["p"].round(4), "fire_observed": te["y"].astype(int),
    }).to_csv(out / "forecast_2019_2020.csv", index=False)
    rng2 = np.random.default_rng(0)
    summary = {"country": a.country, "train": a.train, "test": a.test, "train_rows": len(tr), "test_rows": len(te)}
    for tag in ("all", "new"):
        s = sc[sc["set"] == tag]
        diff = (s["auc_model"] - s["auc_persistence"]).to_numpy()
        boot = [np.mean(rng2.choice(diff, len(diff))) for _ in range(2000)] if len(diff) else [np.nan]
        summary[tag] = {"days": len(s), "auc_model": round(float(s["auc_model"].mean()), 3),
                        "auc_persistence": round(float(s["auc_persistence"].mean()), 3),
                        "diff": round(float(diff.mean()), 3) if len(diff) else None,
                        "diff_95ci": [round(float(np.percentile(boot, q)), 3) for q in (2.5, 97.5)],
                        "days_model_wins": round(float((diff > 0).mean()), 3) if len(diff) else None}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    import joblib
    joblib.dump(model, out / "model.joblib")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
