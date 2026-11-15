"""Point-level S-NPP VIIRS simulation for Malaysia.

FIRMS columns are converted here. pipeline_v2 is imported and not modified.
Pairing uses the v2 footprint rule, |dt| <= 90 minutes, and a coarse radius
that pair_candidates further multiplies by KD_PAD (1.25).
"""
from __future__ import annotations

import calendar
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.stats import ks_2samp, wasserstein_distance
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors

import config
ROOT = config.BASE
sys.path.insert(0, str(ROOT))
from pair_v2 import apply_rule, mark_duplicates, pair_candidates  # noqa: E402

from build_features import add_neighbors, add_other_dn, dense_panel  # noqa: E402
from loyo import adjacent, fit_fusion  # noqa: E402

_P = config.paths()
RAW = config.RAW
TABLE = _P["table"]
PRED = _P["loyo_pred"]
CACHE = _P["cache"]
RESULT = config.OUT
FIG = _P["figures"]
SYN = _P["synthetic"]
TO6933 = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
# Geodesic prefilter inside pair_candidates. Footprint corners are ~3 km,
# so 8 km does not cut a true footprint pair. The kd-tree search is 8 km * 1.25.
RADIUS_M = 8000.0
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
SIM_FEATS = [
    "frp", "brightness", "bright_t31", "scan", "track", "confidence",
    "is_night", "month_sin", "month_cos", "lat", "lon", "n_5km",
]
OUT_COLS = [
    "latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version", "bright_ti5", "frp",
    "daynight", "type", "is_synthetic", "sim_source", "sim_parent_modis", "sim_run",
]
KS = [5, 10, 20, 50]
ALPHAS = [0.0, 0.5, 1.0]
JITTERS = [0.0, 0.187, 0.375]
CAP = 40
METHOD = "fusion_G1"


