"""Build Aqua→S-NPP feature table (cell × year × month × daynight).

MODIS-only inputs. Climate features use 2003–2011 Aqua only.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config
ROOT = config.BASE
RAW = config.RAW
DEDUPE = {"modis_exact": 0, "modis_v2": 0, "viirs_exact": 0, "viirs_v2": 0}
OUT = config.WORK
STEP = 0.25
FORBIDDEN = ("viirs", "snpp", "n20", "year")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def conf_bin_modis(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "unknown"
    if x < 30:
        return "low"
    if x < 80:
        return "nominal"
    return "high"


def conf_bin_viirs(v) -> str:
    s = str(v).strip().lower()
    if s in {"l", "low"}:
        return "low"
    if s in {"n", "nominal"}:
        return "nominal"
    if s in {"h", "high"}:
        return "high"
    return "unknown"


def footprint_dedupe(df: pd.DataFrame, sensor: str) -> pd.DataFrame:
    """Same sensor, same minute, footprint overlap > 30%: keep the max FRP."""
    n_exact = len(df)
    DEDUPE[f"{sensor}_exact"] += n_exact
    if len(df) < 2:
        DEDUPE[f"{sensor}_v2"] += n_exact
        return df
    work = df.reset_index(drop=True)
    tmin = (work["acq_date"].astype(str) + work["acq_time"].astype(str).str.zfill(4)).to_numpy()
    lat = work["lat"].to_numpy(float)
    lon = work["lon"].to_numpy(float)
    scan = work["scan"].to_numpy(float)
    track = work["track"].to_numpy(float)
    frp = work["frp"].to_numpy(float)
    parent = np.arange(len(work))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    order = np.argsort(tmin, kind="mergesort")
    sorted_t = tmin[order]
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and sorted_t[j] == sorted_t[i]:
            j += 1
        idx = order[i:j]
        if len(idx) >= 2:
            xy = np.column_stack([
                lon[idx] * 111320.0 * np.cos(np.radians(lat[idx])),
                lat[idx] * 110570.0,
            ])
            tree = cKDTree(xy)
            for a in range(len(idx)):
                for b in tree.query_ball_point(xy[a], r=5000.0):
                    if b <= a:
                        continue
                    sc = min(scan[idx[a]], scan[idx[b]])
                    tr = min(track[idx[a]], track[idx[b]])
                    if not (sc > 0 and tr > 0):
                        continue
                    dx = abs(lon[idx[a]] - lon[idx[b]]) * 111.32 * math.cos(math.radians(float(lat[idx[a]])))
                    dy = abs(lat[idx[a]] - lat[idx[b]]) * 110.57
                    overlap = max(0.0, 1.0 - dx / sc) * max(0.0, 1.0 - dy / tr)
                    if overlap > 0.3:
                        union(int(idx[a]), int(idx[b]))
        i = j
    comps: dict[int, list[int]] = {}
    for i in range(len(work)):
        comps.setdefault(find(i), []).append(i)
    drop = []
    for members in comps.values():
        if len(members) < 2:
            continue
        vals = np.where(np.isnan(frp[members]), -np.inf, frp[members])
        rep = members[int(np.argmax(vals))]
        drop.extend(m for m in members if m != rep)
    DEDUPE[f"{sensor}_v2"] += n_exact - len(drop)
    if not drop:
        return work
    return work.drop(index=drop).reset_index(drop=True)


def cell_id_from_latlon(lat: np.ndarray, lon: np.ndarray):
    lat_c = np.floor(lat / STEP) * STEP + STEP / 2
    lon_c = np.floor(lon / STEP) * STEP + STEP / 2
    cid = np.array([f"g_{a:.3f}_{b:.3f}" for a, b in zip(lat_c, lon_c)])
    return cid, lat_c, lon_c


def read_aqua_year(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df[df["satellite"].isin(["A", "Aqua", "a"])].copy()
    df["conf_bin"] = df["confidence"].map(conf_bin_modis)
    if "type" in df.columns:
        df = df[df["type"] == "0"]
    df = df[df["conf_bin"].isin(["nominal", "high"])]
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce")
    df["scan"] = pd.to_numeric(df["scan"], errors="coerce")
    df["track"] = pd.to_numeric(df["track"], errors="coerce")
    df["daynight"] = df["daynight"].str.upper().str.strip()
    df = df[df["daynight"].isin(["D", "N"])]
    t = pd.to_datetime(
        df["acq_date"] + " " + df["acq_time"].str.zfill(4),
        format="%Y-%m-%d %H%M", utc=True, errors="coerce",
    )
    df["year"] = t.dt.year
    df["month"] = t.dt.month
    df = df.dropna(subset=["lat", "lon", "year", "month", "frp", "scan", "track"])
    # same-satellite duplicates → one point, then v2 footprint overlap
    df = df.drop_duplicates(subset=["lat", "lon", "acq_date", "acq_time", "satellite"])
    df = footprint_dedupe(df, "modis")
    cid, lat_c, lon_c = cell_id_from_latlon(df["lat"].to_numpy(), df["lon"].to_numpy())
    df["cell_id"] = cid
    df["lat"] = lat_c
    df["lon"] = lon_c
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    return df


def read_snpp_year(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df[df["satellite"].isin(["N", "n", "SNPP", "NPP"])].copy()
    df["conf_bin"] = df["confidence"].map(conf_bin_viirs)
    if "type" in df.columns:
        df = df[df["type"] == "0"]
    df = df[df["conf_bin"].isin(["nominal", "high"])]
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce")
    df["scan"] = pd.to_numeric(df["scan"], errors="coerce")
    df["track"] = pd.to_numeric(df["track"], errors="coerce")
    df["daynight"] = df["daynight"].str.upper().str.strip()
    df = df[df["daynight"].isin(["D", "N"])]
    t = pd.to_datetime(
        df["acq_date"] + " " + df["acq_time"].str.zfill(4),
        format="%Y-%m-%d %H%M", utc=True, errors="coerce",
    )
    df["year"] = t.dt.year
    df["month"] = t.dt.month
    df = df.dropna(subset=["lat", "lon", "year", "month", "frp", "scan", "track"])
    df = df.drop_duplicates(subset=["lat", "lon", "acq_date", "acq_time", "satellite"])
    df = footprint_dedupe(df, "viirs")
    cid, lat_c, lon_c = cell_id_from_latlon(df["lat"].to_numpy(), df["lon"].to_numpy())
    df["cell_id"] = cid
    df["lat"] = lat_c
    df["lon"] = lon_c
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    return df


def aggregate_modis(m: pd.DataFrame) -> pd.DataFrame:
    keys = ["cell_id", "lat", "lon", "year", "month", "daynight"]
    g = m.groupby(keys, as_index=False).agg(
        m_count=("frp", "size"),
        m_frp_sum=("frp", "sum"),
        m_frp_mean=("frp", "mean"),
        m_frp_max=("frp", "max"),
        m_frp_p50=("frp", "median"),
        m_scan_mean=("scan", "mean"),
        m_track_mean=("track", "mean"),
        m_scan_max=("scan", "max"),
        m_frac_offnadir=("scan", lambda s: float((s > 2.0).mean())),
        m_frac_high=("conf_bin", lambda s: float((s == "high").mean())),
        m_frac_nominal=("conf_bin", lambda s: float((s == "nominal").mean())),
    )
    return g


def aggregate_viirs(v: pd.DataFrame) -> pd.DataFrame:
    keys = ["cell_id", "year", "month", "daynight"]
    return v.groupby(keys, as_index=False).agg(v_count=("frp", "size"), v_frp_sum=("frp", "sum"))


def load_years(raw: Path, start: int, end: int, country: str = "Indonesia"):
    parts_m, parts_v, hashes = [], [], {}
    for y in range(start, end + 1):
        mp = raw / "modis" / f"modis_{y}_{country}.csv"
        vp = raw / "viirs-snpp" / f"viirs-snpp_{y}_{country}.csv"
        if not mp.exists() or not vp.exists():
            print(f"skip {y}: missing")
            continue
        hashes[str(mp)] = sha256_file(mp)
        hashes[str(vp)] = sha256_file(vp)
        print(f"load {y}")
        parts_m.append(aggregate_modis(read_aqua_year(mp)))
        parts_v.append(aggregate_viirs(read_snpp_year(vp)))
    return parts_m, parts_v, hashes


def load_clim_modis(raw: Path, clim_start: int = 2003, clim_end: int = 2011, country: str = "Indonesia") -> pd.DataFrame | None:
    """shortcut: if pre-2012 Aqua missing, return None and clim filled later from train years note."""
    parts = []
    for y in range(clim_start, clim_end + 1):
        mp = raw / "modis" / f"modis_{y}_{country}.csv"
        if not mp.exists():
            continue
        print(f"clim load {y}")
        parts.append(aggregate_modis(read_aqua_year(mp)))
    if not parts:
        return None
    c = pd.concat(parts, ignore_index=True)
    return c.groupby(["cell_id", "month", "daynight"], as_index=False).agg(
        m_clim_mean=("m_count", "mean"),
        m_clim_frp=("m_frp_mean", "mean"),
    )


def dense_panel(active_cells: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    cells = active_cells.drop_duplicates("cell_id")[["cell_id", "lat", "lon"]]
    idx = pd.MultiIndex.from_product(
        [cells["cell_id"], years, range(1, 13), ["D", "N"]],
        names=["cell_id", "year", "month", "daynight"],
    )
    panel = idx.to_frame(index=False)
    return panel.merge(cells, on="cell_id", how="left")


def add_other_dn(df: pd.DataFrame) -> pd.DataFrame:
    flip = df[["cell_id", "year", "month", "daynight", "m_count"]].copy()
    flip["daynight"] = flip["daynight"].map({"D": "N", "N": "D"})
    flip = flip.rename(columns={"m_count": "m_count_other_dn"})
    return df.merge(flip, on=["cell_id", "year", "month", "daynight"], how="left")


def add_lags(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values(["cell_id", "daynight", "year", "month"]).copy()
    g = d.groupby(["cell_id", "daynight"], sort=False)["m_count"]
    d["m_count_prev"] = g.shift(1)
    d["m_count_next"] = g.shift(-1)
    # cross year boundary is fine; first/last month NaN → 0
    d["m_count_prev"] = d["m_count_prev"].fillna(0)
    d["m_count_next"] = d["m_count_next"].fillna(0)
    return d


def add_neighbors(df: pd.DataFrame) -> pd.DataFrame:
    """m_count_nb3 / nb5 via shifted merges on integer lat/lon indices."""
    base = df[["year", "month", "daynight", "lat", "lon", "m_count"]].copy()
    base["lat_i"] = np.round(base["lat"] / STEP).astype(int)
    base["lon_i"] = np.round(base["lon"] / STEP).astype(int)
    src = base[["year", "month", "daynight", "lat_i", "lon_i", "m_count"]].drop_duplicates(
        ["year", "month", "daynight", "lat_i", "lon_i"]
    )
    nb3 = np.zeros(len(df), float)
    nb5 = np.zeros(len(df), float)
    left = base[["year", "month", "daynight", "lat_i", "lon_i"]].copy()
    left["_i"] = np.arange(len(left))
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dy == 0 and dx == 0:
                continue
            nbr = src.rename(columns={"lat_i": "nlat", "lon_i": "nlon", "m_count": "mc"})
            tmp = left.copy()
            tmp["nlat"] = tmp["lat_i"] + dy
            tmp["nlon"] = tmp["lon_i"] + dx
            merged = tmp.merge(
                nbr, on=["year", "month", "daynight", "nlat", "nlon"], how="left",
            )
            vals = merged.sort_values("_i")["mc"].fillna(0.0).to_numpy()
            nb5 += vals
            if abs(dy) <= 1 and abs(dx) <= 1:
                nb3 += vals
    out = df.copy()
    out["m_count_nb3"] = nb3
    out["m_count_nb5"] = nb5
    return out


FEATURE_COLS = [
    "m_count", "m_count_other_dn",
    "m_frp_sum", "m_frp_mean", "m_frp_max", "m_frp_p50",
    "m_scan_mean", "m_track_mean", "m_scan_max", "m_frac_offnadir",
    "m_frac_high", "m_frac_nominal",
    "m_count_prev", "m_count_next",
    "m_count_nb3", "m_count_nb5",
    "m_clim_mean", "m_clim_frp",
    "lat", "lon", "month_sin", "month_cos", "is_night",
]


def assert_no_leakage(columns: list[str]) -> None:
    leak = [
        c for c in columns
        if any(b in c.lower() for b in ("viirs", "snpp", "n20")) or c.lower() == "year" or c == "cell_id"
    ]
    if leak:
        raise AssertionError(f"forbidden feature columns: {leak}")


def build(raw: Path, out: Path, year_start: int = 2012, year_end: int = 2023, country: str = "Indonesia") -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for key in DEDUPE:
        DEDUPE[key] = 0
    parts_m, parts_v, hashes = load_years(raw, year_start, year_end, country)
    panel_dedupe = dict(DEDUPE)
    if not parts_m:
        raise SystemExit("no years loaded")
    modis = pd.concat(parts_m, ignore_index=True)
    viirs = pd.concat(parts_v, ignore_index=True)

    # active cells = any Aqua or SNPP fire in loaded years
    # shortcut: without 2003–2025 full archive, active set = overlap-year fires only
    cells = pd.concat([
        modis[["cell_id", "lat", "lon"]],
        viirs.merge(modis[["cell_id", "lat", "lon"]].drop_duplicates("cell_id"), on="cell_id", how="left"),
    ], ignore_index=True)
    # fill lat/lon for VIIRS-only cells from cell_id parse
    miss = cells["lat"].isna()
    if miss.any():
        parsed = cells.loc[miss, "cell_id"].str.extract(r"g_(-?\d+\.\d+)_(-?\d+\.\d+)")
        cells.loc[miss, "lat"] = parsed[0].astype(float).to_numpy()
        cells.loc[miss, "lon"] = parsed[1].astype(float).to_numpy()
    active = cells.dropna(subset=["lat", "lon"]).drop_duplicates("cell_id")[["cell_id", "lat", "lon"]]
    years = sorted(modis["year"].unique())
    print(f"active_cells={len(active)} years={years}")

    panel = dense_panel(active, years)
    keys = ["cell_id", "year", "month", "daynight"]
    feat = panel.merge(
        modis.drop(columns=["lat", "lon"], errors="ignore"),
        on=keys, how="left",
    )
    feat = feat.merge(viirs, on=keys, how="left")
    num_fill = [
        "m_count", "m_frp_sum", "m_frp_mean", "m_frp_max", "m_frp_p50",
        "m_scan_mean", "m_track_mean", "m_scan_max", "m_frac_offnadir",
        "m_frac_high", "m_frac_nominal", "v_count", "v_frp_sum",
    ]
    for c in num_fill:
        if c not in feat.columns:
            feat[c] = 0.0
        feat[c] = feat[c].fillna(0.0)

    feat = add_other_dn(feat)
    feat["m_count_other_dn"] = feat["m_count_other_dn"].fillna(0.0)
    feat = add_lags(feat)
    print("neighbors ...")
    feat = add_neighbors(feat)

    clim = load_clim_modis(raw, country=country)
    if clim is None:
        print("WARNING: no 2003–2011 Aqua; clim from loaded years by month")
        clim = modis.groupby(["cell_id", "month", "daynight"], as_index=False).agg(
            m_clim_mean=("m_count", "mean"),
            m_clim_frp=("m_frp_mean", "mean"),
        )
        clim_source = "loaded_years_fallback"
    else:
        clim_source = "2003_2011"
    feat = feat.merge(clim, on=["cell_id", "month", "daynight"], how="left")
    feat["m_clim_mean"] = feat["m_clim_mean"].fillna(0.0)
    feat["m_clim_frp"] = feat["m_clim_frp"].fillna(0.0)

    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)
    feat["is_night"] = (feat["daynight"] == "N").astype(int)

    assert_no_leakage(FEATURE_COLS)
    # keep year/v_count for splits/targets only; not in FEATURE_COLS
    path = out / f"feature_table_{country}.parquet"
    feat.to_parquet(path, index=False)
    meta = {
        "rows": len(feat),
        "years": [int(y) for y in years],
        "n_cells": int(active["cell_id"].nunique()),
        "feature_cols": FEATURE_COLS,
        "clim_source": clim_source,
        "clim_years": [
            y for y in range(2003, 2012)
            if (raw / "modis" / f"modis_{y}_{country}.csv").exists()
        ],
        "dedupe_panel_exact_kept": {"modis": panel_dedupe["modis_exact"], "viirs": panel_dedupe["viirs_exact"]},
        "dedupe_panel_v2_kept": {"modis": panel_dedupe["modis_v2"], "viirs": panel_dedupe["viirs_v2"]},
        "dedupe_v2_dropped": {
            "modis": panel_dedupe["modis_exact"] - panel_dedupe["modis_v2"],
            "viirs": panel_dedupe["viirs_exact"] - panel_dedupe["viirs_v2"],
        },
        "raw_sha256": hashes,
    }
    (out / f"feature_meta_{country}.json").write_text(json.dumps(meta), encoding="utf-8")
    print(
        f"dedupe exact kept modis={panel_dedupe['modis_exact']} viirs={panel_dedupe['viirs_exact']} "
        f"v2 kept modis={panel_dedupe['modis_v2']} viirs={panel_dedupe['viirs_v2']} "
        f"dropped modis={meta['dedupe_v2_dropped']['modis']} viirs={meta['dedupe_v2_dropped']['viirs']}"
    )
    print(f"clim_source={clim_source} wrote {path} rows={len(feat)}")
    return path

