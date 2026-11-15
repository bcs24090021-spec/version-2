"""MODIS-VIIRS footprint pairing and duplicate detection (used by sim_viirs.py).

A candidate pair is a same-time / same-place hypothesis, not proof of one fire.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
from scipy.spatial import cKDTree

GEOD = Geod(ellps="WGS84")
GEOD = Geod(ellps="WGS84")
_TO_6933 = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
TIERS = {"strict": 5, "medium": 30, "loose": 90}
FOOTPRINT_COARSE_M = 3100.0  # 0.5*(4.8+0.8)*1.1 km before index pad
# EPSG:6933 stretches N-S near the equator (~1.155x); pad k-d search by 1.25 so
# true geodesic neighbours are not dropped before the exact filter.
KD_PAD = 1.25


def mark_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Mark same-sensor same-minute footprint-overlap duplicates; keep max FRP as representative."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    out = df.copy()
    pos = np.arange(len(out))
    lat, lon = out["lat"].to_numpy(float), out["lon"].to_numpy(float)
    scan, track = out["scan"].to_numpy(float), out["track"].to_numpy(float)
    ii, jj = [], []
    for _, g in out.groupby(["sensor", "tmin"], sort=False).indices.items():
        if len(g) < 2:
            continue
        g = pos[g]
        # 5 km coarse search as before; overlap needs |dx|<scan and |dy|<track, so a smaller radius
        # covering 1.7 x the largest pixel (EPSG:6933 stretch x diagonal) finds exactly the same links
        r = min(5000.0, 1700.0 * float(max(scan[g].max(), track[g].max(), 0.0)))
        pr = cKDTree(np.column_stack([out["x"].to_numpy()[g], out["y"].to_numpy()[g]])).query_pairs(r, output_type="ndarray")
        if len(pr):
            ii.append(g[pr[:, 0]]); jj.append(g[pr[:, 1]])
    i = np.concatenate(ii) if ii else np.empty(0, int)
    j = np.concatenate(jj) if jj else np.empty(0, int)
    sc, tr = np.minimum(scan[i], scan[j]), np.minimum(track[i], track[j])
    lo, hi = np.minimum(i, j), np.maximum(i, j)  # original measured dx at the earlier row's latitude
    dx = np.abs(lon[i] - lon[j]) * 111.32 * np.cos(np.radians(lat[lo]))
    dy = np.abs(lat[i] - lat[j]) * 110.57
    with np.errstate(divide="ignore", invalid="ignore"):
        overlap = np.clip(1 - dx / sc, 0, None) * np.clip(1 - dy / tr, 0, None)
    link = (sc > 0) & (tr > 0) & (overlap > 0.3)
    n_dup_links = int(link.sum())
    graph = coo_matrix((np.ones(n_dup_links), (lo[link], hi[link])), shape=(len(out), len(out)))
    _, comp = connected_components(graph, directed=False)
    frp = out["frp"].fillna(-np.inf).to_numpy(float)
    order = np.lexsort((pos, -frp, comp))  # per component: highest FRP, first row on ties
    first = np.r_[True, comp[order][1:] != comp[order][:-1]]
    rep_arr = np.zeros(comp.max() + 1 if len(out) else 0, int)
    rep_arr[comp[order][first]] = order[first]
    rep_pos = rep_arr[comp]
    sizes = np.bincount(comp) if len(out) else np.array([], int)
    is_rep = rep_pos == pos
    ids = out["record_id"].to_numpy()
    out["dup_of"] = np.where(is_rep, "", ids[rep_pos])
    out["is_representative"] = is_rep
    n_marked = int((~is_rep).sum())
    summary = {
        "n_points": len(out),
        "n_duplicate_marked": n_marked,
        "n_components_with_dups": int((sizes > 1).sum()),
        "n_overlap_links": n_dup_links,
        "dup_pct": round(100.0 * n_marked / len(out), 1) if len(out) else 0.0,
        "dup_pct_modis": _dup_pct(out, "MODIS"),
        "dup_pct_viirs": _dup_pct(out, "VIIRS"),
    }
    return out, summary


def _dup_pct(df: pd.DataFrame, sensor: str) -> float:
    sub = df[df["sensor"] == sensor]
    if sub.empty:
        return 0.0
    return round(100.0 * (~sub["is_representative"]).sum() / len(sub), 1)


def geodesic_m(lon1, lat1, lon2, lat2) -> np.ndarray:
    _, _, d = GEOD.inv(
        np.asarray(lon1, float), np.asarray(lat1, float),
        np.asarray(lon2, float), np.asarray(lat2, float),
    )
    return np.asarray(d, dtype=float)


def pair_candidates(
    df: pd.DataFrame,
    window_min: int,
    *,
    radius_m: float,
    viirs_tmin_shift: int = 0,
    use_representatives_only: bool = True,
) -> pd.DataFrame:
    """Many-to-many MODIS-VIIRS pairs within radius_m geodesic and |dt|<=window_min.

    Returns columns including dx_km, dy_km for footprint filtering downstream.
    """
    m = df[df["sensor"] == "MODIS"]
    v = df[df["sensor"] == "VIIRS"]
    if use_representatives_only:
        m = m[m["is_representative"]]
        v = v[v["is_representative"]]
    if m.empty or v.empty:
        return pd.DataFrame(columns=[
            "modis_record_id", "viirs_record_id", "distance_m", "dx_km", "dy_km",
            "dt_min", "daynight", "modis_scan", "modis_track", "viirs_scan", "viirs_track",
        ])

    v = v.copy()
    if viirs_tmin_shift:
        v["tmin"] = v["tmin"] + viirs_tmin_shift
        v["day"] = v["tmin"] // 1440

    v_by_day = {d: g for d, g in v.groupby("day")}
    span = math.ceil(window_min / 1440) if window_min else 0
    rows = []
    for day, mg in m.groupby("day"):
        parts = [
            v_by_day[d]
            for d in range(day - span - (1 if window_min else 0), day + span + 2)
            if d in v_by_day
        ]
        if not parts:
            continue
        vg = pd.concat(parts)
        t0, t1 = int(mg["tmin"].min()) - window_min, int(mg["tmin"].max()) + window_min
        vg = vg[(vg["tmin"] >= t0) & (vg["tmin"] <= t1)]
        if vg.empty:
            continue
        tree = cKDTree(vg[["x", "y"]].to_numpy())
        hits = tree.query_ball_point(mg[["x", "y"]].to_numpy(), r=radius_m * KD_PAD)
        vt = vg["tmin"].to_numpy()
        vlon = vg["lon"].to_numpy()
        vlat = vg["lat"].to_numpy()
        vscan = vg["scan"].to_numpy()
        vtrack = vg["track"].to_numpy()
        vids = vg["record_id"].to_numpy()
        for i, js in enumerate(hits):
            if not js:
                continue
            js = np.asarray(js, dtype=np.int64)
            dt = vt[js] - int(mg["tmin"].iat[i])
            keep = np.abs(dt) <= window_min
            if not keep.any():
                continue
            js, dt = js[keep], dt[keep]
            mlat = float(mg["lat"].iat[i])
            mlon = float(mg["lon"].iat[i])
            # Keep full-precision geodesic metres for the exact filter (do not round first).
            d = geodesic_m(np.full(len(js), mlon), np.full(len(js), mlat), vlon[js], vlat[js])
            ok = d <= radius_m
            js, dt, d = js[ok], dt[ok], d[ok]
            if len(js) == 0:
                continue
            coslat = math.cos(math.radians(mlat))
            dx = np.abs(vlon[js] - mlon) * 111.32 * coslat
            dy = np.abs(vlat[js] - mlat) * 110.57
            mid = mg["record_id"].iat[i]
            mdn = mg["daynight"].iat[i]
            msc = float(mg["scan"].iat[i])
            mtr = float(mg["track"].iat[i])
            n = len(js)
            rows.append((np.full(n, mid, dtype=object), vids[js], d, dx, dy, dt,
                         np.full(n, mdn, dtype=object), np.full(n, msc), np.full(n, mtr), vscan[js], vtrack[js]))
    cols = [
        "modis_record_id", "viirs_record_id", "distance_m", "dx_km", "dy_km",
        "dt_min", "daynight", "modis_scan", "modis_track", "viirs_scan", "viirs_track",
    ]
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({c: np.concatenate([r[k] for r in rows]) for k, c in enumerate(cols)})
    out = out.astype({c: float for c in ("distance_m", "dx_km", "dy_km", "modis_scan", "modis_track", "viirs_scan", "viirs_track")})
    return out.astype({"dt_min": np.int64})


def apply_rule(cands: pd.DataFrame, rule: str) -> pd.DataFrame:
    if cands.empty:
        return cands.iloc[0:0].copy()
    if rule == "fixed1km":
        # Compare unrounded geodesic metres (rounding 1000.04 -> 1000.0 would falsely keep).
        keep = cands["distance_m"] <= 1000.0
    elif rule == "footprint":
        keep = (
            (cands["dx_km"] <= (cands["modis_scan"] + cands["viirs_scan"]) / 2.0)
            & (cands["dy_km"] <= (cands["modis_track"] + cands["viirs_track"]) / 2.0)
        )
    else:
        raise ValueError(rule)
    out = cands.loc[keep].copy()
    out["rule"] = rule
    return out


