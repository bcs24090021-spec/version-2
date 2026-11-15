"""Leave-one-year comparison for Malaysia. 200 trees. January 2012 is not scored."""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

import config
_P = config.paths()
TABLE = _P["table"]
META = _P["meta"]
OUT = _P["loyo_xlsx"]
PARTIAL = _P["loyo_partial"]
TREES = 200
EXAM = {2012, 2019, 2020}
FEATS = [
    "base", "m_count", "m_frp_mean", "m_frp_max", "pixel_area",
    "m_frac_high", "m_frac_nominal", "m_count_other_dn", "nb_adj",
    "m_clim_mean", "m_clim_frp", "lat", "lon", "month_sin", "month_cos", "is_night", "k_dn",
]
HOLE_FEATS = [c for c in FEATS if c not in {"base", "k_dn"}]


def adjacent(df: pd.DataFrame) -> np.ndarray:
    work = df[["year", "month", "daynight", "lat", "lon", "m_count"]].copy()
    work["lat"] = work["lat"].round(3)
    work["lon"] = work["lon"].round(3)
    src = work.groupby(["year", "month", "daynight", "lat", "lon"], as_index=False)["m_count"].sum()
    total = np.zeros(len(work))
    left = work[["year", "month", "daynight", "lat", "lon"]].copy()
    left["_i"] = np.arange(len(left))
    for dy in (-0.25, 0.0, 0.25):
        for dx in (-0.25, 0.0, 0.25):
            if dy == 0.0 and dx == 0.0:
                continue
            nbr = src.rename(columns={"lat": "nlat", "lon": "nlon", "m_count": "mc"})
            tmp = left.copy()
            tmp["nlat"] = (tmp["lat"] + dy).round(3)
            tmp["nlon"] = (tmp["lon"] + dx).round(3)
            merged = tmp.merge(nbr, on=["year", "month", "daynight", "nlat", "nlon"], how="left")
            total += merged.sort_values("_i")["mc"].fillna(0.0).to_numpy(float)
    return total


def forest():
    return RandomForestRegressor(
        n_estimators=TREES, criterion="squared_error", max_features=0.33,
        min_samples_leaf=20, max_depth=24, n_jobs=-1, random_state=42,
    )


def clf():
    return RandomForestClassifier(
        n_estimators=TREES, max_features=0.33, min_samples_leaf=20,
        max_depth=24, n_jobs=-1, random_state=42,
    )


def fill(train, frame, cols):
    out = frame.copy()
    for c in cols:
        med = float(train[c].median()) if train[c].notna().any() else 0.0
        out[c] = out[c].fillna(med)
    return out


def daynight_k(train):
    out = {}
    seen = train[train["m_count"] > 0]
    for dn, sub in seen.groupby(seen["daynight"].astype(str)):
        modis = float(sub["m_count"].sum())
        out[str(dn)] = float(sub["v_count"].sum()) / modis if modis > 0 else 1.0
    return out


def frp_k(train):
    out = {}
    for dn, sub in train.groupby(train["daynight"].astype(str)):
        modis = float(sub["m_frp_sum"].sum())
        out[str(dn)] = float(sub["v_frp_sum"].sum()) / modis if modis > 0 else 1.0
    return out


def strat_predict(train, test):
    tr = train.copy()
    te = test.copy()
    tr["region"] = np.floor(tr["lat"]).astype(int)
    te["region"] = np.floor(te["lat"]).astype(int)
    country = tr.groupby("daynight", as_index=False).agg(sv=("v_count", "sum"), sm=("m_count", "sum"))
    country["k_country"] = np.where(country["sm"] > 0, country["sv"] / country["sm"], 1.0)
    tr = tr.merge(country[["daynight", "k_country"]], on="daynight", how="left")
    month = tr.groupby(["month", "daynight"], as_index=False).agg(
        sv=("v_count", "sum"), sm=("m_count", "sum"), pk=("k_country", "first")
    )
    month["k_month"] = (month["sv"] + 50 * month["pk"]) / (month["sm"] + 50)
    tr = tr.merge(month[["month", "daynight", "k_month"]], on=["month", "daynight"], how="left")
    region = tr.groupby(["region", "month", "daynight"], as_index=False).agg(
        sv=("v_count", "sum"), sm=("m_count", "sum"), pk=("k_month", "first")
    )
    region["k"] = (region["sv"] + 50 * region["pk"]) / (region["sm"] + 50)
    te = te.merge(region[["region", "month", "daynight", "k"]], on=["region", "month", "daynight"], how="left")
    te = te.merge(month[["month", "daynight", "k_month"]], on=["month", "daynight"], how="left")
    te = te.merge(country[["daynight", "k_country"]], on="daynight", how="left")
    k = te["k"].fillna(te["k_month"]).fillna(te["k_country"]).fillna(1.0).to_numpy(float)
    return te["m_count"].to_numpy(float) * k


