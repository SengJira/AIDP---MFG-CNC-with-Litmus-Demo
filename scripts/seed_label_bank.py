#!/usr/bin/env python3
"""Pre-seed the label bank and initial labels from the ground-truth guide.

Creates local JSON files used by the detection job in seed-session mode and
(optionally) inserts the same rows into Trino.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import trino
from trino.auth import BasicAuthentication

PROCESSED = Path("data/processed")
CATALOG = "js_manuf_ice"
SCHEMA = "smart_mfg"

SESSION = "cnc01_baseline"
EQUIPMENT_TYPE = "CNC Machining Center"


def tznow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_label_bank():
    """Promoted, reusable labels from the CNC-01 60-day dataset."""
    rows = [
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-vibx-bearing",
            "signal": "VIB_X_MM_S",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "impulsive",
                    "start_ts": "2024-01-16 00:00:00",
                    "end_ts": "2024-02-06 23:00:00",
                    "peak_ts": "2024-01-29 12:00:00",
                    "severity": "high",
                    "note": "Drive-end spindle bearing wear",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-viby-bearing",
            "signal": "VIB_Y_MM_S",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "impulsive",
                    "start_ts": "2024-01-16 00:00:00",
                    "end_ts": "2024-02-06 23:00:00",
                    "note": "Drive-end spindle bearing wear",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-acoustic-bearing",
            "signal": "ACOUSTIC_DB",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "impulsive",
                    "start_ts": "2024-01-16 00:00:00",
                    "end_ts": "2024-02-06 23:00:00",
                    "note": "Drive-end spindle bearing wear",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-bearing-temp",
            "signal": "BEARING_TEMP_C",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "impulsive",
                    "start_ts": "2024-01-16 00:00:00",
                    "end_ts": "2024-02-06 23:00:00",
                    "note": "Drive-end spindle bearing wear",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-coolant-flow",
            "signal": "COOLANT_FLOW_LPM",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "smooth",
                    "start_ts": "2024-02-13 00:00:00",
                    "end_ts": "2024-02-16 23:00:00",
                    "note": "Coolant filter restriction",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-coolant-pressure",
            "signal": "COOLANT_PRESSURE_BAR",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_anomaly",
                    "signature": "smooth",
                    "start_ts": "2024-02-13 00:00:00",
                    "end_ts": "2024-02-16 23:00:00",
                    "note": "Coolant filter restriction",
                }
            ),
            "promoted_at": tznow(),
        },
        {
            "session_name": SESSION,
            "equipment_type_tag": EQUIPMENT_TYPE,
            "label_id": "lb-normal-baseline",
            "signal": "ALL",
            "feature_profile": json.dumps(
                {
                    "label_type": "confirmed_normal",
                    "start_ts": "2024-01-01 00:00:00",
                    "end_ts": "2024-01-12 23:00:00",
                    "note": "Clean baseline window",
                }
            ),
            "promoted_at": tznow(),
        },
    ]
    return rows


def build_labels():
    """All annotations for the seed session, including the non-promoted dismissed drift."""
    rows = [
        {
            "session_name": SESSION,
            "label_id": "lbl-drift-current",
            "equipment_id": "CNC-01",
            "signal": "MOTOR_CURRENT_A",
            "start_ts": "2024-02-20 00:00:00",
            "end_ts": "2024-02-25 23:00:00",
            "label_type": "dismissed",
            "confidence": 0.95,
            "root_cause_category": "Instrumentation",
            "note": "Current transmitter drift; no mechanical change",
            "author": "devin",
            "created_at": tznow(),
        }
    ]
    return rows


def sql_literal(value, kind="string"):
    if kind == "string":
        if value is None:
            return "NULL"
        s = str(value).replace("'", "''")
        return f"'{s}'"
    if kind == "float":
        return str(float(value)) if value is not None else "NULL"
    return f"'{value}'"


def load_to_trino(bank, labels):
    if not (os.environ.get("TRINO_USER") and os.environ.get("TRINO_PASS")):
        return
    conn = trino.dbapi.connect(
        host="ddae.lab9bgp.com",
        port=443,
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        catalog=CATALOG,
        verify=False,
    )
    cur = conn.cursor()

    cur.execute(f"DELETE FROM {CATALOG}.{SCHEMA}.label_bank WHERE session_name = '{SESSION}'")
    for row in bank:
        vals = (
            sql_literal(row["session_name"]),
            sql_literal(row["equipment_type_tag"]),
            sql_literal(row["label_id"]),
            sql_literal(row["signal"]),
            sql_literal(row["feature_profile"]),
            f"TIMESTAMP '{row['promoted_at']}'",
        )
        cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.label_bank VALUES ({', '.join(vals)})")

    # labels table has no session_name column per spec, so we just insert the row; the session is implicit in the demo
    cur.execute(f"DELETE FROM {CATALOG}.{SCHEMA}.labels WHERE signal = '{labels[0]['signal']}' AND label_type = 'dismissed'")
    for row in labels:
        vals = (
            sql_literal(row["label_id"]),
            sql_literal(row["equipment_id"]),
            sql_literal(row["signal"]),
            f"TIMESTAMP '{row['start_ts']}'",
            f"TIMESTAMP '{row['end_ts']}'",
            sql_literal(row["label_type"]),
            sql_literal(row["confidence"], "float"),
            sql_literal(row["root_cause_category"]),
            sql_literal(row["note"]),
            sql_literal(row["author"]),
            f"TIMESTAMP '{row['created_at']}'",
        )
        cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.labels VALUES ({', '.join(vals)})")
    print("Seeded label bank and labels in Trino")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-trino", action="store_true")
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    bank = build_label_bank()
    labels = build_labels()

    with open(PROCESSED / "seed_label_bank.json", "w") as f:
        json.dump(bank, f, indent=2)
    with open(PROCESSED / "seed_labels.json", "w") as f:
        json.dump(labels, f, indent=2)
    print(f"Wrote {len(bank)} label-bank and {len(labels)} label rows to data/processed/*.json")

    if not args.no_trino:
        load_to_trino(bank, labels)


if __name__ == "__main__":
    main()
