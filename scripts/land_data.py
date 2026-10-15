#!/usr/bin/env python3
"""Land raw CSVs to S3, create smart_mfg schema/tables, and load the sensor data.

Also writes combined Parquet files under data/processed/ for the OFFLINE_MODE fallback.
"""
import argparse
import os
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import trino
from trino.auth import BasicAuthentication

RAW_DIR = Path("data/raw")
S3_BUCKET = "js-demo"
S3_PREFIX = "cnc-demo/raw/"
CATALOG = "js_manuf_ice"
SCHEMA = "smart_mfg"

FILES = [
    ("CNC01_SpindleLine_60days_hourly.csv", "CNC-01"),
    ("CNC01_SpindleLine_Month3_hourly.csv", "CNC-01"),
    ("CNC02_SpindleLine_30days_hourly.csv", "CNC-02"),
]

EQUIPMENT = [
    {"equipment_id": "CNC-01", "equipment_type": "CNC Machining Center", "line": "Spindle Line 1", "install_year": 2019},
    {"equipment_id": "CNC-02", "equipment_type": "CNC Machining Center", "line": "Spindle Line 2", "install_year": 2020},
]

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

TABLES = {
    "sensor_readings": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.sensor_readings (
            equipment_id VARCHAR,
            ts TIMESTAMP(6),
            SPINDLE_RPM DOUBLE,
            SPINDLE_LOAD_PCT DOUBLE,
            MOTOR_CURRENT_A DOUBLE,
            VIB_X_MM_S DOUBLE,
            VIB_Y_MM_S DOUBLE,
            BEARING_TEMP_C DOUBLE,
            COOLANT_FLOW_LPM DOUBLE,
            COOLANT_PRESSURE_BAR DOUBLE,
            FEED_RATE_MM_MIN DOUBLE,
            AIR_PRESSURE_BAR DOUBLE,
            AMBIENT_TEMP_C DOUBLE,
            ACOUSTIC_DB DOUBLE
        ) WITH (
            partitioning = ARRAY['equipment_id', 'day(ts)']
        )
    """,
    "equipment": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.equipment (
            equipment_id VARCHAR,
            equipment_type VARCHAR,
            line VARCHAR,
            install_year INTEGER
        )
    """,
    "anomaly_scores": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.anomaly_scores (
            run_id VARCHAR,
            equipment_id VARCHAR,
            ts TIMESTAMP(6),
            signal VARCHAR,
            detector VARCHAR,
            score DOUBLE,
            is_anomaly BOOLEAN,
            consensus_score DOUBLE
        )
    """,
    "anomaly_events": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.anomaly_events (
            event_id VARCHAR,
            run_id VARCHAR,
            equipment_id VARCHAR,
            signals ARRAY(VARCHAR),
            start_ts TIMESTAMP(6),
            end_ts TIMESTAMP(6),
            peak_ts TIMESTAMP(6),
            severity VARCHAR,
            signature VARCHAR
        )
    """,
    "labels": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.labels (
            label_id VARCHAR,
            equipment_id VARCHAR,
            signal VARCHAR,
            start_ts TIMESTAMP(6),
            end_ts TIMESTAMP(6),
            label_type VARCHAR,
            confidence DOUBLE,
            root_cause_category VARCHAR,
            note VARCHAR,
            author VARCHAR,
            created_at TIMESTAMP(6)
        )
    """,
    "label_bank": """
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.label_bank (
            session_name VARCHAR,
            equipment_type_tag VARCHAR,
            label_id VARCHAR,
            signal VARCHAR,
            feature_profile VARCHAR,
            promoted_at TIMESTAMP(6)
        )
    """,
}


def sql_literal(value, kind="string"):
    if kind == "string":
        if value is None:
            return "NULL"
        s = str(value).replace("'", "''")
        return f"'{s}'"
    if kind == "int":
        return str(int(value)) if value is not None else "NULL"
    if kind == "float":
        return str(float(value)) if value is not None and pd.notna(value) else "NULL"
    raise ValueError(f"Unknown kind {kind}")


def upload_to_s3():
    endpoint = os.environ["S3_ENDPOINT"]
    access = os.environ["S3_ACCESS_KEY"]
    secret = os.environ["S3_SECRET_KEY"]
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
    )
    for filename, _ in FILES:
        local = RAW_DIR / filename
        key = S3_PREFIX + filename
        client.upload_file(str(local), S3_BUCKET, key)
        print(f"S3 upload: s3://{S3_BUCKET}/{key}")


def trino_conn():
    return trino.dbapi.connect(
        host="ddae.lab9bgp.com",
        port=443,
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        catalog=CATALOG,
        verify=False,
    )


def create_tables(cur):
    # Recreate schema so the location property is set correctly; no real data exists yet.
    try:
        cur.execute(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA} CASCADE")
    except Exception as e:
        print(f"Note: drop schema failed: {e}")
    cur.execute(
        f"CREATE SCHEMA {CATALOG}.{SCHEMA} "
        f"WITH (location = 's3://js-demo/cnc-demo/warehouse/{SCHEMA}')"
    )
    for name, ddl in TABLES.items():
        cur.execute(ddl.format(catalog=CATALOG, schema=SCHEMA))
        print(f"Created/verified table: {name}")


def load_equipment(cur):
    cur.execute(f"DELETE FROM {CATALOG}.{SCHEMA}.equipment")
    values = ", ".join(
        f"({sql_literal(e['equipment_id'])}, {sql_literal(e['equipment_type'])}, {sql_literal(e['line'])}, {sql_literal(e['install_year'], 'int')})"
        for e in EQUIPMENT
    )
    cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.equipment VALUES {values}")
    print(f"Inserted {len(EQUIPMENT)} equipment rows")


def load_sensor_readings(cur):
    cur.execute(f"DELETE FROM {CATALOG}.{SCHEMA}.sensor_readings")
    for filename, equip_id in FILES:
        df = pd.read_csv(RAW_DIR / filename)
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df["equipment_id"] = equip_id

        # Insert in batches of 250 rows
        batch_size = 250
        for start in range(0, len(df), batch_size):
            batch = df.iloc[start : start + batch_size]
            value_rows = []
            for _, row in batch.iterrows():
                vals = [sql_literal(equip_id)]
                vals.append(f"TIMESTAMP '{row['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')}'")
                for sig in SIGNALS:
                    v = row[sig]
                    if pd.isna(v) or not (float(v) == float(v)):
                        vals.append("NULL")
                    else:
                        vals.append(str(float(v)))
                value_rows.append("(" + ", ".join(vals) + ")")

            sql = (
                f"INSERT INTO {CATALOG}.{SCHEMA}.sensor_readings "
                f"(equipment_id, ts, {', '.join(SIGNALS)}) VALUES " + ", ".join(value_rows)
            )
            cur.execute(sql)
        print(f"Loaded {len(df)} rows for {equip_id} from {filename}")


def save_parquet():
    all_frames = []
    for filename, equip_id in FILES:
        df = pd.read_csv(RAW_DIR / filename)
        df["equipment_id"] = equip_id
        all_frames.append(df)
    combined = pd.concat(all_frames, ignore_index=True)
    combined["Timestamp"] = pd.to_datetime(combined["Timestamp"])
    os.makedirs("data/processed", exist_ok=True)
    combined.to_parquet("data/processed/sensor_readings.parquet", index=False)
    eq = pd.DataFrame(EQUIPMENT)
    eq.to_parquet("data/processed/equipment.parquet", index=False)
    print("Wrote data/processed/sensor_readings.parquet and equipment.parquet")


def verify_counts(cur):
    cur.execute(f"SELECT equipment_id, count(*) FROM {CATALOG}.{SCHEMA}.sensor_readings GROUP BY 1 ORDER BY 1")
    rows = cur.fetchall()
    print("Row counts in Trino:")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
    return dict(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-s3", action="store_true", help="Skip S3 upload")
    parser.add_argument("--no-trino", action="store_true", help="Skip Trino load")
    parser.add_argument("--no-parquet", action="store_true", help="Skip local Parquet")
    args = parser.parse_args()

    if not args.no_parquet:
        save_parquet()

    if not args.no_s3:
        upload_to_s3()

    if not args.no_trino:
        conn = trino_conn()
        cur = conn.cursor()
        create_tables(cur)
        load_equipment(cur)
        load_sensor_readings(cur)
        counts = verify_counts(cur)

        expected = {"CNC-01": 2184, "CNC-02": 720}
        for k, v in expected.items():
            if counts.get(k) != v:
                raise RuntimeError(f"Unexpected count for {k}: {counts.get(k)} (expected {v})")
        print("All counts verified.")


if __name__ == "__main__":
    main()
