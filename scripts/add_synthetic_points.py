"""Add point-level synthetic VIIRS (2003-2011) to the delivery archive, one gzip shard per month.

    python scripts/add_synthetic_points.py <DELIVERY>/results

Reads results/{Country}/synthetic_viirs/viirs-sim_{year}_{Country}.csv, writes
frontend/public/data/delivery/{Country}/synthetic/{YYYY-MM}.json.gz (same compact rows as points/)
and adds months[m].synthetic = {url, count} to that country's manifest.json.
"""
import gzip
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "data" / "delivery"


def rows(df: pd.DataFrame) -> list:
    num = lambda c, n: pd.to_numeric(df[c], errors="coerce").round(n)
    packed = pd.DataFrame({
        "lat": num("latitude", 5), "lon": num("longitude", 5), "date": df["acq_date"],
        "time": df["acq_time"].astype(str).str.zfill(4), "satellite": "S-NPP", "sensor": "VIIRS",
        "confidence": df["confidence"].astype(str), "frp": num("frp", 2), "dn": df["daynight"],
        "brightness": num("bright_ti4", 2), "scan": num("scan", 3), "track": num("track", 3),
        "bright5": num("bright_ti5", 2), "synthetic": True, "origin": df["sim_source"].astype(str),
        "parent": df["sim_parent_modis"].astype(str), "run": df["sim_run"].astype(int)})
    return packed.astype(object).where(packed.notna(), None).values.tolist()


def main(results: Path) -> None:
    for folder in sorted(results.glob("*/synthetic_viirs")):
        country = folder.parent.name
        manifest_path = ROOT / country / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        (ROOT / country / "synthetic").mkdir(exist_ok=True)
        for csv in sorted(folder.glob("viirs-sim_*.csv")):
            df = pd.read_csv(csv, dtype={"acq_time": str, "sim_parent_modis": str})
            for month, g in df.groupby(df["acq_date"].str[:7]):
                if month not in manifest["months"]:
                    continue
                url = f"synthetic/{month}.json.gz"
                with gzip.open(ROOT / country / url, "wt", encoding="utf-8") as fh:
                    json.dump(rows(g), fh, separators=(",", ":"))
                manifest["months"][month]["synthetic"] = {"url": url, "count": int(len(g))}
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
        n = sum(m.get("synthetic", {}).get("count", 0) for m in manifest["months"].values())
        print(f"{country}: {n} synthetic points")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
