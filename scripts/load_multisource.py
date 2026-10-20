#!/usr/bin/env python3
"""Step 1: land all six sources for the Spindle-to-Customer demo.

- Uploads raw files to s3://js-demo/cnc-demo/raw/<source>/
- Loads historian/QA/CMMS into Iceberg (js_manuf_ice.cnc_*)
- Loads MES/ERP into MySQL via Iceberg staging (cnc_staging -> cnc_mes / cnc_erp)
- Loads shift logbook into Elasticsearch (cnc-demo-shift-logbook)
- Verifies all row counts from data/multisource/README.md
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import boto3
import pandas as pd
import trino
from botocore.config import Config
from elasticsearch import Elasticsearch, helpers
from trino.auth import BasicAuthentication

DATA_DIR = Path("data/multisource")
S3_BUCKET = "js-demo"
S3_PREFIX = "cnc-demo/raw/"
CATALOG = "js_manuf_ice"
STAGING_SCHEMA = "cnc_staging"


def sql_literal(value, kind="string"):
    if value is None or (kind in ("float", "int", "string", "json") and pd.isna(value)):
        return "NULL"
    if kind == "string" or kind == "json":
        s = str(value).replace("'", "''")
        return f"'{s}'"
    if kind == "int":
        return str(int(value))
    if kind == "float":
        return str(float(value))
    if kind == "bool":
        return "TRUE" if value else "FALSE"
    if kind == "timestamp":
        if pd.isna(value):
            return "NULL"
        if isinstance(value, str):
            value = pd.to_datetime(value)
        return f"TIMESTAMP '{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if kind == "date":
        if pd.isna(value):
            return "NULL"
        if isinstance(value, str):
            value = pd.to_datetime(value)
        return f"DATE '{value.strftime('%Y-%m-%d')}'"
    raise ValueError(f"Unknown kind {kind}")


def trino_conn():
    return trino.dbapi.connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.environ.get("TRINO_PORT", "443")),
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        catalog=CATALOG,
        verify=False,
    )


def es_client():
    return Elasticsearch(
        os.environ["ELASTIC_ENDPOINT"],
        api_key=os.environ["ELASTIC_API_KEY"],
        verify_certs=False,
        ssl_show_warn=False,
    )


def ensure_iceberg_schema(cur, schema, location):
    cur.execute(f"DROP SCHEMA IF EXISTS {CATALOG}.{schema} CASCADE")
    cur.execute(
        f"CREATE SCHEMA {CATALOG}.{schema} WITH (location = '{location}')"
    )
    print(f"Created/recreated schema: {CATALOG}.{schema}")


def ensure_mysql_schema(cur, catalog, schema):
    # js_mysql_mfg catalog is writable in its default database/schema (also named js_mysql_mfg).
    # Tables are created with cnc_mes_ / cnc_erp_ prefixes inside that default schema.
    print(f"Using default schema {catalog}.js_mysql_mfg with cnc_{schema}_ prefixes")


def upload_to_s3():
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}),
    )
    for src_dir in DATA_DIR.iterdir():
        if not src_dir.is_dir() or src_dir.name == "__pycache__":
            continue
        for f in src_dir.iterdir():
            if f.is_file() and not f.name.endswith(".zip"):
                key = f"{S3_PREFIX}{src_dir.name}/{f.name}"
                client.upload_file(str(f), S3_BUCKET, key)
                print(f"S3 upload: s3://{S3_BUCKET}/{key}")
    # also put the README and generator at the root of the raw prefix
    for extra in ["README.md", "generate.py"]:
        local = DATA_DIR / extra
        if local.exists():
            key = f"{S3_PREFIX}{extra}"
            client.upload_file(str(local), S3_BUCKET, key)
            print(f"S3 upload: s3://{S3_BUCKET}/{key}")


def run_ddl(cur, ddl):
    cur.execute(ddl)
    print("Created/verified table")


def insert_df(cur, full_table, df, col_spec, batch_size=100, comment=None):
    """col_spec: ordered list of (column_name, kind)"""
    col_names = [c for c, _ in col_spec]
    cur.execute(f"DELETE FROM {full_table}")
    total = 0
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start : start + batch_size]
        rows = []
        for _, row in batch.iterrows():
            vals = [sql_literal(row[c], kind) for c, kind in col_spec]
            rows.append("(" + ", ".join(vals) + ")")
        sql = f"INSERT INTO {full_table} ({', '.join(col_names)}) VALUES " + ", ".join(rows)
        cur.execute(sql)
        total += len(batch)
    print(f"Inserted {total} rows into {full_table}")


def load_historian(cur):
    files = [
        ("CNC01_SpindleLine_60days_hourly_mes_aligned.csv", "CNC-01"),
        ("CNC01_SpindleLine_Month3_hourly.csv", "CNC-01"),
        ("CNC02_SpindleLine_30days_hourly.csv", "CNC-02"),
    ]
    signals = [
        "SPINDLE_RPM", "SPINDLE_LOAD_PCT", "MOTOR_CURRENT_A", "VIB_X_MM_S",
        "VIB_Y_MM_S", "BEARING_TEMP_C", "COOLANT_FLOW_LPM", "COOLANT_PRESSURE_BAR",
        "FEED_RATE_MM_MIN", "AIR_PRESSURE_BAR", "AMBIENT_TEMP_C", "ACOUSTIC_DB",
    ]
    cur.execute("DELETE FROM js_manuf_ice.cnc_historian.sensor_readings")
    for filename, equip_id in files:
        df = pd.read_csv(DATA_DIR / "historian" / filename)
        df["ts"] = pd.to_datetime(df["Timestamp"])
        df["equipment_id"] = equip_id
        df = df[["equipment_id", "ts"] + signals]
        for start in range(0, len(df), 250):
            batch = df.iloc[start : start + 250]
            rows = []
            for _, row in batch.iterrows():
                vals = [sql_literal(equip_id, "string"), sql_literal(row["ts"], "timestamp")]
                for sig in signals:
                    v = row[sig]
                    if pd.isna(v) or v != v:
                        vals.append("NULL")
                    else:
                        vals.append(str(float(v)))
                rows.append("(" + ", ".join(vals) + ")")
            sql = (
                "INSERT INTO js_manuf_ice.cnc_historian.sensor_readings "
                f"(equipment_id, ts, {', '.join(signals)}) VALUES " + ", ".join(rows)
            )
            cur.execute(sql)
        print(f"Loaded {len(df)} historian rows for {equip_id} from {filename}")


def load_iceberg_qa(cur):
    cmm = pd.read_csv(DATA_DIR / "qa" / "cmm_inspections.csv")
    cmm["inspect_ts"] = pd.to_datetime(cmm["inspect_ts"])
    insert_df(cur, "js_manuf_ice.cnc_qa.cmm_inspections", cmm, [
        ("inspection_id", "string"),
        ("lot_id", "string"),
        ("machine_id", "string"),
        ("material_id", "string"),
        ("sample_no", "int"),
        ("inspect_ts", "timestamp"),
        ("characteristic", "string"),
        ("nominal", "float"),
        ("lsl", "float"),
        ("usl", "float"),
        ("measured", "float"),
        ("unit", "string"),
        ("result", "string"),
        ("gauge", "string"),
    ], batch_size=200)

    ncr = pd.read_csv(DATA_DIR / "qa" / "ncr.csv")
    ncr["opened_ts"] = pd.to_datetime(ncr["opened_ts"])
    insert_df(cur, "js_manuf_ice.cnc_qa.ncr", ncr, [
        ("ncr_id", "string"),
        ("lot_id", "string"),
        ("machine_id", "string"),
        ("material_id", "string"),
        ("opened_ts", "timestamp"),
        ("characteristic", "string"),
        ("defect_code", "string"),
        ("qty_sorted", "int"),
        ("qty_scrapped", "int"),
        ("disposition", "string"),
        ("scrap_cost_usd", "float"),
    ])

    comp = pd.read_csv(DATA_DIR / "qa" / "customer_complaints.csv")
    comp["received_date"] = pd.to_datetime(comp["received_date"])
    insert_df(cur, "js_manuf_ice.cnc_qa.customer_complaints", comp, [
        ("complaint_id", "string"),
        ("customer_id", "string"),
        ("so_id", "string"),
        ("material_id", "string"),
        ("received_date", "date"),
        ("qty_rejected_at_customer", "int"),
        ("description", "string"),
        ("cost_usd", "float"),
        ("status", "string"),
    ])


def load_iceberg_cmms(cur):
    with open(DATA_DIR / "cmms" / "assets.json") as f:
        assets = json.load(f)
    assets_df = pd.DataFrame(assets)
    assets_df["spindle"] = assets_df["spindle"].apply(json.dumps)
    insert_df(cur, "js_manuf_ice.cnc_cmms.assets", assets_df, [
        ("asset_id", "string"),
        ("description", "string"),
        ("manufacturer", "string"),
        ("install_year", "int"),
        ("location", "string"),
        ("criticality", "string"),
        ("spindle", "string"),
    ])

    wos = []
    with open(DATA_DIR / "cmms" / "work_orders.jsonl") as f:
        for line in f:
            if line.strip():
                wos.append(json.loads(line))
    wo_df = pd.DataFrame(wos)
    for col in ["created_ts", "started_ts", "completed_ts"]:
        wo_df[col] = pd.to_datetime(wo_df[col])
    wo_df["parts"] = wo_df["parts"].apply(lambda x: json.dumps(x) if x is not None else None)
    insert_df(cur, "js_manuf_ice.cnc_cmms.work_orders", wo_df, [
        ("wo_id", "string"),
        ("asset_id", "string"),
        ("type", "string"),
        ("priority", "int"),
        ("status", "string"),
        ("created_ts", "timestamp"),
        ("started_ts", "timestamp"),
        ("completed_ts", "timestamp"),
        ("failure_code", "string"),
        ("problem", "string"),
        ("cause", "string"),
        ("remedy", "string"),
        ("labour_hours", "float"),
        ("parts", "string"),
        ("technician", "string"),
    ])


def load_staging_then_mysql_mes(cur):
    po = pd.read_csv(DATA_DIR / "mes" / "production_orders.csv")
    for c in ["planned_finish", "actual_start", "actual_end"]:
        po[c] = pd.to_datetime(po[c], errors="coerce")
    insert_df(cur, "js_manuf_ice.cnc_staging.production_orders", po, [
        ("prod_order_id", "string"),
        ("so_id", "string"),
        ("material_id", "string"),
        ("machine_id", "string"),
        ("qty_target", "int"),
        ("planned_finish", "timestamp"),
        ("actual_start", "timestamp"),
        ("actual_end", "timestamp"),
        ("qty_good", "int"),
        ("qty_scrap", "int"),
        ("status", "string"),
    ])

    lots = pd.read_csv(DATA_DIR / "mes" / "production_lots.csv")
    for c in ["start_ts", "end_ts"]:
        lots[c] = pd.to_datetime(lots[c])
    lots["shift_date"] = pd.to_datetime(lots["shift_date"])
    insert_df(cur, "js_manuf_ice.cnc_staging.production_lots", lots, [
        ("lot_id", "string"),
        ("prod_order_id", "string"),
        ("machine_id", "string"),
        ("material_id", "string"),
        ("shift_date", "date"),
        ("shift", "string"),
        ("start_ts", "timestamp"),
        ("end_ts", "timestamp"),
        ("planned_production_min", "int"),
        ("run_min", "int"),
        ("unplanned_downtime_min", "int"),
        ("qty_produced", "int"),
        ("qty_good", "int"),
        ("qty_scrap", "int"),
        ("scrap_bore_dia", "int"),
        ("scrap_roundness", "int"),
        ("scrap_surface_ra", "int"),
        ("ideal_cycle_min", "float"),
        ("availability", "float"),
        ("performance", "float"),
        ("quality", "float"),
        ("oee", "float"),
    ])

    dt = pd.read_csv(DATA_DIR / "mes" / "downtime_events.csv")
    for c in ["start_ts", "end_ts"]:
        dt[c] = pd.to_datetime(dt[c])
    insert_df(cur, "js_manuf_ice.cnc_staging.downtime_events", dt, [
        ("stop_id", "string"),
        ("machine_id", "string"),
        ("lot_id", "string"),
        ("start_ts", "timestamp"),
        ("end_ts", "timestamp"),
        ("duration_min", "int"),
        ("category", "string"),
        ("reason_code", "string"),
        ("reason_text", "string"),
    ])

    # move to MySQL via CTAS, inside the writable default js_mysql_mfg schema
    for tbl in ["production_orders", "production_lots", "downtime_events"]:
        target = f"js_mysql_mfg.js_mysql_mfg.cnc_mes_{tbl}"
        cur.execute(f"DROP TABLE IF EXISTS {target}")
        cur.execute(
            f"CREATE TABLE {target} AS SELECT * FROM js_manuf_ice.cnc_staging.{tbl}"
        )
        print(f"CTAS into {target}")
        cur.execute(f"DROP TABLE js_manuf_ice.cnc_staging.{tbl}")


def load_staging_then_mysql_erp(cur):
    customers = pd.read_csv(DATA_DIR / "erp" / "customers.csv")
    insert_df(cur, "js_manuf_ice.cnc_staging.customers", customers, [
        ("customer_id", "string"),
        ("customer_name", "string"),
        ("industry", "string"),
        ("segment", "string"),
        ("payment_terms", "string"),
    ])

    mats = pd.read_csv(DATA_DIR / "erp" / "materials.csv")
    insert_df(cur, "js_manuf_ice.cnc_staging.materials", mats, [
        ("material_id", "string"),
        ("description", "string"),
        ("material_type", "string"),
        ("unit_cost_usd", "float"),
        ("unit_price_usd", "float"),
        ("ideal_cycle_min", "float"),
        ("bore_nominal_mm", "float"),
        ("std_lead_time_days", "float"),
    ])

    so = pd.read_csv(DATA_DIR / "erp" / "sales_orders.csv")
    for c in ["ship_date"]:
        so[c] = pd.to_datetime(so[c], errors="coerce")
    for c in ["order_date", "due_date"]:
        so[c] = pd.to_datetime(so[c], errors="coerce")
    insert_df(cur, "js_manuf_ice.cnc_staging.sales_orders", so, [
        ("so_id", "string"),
        ("customer_id", "string"),
        ("material_id", "string"),
        ("qty", "int"),
        ("unit_price_usd", "float"),
        ("order_value_usd", "float"),
        ("order_date", "date"),
        ("due_date", "date"),
        ("ship_date", "timestamp"),
        ("qty_shipped", "int"),
        ("status", "string"),
        ("days_late", "float"),
        ("late_penalty_usd", "float"),
        ("penalty_terms", "string"),
    ])

    po = pd.read_csv(DATA_DIR / "erp" / "purchase_orders.csv")
    for c in ["order_date", "promised_date", "received_ts"]:
        po[c] = pd.to_datetime(po[c], errors="coerce")
    insert_df(cur, "js_manuf_ice.cnc_staging.purchase_orders", po, [
        ("po_id", "string"),
        ("material_id", "string"),
        ("vendor", "string"),
        ("qty", "int"),
        ("unit_price_usd", "float"),
        ("freight_usd", "float"),
        ("expedited", "bool"),
        ("order_date", "timestamp"),
        ("promised_date", "timestamp"),
        ("received_ts", "timestamp"),
        ("std_lead_time_days", "float"),
        ("ref_work_order", "string"),
        ("note", "string"),
    ])

    stock = pd.read_csv(DATA_DIR / "erp" / "spare_parts_stock.csv")
    stock["as_of_date"] = pd.to_datetime(stock["as_of_date"])
    insert_df(cur, "js_manuf_ice.cnc_staging.spare_parts_stock", stock, [
        ("material_id", "string"),
        ("plant", "string"),
        ("qty_on_hand", "int"),
        ("reorder_point", "int"),
        ("as_of_date", "date"),
        ("note", "string"),
    ])

    rates = pd.read_csv(DATA_DIR / "erp" / "cost_rates.csv")
    insert_df(cur, "js_manuf_ice.cnc_staging.cost_rates", rates, [
        ("rate_type", "string"),
        ("scope", "string"),
        ("value_usd", "float"),
        ("description", "string"),
    ])

    for tbl in ["customers", "materials", "sales_orders", "purchase_orders", "spare_parts_stock", "cost_rates"]:
        target = f"js_mysql_mfg.js_mysql_mfg.cnc_erp_{tbl}"
        cur.execute(f"DROP TABLE IF EXISTS {target}")
        cur.execute(
            f"CREATE TABLE {target} AS SELECT * FROM js_manuf_ice.cnc_staging.{tbl}"
        )
        print(f"CTAS into {target}")
        cur.execute(f"DROP TABLE js_manuf_ice.cnc_staging.{tbl}")


def load_logbook(es):
    idx = "cnc-demo-shift-logbook"
    try:
        es.indices.delete(index=idx)
    except Exception:
        pass
    es.indices.create(
        index=idx,
        body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "note_id": {"type": "keyword"},
                    "ts": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd HH:mm"},
                    "machine_id": {"type": "keyword"},
                    "shift": {"type": "keyword"},
                    "author_role": {"type": "keyword"},
                    "text": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 32766}},
                    },
                }
            },
        },
    )

    docs = []
    with open(DATA_DIR / "logbook" / "shift_logbook.jsonl") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                # pad ts to seconds if needed
                ts = d["ts"]
                if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", ts):
                    ts += ":00"
                d["ts"] = ts
                d["_index"] = idx
                d["_id"] = d["note_id"]
                docs.append(d)
    helpers.bulk(es, docs)
    print(f"Indexed {len(docs)} logbook documents into {idx}")


def verify_counts(cur, es):
    expected = {
        "js_manuf_ice.cnc_historian.sensor_readings": 2904,
        "js_manuf_ice.cnc_qa.cmm_inspections": 5370,
        "js_manuf_ice.cnc_qa.ncr": 33,
        "js_manuf_ice.cnc_qa.customer_complaints": 1,
        "js_manuf_ice.cnc_cmms.assets": 2,
        "js_manuf_ice.cnc_cmms.work_orders": 9,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders": 9,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots": 363,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_downtime_events": 473,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_customers": 3,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_materials": 6,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders": 10,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders": 3,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_spare_parts_stock": 5,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_cost_rates": 4,
    }
    ok = True
    for full, n in expected.items():
        cur.execute(f"SELECT count(*) FROM {full}")
        got = cur.fetchone()[0]
        status = "OK" if got == n else f"FAIL (got {got})"
        print(f"  {full}: {status}")
        if got != n:
            ok = False
    es_count = es.count(index="cnc-demo-shift-logbook")["count"]
    print(f"  cnc-demo-shift-logbook: {'OK' if es_count == 220 else f'FAIL (got {es_count})'}")
    if es_count != 220:
        ok = False
    if not ok:
        raise RuntimeError("One or more row counts did not match expected values.")
    print("All counts verified.")


TABLES = {
    "js_manuf_ice.cnc_historian.sensor_readings": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_historian.sensor_readings (
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
        ) WITH (partitioning = ARRAY['equipment_id', 'day(ts)'])
    """,
    "js_manuf_ice.cnc_qa.cmm_inspections": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_qa.cmm_inspections (
            inspection_id VARCHAR,
            lot_id VARCHAR,
            machine_id VARCHAR,
            material_id VARCHAR,
            sample_no INTEGER,
            inspect_ts TIMESTAMP(6),
            characteristic VARCHAR,
            nominal DOUBLE,
            lsl DOUBLE,
            usl DOUBLE,
            measured DOUBLE,
            unit VARCHAR,
            result VARCHAR,
            gauge VARCHAR
        )
    """,
    "js_manuf_ice.cnc_qa.ncr": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_qa.ncr (
            ncr_id VARCHAR,
            lot_id VARCHAR,
            machine_id VARCHAR,
            material_id VARCHAR,
            opened_ts TIMESTAMP(6),
            characteristic VARCHAR,
            defect_code VARCHAR,
            qty_sorted INTEGER,
            qty_scrapped INTEGER,
            disposition VARCHAR,
            scrap_cost_usd DOUBLE
        )
    """,
    "js_manuf_ice.cnc_qa.customer_complaints": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_qa.customer_complaints (
            complaint_id VARCHAR,
            customer_id VARCHAR,
            so_id VARCHAR,
            material_id VARCHAR,
            received_date DATE,
            qty_rejected_at_customer INTEGER,
            description VARCHAR,
            cost_usd DOUBLE,
            status VARCHAR
        )
    """,
    "js_manuf_ice.cnc_cmms.assets": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_cmms.assets (
            asset_id VARCHAR,
            description VARCHAR,
            manufacturer VARCHAR,
            install_year INTEGER,
            location VARCHAR,
            criticality VARCHAR,
            spindle VARCHAR
        )
    """,
    "js_manuf_ice.cnc_cmms.work_orders": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_cmms.work_orders (
            wo_id VARCHAR,
            asset_id VARCHAR,
            type VARCHAR,
            priority INTEGER,
            status VARCHAR,
            created_ts TIMESTAMP(6),
            started_ts TIMESTAMP(6),
            completed_ts TIMESTAMP(6),
            failure_code VARCHAR,
            problem VARCHAR,
            cause VARCHAR,
            remedy VARCHAR,
            labour_hours DOUBLE,
            parts VARCHAR,
            technician VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.production_orders": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.production_orders (
            prod_order_id VARCHAR,
            so_id VARCHAR,
            material_id VARCHAR,
            machine_id VARCHAR,
            qty_target INTEGER,
            planned_finish TIMESTAMP(6),
            actual_start TIMESTAMP(6),
            actual_end TIMESTAMP(6),
            qty_good INTEGER,
            qty_scrap INTEGER,
            status VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.production_lots": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.production_lots (
            lot_id VARCHAR,
            prod_order_id VARCHAR,
            machine_id VARCHAR,
            material_id VARCHAR,
            shift_date DATE,
            shift VARCHAR,
            start_ts TIMESTAMP(6),
            end_ts TIMESTAMP(6),
            planned_production_min INTEGER,
            run_min INTEGER,
            unplanned_downtime_min INTEGER,
            qty_produced INTEGER,
            qty_good INTEGER,
            qty_scrap INTEGER,
            scrap_bore_dia INTEGER,
            scrap_roundness INTEGER,
            scrap_surface_ra INTEGER,
            ideal_cycle_min DOUBLE,
            availability DOUBLE,
            performance DOUBLE,
            quality DOUBLE,
            oee DOUBLE
        )
    """,
    "js_manuf_ice.cnc_staging.downtime_events": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.downtime_events (
            stop_id VARCHAR,
            machine_id VARCHAR,
            lot_id VARCHAR,
            start_ts TIMESTAMP(6),
            end_ts TIMESTAMP(6),
            duration_min INTEGER,
            category VARCHAR,
            reason_code VARCHAR,
            reason_text VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.customers": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.customers (
            customer_id VARCHAR,
            customer_name VARCHAR,
            industry VARCHAR,
            segment VARCHAR,
            payment_terms VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.materials": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.materials (
            material_id VARCHAR,
            description VARCHAR,
            material_type VARCHAR,
            unit_cost_usd DOUBLE,
            unit_price_usd DOUBLE,
            ideal_cycle_min DOUBLE,
            bore_nominal_mm DOUBLE,
            std_lead_time_days DOUBLE
        )
    """,
    "js_manuf_ice.cnc_staging.sales_orders": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.sales_orders (
            so_id VARCHAR,
            customer_id VARCHAR,
            material_id VARCHAR,
            qty INTEGER,
            unit_price_usd DOUBLE,
            order_value_usd DOUBLE,
            order_date DATE,
            due_date DATE,
            ship_date TIMESTAMP(6),
            qty_shipped INTEGER,
            status VARCHAR,
            days_late DOUBLE,
            late_penalty_usd DOUBLE,
            penalty_terms VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.purchase_orders": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.purchase_orders (
            po_id VARCHAR,
            material_id VARCHAR,
            vendor VARCHAR,
            qty INTEGER,
            unit_price_usd DOUBLE,
            freight_usd DOUBLE,
            expedited BOOLEAN,
            order_date TIMESTAMP(6),
            promised_date TIMESTAMP(6),
            received_ts TIMESTAMP(6),
            std_lead_time_days DOUBLE,
            ref_work_order VARCHAR,
            note VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.spare_parts_stock": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.spare_parts_stock (
            material_id VARCHAR,
            plant VARCHAR,
            qty_on_hand INTEGER,
            reorder_point INTEGER,
            as_of_date DATE,
            note VARCHAR
        )
    """,
    "js_manuf_ice.cnc_staging.cost_rates": """
        CREATE TABLE IF NOT EXISTS js_manuf_ice.cnc_staging.cost_rates (
            rate_type VARCHAR,
            scope VARCHAR,
            value_usd DOUBLE,
            description VARCHAR
        )
    """,
}


def main():
    no_s3 = "--no-s3" in sys.argv
    no_trino = "--no-trino" in sys.argv
    no_es = "--no-es" in sys.argv

    if not no_s3:
        upload_to_s3()

    if not no_trino:
        conn = trino_conn()
        cur = conn.cursor()

        # Iceberg schemas
        ensure_iceberg_schema(cur, "cnc_historian", "s3://js-demo/cnc-demo/warehouse/cnc_historian")
        ensure_iceberg_schema(cur, "cnc_qa", "s3://js-demo/cnc-demo/warehouse/cnc_qa")
        ensure_iceberg_schema(cur, "cnc_cmms", "s3://js-demo/cnc-demo/warehouse/cnc_cmms")
        ensure_iceberg_schema(cur, STAGING_SCHEMA, "s3://js-demo/cnc-demo/warehouse/cnc_staging")

        # MySQL schemas (new js_mysql_mfg catalog has r/w and CREATE privileges)
        ensure_mysql_schema(cur, "js_mysql_mfg", "cnc_mes")
        ensure_mysql_schema(cur, "js_mysql_mfg", "cnc_erp")

        for full, ddl in TABLES.items():
            run_ddl(cur, ddl)

        load_historian(cur)
        load_iceberg_qa(cur)
        load_iceberg_cmms(cur)
        load_staging_then_mysql_mes(cur)
        load_staging_then_mysql_erp(cur)

        # also create cnc_analytics empty schema for Step 2
        ensure_iceberg_schema(cur, "cnc_analytics", "s3://js-demo/cnc-demo/warehouse/cnc_analytics")

    if not no_es:
        es = es_client()
        load_logbook(es)

    if not no_trino:
        es = es_client()
        verify_counts(cur, es)


if __name__ == "__main__":
    main()
