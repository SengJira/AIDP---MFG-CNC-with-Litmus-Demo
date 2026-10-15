#!/usr/bin/env python3
"""Generate the missing synthetic CNC-01 Month 3 and CNC-02 CSVs.

Noise levels are sampled from CNC-01's clean window (2024-01-01..2024-01-12).
The generator is deterministic for a given seed.
"""
import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

COLUMNS = [
    "Timestamp",
    "SPINDLE_RPM",
    "SPINDLE_LOAD_PCT",
    "MOTOR_CURRENT_A",
    "VIB_X_MM_S",
    "VIB_Y_MM_S",
    "BEARING_TEMP_C",
    "COOLANT_FLOW_LPM",
    "COOLANT_PRESSURE_BAR",
    "FEED_RATE_MM_MIN",
    "AIR_PRESSURE_BAR",
    "AMBIENT_TEMP_C",
    "ACOUSTIC_DB",
]


def load_clean_baseline(raw_dir: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(raw_dir, "CNC01_SpindleLine_60days_hourly.csv"))
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    clean = df[df["Timestamp"] < "2024-01-13"].copy()
    if len(clean) == 0:
        raise ValueError("No clean baseline rows found in CNC01 file")
    return clean


def build_index(start: datetime, hours: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=hours, freq="h")


def make_trend(idx: pd.DatetimeIndex, start_ts: datetime, end_ts: datetime, peak: float) -> np.ndarray:
    """Return a 0..peak smooth (sinusoidal) multiplier active between start and end."""
    t = np.zeros(len(idx), dtype=float)
    in_window = (idx >= start_ts) & (idx <= end_ts)
    if not in_window.any():
        return t
    positions = (idx[in_window] - start_ts) / (end_ts - start_ts)
    # smooth rise: half of a sine wave, then hold at 1.0 at the end
    t[in_window] = np.sin(np.pi * positions / 2) * peak
    return t


def generate_series(
    idx: pd.DatetimeIndex,
    base_means: pd.Series,
    residuals: pd.DataFrame,
    rng: np.random.Generator,
    vib_x_scale: float = 1.0,
    trend_specs: dict | None = None,
    seed_shift: int = 0,
) -> pd.DataFrame:
    """Generate one full sensor reading series using sampled residuals and optional trends."""
    n = len(idx)
    out = pd.DataFrame(index=idx, columns=[c for c in COLUMNS if c != "Timestamp"])

    # sample residual indices for each row
    base_ix = np.arange(n)
    res_ix = rng.integers(0, len(residuals), size=n)

    for col in out.columns:
        mean = base_means[col]
        if col == "VIB_X_MM_S":
            mean *= vib_x_scale

        # base value per row = mean + residual from CNC-01 clean window
        base = mean + residuals[col].values[res_ix]

        # deterministic cycle per column: tiny hour-of-day-ish oscillation
        cycle = np.sin((base_ix + seed_shift) * 2 * np.pi / 24) * base_means[col] * 0.01
        values = base + cycle

        if trend_specs and col in trend_specs:
            spec = trend_specs[col]
            trend = make_trend(idx, spec["start"], spec["end"], spec["peak"])
            values = values + trend

        # ensure no negative or impossible values
        if "TEMP" in col or "PRESSURE" in col or "FLOW" in col or "CURRENT" in col or "LOAD" in col or "DB" in col or "RPM" in col or "RATE" in col:
            values = np.clip(values, 0, None)

        out[col] = values

    out.insert(0, "Timestamp", idx.strftime("%Y-%m-%d %H:%M:%S"))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    clean = load_clean_baseline(args.raw_dir)
    residuals = clean.drop(columns=["Timestamp"]) - clean.drop(columns=["Timestamp"]).mean()
    base_means = clean.drop(columns=["Timestamp"]).mean()

    # ---- CNC-01 Month 3 ----
    # 31 days: 2024-03-01 00:00..2024-03-31 23:00 (744 rows)
    m3_idx = build_index(datetime(2024, 3, 1), 744)
    m3_trends = {
        "VIB_X_MM_S": {"start": datetime(2024, 3, 25), "end": datetime(2024, 3, 31, 23), "peak": 1.35},
        "VIB_Y_MM_S": {"start": datetime(2024, 3, 25), "end": datetime(2024, 3, 31, 23), "peak": 0.90},
        "ACOUSTIC_DB": {"start": datetime(2024, 3, 25), "end": datetime(2024, 3, 31, 23), "peak": 4.5},
        "BEARING_TEMP_C": {"start": datetime(2024, 3, 25), "end": datetime(2024, 3, 31, 23), "peak": 2.5},
    }
    m3 = generate_series(m3_idx, base_means, residuals, rng, vib_x_scale=1.0, trend_specs=m3_trends, seed_shift=1000)
    m3_path = os.path.join(args.raw_dir, "CNC01_SpindleLine_Month3_hourly.csv")
    m3.to_csv(m3_path, index=False)
    print(f"Wrote {m3_path}: {len(m3)} rows")

    # ---- CNC-02 ----
    # 30 days: 2024-04-01 00:00..2024-04-30 23:00 (720 rows)
    c2_idx = build_index(datetime(2024, 4, 1), 720)
    c2_trends = {
        "VIB_X_MM_S": {"start": datetime(2024, 4, 11), "end": datetime(2024, 4, 30, 23), "peak": 2.10},
        "VIB_Y_MM_S": {"start": datetime(2024, 4, 11), "end": datetime(2024, 4, 30, 23), "peak": 1.30},
        "BEARING_TEMP_C": {"start": datetime(2024, 4, 11), "end": datetime(2024, 4, 30, 23), "peak": 4.5},
        "ACOUSTIC_DB": {"start": datetime(2024, 4, 11), "end": datetime(2024, 4, 30, 23), "peak": 6.5},
    }
    c2 = generate_series(c2_idx, base_means, residuals, rng, vib_x_scale=1.175, trend_specs=c2_trends, seed_shift=2000)
    c2_path = os.path.join(args.raw_dir, "CNC02_SpindleLine_30days_hourly.csv")
    c2.to_csv(c2_path, index=False)
    print(f"Wrote {c2_path}: {len(c2)} rows")


if __name__ == "__main__":
    main()