def fit_fusion(train, test):
    ks = daynight_k(train)
    def attach(frame):
        out = frame.copy()
        out["k_dn"] = out["daynight"].astype(str).map(ks).fillna(1.0)
        out["base"] = out["m_count"].to_numpy(float) * out["k_dn"].to_numpy(float)
        return out
    tr = fill(attach(train), attach(train), FEATS)
    te = fill(tr, attach(test), FEATS)
    model = forest()
    residual = tr["v_count"].to_numpy(float) - tr["base"].to_numpy(float)
    weight = np.maximum(tr["m_count"].to_numpy(float), 1.0)
    model.fit(tr[FEATS], residual, sample_weight=weight)
    pred = np.clip(te["base"].to_numpy(float) + model.predict(te[FEATS]), 0, None)
    del model
    return pred, te


def g2_holes(train, test, fusion_pred):
    tr = train[train["m_count"] <= 0].copy()
    te = test.copy()
    for frame in (tr, te):
        frame["k_dn"] = 1.0
        frame["base"] = 0.0
    if tr.empty or tr["v_count"].nunique() < 2:
        return fusion_pred
    tr = fill(tr, tr, HOLE_FEATS)
    te_x = fill(tr, te, HOLE_FEATS)
    y = (tr["v_count"].to_numpy(float) > 0).astype(int)
    model_c = clf()
    model_c.fit(tr[HOLE_FEATS], y)
    proba = model_c.predict_proba(te_x[HOLE_FEATS])
    classes = list(model_c.classes_)
    p_fire = proba[:, classes.index(1)] if 1 in classes else np.zeros(len(te_x))
    seen = tr[tr["v_count"] > 0]
    if len(seen) < 20:
        amount = np.full(len(te_x), float(seen["v_count"].mean()) if len(seen) else 0.0)
    else:
        model_r = forest()
        model_r.fit(seen[HOLE_FEATS], seen["v_count"].to_numpy(float))
        amount = np.clip(model_r.predict(te_x[HOLE_FEATS]), 0, None)
        del model_r
    hole_pred = p_fire * amount
    pred = fusion_pred.copy()
    empty = te["m_count"].to_numpy(float) <= 0
    pred[empty] = hole_pred[empty]
    del model_c
    return pred


