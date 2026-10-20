#!/usr/bin/env python3
"""Back up the v1 tables that v2 will change to S3 as Parquet, and record Iceberg snapshot ids."""
import json
import os
import re
import tempfile
from io import StringIO

import boto3
import pandas as pd
import trino
from trino.auth import BasicAuthentication

TABLES = {
    "iceberg": {
        "js_manuf_ice.cnc_historian.sensor_readings": "sensor_readings",
        "js_manuf_ice.cnc_qa.cmm_inspections": "cmm_inspections",
        "js_manuf_ice.cnc_qa.ncr": "ncr",
        "js_manuf_ice.cnc_cmms.work_orders": "work_orders",
    },
    "mysql": {
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots": "production_lots",
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders": "production_orders",
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_materials": "materials",
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders": "purchase_orders",
    },
}

S3_BUCKET = "js-demo"
S3_PREFIX = "cnc-demo/backup/v1/"


def conn():
    return trino.dbapi.connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.environ.get("TRINO_PORT", "443")),
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        verify=False,
    )


def query(sql):
    with conn() as c:
        cur = c.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(rows, columns=cols)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )


def safe_name(fqn):
    return re.sub(r"[^a-z0-9_]", "_", fqn.split(".")[-1], flags=re.I)


def backup_table(fqn, s3_key):
    df = query(f"SELECT * FROM {fqn}")
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        df.to_parquet(tmp.name, index=False)
        tmp_path = tmp.name
    try:
        s3_client().upload_file(tmp_path, S3_BUCKET, s3_key)
        print(f"Backed up {fqn} -> s3://{S3_BUCKET}/{s3_key} ({len(df)} rows)")
    finally:
        os.unlink(tmp_path)


def record_snapshots():
    snapshots = {}
    for fqn, name in TABLES["iceberg"].items():
        schema, tbl = fqn.replace("js_manuf_ice.", "").split(".")
        try:
            snap = query(f"SELECT snapshot_id, committed_at, parent_id FROM js_manuf_ice.{schema}.\"{tbl}$snapshots\" ORDER BY committed_at DESC LIMIT 1")
            snapshots[name] = snap.to_dict(orient="records")[0] if not snap.empty else None
        except Exception as e:
            print(f"Could not get snapshot for {fqn}: {e}")
            snapshots[name] = None
    snap_json = json.dumps(snapshots, indent=2, default=str)
    s3_client().put_object(Bucket=S3_BUCKET, Key=S3_PREFIX + "snapshots.json", Body=snap_json)
    print(f"Recorded snapshots to s3://{S3_BUCKET}/{S3_PREFIX}snapshots.json")


def main():
    s3 = s3_client()
    for fqn, name in {**TABLES["iceberg"], **TABLES["mysql"]}.items():
        backup_table(fqn, S3_PREFIX + f"{name}/part-00001.parquet")
    record_snapshots()
    print("v1 backup complete.")


if __name__ == "__main__":
    main()