def firms_to_pair_frame(df: pd.DataFrame, sensor: str, year: int) -> pd.DataFrame:
    """Map a FIRMS country-year CSV onto the columns mark_duplicates expects."""
    out = df.copy()
    out["file_row"] = out.index.to_numpy() + 2
    if sensor == "MODIS":
        out = out[out["satellite"].isin(["A", "Aqua", "a"])]
        out["confidence_num"] = pd.to_numeric(out["confidence"], errors="coerce")
        out["conf_bin"] = np.where(out["confidence_num"] < 30, "low", np.where(out["confidence_num"] < 80, "nominal", "high"))
        out["brightness"] = pd.to_numeric(out["brightness"], errors="coerce")
        out["bright_t31"] = pd.to_numeric(out["bright_t31"], errors="coerce")
        out["sensor"] = "MODIS"
        prefix = "M"
    else:
        out = out[out["satellite"].isin(["N", "n", "SNPP", "NPP"])]
        token = out["confidence"].astype(str).str.strip().str.lower()
        out["conf_bin"] = token.map({"l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high"}).fillna("unknown")
        out["bright_ti4"] = pd.to_numeric(out["bright_ti4"], errors="coerce")
        out["bright_ti5"] = pd.to_numeric(out["bright_ti5"], errors="coerce")
        out["sensor"] = "VIIRS"
        prefix = "V"
    if "type" in out.columns:
        out = out[out["type"].astype(str) == "0"]
    out = out[out["conf_bin"].isin(["nominal", "high"])]
    out["lat"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["lon"] = pd.to_numeric(out["longitude"], errors="coerce")
    out["frp"] = pd.to_numeric(out["frp"], errors="coerce")
    out["scan"] = pd.to_numeric(out["scan"], errors="coerce")
    out["track"] = pd.to_numeric(out["track"], errors="coerce")
    out["daynight"] = out["daynight"].astype(str).str.upper().str.strip()
    out = out[out["daynight"].isin(["D", "N"])]
    stamp = pd.to_datetime(
        out["acq_date"].astype(str) + " " + out["acq_time"].astype(str).str.zfill(4),
        format="%Y-%m-%d %H%M", utc=True, errors="coerce",
    )
    out = out.loc[stamp.notna()].copy()
    stamp = stamp.loc[stamp.notna()]
    out["tmin"] = ((stamp - EPOCH).dt.total_seconds() // 60).astype(np.int64)
    out["day"] = out["tmin"] // 1440
    out["year"] = stamp.dt.year.to_numpy()
    out["month"] = stamp.dt.month.to_numpy()
    out["dom"] = stamp.dt.day.to_numpy()
    out["acq_date"] = stamp.dt.strftime("%Y-%m-%d").to_numpy()
    out["acq_time"] = stamp.dt.strftime("%H%M").to_numpy()
    out = out[out["year"] == year]
    out = out.dropna(subset=["lat", "lon", "frp", "scan", "track"])
    out = out.drop_duplicates(["lat", "lon", "acq_date", "acq_time", "satellite"])
    out["x"], out["y"] = TO6933.transform(out["lon"].to_numpy(float), out["lat"].to_numpy(float))
    out["record_id"] = [f"{prefix}{year}_{int(r)}" for r in out["file_row"].to_numpy()]
    out["parent_label"] = [f"{year}:{int(r)}" for r in out["file_row"].to_numpy()]
    step = 0.25
    lat_c = np.floor(out["lat"].to_numpy(float) / step) * step + step / 2
    lon_c = np.floor(out["lon"].to_numpy(float) / step) * step + step / 2
    out["cell_lat"] = lat_c
    out["cell_lon"] = lon_c
    out["cell_id"] = [f"g_{a:.3f}_{b:.3f}" for a, b in zip(lat_c, lon_c)]
    return out.reset_index(drop=True)


def load_sensor(sensor: str, years: range) -> pd.DataFrame:
    kind = "modis" if sensor == "MODIS" else "viirs-snpp"
    parts = []
    for year in years:
        path = RAW / kind / f"{kind}_{year}_{config.COUNTRY}.csv"
        if not path.exists():
            print(f"missing {path.name}", flush=True)
            continue
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        parts.append(firms_to_pair_frame(raw, sensor, year))
        print(f"load {path.name} rows={len(parts[-1])}", flush=True)
    if not parts:
        raise SystemExit(f"no {sensor} files")
    return pd.concat(parts, ignore_index=True)


def keep_representatives(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    slim = df[["record_id", "sensor", "lat", "lon", "scan", "track", "frp", "tmin", "day", "x", "y", "daynight"]].reset_index(drop=True)
    marked, summary = mark_duplicates(slim)
    keep = set(marked.loc[marked["is_representative"], "record_id"])
    out = df[df["record_id"].isin(keep)].reset_index(drop=True)
    print(f"{df['sensor'].iloc[0]} in={len(df)} representatives={len(out)} summary={summary}", flush=True)
    return out, summary


def add_n5(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    lat = out["lat"].to_numpy(float)
    lon = out["lon"].to_numpy(float)
    xy = np.column_stack([lon * 111.32 * np.cos(np.radians(lat)), lat * 110.57])
    days = out["day"].to_numpy()
    n = np.zeros(len(out), dtype=int)
    for day in np.unique(days):
        sel = np.flatnonzero(days == day)
        if len(sel) == 1:
            continue
        tree = cKDTree(xy[sel])
        lists = tree.query_ball_point(xy[sel], r=5.0)
        n[sel] = np.fromiter((len(js) - 1 for js in lists), dtype=int, count=len(sel))
    out["n_5km"] = n
    out["is_night"] = (out["daynight"] == "N").astype(int)
    out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12)
    out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12)
    if "confidence_num" in out.columns:
        out["confidence"] = out["confidence_num"]
    return out


def build_cache() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    train_years = list(getattr(config, "POINT_TRAIN_YEARS", range(2012, 2021)))
    modis = load_sensor("MODIS", getattr(config, "MODIS_LOAD_YEARS", range(2003, 2021)))
    viirs = load_sensor("VIIRS", train_years)
    modis, msum = keep_representatives(modis)
    viirs, vsum = keep_representatives(viirs)
    modis = add_n5(modis)
    both = pd.concat([
        modis.loc[modis["year"].isin(train_years)].assign(sensor="MODIS"),
        viirs.assign(sensor="VIIRS"),
    ], ignore_index=True)
    both["is_representative"] = True
    print("pairing", flush=True)
    cands = pair_candidates(both, 90, radius_m=RADIUS_M, use_representatives_only=True)
    kept = apply_rule(cands, "footprint")
    print(f"coarse={len(cands)} footprint={len(kept)}", flush=True)
    if kept.empty:
        raise SystemExit("pairing returned no footprint matches")
    mm = modis.rename(columns={"record_id": "modis_record_id", "lat": "mlat", "lon": "mlon", "frp": "mfrp", "tmin": "mtmin"})
    vv = viirs.rename(columns={
        "record_id": "viirs_record_id", "lat": "vlat", "lon": "vlon", "frp": "vfrp",
        "scan": "vscan", "track": "vtrack", "confidence": "vconfidence", "daynight": "vdaynight",
    })
    pairs = kept.merge(mm[["modis_record_id", "mlat", "mlon", "mfrp", "mtmin", "year"]], on="modis_record_id", how="inner")
    pairs = pairs.merge(
        vv[["viirs_record_id", "vlat", "vlon", "vfrp", "vscan", "vtrack", "vconfidence", "vdaynight", "bright_ti4", "bright_ti5"]],
        on="viirs_record_id", how="inner",
    )
    pairs["east_km"] = (pairs["vlon"] - pairs["mlon"]) * 111.32 * np.cos(np.radians(pairs["mlat"]))
    pairs["north_km"] = (pairs["vlat"] - pairs["mlat"]) * 110.57
    paired_ids = set(pairs["viirs_record_id"])
    holes = viirs[~viirs["record_id"].isin(paired_ids)].copy()
    holes["region_lat"] = np.floor(holes["lat"]).astype(int)
    holes["region_lon"] = np.floor(holes["lon"]).astype(int)
    sizes = pairs.groupby("modis_record_id").size()
    print(
        f"modis={len(modis)} viirs={len(viirs)} paired_viirs={len(paired_ids)} "
        f"holes={len(holes)} hole_pct={100 * len(holes) / max(len(viirs), 1):.2f} "
        f"cluster_p50={float(sizes.median()) if len(sizes) else 0:.1f} "
        f"cluster_p95={float(sizes.quantile(0.95)) if len(sizes) else 0:.1f} "
        f"cluster_max={int(sizes.max()) if len(sizes) else 0}",
        flush=True,
    )
    modis.to_parquet(CACHE / "modis.parquet", index=False)
    viirs.to_parquet(CACHE / "viirs.parquet", index=False)
    pairs.to_parquet(CACHE / "pairs.parquet", index=False)
    holes.to_parquet(CACHE / "holes.parquet", index=False)
    (CACHE / "dedupe.json").write_text(json.dumps({"modis": msum, "viirs": vsum}, default=str), encoding="utf-8")


def pack_groups(pairs: pd.DataFrame) -> dict:
    cols = ["east_km", "north_km", "dt_min", "vfrp", "bright_ti4", "bright_ti5", "vscan", "vtrack", "vconfidence", "vdaynight"]
    out = {}
    for mid, g in pairs.groupby("modis_record_id", sort=False):
        out[mid] = {c: g[c].to_numpy() for c in cols}
        out[mid]["n"] = len(g)
    return out


def design_matrix(df: pd.DataFrame, medians: pd.Series | None = None):
    X = df[SIM_FEATS].apply(pd.to_numeric, errors="coerce")
    if medians is None:
        medians = X.median(numeric_only=True).fillna(0.0)
    X = X.fillna(medians).fillna(0.0)
    return X.to_numpy(float), medians


def fit_count(train: pd.DataFrame):
    y = train["n_viirs"].to_numpy(float)
    X, med = design_matrix(train)
    model = RandomForestRegressor(
        n_estimators=200, criterion="poisson", min_samples_leaf=5,
        max_features=0.33, n_jobs=-1, random_state=42,
    )
    model.fit(X, y)
    return model, med


def predict_count(model, med, frame: pd.DataFrame) -> np.ndarray:
    X, _ = design_matrix(frame, med)
    pred = np.clip(model.predict(X), 0, None)
    n = np.rint(pred).astype(int)
    return np.minimum(n, CAP), int((n > CAP).sum())


def analog_index(train: pd.DataFrame):
    pool = train[train["n_viirs"] >= 1]
    if pool.empty:
        raise SystemExit("no MODIS points with a VIIRS group")
    X, med = design_matrix(pool)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    k = min(50, len(pool))
    nn = NearestNeighbors(n_neighbors=k, algorithm="kd_tree")
    nn.fit(Z)
    return pool.reset_index(drop=True), nn, mu, sd, med


def choose_donors(test: pd.DataFrame, pool, nn, mu, sd, med, k: int, rng: np.random.Generator) -> np.ndarray:
    X, _ = design_matrix(test, med)
    Z = (X - mu) / sd
    kk = min(k, len(pool))
    idx = nn.kneighbors(Z, n_neighbors=kk, return_distance=False)
    pick = rng.integers(0, idx.shape[1], size=len(test))
    return pool["record_id"].to_numpy()[idx[np.arange(len(test)), pick]]


def emit_paired(test, n_hat, donors, groups, alpha: float, rng: np.random.Generator) -> pd.DataFrame:
    rows_tmin = []
    rows = []
    ids = test["record_id"].to_numpy()
    frp = test["frp"].to_numpy(float)
    lat = test["lat"].to_numpy(float)
    lon = test["lon"].to_numpy(float)
    tmin = test["tmin"].to_numpy(np.int64)
    parent = test["parent_label"].to_numpy()
    budget_cell = test["cell_id"].astype(str).to_numpy()
    budget_month = test["month"].to_numpy(int)
    budget_dn = test["daynight"].astype(str).to_numpy()
    for i in range(len(test)):
        n = int(n_hat[i])
        if n <= 0:
            continue
        g = groups.get(donors[i])
        if g is None or g["n"] == 0:
            continue
        take = rng.choice(g["n"], size=n, replace=n > g["n"])
        afrp = float(np.nanmedian(g["vfrp"]))
        scale = 1.0
        if alpha != 0 and afrp > 0 and frp[i] > 0:
            scale = (frp[i] / afrp) ** alpha
        coslat = np.cos(np.radians(lat[i])) * 111.32
        new_lat = lat[i] + g["north_km"][take] / 110.57
        new_lon = lon[i] + g["east_km"][take] / coslat if coslat else lon[i]
        new_t = tmin[i] + g["dt_min"][take].astype(np.int64)
        for j in range(n):
            rows.append((
                float(new_lat[j]), float(new_lon[j]), float(g["bright_ti4"][take[j]]),
                float(g["vscan"][take[j]]), float(g["vtrack"][take[j]]),
                str(g["vconfidence"][take[j]]), float(g["bright_ti5"][take[j]]),
                float(g["vfrp"][take[j]]) * scale, str(g["vdaynight"][take[j]]),
                "paired", str(parent[i]), str(budget_cell[i]), int(budget_month[i]), str(budget_dn[i]),
            ))
            rows_tmin.append(int(new_t[j]))
    cols = ["lat", "lon", "bright_ti4", "scan", "track", "confidence", "bright_ti5", "frp", "daynight", "sim_source", "sim_parent_modis", "budget_cell", "budget_month", "budget_dn"]
    if not rows:
        return pd.DataFrame(columns=cols + ["tmin"])
    out = pd.DataFrame(rows, columns=cols)
    out["tmin"] = rows_tmin
    return out


def pack_index(df: pd.DataFrame, keys: list[str]) -> dict:
    grouped = df.groupby(keys, sort=False).indices
    out = {}
    for key, val in grouped.items():
        if not isinstance(key, tuple):
            key = (key,)
        norm = []
        for item in key:
            if isinstance(item, (np.integer, int)):
                norm.append(int(item))
            else:
                norm.append(str(item))
        out[tuple(norm)] = np.asarray(val)
    return out


def neighbor_map(cell_ids) -> dict:
    out = {}
    for cid in cell_ids:
        lat = float(str(cid).split("_")[1])
        lon = float(str(cid).split("_")[2])
        out[str(cid)] = [
            f"g_{lat + dy:.3f}_{lon + dx:.3f}"
            for dy in (-0.25, 0.0, 0.25)
            for dx in (-0.25, 0.0, 0.25)
        ]
    return out


def day_weights(modis_year: pd.DataFrame) -> dict:
    if modis_year.empty:
        return {}
    g = modis_year.groupby(["cell_id", "month", "dom"]).size()
    acc: dict[tuple, dict] = {}
    for (cid, month, dom), w in g.items():
        acc.setdefault((str(cid), int(month)), {})[int(dom)] = acc.setdefault((str(cid), int(month)), {}).get(int(dom), 0) + int(w)
    out = {}
    for key, days in acc.items():
        dd = np.array(list(days.keys()), dtype=int)
        ww = np.array([days[int(d)] for d in dd], dtype=float)
        out[key] = (dd, ww / ww.sum())
    return out


def combined_weights(cell_id: str, month: int, table: dict, neighbors: dict, cache: dict):
    key = (cell_id, month)
    if key in cache:
        return cache[key]
    total: dict[int, float] = {}
    for nid in neighbors.get(cell_id, [cell_id]):
        hit = table.get((nid, month))
        if hit is None:
            continue
        for d, w in zip(hit[0], hit[1]):
            total[int(d)] = total.get(int(d), 0.0) + float(w)
    if not total:
        cache[key] = None
        return None
    days = np.array(list(total.keys()), dtype=int)
    ww = np.array(list(total.values()), dtype=float)
    cache[key] = (days, ww / ww.sum())
    return cache[key]


def emit_holes(lambdas: pd.DataFrame, pool: pd.DataFrame, modis_year: pd.DataFrame, rng: np.random.Generator, jitter_km: float, year: int) -> tuple[pd.DataFrame, int]:
    empty = pd.DataFrame(columns=["lat", "lon", "bright_ti4", "scan", "track", "confidence", "bright_ti5", "frp", "daynight", "sim_source", "sim_parent_modis", "acq_date", "acq_time"])
    if lambdas.empty or pool.empty:
        return empty, 0
    pool = pool.reset_index(drop=True)
    cell_ix = pack_index(pool, ["cell_id", "month", "daynight"])
    region_ix = pack_index(pool, ["region_lat", "region_lon", "month", "daynight"])
    country_ix = pack_index(pool, ["month", "daynight"])
    lat = pool["lat"].to_numpy(float)
    lon = pool["lon"].to_numpy(float)
    ti4 = pool["bright_ti4"].to_numpy(float)
    ti5 = pool["bright_ti5"].to_numpy(float)
    scan = pool["scan"].to_numpy(float)
    track = pool["track"].to_numpy(float)
    frp = pool["frp"].to_numpy(float)
    conf = pool["confidence"].astype(str).to_numpy()
    dn = pool["daynight"].astype(str).to_numpy()
    times = pool["acq_time"].astype(str).to_numpy()
    table = day_weights(modis_year)
    neighbors = neighbor_map(lambdas["cell_id"].unique())
    wcache = {}
    if "n_fixed" in lambdas.columns:
        counts = lambdas["n_fixed"].to_numpy(int)
    else:
        lams = np.clip(lambdas["lam"].to_numpy(float), 0, None)
        counts = rng.poisson(lams)
    rows = []
    missed = 0
    rlat = np.floor(lambdas["lat"].to_numpy(float)).astype(int)
    rlon = np.floor(lambdas["lon"].to_numpy(float)).astype(int)
    for i in np.flatnonzero(counts > 0):
        n = int(counts[i])
        month = int(lambdas["month"].iloc[i])
        daynight = str(lambdas["daynight"].iloc[i])
        cid = str(lambdas["cell_id"].iloc[i])
        idx = cell_ix.get((cid, month, daynight))
        if idx is None:
            idx = region_ix.get((int(rlat[i]), int(rlon[i]), month, daynight))
        if idx is None:
            idx = country_ix.get((month, daynight))
        if idx is None or len(idx) == 0:
            missed += n
            continue
        take = rng.choice(idx, size=n, replace=True)
        picked = combined_weights(cid, month, table, neighbors, wcache)
        if picked is None:
            nd = calendar.monthrange(year, month)[1]
            days = rng.integers(1, nd + 1, size=n)
        else:
            days = rng.choice(picked[0], size=n, p=picked[1])
        east = rng.uniform(-jitter_km, jitter_km, size=n)
        north = rng.uniform(-jitter_km, jitter_km, size=n)
        base_lat = lat[take]
        base_lon = lon[take]
        new_lat = base_lat + north / 110.57
        new_lon = base_lon + east / (111.32 * np.cos(np.radians(base_lat)))
        for j in range(n):
            rows.append((
                float(new_lat[j]), float(new_lon[j]), float(ti4[take[j]]),
                float(scan[take[j]]), float(track[take[j]]), str(conf[take[j]]),
                float(ti5[take[j]]), float(frp[take[j]]), str(dn[take[j]]),
                "hole", "", f"{year}-{month:02d}-{int(days[j]):02d}", str(times[take[j]]).zfill(4),
            ))
    if not rows:
        return empty, missed
    out = pd.DataFrame(rows, columns=["lat", "lon", "bright_ti4", "scan", "track", "confidence", "bright_ti5", "frp", "daynight", "sim_source", "sim_parent_modis", "acq_date", "acq_time"])
    return out, missed


def stamp_paired(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    ts = pd.to_datetime(df["tmin"].to_numpy(np.int64), unit="m", utc=True)
    out = df.copy()
    out["acq_date"] = ts.strftime("%Y-%m-%d")
    out["acq_time"] = ts.strftime("%H%M")
    return out


def attach_cell(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    step = 0.25
    lat_c = np.floor(df["lat"].to_numpy(float) / step) * step + step / 2
    lon_c = np.floor(df["lon"].to_numpy(float) / step) * step + step / 2
    out = df.copy()
    out["cell_id"] = [f"g_{a:.3f}_{b:.3f}" for a, b in zip(lat_c, lon_c)]
    out["month"] = pd.to_datetime(out["acq_date"]).dt.month.to_numpy()
    return out


def official_frame(df: pd.DataFrame, sim_run: int) -> pd.DataFrame:
    out = df.copy()
    out["latitude"] = out["lat"]
    out["longitude"] = out["lon"]
    out["satellite"] = "N"
    out["instrument"] = "VIIRS"
    out["version"] = "SIM1.0"
    out["type"] = 0
    out["is_synthetic"] = True
    out["sim_run"] = sim_run
    out["sim_parent_modis"] = out["sim_parent_modis"].fillna("").astype(str).replace({"nan": ""})
    for col in OUT_COLS:
        if col not in out.columns:
            out[col] = ""
    return out[OUT_COLS]


def load_points():
    modis = pd.read_parquet(CACHE / "modis.parquet")
    viirs = pd.read_parquet(CACHE / "viirs.parquet")
    pairs = pd.read_parquet(CACHE / "pairs.parquet")
    holes = pd.read_parquet(CACHE / "holes.parquet")
    sizes = pairs.groupby("modis_record_id").size()
    modis["n_viirs"] = modis["record_id"].map(sizes).fillna(0).astype(int)
    return modis, viirs, pairs, holes


def load_fusion_predictions() -> pd.DataFrame:
    pred = pd.read_parquet(PRED, columns=["year", "cell_id", "lat", "lon", "month", "daynight", "m_count", "method", "pred"])
    pred = pred[pred["method"] == METHOD].copy()
    pred["lam"] = pred["pred"].clip(lower=0)
    return pred


def fusion_lambdas(pred: pd.DataFrame, year: int) -> pd.DataFrame:
    sub = pred[pred["year"] == year].copy()
    if year == 2012:
        sub = sub[sub["month"] != 1]
    return sub[["cell_id", "lat", "lon", "month", "daynight", "lam"]]


def reconcile(paired, lambdas, holes, modis_year, rng, jitter, year):
    """Make each cell x month x daynight total a Poisson draw of the fusion prediction.

    Paired points fill that cell first. Any shortfall is drawn from the hole pool.
    Extra paired points are dropped. This is the 'count follows fusion' rule.
    """
    lam = lambdas.copy()
    lam["n"] = rng.poisson(np.clip(lam["lam"].to_numpy(float), 0, None))
    if paired is None or paired.empty:
        paired = pd.DataFrame(columns=["budget_cell", "budget_month", "budget_dn"])
    else:
        paired = paired.reset_index(drop=True)
    grouped = {}
    if len(paired) and "budget_cell" in paired.columns:
        for key, idx in paired.groupby(["budget_cell", "budget_month", "budget_dn"], sort=False).indices.items():
            grouped[(str(key[0]), int(key[1]), str(key[2]))] = np.asarray(idx)
    keep = []
    seen = set()
    extra_rows = []
    for rec in lam.itertuples(index=False):
        key = (str(rec.cell_id), int(rec.month), str(rec.daynight))
        seen.add(key)
        n = int(rec.n)
        idx = grouped.get(key, np.array([], dtype=int))
        if len(idx) > n:
            if n > 0:
                keep.extend(rng.choice(idx, size=n, replace=False).tolist())
        else:
            keep.extend(idx.tolist())
            add = n - len(idx)
            if add > 0:
                extra_rows.append((rec.cell_id, float(rec.lat), float(rec.lon), int(rec.month), str(rec.daynight), add))
    for key, idx in grouped.items():
        if key not in seen:
            keep.extend(idx.tolist())
    kept = paired.iloc[keep].copy() if keep else paired.iloc[0:0].copy()
    if not extra_rows:
        empty = pd.DataFrame(columns=["lat", "lon", "bright_ti4", "scan", "track", "confidence", "bright_ti5", "frp", "daynight", "sim_source", "sim_parent_modis", "acq_date", "acq_time"])
        return kept, empty, 0
    extra = pd.DataFrame(extra_rows, columns=["cell_id", "lat", "lon", "month", "daynight", "n_fixed"])
    hole_pts, missed = emit_holes(extra, holes, modis_year, rng, jitter, year)
    return kept, hole_pts, missed


def simulate_year(year, test, train, pairs, holes, lambdas, k, alpha, jitter, sim_run, count_model=None, med=None, analog=None, groups=None):
    rng = np.random.default_rng(sim_run)
    if count_model is None:
        count_model, med = fit_count(train)
        analog = analog_index(train)
    pool, nn, mu, sd, amed = analog
    if groups is None:
        groups = pack_groups(pairs)
    n_hat, n_cap = predict_count(count_model, med, test)
    donors = choose_donors(test, pool, nn, mu, sd, amed, k, rng)
    paired = stamp_paired(emit_paired(test, n_hat, donors, groups, alpha, rng))
    paired, hole_pts, missed = reconcile(paired, lambdas, holes, test, rng, jitter, year)
    parts = [p for p in (paired, hole_pts) if len(p)]
    sim = pd.concat(parts, ignore_index=True) if parts else paired.iloc[0:0].copy()
    if len(sim):
        sim = attach_cell(sim)
    return sim, n_cap, missed, count_model, med, analog


def train_bundle(modis, pairs, holes, train_years):
    train = modis[modis["year"].isin(train_years)].reset_index(drop=True)
    model, med = fit_count(train)
    analog = analog_index(train)
    pool = analog[0]
    groups_ids = set(pool["record_id"])
    pp = pairs[pairs["modis_record_id"].isin(groups_ids)]
    hh = holes[holes["year"].isin(train_years)]
    return model, med, analog, pp, hh, pack_groups(pp)


def run_one(year, modis, model, med, analog, pairs, holes, lambdas, k, alpha, jitter, sim_run, groups=None):
    test = modis[modis["year"] == year].reset_index(drop=True)
    if year == 2012:
        test = test[test["month"] != 1].reset_index(drop=True)
    sim, n_cap, missed, *_ = simulate_year(
        year, test, modis, pairs, holes, lambdas, k, alpha, jitter, sim_run,
        count_model=model, med=med, analog=analog, groups=groups,
    )
    return sim, n_cap, missed


def month_wape(actual: pd.DataFrame, sim: pd.DataFrame) -> tuple[float, float]:
    a = actual.groupby("month").size()
    b = sim.groupby("month").size() if len(sim) else pd.Series(dtype=float)
    months = sorted(set(a.index) | set(b.index))
    av = np.array([float(a.get(m, 0)) for m in months])
    bv = np.array([float(b.get(m, 0)) for m in months])
    wape = float(np.abs(bv - av).sum() / max(av.sum(), 1.0) * 100)
    year_abs = abs(float(bv.sum()) - float(av.sum())) / max(float(av.sum()), 1.0) * 100
    return wape, year_abs


def finite(s) -> np.ndarray:
    x = pd.to_numeric(pd.Series(s), errors="coerce").to_numpy(float)
    return x[np.isfinite(x)]


def w1(a, b) -> float | None:
    aa, bb = finite(a), finite(b)
    if len(aa) == 0 or len(bb) == 0:
        return None
    return float(wasserstein_distance(aa, bb))


def ks(a, b) -> float | None:
    aa, bb = finite(a), finite(b)
    if len(aa) < 2 or len(bb) < 2:
        return None
    return float(ks_2samp(aa, bb).statistic)


def conf_bin(v: str) -> str:
    s = str(v).strip().lower()
    if s in {"l", "low"}:
        return "low"
    if s in {"n", "nominal"}:
        return "nominal"
    if s in {"h", "high"}:
        return "high"
    try:
        x = float(s)
    except ValueError:
        return "unknown"
    if x < 30:
        return "low"
    if x < 80:
        return "nominal"
    return "high"


def share_tv(a, b, bins) -> float:
    aa = pd.Series(a).map(conf_bin) if bins == "conf" else pd.Series(a).astype(str)
    bb = pd.Series(b).map(conf_bin) if bins == "conf" else pd.Series(b).astype(str)
    keys = sorted(set(aa) | set(bb))
    if not keys:
        return 0.0
    pa = aa.value_counts(normalize=True)
    pb = bb.value_counts(normalize=True)
    return 0.5 * float(sum(abs(pa.get(k, 0.0) - pb.get(k, 0.0)) for k in keys))


def hour_of(times) -> np.ndarray:
    return pd.Series(times).astype(str).str.zfill(4).str[:2].astype(int).to_numpy()


def hour_tv(a, b) -> float:
    ha, hb = hour_of(a), hour_of(b)
    pa = np.bincount(ha, minlength=24) / max(len(ha), 1)
    pb = np.bincount(hb, minlength=24) / max(len(hb), 1)
    return 0.5 * float(np.abs(pa - pb).sum())


def xy_km(lat, lon):
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    return np.column_stack([lon * 111.32 * np.cos(np.radians(lat)), lat * 110.57])


def within_1km(src: pd.DataFrame, dst: pd.DataFrame) -> np.ndarray:
    hit = np.zeros(len(src), dtype=bool)
    if src.empty or dst.empty:
        return hit
    dst_xy = xy_km(dst["lat"], dst["lon"])
    dst_day = dst["acq_date"].astype(str).to_numpy()
    src_day = src["acq_date"].astype(str).to_numpy()
    src_xy = xy_km(src["lat"], src["lon"])
    for day in pd.unique(src_day):
        s = np.flatnonzero(src_day == day)
        d = np.flatnonzero(dst_day == day)
        if len(s) == 0 or len(d) == 0:
            continue
        tree = cKDTree(dst_xy[d])
        lists = tree.query_ball_point(src_xy[s], r=1.25)
        block = dst_xy[d]
        for i, js in enumerate(lists):
            if not js:
                continue
            dif = block[js] - src_xy[s[i]]
            if np.any(np.hypot(dif[:, 0], dif[:, 1]) <= 1.0):
                hit[s[i]] = True
    return hit


def cell_vectors(actual, sim, cells, months):
    def counts(df):
        if df is None or df.empty:
            s = pd.Series(0.0, index=pd.MultiIndex.from_product([cells, months], names=["cell_id", "month"]))
            return s
        g = df.groupby(["cell_id", "month"]).size()
        idx = pd.MultiIndex.from_product([cells, months], names=["cell_id", "month"])
        return g.reindex(idx, fill_value=0).astype(float)
    a = counts(actual).to_numpy()
    b = counts(sim).to_numpy()
    mae = float(np.mean(np.abs(a - b)))
    if np.std(a) > 0 and np.std(b) > 0:
        corr = float(np.corrcoef(a, b)[0, 1])
    else:
        corr = None
    return mae, corr


def param_row(tag, actual, sim) -> dict:
    row = {"tag": tag}
    for name in ["frp", "bright_ti4", "bright_ti5", "scan", "track"]:
        row[f"{name}_w1"] = w1(actual[name] if name in actual else actual.get(name), sim[name] if len(sim) else [])
        row[f"{name}_ks"] = ks(actual[name] if name in actual else [], sim[name] if len(sim) else [])
    row["confidence_tv"] = share_tv(actual["confidence"], sim["confidence"] if len(sim) else [], "conf")
    row["daynight_abs"] = abs(float((actual["daynight"] == "N").mean()) - (float((sim["daynight"] == "N").mean()) if len(sim) else 0.0))
    row["hour_tv"] = hour_tv(actual["acq_time"], sim["acq_time"] if len(sim) else [])
    row["hour_w1"] = w1(hour_of(actual["acq_time"]), hour_of(sim["acq_time"]) if len(sim) else [])
    return row


def prep_actual(viirs, year: int) -> pd.DataFrame:
    sub = viirs[viirs["year"] == year].copy()
    if year == 2012:
        sub = sub[sub["month"] != 1]
    sub["lat"] = sub["lat"]
    return sub.reset_index(drop=True)


def draw_control(train_viirs, actual, year: int, rng: np.random.Generator) -> pd.DataFrame:
    parts = []
    for month, n in actual.groupby("month").size().items():
        pool = train_viirs[train_viirs["month"] == int(month)]
        if pool.empty or int(n) == 0:
            continue
        take = rng.choice(len(pool), size=int(n), replace=True)
        chunk = pool.iloc[take].copy()
        nd = calendar.monthrange(year, int(month))[1]
        days = rng.integers(1, nd + 1, size=int(n))
        chunk["acq_date"] = [f"{year}-{int(month):02d}-{int(d):02d}" for d in days]
        chunk["month"] = int(month)
        parts.append(chunk)
    if not parts:
        return actual.iloc[0:0].copy()
    out = pd.concat(parts, ignore_index=True)
    return attach_cell(out)


def score_block(actual, sim, control, cells, year: int) -> dict:
    months = [m for m in range(1, 13) if not (year == 2012 and m == 1)]
    wape, year_abs = month_wape(actual, sim)
    cw, _ = month_wape(actual, control)
    mae, corr = cell_vectors(actual, sim, cells, months)
    cmae, ccorr = cell_vectors(actual, control, cells, months)
    row = {
        "year": year,
        "n_sim": int(len(sim)),
        "n_actual": int(len(actual)),
        "n_paired": int((sim["sim_source"] == "paired").sum()) if len(sim) else 0,
        "n_hole": int((sim["sim_source"] == "hole").sum()) if len(sim) else 0,
        "month_wape": round(wape, 2),
        "year_abs_pct": round(year_abs, 2),
        "control_month_wape": round(cw, 2),
        "cell_mae": None if mae is None else round(mae, 4),
        "cell_r": None if corr is None else round(corr, 3),
        "control_cell_mae": None if cmae is None else round(cmae, 4),
        "control_cell_r": None if ccorr is None else round(ccorr, 3),
    }
    sim_p = param_row("sim", actual, sim)
    ctl_p = param_row("control", actual, control)
    for key, val in sim_p.items():
        if key == "tag":
            continue
        row[key] = None if val is None else round(float(val), 4)
        cval = ctl_p[key]
        row[f"control_{key}"] = None if cval is None else round(float(cval), 4)
        if val is not None and cval is not None:
            row[f"better_{key}"] = bool(val < cval)
    if len(sim) and len(actual):
        for source in ["paired", "hole"]:
            part = sim[sim["sim_source"] == source]
            if part.empty:
                row[f"{source}_precision"] = None
                row[f"{source}_recall"] = None
                continue
            prec = float(within_1km(part, actual).mean())
            rec = float(within_1km(actual, part).mean())
            row[f"{source}_precision"] = round(prec, 4)
            row[f"{source}_recall"] = round(rec, 4)
        row["control_precision"] = round(float(within_1km(control, actual).mean()), 4) if len(control) else None
        row["control_recall"] = round(float(within_1km(actual, control).mean()), 4) if len(control) else None
    return row


def tune(modis, viirs, pairs, holes) -> dict:
    years = list(range(2013, 2019))
    cells = sorted(pd.read_parquet(TABLE, columns=["cell_id"])["cell_id"].unique())
    fusion_pred = load_fusion_predictions()
    rows = []
    bundles = {}
    for year in years:
        train_years = [y for y in years if y != year]
        print(f"tune fit {year}", flush=True)
        bundles[year] = train_bundle(modis, pairs, holes, train_years)
    for k in KS:
        for alpha in ALPHAS:
            for jitter in JITTERS:
                wapes = []
                maes = []
                frps = []
                for year in years:
                    model, med, analog, pp, hh, groups = bundles[year]
                    lam = fusion_lambdas(fusion_pred, year)
                    sim, n_cap, missed = run_one(year, modis, model, med, analog, pp, hh, lam, k, alpha, jitter, 1, groups)
                    actual = prep_actual(viirs, year)
                    if year == 2012:
                        sim = sim[sim["month"] != 1] if len(sim) else sim
                    wape, _ = month_wape(actual, sim)
                    months = list(range(1, 13))
                    mae, _ = cell_vectors(actual, sim, cells, months)
                    frp = w1(actual["frp"], sim["frp"] if len(sim) else [])
                    wapes.append(wape)
                    maes.append(0.0 if mae is None else mae)
                    frps.append(999.0 if frp is None else frp)
                    print(f"tune K={k} a={alpha} j={jitter} {year} wape={wape:.2f} cap={n_cap} missed={missed}", flush=True)
                rows.append({
                    "K": k, "alpha": alpha, "jitter_km": jitter,
                    "month_wape": round(float(np.mean(wapes)), 2),
                    "cell_mae": round(float(np.mean(maes)), 4),
                    "frp_w1": round(float(np.mean(frps)), 4),
                })
                pd.DataFrame(rows).to_csv(CACHE / "tune_scores.csv", index=False)
    tab = pd.DataFrame(rows).sort_values(["month_wape", "cell_mae", "frp_w1"])
    best = tab.iloc[0].to_dict()
    (CACHE / "chosen_sim.json").write_text(json.dumps(best), encoding="utf-8")
    print("CHOSEN_SIM", best, flush=True)
    return best


def exam(modis, viirs, pairs, holes, chosen: dict) -> pd.DataFrame:
    train_years = list(range(2013, 2019))
    model, med, analog, pp, hh, groups = train_bundle(modis, pairs, holes, train_years)
    cells = sorted(pd.read_parquet(TABLE, columns=["cell_id"])["cell_id"].unique())
    train_viirs = viirs[viirs["year"].isin(train_years)]
    rows = []
    kept_run1 = {}
    actuals = {}
    controls = {}
    k = int(chosen["K"])
    alpha = float(chosen["alpha"])
    jitter = float(chosen["jitter_km"])
    fusion_pred = load_fusion_predictions()
    for year in (2012, 2019, 2020):
        lam = fusion_lambdas(fusion_pred, year)
        actual = prep_actual(viirs, year)
        actuals[year] = actual
        for run, seed in zip(range(1, getattr(config, "SIM_RUNS", 5) + 1), (11, 22, 33, 44, 55)):
            sim, n_cap, missed = run_one(year, modis, model, med, analog, pp, hh, lam, k, alpha, jitter, run, groups)
            if year == 2012 and len(sim):
                sim = sim[sim["month"] != 1]
            ctl = draw_control(train_viirs, actual, year, np.random.default_rng(seed))
            row = score_block(actual, sim, ctl, cells, year)
            row.update({"sim_run": run, "K": k, "alpha": alpha, "jitter_km": jitter, "capped": n_cap, "holes_missed": missed})
            rows.append(row)
            print(f"exam {year} run={run} wape={row['month_wape']} n={row['n_sim']}", flush=True)
            if run == 1:
                kept_run1[year] = sim
                controls[year] = ctl
            pd.DataFrame(rows).to_csv(CACHE / "exam_scores.csv", index=False)
    scores = pd.DataFrame(rows)
    make_figures(actuals, kept_run1, controls, scores)
    write_exam_book(scores, chosen)
    (CACHE / "exam_done.json").write_text(json.dumps({"rows": len(scores)}), encoding="utf-8")
    return scores


def make_figures(actuals, sims, controls, scores: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    # Pool exam years, sim run 1 vs actual vs one control.
    a = pd.concat([actuals[y] for y in actuals], ignore_index=True)
    s = pd.concat([sims[y] for y in sims if len(sims[y])], ignore_index=True)
    c = pd.concat([controls[y] for y in controls if len(controls[y])], ignore_index=True)
    for name, label in [("frp", "FRP"), ("bright_ti4", "bright_ti4"), ("bright_ti5", "bright_ti5"), ("scan", "scan"), ("track", "track")]:
        aa, ss, cc = finite(a[name]), finite(s[name]) if name in s else np.array([]), finite(c[name])
        if len(aa) == 0:
            continue
        hi = float(np.quantile(aa, 0.99))
        lo = float(np.quantile(aa, 0.01))
        bins = np.linspace(lo, hi if hi > lo else lo + 1, 40)
        plt.figure(figsize=(7, 4))
        plt.hist(aa, bins=bins, density=True, histtype="step", linewidth=1.6, label="actual")
        if len(ss):
            plt.hist(ss, bins=bins, density=True, histtype="step", linewidth=1.6, label="sim run 1")
        if len(cc):
            plt.hist(cc, bins=bins, density=True, histtype="step", linewidth=1.6, label="random")
        plt.xlabel(label)
        plt.ylabel("density")
        plt.title(f"{label} on exam years (display clipped to actual 1–99%)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIG / f"param_{name}.png", dpi=120)
        plt.close()
    y2019 = actuals.get(2019)
    if y2019 is not None and len(y2019):
        peak = int(y2019.groupby("month").size().idxmax())
        real = y2019[y2019["month"] == peak]
        syn = sims.get(2019, pd.DataFrame())
        syn = syn[syn["month"] == peak] if len(syn) else syn
        fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharex=True, sharey=True)
        axes[0].scatter(real["lon"], real["lat"], s=4, c="black", alpha=0.45, linewidths=0)
        axes[0].set_title(f"2019-{peak:02d} actual")
        if len(syn):
            axes[1].scatter(syn["lon"], syn["lat"], s=4, c="tab:red", alpha=0.45, linewidths=0)
        axes[1].set_title(f"2019-{peak:02d} sim run 1")
        for ax in axes:
            ax.set_xlabel("longitude")
            ax.set_ylabel("latitude")
        fig.tight_layout()
        fig.savefig(FIG / f"map_2019_m{peak:02d}.png", dpi=120)
        plt.close(fig)


def write_exam_book(scores: pd.DataFrame, chosen: dict) -> None:
    RESULT.mkdir(parents=True, exist_ok=True)
    means = scores.groupby("year", as_index=False).mean(numeric_only=True)
    better_cols = [c for c in scores.columns if c.startswith("better_")]
    flag = {}
    if better_cols:
        flag = {c: bool(scores[c].fillna(False).all()) for c in better_cols}
    wape = float(scores["month_wape"].mean())
    passed = wape <= 15 and all(flag.values()) if flag else False
    notes = pd.DataFrame([
        {"item": "chosen", "value": json.dumps(chosen)},
        {"item": "exam_mean_month_wape", "value": round(wape, 2)},
        {"item": "pass_wape_15_and_all_params_better", "value": passed},
        {"item": "count_model", "value": "RandomForestRegressor poisson, 200 trees, seed 42, min_samples_leaf 5, count capped at 40"},
        {"item": "control", "value": "same month, n = actual count, drawn from 2013-2018 VIIRS; day reassigned uniformly inside the test month so the 1 km same-day score is defined. Count WAPE of this control is 0 by construction."},
        {"item": "quantity_source", "value": "Each cell x month x daynight total is a Poisson draw of fusion_G1. Paired points fill that cell first; the shortfall, including MODIS=0 cells, is drawn from the unpaired VIIRS pool. Footprint groups alone are only about 16% of VIIRS, so without this alignment the monthly total cannot follow fusion."},
        {"item": "pairing", "value": "footprint rule, |dt|<=90 min (may cross UTC midnight), coarse geodesic cap 8000 m times KD_PAD 1.25"},
        {"item": "hole_pool", "value": "sampling from training years, not a model feature"},
        {"item": "january_2012", "value": "excluded from scores"},
    ])
    fusion_rows = []
    pred = pd.read_parquet(PRED, columns=["year", "month", "method", "pred", "m_count"])
    for year in (2012, 2019, 2020):
        sub = pred[(pred["method"] == METHOD) & (pred["year"] == year)]
        if year == 2012:
            sub = sub[sub["month"] != 1]
        fusion_sum = float(sub["pred"].sum())
        sim_mean = float(scores.loc[scores["year"] == year, "n_sim"].mean())
        fusion_rows.append({
            "year": year,
            "fusion_G1_sum": round(fusion_sum, 1),
            "sim_mean_count": round(sim_mean, 1),
            "gap_pct": round((sim_mean - fusion_sum) / max(fusion_sum, 1.0) * 100, 2),
        })
    path = RESULT / "sim_eval_malaysia.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        scores.to_excel(writer, sheet_name="by_run", index=False)
        means.to_excel(writer, sheet_name="by_year_mean", index=False)
        pd.DataFrame([chosen]).to_excel(writer, sheet_name="choice", index=False)
        pd.DataFrame(fusion_rows).to_excel(writer, sheet_name="vs_fusion", index=False)
        notes.to_excel(writer, sheet_name="notes", index=False)
        if (CACHE / "tune_scores.csv").exists():
            pd.read_csv(CACHE / "tune_scores.csv").to_excel(writer, sheet_name="tune", index=False)
    print(f"wrote {path} pass={passed} wape={wape:.2f}", flush=True)


def g1_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    pred, te = fit_fusion(train, test)
    pred = pred.copy()
    isolated = (te["m_count"].to_numpy(float) <= 0) & (te["nb_adj"].to_numpy(float) <= 0) & (te["m_count_other_dn"].to_numpy(float) <= 0)
    pred[isolated] = 0.0
    return pred


def historical_grid(modis: pd.DataFrame, train_grid: pd.DataFrame) -> pd.DataFrame:
    pts = modis[modis["year"].between(2003, 2011)].copy()
    pts["conf_bin"] = np.where(pts["confidence"] >= 80, "high", "nominal")
    keys = ["cell_id", "cell_lat", "cell_lon", "year", "month", "daynight"]
    agg = pts.groupby(keys, as_index=False).agg(
        m_count=("frp", "size"),
        m_frp_sum=("frp", "sum"),
        m_frp_mean=("frp", "mean"),
        m_frp_max=("frp", "max"),
        m_scan_mean=("scan", "mean"),
        m_track_mean=("track", "mean"),
        m_frac_high=("conf_bin", lambda s: float((s == "high").mean())),
        m_frac_nominal=("conf_bin", lambda s: float((s == "nominal").mean())),
    )
    active = agg[["cell_id", "cell_lat", "cell_lon"]].drop_duplicates("cell_id").rename(columns={"cell_lat": "lat", "cell_lon": "lon"})
    years = sorted(int(y) for y in agg["year"].unique())
    panel = dense_panel(active, years)
    feat = panel.merge(agg.drop(columns=["cell_lat", "cell_lon"]), on=["cell_id", "year", "month", "daynight"], how="left")
    for col in ["m_count", "m_frp_sum", "m_frp_mean", "m_frp_max", "m_scan_mean", "m_track_mean", "m_frac_high", "m_frac_nominal"]:
        if col not in feat.columns:
            feat[col] = 0.0
        feat[col] = feat[col].fillna(0.0)
    feat = add_other_dn(feat)
    feat["m_count_other_dn"] = feat["m_count_other_dn"].fillna(0.0)
    feat = add_neighbors(feat)
    feat["nb_adj"] = adjacent(feat)
    clim = train_grid[["cell_id", "month", "daynight", "m_clim_mean", "m_clim_frp"]].drop_duplicates(["cell_id", "month", "daynight"])
    feat = feat.merge(clim, on=["cell_id", "month", "daynight"], how="left")
    feat["m_clim_mean"] = feat["m_clim_mean"].fillna(0.0)
    feat["m_clim_frp"] = feat["m_clim_frp"].fillna(0.0)
    feat["pixel_area"] = feat["m_scan_mean"] * feat["m_track_mean"]
    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)
    feat["is_night"] = (feat["daynight"] == "N").astype(int)
    return feat


def lambdas_from_pred(frame: pd.DataFrame, pred: np.ndarray, year: int) -> pd.DataFrame:
    out = frame.loc[:, ["cell_id", "lat", "lon", "month", "daynight", "m_count", "year"]].copy()
    out["lam"] = pred
    out = out[out["year"] == year]
    if year == 2012:
        out = out[out["month"] != 1]
    return out


def write_year_csv(sim: pd.DataFrame, year: int) -> None:
    SYN.mkdir(parents=True, exist_ok=True)
    frame = official_frame(sim, 1) if len(sim) else pd.DataFrame(columns=OUT_COLS)
    spec = {"latitude": 5, "longitude": 5, "bright_ti4": 2, "bright_ti5": 2, "frp": 2, "scan": 2, "track": 2}
    for col, nd in spec.items():
        if col not in frame.columns:
            continue
        frame[col] = pd.to_numeric(frame[col], errors="coerce").map(
            lambda v, n=nd: "" if pd.isna(v) else f"{float(v):.{n}f}"
        )
    path = SYN / f"viirs-sim_{year}_{config.COUNTRY}.csv"
    frame.to_csv(path, index=False)
    print(f"wrote {path} rows={len(frame)}", flush=True)


def leave_one_year_climate(early: pd.DataFrame) -> pd.DataFrame:
    """2003–2011 climate for each simulated year, excluding that year.

    Same rule as the feature table: average only years that had fire.
    """
    pos = early.loc[early["m_count"] > 0, ["cell_id", "year", "month", "daynight", "m_count", "m_frp_mean"]]
    parts = []
    for year in sorted(int(y) for y in early["year"].unique()):
        others = pos[pos["year"] != year]
        part = early[early["year"] == year].drop(columns=["m_clim_mean", "m_clim_frp"])
        if others.empty:
            part["m_clim_mean"] = 0.0
            part["m_clim_frp"] = 0.0
        else:
            clim = others.groupby(["cell_id", "month", "daynight"], as_index=False).agg(
                m_clim_mean=("m_count", "mean"),
                m_clim_frp=("m_frp_mean", "mean"),
            )
            part = part.merge(clim, on=["cell_id", "month", "daynight"], how="left")
            part["m_clim_mean"] = part["m_clim_mean"].fillna(0.0)
            part["m_clim_frp"] = part["m_clim_frp"].fillna(0.0)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def out_of_sample_table() -> pd.DataFrame:
    if not PRED.exists():  # only the Malaysia `full` step runs the 9-year test that writes PRED
        return pd.DataFrame()
    pred = pd.read_parquet(PRED, columns=["year", "month", "method", "pred", "v_count"])
    pred = pred[pred["method"] == METHOD]
    rows = []
    for year in range(2012, 2021):
        sub = pred[pred["year"] == year]
        if year == 2012:
            sub = sub[sub["month"] != 1]
        actual = float(sub["v_count"].sum())
        hat = float(sub["pred"].sum())
        rows.append({
            "year": year,
            "actual": round(actual),
            "fusion_G1_loyo": round(hat, 1),
            "signed_gap_pct": round((hat - actual) / actual * 100, 2) if actual else None,
            "january_2012": "excluded" if year == 2012 else "",
        })
    return pd.DataFrame(rows)


def historical(modis, viirs, pairs, holes, chosen: dict) -> None:
    print("historical fit", flush=True)
    grid = pd.read_parquet(TABLE)
    grid = grid[grid["year"].between(2012, 2020)].copy()
    grid["pixel_area"] = grid["m_scan_mean"] * grid["m_track_mean"]
    grid["nb_adj"] = adjacent(grid)
    early = leave_one_year_climate(historical_grid(modis, grid))
    pred_early = g1_predict(grid, early)
    early = early.copy()
    early["pred"] = pred_early
    CACHE.mkdir(parents=True, exist_ok=True)
    early.groupby(["year", "month"], as_index=False)["pred"].sum().to_csv(CACHE / "early_monthly.csv", index=False)
    # In-sample handover on 2012-2014, as specified: train includes those years.
    pred_hand = g1_predict(grid, grid)
    grid = grid.copy()
    grid["pred"] = pred_hand
    train_years = list(getattr(config, "POINT_TRAIN_YEARS", range(2012, 2021)))
    model, med, analog, pp, hh, groups = train_bundle(modis, pairs, holes, train_years)
    k = int(chosen["K"])
    alpha = float(chosen["alpha"])
    jitter = float(chosen["jitter_km"])
    summary = []
    annual = []
    extra_years = list(getattr(config, "HIST_EXTRA_YEARS", [2012, 2013, 2014]))
    for year in list(range(2003, 2012)) + extra_years:
        if year <= 2011:
            lam = lambdas_from_pred(early, pred_early, year)
        else:
            lam = lambdas_from_pred(grid, pred_hand, year)
        counts = []
        run1 = None
        for run in range(1, getattr(config, "SIM_RUNS", 5) + 1):
            sim, n_cap, missed = run_one(year, modis, model, med, analog, pp, hh, lam, k, alpha, jitter, run, groups)
            if year == 2012 and len(sim):
                scored = sim[sim["month"] != 1]
            else:
                scored = sim
            n = int(len(scored))
            counts.append(n)
            summary.append({
                "year": year, "sim_run": run, "n_points_scored": n, "n_points_all_months": int(len(sim)),
                "n_paired": int((sim["sim_source"] == "paired").sum()) if len(sim) else 0,
                "n_hole": int((sim["sim_source"] == "hole").sum()) if len(sim) else 0,
                "capped": n_cap, "holes_missed": missed,
            })
            if run == 1:
                run1 = sim
            print(f"hist {year} run={run} n={n}", flush=True)
        if year <= 2011 and run1 is not None:
            write_year_csv(run1, year)
        annual.append({
            "year": year,
            "sim_mean": float(np.mean(counts)),
            "sim_min": int(min(counts)),
            "sim_max": int(max(counts)),
            "sim_run1": counts[0],
        })
        pd.DataFrame(summary).to_csv(SYN / "sim_runs_summary.csv", index=False)
    actual_rows = []
    for year in range(2012, 2021):
        sub = viirs[viirs["year"] == year]
        if year == 2012:
            sub = sub[sub["month"] != 1]
        actual_rows.append({"year": year, "actual": int(len(sub))})
    actual = pd.DataFrame(actual_rows)
    ann = pd.DataFrame(annual)
    hand = ann[ann["year"].isin([2012, 2013, 2014])].merge(actual, on="year")
    hand["gap_pct"] = (hand["sim_mean"] - hand["actual"]).abs() / hand["actual"].clip(lower=1) * 100
    hand.to_csv(CACHE / "handover.csv", index=False)
    print(hand.to_string(index=False), flush=True)
    plot_timeline(ann, actual)
    with pd.ExcelWriter(RESULT / f"handover_{config.COUNTRY.lower()}.xlsx", engine="openpyxl") as writer:
        hand.to_excel(writer, sheet_name="handover", index=False)
        ann.to_excel(writer, sheet_name="sim_annual", index=False)
        actual.to_excel(writer, sheet_name="actual_2012_2020", index=False)
        pd.DataFrame(summary).to_excel(writer, sheet_name="runs", index=False)
        out_of_sample_table().to_excel(writer, sheet_name="out_of_sample", index=False)


def plot_timeline(sim_ann: pd.DataFrame, actual: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    early = sim_ann[sim_ann["year"] <= 2011]
    hand = sim_ann[sim_ann["year"].between(2012, 2014)]
    plt.figure(figsize=(8, 4))
    plt.plot(early["year"], early["sim_run1"], color="tab:blue", label="sim run 1, 2003–2011")
    plt.plot(actual["year"], actual["actual"], color="black", label="actual S-NPP, 2012–2020")
    plt.plot(hand["year"], hand["sim_run1"], color="tab:blue", linestyle="--", label="sim run 1, 2012–2014")
    plt.xlabel("year")
    plt.ylabel("VIIRS points")
    plt.title(f"{config.COUNTRY} fire counts (2012 excludes January)")
    plt.legend()
    plt.tight_layout()
    path = FIG / "annual_timeline_2003_2020.png"
    plt.savefig(path, dpi=120)
    plt.close()
    print(f"wrote {path}", flush=True)


def main(stage: str) -> int:
    if stage == "pair" or not (CACHE / "pairs.parquet").exists():
        build_cache()
    if stage == "pair":
        return 0
    modis, viirs, pairs, holes = load_points()
    if stage in {"tune", "all"} or not (CACHE / "chosen_sim.json").exists():
        chosen = tune(modis, viirs, pairs, holes)
    else:
        chosen = json.loads((CACHE / "chosen_sim.json").read_text(encoding="utf-8"))
    if stage in {"exam", "all"}:
        exam(modis, viirs, pairs, holes, chosen)
    if stage in {"hist", "all"}:
        historical(modis, viirs, pairs, holes, chosen)
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    raise SystemExit(main(arg))
