#!/usr/bin/env python3
"""CNC Spindle Health — anomaly detection job.

Runs PySpark locally (small data) and writes anomaly scores/events to Parquet.
Optional Trino write and optional seed-session from a local JSON label bank.

Usage:
    python jobs/detect.py --equipment-id CNC-01 --run-id cnc01_baseline
    python jobs/detect.py --equipment-id CNC-02 --run-id cnc02_seeded --seed-session cnc01_baseline
"""
import argparse
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from pyspark.sql import SparkSession
from scipy.stats import kurtosis
from sklearn.ensemble import IsolationForest

PROCESSED = Path("data/processed")
RAW = Path("data/raw")
SIGNALS = [
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


def load_sensor_readings(equipment_id: str, start_ts: str | None = None, end_ts: str | None = None) -> pd.DataFrame:
    parquet = PROCESSED / "sensor_readings.parquet"
    if parquet.exists():
        df = pd.read_parquet(parquet)
    else:
        raise FileNotFoundError("data/processed/sensor_readings.parquet not found; run land_data first")
    df = df[df["equipment_id"] == equipment_id].copy()
    df["ts"] = pd.to_datetime(df["Timestamp"])
    if start_ts:
        df = df[df["ts"] >= start_ts]
    if end_ts:
        df = df[df["ts"] < end_ts]
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def load_seed_data(session_name: str):
    bank_path = PROCESSED / "seed_label_bank.json"
    labels_path = PROCESSED / "seed_labels.json"
    bank = []
    dismissed = []
    if bank_path.exists():
        with open(bank_path) as f:
            for row in json.load(f):
                if row.get("session_name") == session_name:
                    bank.append(row)
    if labels_path.exists():
        with open(labels_path) as f:
            for row in json.load(f):
                if row.get("session_name") == session_name:
                    if row.get("label_type") == "dismissed":
                        dismissed.append(row)
    return bank, dismissed


def compute_detectors(df: pd.DataFrame, baseline_hours: int, seed_bank: list, seed_dismissed: list) -> pd.DataFrame:
    baseline = df.iloc[:baseline_hours].copy()
    scores = df[["ts", "equipment_id"]].copy()

    # 1) baseline stats
    means = baseline[SIGNALS].mean()
    stds = baseline[SIGNALS].std().replace(0, 1e-9)
    q1 = baseline[SIGNALS].quantile(0.25)
    q3 = baseline[SIGNALS].quantile(0.75)
    iqr = q3 - q1

    # Z-Score on a 6-hour rolling mean to avoid single-hour noise
    rolling_mean = df[SIGNALS].rolling(window=6, min_periods=6).mean()
    z = (rolling_mean - means) / stds

    z_threshold = 3.0
    for sig in SIGNALS:
        flags = z[sig].abs() > z_threshold
        scores[f"zscore_{sig}_is_anomaly"] = flags
        scores[f"zscore_{sig}_score"] = z[sig].abs()

    # 2) IQR per signal
    for sig in SIGNALS:
        lo = q1[sig] - 1.5 * iqr[sig]
        hi = q3[sig] + 1.5 * iqr[sig]
        flags = (df[sig] < lo) | (df[sig] > hi)
        scores[f"iqr_{sig}_is_anomaly"] = flags
        scores[f"iqr_{sig}_score"] = np.maximum(df[sig] - hi, lo - df[sig]) / (iqr[sig] + 1e-9)

    # 3) EWMA control chart per signal
    for sig in SIGNALS:
        ewma = df[sig].ewm(span=12, min_periods=24, adjust=False).mean()
        ewmstd = df[sig].ewm(span=12, min_periods=24, adjust=False).std().replace(0, 1e-9)
        deviations = (df[sig] - ewma).abs() / ewmstd
        flags = deviations > 2.5
        scores[f"ewma_{sig}_is_anomaly"] = flags
        scores[f"ewma_{sig}_score"] = deviations

    # 4) multivariate Isolation Forest trained on baseline
    if_model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )
    if_model.fit(baseline[SIGNALS].values)
    if_scores = if_model.decision_function(df[SIGNALS].values)
    # threshold below the minimum baseline score, so the baseline itself is never flagged
    baseline_if_scores = if_model.decision_function(baseline[SIGNALS].values)
    threshold = float(np.min(baseline_if_scores)) - 1e-6
    flags = if_scores < threshold
    scores["if_is_anomaly"] = flags
    scores["if_score"] = -if_scores  # higher = more anomalous

    # do not flag the baseline rows (they are the reference)
    not_eval = np.zeros(len(df), dtype=bool)
    not_eval[:baseline_hours] = True
    for sig in SIGNALS:
        for det in ["zscore", "iqr", "ewma"]:
            scores.loc[not_eval, f"{det}_{sig}_is_anomaly"] = False
    scores.loc[not_eval, "if_is_anomaly"] = False

    # keep raw signal columns for event signature/kurtosis
    for sig in SIGNALS:
        scores[sig] = df[sig].values
    return scores