def g3_predict(train, test):
    years = sorted(train["year"].unique())
    val_year = int(years[len(years) // 2])
    fit_rows = train[train["year"] != val_year]
    val_rows = train[train["year"] == val_year]
    if fit_rows.empty or val_rows.empty:
        pred, _ = fit_fusion(train, test)
        return pred
    val_pred, _ = fit_fusion(fit_rows, val_rows)
    empty_val = val_rows["m_count"].to_numpy(float) <= 0
    denom = float(val_pred[empty_val].sum())
    scale = float(val_rows["v_count"].to_numpy(float)[empty_val].sum()) / denom if denom > 0 else 1.0
    pred, te = fit_fusion(fit_rows, test)
    empty = te["m_count"].to_numpy(float) <= 0
    pred = pred.copy()
    pred[empty] *= scale
    return pred


def frp_from_count(train, pred, frame):
    ratio = {}
    for (month, dn), sub in train.groupby(["month", train["daynight"].astype(str)]):
        fires = float(sub["v_count"].sum())
        ratio[(int(month), str(dn))] = float(sub["v_frp_sum"].sum()) / fires if fires > 0 else 0.0
    global_r = float(train["v_frp_sum"].sum()) / max(float(train["v_count"].sum()), 1.0)
    keys = list(zip(frame["month"].to_numpy(int), frame["daynight"].astype(str)))
    per = np.array([ratio.get(k, global_r) for k in keys])
    return pred * per


def score_year(year, frame, pred, pred_frp, month_median):
    # January 2012 is not scored. Training rows are left untouched by the caller.
    keep = ~((frame["year"].to_numpy(int) == 2012) & (frame["month"].to_numpy(int) == 1))
    pred = np.asarray(pred, float)[keep]
    pred_frp = np.asarray(pred_frp, float)[keep]
    sub = frame.iloc[np.flatnonzero(keep)].copy()
    sub["pred"] = pred
    sub["pred_frp"] = pred_frp
    month = sub.groupby("month", as_index=False).agg(
        actual=("v_count", "sum"), pred=("pred", "sum"),
        actual_frp=("v_frp_sum", "sum"), pred_frp=("pred_frp", "sum"),
    )
    wape = float(np.abs(month["pred"] - month["actual"]).sum() / max(month["actual"].sum(), 1.0) * 100)
    frp_wape = float(np.abs(month["pred_frp"] - month["actual_frp"]).sum() / max(month["actual_frp"].sum(), 1.0) * 100)
    year_abs = abs(float(month["pred"].sum()) - float(month["actual"].sum())) / max(float(month["actual"].sum()), 1.0) * 100
    if len(month) >= 2 and month["actual"].std() > 0 and month["pred"].std() > 0:
        month_r = float(np.corrcoef(month["actual"], month["pred"])[0, 1])
    else:
        month_r = None
    peak_hit = int(month.loc[month["actual"].idxmax(), "month"] == month.loc[month["pred"].idxmax(), "month"]) if len(month) else 0
    signs = []
    for _, row in month.iterrows():
        med = month_median.get(int(row["month"]), 0.0)
        a = np.sign(row["actual"] - med)
        p = np.sign(row["pred"] - med)
        signs.append(a == p)
    cell_mae = float(np.mean(np.abs(sub["pred"].to_numpy(float) - sub["v_count"].to_numpy(float))))
    return {
        "year": int(year),
        "month_wape": round(wape, 2),
        "year_abs_pct": round(year_abs, 2),
        "month_r": None if month_r is None else round(month_r, 3),
        "peak_hit": peak_hit,
        "anomaly_sign_pct": round(100.0 * float(np.mean(signs)), 1) if signs else None,
        "cell_mae": round(cell_mae, 3),
        "frp_month_wape": round(frp_wape, 2),
        "actual_sum": round(float(month["actual"].sum()), 1),
        "pred_sum": round(float(month["pred"].sum()), 1),
    }


def main(country: str = "Malaysia", trees: int = 200, only: str | None = None) -> int:
    global TREES
    TREES = trees
    root = config.WORK
    result = config.OUT
    table_path = root / f"feature_table_{country}.parquet"
    meta_path = root / f"feature_meta_{country}.json"
    keep = [part.strip() for part in only.split(",")] if only else None
    side = keep is not None
    if side:
        slug = f"{country.lower()}_t{trees}" + ("" if not keep else "_" + "-".join(keep))
        out_xlsx = result / f"loyo_{slug}.xlsx"
        partial = root / f"loyo_{slug}_partial.csv"
        pred_path = root / f"loyo_{slug}_predictions.parquet"
    else:
        out_xlsx = OUT
        partial = PARTIAL
        out_xlsx = result / f"loyo_{country.lower()}.xlsx"
        partial = root / f"loyo_{country.lower()}_partial.csv"
        pred_path = root / f"loyo_{country.lower()}_predictions.parquet"
    df = pd.read_parquet(table_path)
    df = df[df["year"].between(2012, 2020)].copy()
    df["pixel_area"] = df["m_scan_mean"] * df["m_track_mean"]
    print("adjacent", country, "trees", trees, flush=True)
    df["nb_adj"] = adjacent(df)
    clim_used = float((df["m_clim_mean"] > 0).mean())
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta.get("clim_source"):
        meta["clim_source"] = "2003_2011" if clim_used > 0 else "missing"
        meta["clim_positive_share"] = round(clim_used, 4)
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    print(f"clim_positive_share {clim_used:.3f} source {meta.get('clim_source')}", flush=True)

    scored = df[~((df["year"] == 2012) & (df["month"] == 1))]
    month_actual = scored.groupby(["year", "month"], as_index=False)["v_count"].sum()
    month_median = month_actual.groupby("month")["v_count"].median().to_dict()
    rows = []
    pred_rows = []
    for year in range(2012, 2021):
        train = df[df["year"] != year]
        test = df[df["year"] == year].copy()
        if len(test) == 0:
            print(f"year {year} empty, skip", flush=True)
            continue
        if meta.get("clim_source") == "loaded_years_fallback":
            pool = df[(df["year"] != year) & (df["m_count"] > 0)]
            clim = pool.groupby(["cell_id", "month", "daynight"], as_index=False).agg(
                m_clim_mean=("m_count", "mean"),
                m_clim_frp=("m_frp_mean", "mean"),
            )
            def apply_clim(frame):
                out = frame.drop(columns=["m_clim_mean", "m_clim_frp"]).merge(
                    clim, on=["cell_id", "month", "daynight"], how="left"
                )
                out["m_clim_mean"] = out["m_clim_mean"].fillna(0.0)
                out["m_clim_frp"] = out["m_clim_frp"].fillna(0.0)
                return out
            train = apply_clim(train)
            test = apply_clim(test)
        print(f"year {year}", flush=True)
        wanted = keep or ["raw", "daynight_k", "strat_k", "fusion", "fusion_G1", "fusion_G2", "fusion_G3"]
        methods = {}
        if "raw" in wanted:
            methods["raw"] = test["m_count"].to_numpy(float)
        if "daynight_k" in wanted:
            methods["daynight_k"] = test["m_count"].to_numpy(float) * test["daynight"].astype(str).map(daynight_k(train)).fillna(1.0).to_numpy(float)
        if "strat_k" in wanted:
            methods["strat_k"] = strat_predict(train, test)
        fusion_pred = None
        if any(name in wanted for name in ("fusion", "fusion_G1", "fusion_G2")):
            fusion_pred, _ = fit_fusion(train, test)
        if "fusion" in wanted:
            methods["fusion"] = fusion_pred
        if "fusion_G1" in wanted:
            methods["fusion_G1"] = fusion_pred.copy()
            isolated = (test["m_count"].to_numpy(float) <= 0) & (test["nb_adj"].to_numpy(float) <= 0) & (test["m_count_other_dn"].to_numpy(float) <= 0)
            methods["fusion_G1"][isolated] = 0.0
        if "fusion_G2" in wanted:
            methods["fusion_G2"] = g2_holes(train, test, fusion_pred)
        if "fusion_G3" in wanted:
            methods["fusion_G3"] = g3_predict(train, test)
        frp_ks = frp_k(train)
        for name, pred in methods.items():
            if name == "raw":
                pred_frp = test["m_frp_sum"].to_numpy(float)
            elif name in {"daynight_k", "strat_k"}:
                if name == "daynight_k":
                    pred_frp = test["m_frp_sum"].to_numpy(float) * test["daynight"].astype(str).map(frp_ks).fillna(1.0).to_numpy(float)
                else:
                    pred_frp = frp_from_count(train, pred, test)
            else:
                pred_frp = frp_from_count(train, pred, test)
            row = score_year(year, test, pred, pred_frp, month_median)
            row["method"] = name
            rows.append(row)
            print(name, row["month_wape"], row["year_abs_pct"], flush=True)
            block = test[["year", "cell_id", "lat", "lon", "month", "daynight", "m_count", "v_count"]].copy()
            block["method"] = name
            block["pred"] = pred
            pred_rows.append(block)
        pd.DataFrame(rows).to_csv(partial, index=False)
    scores = pd.DataFrame(rows)
    preds = pd.concat(pred_rows, ignore_index=True)
    preds.to_parquet(pred_path, index=False)

    def summarize(part, label):
        out = []
        for method, sub in part.groupby("method"):
            ratio = float(sub["pred_sum"].std(ddof=0) / sub["actual_sum"].std(ddof=0)) if sub["actual_sum"].std(ddof=0) > 0 else None
            out.append({
                "slice": label,
                "method": method,
                "month_wape": round(float(sub["month_wape"].mean()), 2),
                "year_abs_pct": round(float(sub["year_abs_pct"].mean()), 2),
                "month_r": round(float(sub["month_r"].mean()), 3),
                "peak_hit": round(float(sub["peak_hit"].mean()), 2),
                "anomaly_sign_pct": round(float(sub["anomaly_sign_pct"].mean()), 1),
                "cell_mae": round(float(sub["cell_mae"].mean()), 3),
                "frp_month_wape": round(float(sub["frp_month_wape"].mean()), 2),
                "interannual_ratio": None if ratio is None else round(ratio, 3),
            })
        return pd.DataFrame(out)

    exam = summarize(scores[scores["year"].isin(EXAM)], "exam_2012_2019_2020")
    tune = summarize(scores[scores["year"].between(2013, 2018)], "tune_2013_2018")
    overall = summarize(scores, "all_scored_years")
    summary = pd.concat([exam, tune, overall], ignore_index=True)
    exam_pick = exam.copy()
    exam_pick["distance"] = (exam_pick["interannual_ratio"] - 1).abs()
    exam_pick = exam_pick.sort_values(["month_wape", "distance"])
    chosen = str(exam_pick.iloc[0]["method"])
    print("CHOSEN", chosen, flush=True)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        scores.to_excel(writer, sheet_name="by_year", index=False)
        summary.to_excel(writer, sheet_name="averages", index=False)
        pd.DataFrame([{
            "chosen_method": chosen, "trees": TREES, "country": country,
            "rule": "lowest exam month_wape, then interannual_ratio closest to 1",
        }]).to_excel(writer, sheet_name="choice", index=False)
    print(f"wrote {out_xlsx}", flush=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="Malaysia")
    ap.add_argument("--trees", type=int, default=200)
    ap.add_argument("--only", default=None, help="comma-separated method names")
    args = ap.parse_args()
    raise SystemExit(main(args.country, args.trees, args.only))
