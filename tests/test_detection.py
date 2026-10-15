"""Acceptance tests for the CNC Spindle Health detection job.

Tests run the PySpark detection job offline and verify the key findings
match the ARIA guide and acceptance criteria.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"


def run_cmd(cmd, **kwargs):
    """Run a shell command from the repo root, returning stdout."""
    env = dict(os.environ) if "env" in kwargs else os.environ
    return subprocess.run(cmd, cwd=str(ROOT), check=True, text=True, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def ensure_data():
    """Ensure the processed Parquet, seed labels and detection outputs exist."""
    if not (PROCESSED / "sensor_readings.parquet").exists():
        run_cmd(["python3", "scripts/land_data.py", "--no-s3", "--no-trino"])
    if not (PROCESSED / "seed_label_bank.json").exists():
        run_cmd(["python3", "scripts/seed_label_bank.py", "--no-trino"])

    # baseline run
    run_cmd(
        [
            "python3",
            "jobs/detect.py",
            "--equipment-id",
            "CNC-01",
            "--run-id",
            "cnc01_baseline",
            "--start-ts",
            "2024-01-01",
            "--end-ts",
            "2024-03-01",
            "--baseline-hours",
            "360",
        ]
    )
    # seeded re-run on CNC-01 with dismissed drift
    run_cmd(
        [
            "python3",
            "jobs/detect.py",
            "--equipment-id",
            "CNC-01",
            "--run-id",
            "cnc01_seeded",
            "--start-ts",
            "2024-01-01",
            "--end-ts",
            "2024-03-01",
            "--seed-session",
            "cnc01_baseline",
            "--baseline-hours",
            "360",
        ]
    )
    # cross-equipment seeded run on CNC-02
    run_cmd(
        [
            "python3",
            "jobs/detect.py",
            "--equipment-id",
            "CNC-02",
            "--run-id",
            "cnc02_seeded",
            "--start-ts",
            "2024-04-01",
            "--end-ts",
            "2024-05-01",
            "--seed-session",
            "cnc01_baseline",
            "--baseline-hours",
            "240",
        ]
    )


def load_scores(run_id: str) -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / run_id / "anomaly_scores.parquet")


def load_events(run_id: str) -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / run_id / "anomaly_events.parquet")


def test_cnc01_top_signals():
    scores = load_scores("cnc01_baseline")
    top = scores.groupby("signal")["is_anomaly"].sum().sort_values(ascending=False)
    top3 = set(top.head(3).index.tolist())
    assert "VIB_X_MM_S" in top3, f"VIB_X not in top-3: {top3}"
    assert "VIB_Y_MM_S" in top3, f"VIB_Y not in top-3: {top3}"


def test_cnc01_bearing_event():
    events = load_events("cnc01_baseline")
    target_start = datetime(2024, 1, 29)
    target_end = datetime(2024, 2, 4)
    match = events[
        (events["start_ts"] <= target_start)
        & (events["end_ts"] >= target_end)
        & (events["severity"] == "high")
        & (events["signature"] == "impulsive")
    ]
    assert len(match) >= 1, "No high/impulsive event covering 01-29..02-04"


def test_cnc01_first_vibx_flag():
    scores = load_scores("cnc01_baseline")
    vibx = scores[(scores["signal"] == "VIB_X_MM_S") & (scores["is_anomaly"] == True)]
    first = vibx["ts"].min()
    assert first is not None and not pd.isna(first)
    assert datetime(2024, 1, 16) <= first < datetime(2024, 1, 20), f"first VIB_X flag at {first}"


def test_cnc01_coolant_event():
    events = load_events("cnc01_baseline")
    cs, ce = datetime(2024, 2, 13), datetime(2024, 2, 17)
    match = events[
        (events["start_ts"] <= ce)
        & (events["end_ts"] >= cs)
        & (events["signals"].apply(lambda s: "COOLANT_FLOW_LPM" in s))
        & (events["signals"].apply(lambda s: "COOLANT_PRESSURE_BAR" in s))
    ]
    assert len(match) >= 1, "No coolant event with flow and pressure signals"


def test_cnc01_drift_suppression():
    events = load_events("cnc01_seeded")
    cs, ce = datetime(2024, 2, 20), datetime(2024, 2, 26)
    current_events = events[
        (events["start_ts"] <= ce)
        & (events["end_ts"] >= cs)
        & (events["signals"].apply(lambda s: "MOTOR_CURRENT_A" in s))
        & (events["severity"] == "high")
    ]
    assert len(current_events) == 0, f"High-severity current drift event still present: {current_events}"


def test_cnc02_seeded_vibx():
    scores = load_scores("cnc02_seeded")
    vibx = scores[(scores["signal"] == "VIB_X_MM_S") & (scores["is_anomaly"] == True)]
    first = vibx["ts"].min()
    assert first is not None and not pd.isna(first)
    assert datetime(2024, 4, 10) <= first < datetime(2024, 4, 14), f"CNC02 first VIB_X flag at {first}"

    events = load_events("cnc02_seeded")
    match = events[
        (events["signature"] == "smooth")
        & (events["severity"] == "high")
        & (events["signals"].apply(lambda s: "VIB_X_MM_S" in s))
    ]
    assert len(match) >= 1, "No high/smooth event with VIB_X for CNC-02"