def build_anomaly_scores(scores: pd.DataFrame, run_id: str, equipment_id: str) -> pd.DataFrame:
    # detector labels: each detector flags any signal at a given hour
    detectors = ["zscore", "iqr", "ewma"]
    hour_flags = pd.DataFrame(index=scores.index)
    for det in detectors:
        cols = [c for c in scores.columns if c.startswith(f"{det}_") and c.endswith("_is_anomaly")]
        hour_flags[det] = scores[cols].any(axis=1)
    hour_flags["if"] = scores["if_is_anomaly"]

    hour_consensus = hour_flags[detectors + ["if"]].mean(axis=1)

    rows = []
    for sig in SIGNALS:
        for det in ["zscore", "iqr", "ewma"]:
            is_a = scores[f"{det}_{sig}_is_anomaly"].values
            score_v = scores[f"{det}_{sig}_score"].values
            rows.append(
                pd.DataFrame(
                    {
                        "run_id": run_id,
                        "equipment_id": equipment_id,
                        "ts": scores["ts"].values,
                        "signal": sig,
                        "detector": det,
                        "score": score_v,
                        "is_anomaly": is_a,
                        "consensus_score": hour_consensus.values,
                    }
                )
            )
    # add multivariate if as a detector/signal per signal? we keep it as a special detector 'if' per signal
    for sig in SIGNALS:
        rows.append(
            pd.DataFrame(
                {
                    "run_id": run_id,
                    "equipment_id": equipment_id,
                    "ts": scores["ts"].values,
                    "signal": sig,
                    "detector": "if",
                    "score": scores["if_score"].values,
                    "is_anomaly": scores["if_is_anomaly"].values,
                    "consensus_score": hour_consensus.values,
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    return out


def build_anomaly_events(
    scores: pd.DataFrame,
    run_id: str,
    equipment_id: str,
    dismissed: list,
) -> pd.DataFrame:
    detectors = ["zscore", "iqr", "ewma"]
    hour_flags = pd.DataFrame(index=scores.index)
    for det in detectors:
        cols = [c for c in scores.columns if c.startswith(f"{det}_") and c.endswith("_is_anomaly")]
        hour_flags[det] = scores[cols].any(axis=1)
    hour_flags["if"] = scores["if_is_anomaly"]
    hour_consensus = hour_flags[detectors + ["if"]].mean(axis=1)

    # group consecutive hours with consensus >= 0.5
    threshold = 0.5
    is_event = hour_consensus >= threshold
    events = []
    start = None
    for i, flag in enumerate(is_event):
        if flag and start is None:
            start = i
        if (not flag or i == len(is_event) - 1) and start is not None:
            end = i if not flag else i + 1
            if end - start >= 2:  # at least 2 hours
                events.append((start, end - 1))
            start = None

    # Build event list
    event_rows = []
    for start_idx, end_idx in events:
        window = scores.iloc[start_idx : end_idx + 1]
        start_ts = window["ts"].iloc[0]
        end_ts = window["ts"].iloc[-1]
        peak_ts = window.loc[window["if_score"].idxmax(), "ts"]

        # top signals in this window by per-signal consensus
        per_signal = {}
        for sig in SIGNALS:
            sig_cons = 0.0
            for det in ["zscore", "iqr", "ewma"]:
                col = f"{det}_{sig}_is_anomaly"
                sig_cons += window[col].astype(int).sum()
            per_signal[sig] = sig_cons
        top_sigs = sorted(per_signal.items(), key=lambda x: x[1], reverse=True)
        top_sig_names = [s for s, _ in top_sigs if _ > 0][:5]

        # severity by max consensus
        max_cons = hour_consensus.iloc[start_idx : end_idx + 1].max()
        n_sigs = len(top_sig_names)
        if max_cons >= 0.75 and n_sigs >= 3:
            severity = "high"
        elif max_cons >= 0.5:
            severity = "medium"
        else:
            severity = "low"

        # signature: impulsive if kurtosis of the consensus or any top signal > threshold
        sig_type = "smooth"
        for sig in top_sig_names[:3]:
            vals = window[sig].values
            if len(vals) > 3:
                k = kurtosis(vals, fisher=False)
                # ratio peak to median
                med = np.median(vals)
                peak = np.max(vals)
                if k > 5.0 or (med > 0 and peak / med > 2.0):
                    sig_type = "impulsive"
                    break

        event_rows.append(
            {
                "event_id": str(uuid.uuid4()),
                "run_id": run_id,
                "equipment_id": equipment_id,
                "signals": top_sig_names,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "peak_ts": peak_ts,
                "severity": severity,
                "signature": sig_type,
            }
        )

    # Apply dismissed labels: remove events whose top signal matches a dismissed label and overlap
    filtered = []
    for ev in event_rows:
        suppressed = False
        for lbl in dismissed:
            sig = lbl.get("signal")
            if sig in ev["signals"]:
                ls = pd.to_datetime(lbl.get("start_ts"))
                le = pd.to_datetime(lbl.get("end_ts"))
                # overlap of the dismissed window and the event window
                if ev["start_ts"] <= le and ev["end_ts"] >= ls:
                    suppressed = True
                    break
        if not suppressed:
            filtered.append(ev)

    events_df = pd.DataFrame(filtered)
    return events_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--equipment-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-ts", default=None)
    parser.add_argument("--end-ts", default=None)
    parser.add_argument("--seed-session", default=None)
    parser.add_argument("--baseline-hours", type=int, default=168)  # 7 days
    parser.add_argument("--output-dir", default="data/processed")
    args = parser.parse_args()

    spark = SparkSession.builder.master("local[4]").appName("cnc_detect").getOrCreate()
    spark.conf.set("spark.sql.shuffle.partitions", "4")
    spark.conf.set("spark.sql.adaptive.enabled", "false")
    spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "false")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.output_dir) / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_sensor_readings(args.equipment_id, args.start_ts, args.end_ts)
    seed_bank, dismissed = [], []
    if args.seed_session:
        seed_bank, dismissed = load_seed_data(args.seed_session)

    scores = compute_detectors(df, args.baseline_hours, seed_bank, dismissed)
    scores["equipment_id"] = args.equipment_id

    scores_out = build_anomaly_scores(scores, args.run_id, args.equipment_id)
    scores_spark = spark.createDataFrame(scores_out)
    scores_spark.write.mode("overwrite").parquet(str(out_dir / "anomaly_scores.parquet"))
    print(f"Wrote {len(scores_out)} anomaly score rows to {out_dir}/anomaly_scores.parquet")

    events = build_anomaly_events(scores, args.run_id, args.equipment_id, dismissed)
    if len(events):
        events_spark = spark.createDataFrame(events)
        events_spark.write.mode("overwrite").parquet(str(out_dir / "anomaly_events.parquet"))
        print(f"Wrote {len(events)} events to {out_dir}/anomaly_events.parquet")
    else:
        print("No events produced")

    spark.stop()


if __name__ == "__main__":
    main()
