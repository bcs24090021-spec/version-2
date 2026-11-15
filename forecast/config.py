"""Settings for spread_model.py (daily forecast only needs BASE)."""
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw_data"  # only needed to retrain
