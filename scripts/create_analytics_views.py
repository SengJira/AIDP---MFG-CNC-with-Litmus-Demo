#!/usr/bin/env python3
"""Step 2: create federated analytics tables in js_manuf_ice.cnc_analytics.

Tables (materialised for speed; refreshed by this job):
- lot_context        one row per MES lot with telemetry means, QA fails, NCR, ERP cost
- cnc_daily_360      per machine/day overview (VIB_X, OEE, scrap, NCR, WOs, downtime)
- event_cost         cost lines per incident (bearing, coolant, current, CNC-02)
- order_risk         per open sales order, projected finish with/without an 8h stop
"""
import os
import time
import trino
from trino.auth import BasicAuthentication

CATALOG = "js_manuf_ice"
SCHEMA = "cnc_analytics"


def trino_conn():
    return trino.dbapi.connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.environ.get("TRINO_PORT", "443")),
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        catalog=CATALOG,
        verify=False,
    )


def run(cur, sql, name):
    print(f"Running {name} ...")
    t0 = time.time()
    cur.execute(sql)
    print(f"  {name} done in {time.time() - t0:.2f}s")


def main():
    conn = trino_conn()
    cur = conn.cursor()

    # ensure schema
    cur.execute(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA} CASCADE")
    cur.execute(f"CREATE SCHEMA {CATALOG}.{SCHEMA} WITH (location = 's3://js-demo/cnc-demo/warehouse/{SCHEMA}')")
    print(f"Created schema: {CATALOG}.{SCHEMA}")

    # 1. lot_context
    run(cur, f"""
        CREATE TABLE {CATALOG}.{SCHEMA}.lot_context AS
        SELECT
            l.lot_id,
            l.prod_order_id,
            l.machine_id,
            l.material_id,
            l.shift_date,
            l.shift,
            l.start_ts,
            l.end_ts,
            l.planned_production_min,
            l.run_min,
            l.unplanned_downtime_min,
            l.qty_produced,
            l.qty_good,
            l.qty_scrap,
            l.scrap_bore_dia,
            l.scrap_roundness,
            l.scrap_surface_ra,
            l.oee,
            AVG(CASE WHEN s.SPINDLE_RPM > 1000 THEN s.VIB_X_MM_S END) AS avg_vib_x,
            AVG(CASE WHEN s.SPINDLE_RPM > 1000 THEN s.VIB_Y_MM_S END) AS avg_vib_y,
            AVG(CASE WHEN s.SPINDLE_RPM > 1000 THEN s.BEARING_TEMP_C END) AS avg_bearing_temp,
            AVG(CASE WHEN s.SPINDLE_RPM > 1000 THEN s.COOLANT_FLOW_LPM END) AS avg_coolant_flow,
            AVG(CASE WHEN s.SPINDLE_RPM > 1000 THEN s.MOTOR_CURRENT_A END) AS avg_motor_current,
            COUNT(CASE WHEN c.characteristic = 'BORE_DIA' AND c.result = 'FAIL' THEN 1 END) AS bore_dia_fails,
            COUNT(CASE WHEN c.characteristic = 'ROUNDNESS' AND c.result = 'FAIL' THEN 1 END) AS roundness_fails,
            COUNT(CASE WHEN c.characteristic = 'SURFACE_RA' AND c.result = 'FAIL' THEN 1 END) AS surface_fails,
            MAX(n.ncr_id) AS ncr_id,
            m.unit_cost_usd,
            (l.qty_scrap * m.unit_cost_usd) AS scrap_usd
        FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l
        LEFT JOIN {CATALOG}.cnc_historian.sensor_readings s
            ON s.equipment_id = l.machine_id
            AND s.ts >= l.start_ts
            AND s.ts < l.end_ts
        LEFT JOIN {CATALOG}.cnc_qa.cmm_inspections c
            ON c.lot_id = l.lot_id
        LEFT JOIN {CATALOG}.cnc_qa.ncr n
            ON n.lot_id = l.lot_id
        LEFT JOIN js_mysql_mfg.js_mysql_mfg.cnc_erp_materials m
            ON m.material_id = l.material_id
        GROUP BY
            l.lot_id, l.prod_order_id, l.machine_id, l.material_id, l.shift_date, l.shift,
            l.start_ts, l.end_ts, l.planned_production_min, l.run_min, l.unplanned_downtime_min,
            l.qty_produced, l.qty_good, l.qty_scrap, l.scrap_bore_dia, l.scrap_roundness, l.scrap_surface_ra,
            l.oee, m.unit_cost_usd
    """, "lot_context")

    # 2. cnc_daily_360
    run(cur, f"""
        CREATE TABLE {CATALOG}.{SCHEMA}.cnc_daily_360 AS
        WITH telemetry_day AS (
            SELECT equipment_id AS machine_id, DATE(ts) AS day, AVG(VIB_X_MM_S) AS avg_vib_x
            FROM {CATALOG}.cnc_historian.sensor_readings
            GROUP BY equipment_id, DATE(ts)
        ),
        lot_day AS (
            SELECT
                machine_id,
                shift_date AS day,
                SUM(qty_scrap) AS scrap_qty,
                AVG(oee) AS oee,
                SUM(qty_produced) AS produced,
                SUM(qty_good) AS good
            FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots
            GROUP BY machine_id, shift_date
        ),
        scrap_usd_day AS (
            SELECT
                l.machine_id,
                l.shift_date AS day,
                SUM(l.qty_scrap * m.unit_cost_usd) AS scrap_usd
            FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_erp_materials m ON m.material_id = l.material_id
            GROUP BY l.machine_id, l.shift_date
        ),
        ncr_day AS (
            SELECT machine_id, DATE(opened_ts) AS day, COUNT(*) AS ncr_count
            FROM {CATALOG}.cnc_qa.ncr
            GROUP BY machine_id, DATE(opened_ts)
        ),
        downtime_day AS (
            SELECT
                machine_id,
                DATE(start_ts) AS day,
                SUM(CASE WHEN category = 'Unplanned' THEN duration_min END) AS unplanned_downtime_min,
                SUM(CASE WHEN category = 'Planned' THEN duration_min END) AS planned_downtime_min
            FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_downtime_events
            GROUP BY machine_id, DATE(start_ts)
        ),
        wo_day AS (
            SELECT
                asset_id AS machine_id,
                CAST(d AS DATE) AS day,
                COUNT(*) AS open_corrective_wos
            FROM {CATALOG}.cnc_cmms.work_orders w
            CROSS JOIN UNNEST(
                sequence(CAST(DATE(started_ts) AS DATE), COALESCE(CAST(DATE(completed_ts) AS DATE), CAST(DATE('2024-05-01') AS DATE)), INTERVAL '1' DAY)
            ) AS t(d)
            WHERE w.type = 'CORRECTIVE'
            GROUP BY asset_id, d
        )
        SELECT
            COALESCE(t.machine_id, l.machine_id, s.machine_id, nc.machine_id, d.machine_id, wd.machine_id) AS machine_id,
            COALESCE(t.day, l.day, s.day, nc.day, d.day, wd.day) AS day,
            t.avg_vib_x,
            l.oee,
            l.scrap_qty AS scrap,
            s.scrap_usd,
            l.produced,
            l.good,
            COALESCE(nc.ncr_count, 0) AS ncr_count,
            COALESCE(wd.open_corrective_wos, 0) AS open_corrective_wos,
            COALESCE(d.unplanned_downtime_min, 0) AS unplanned_downtime_min,
            COALESCE(d.planned_downtime_min, 0) AS planned_downtime_min
        FROM telemetry_day t
        FULL OUTER JOIN lot_day l
            ON t.machine_id = l.machine_id AND t.day = l.day
        FULL OUTER JOIN scrap_usd_day s
            ON t.machine_id = s.machine_id AND t.day = s.day
        FULL OUTER JOIN ncr_day nc
            ON t.machine_id = nc.machine_id AND t.day = nc.day
        FULL OUTER JOIN downtime_day d
            ON t.machine_id = d.machine_id AND t.day = d.day
        FULL OUTER JOIN wo_day wd
            ON t.machine_id = wd.machine_id AND t.day = wd.day
    """, "cnc_daily_360")

    # 3. event_cost
    run(cur, f"""
        CREATE TABLE {CATALOG}.{SCHEMA}.event_cost AS
        WITH roundness_scrap AS (
            SELECT
                'bearing wear' AS event_name,
                'roundness scrap' AS cost_type,
                SUM(l.scrap_roundness) AS parts,
                SUM(l.scrap_roundness * m.unit_cost_usd) AS cost_usd,
                TRUE AS avoidable_with_early_warning
            FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_erp_materials m ON m.material_id = l.material_id
            WHERE l.machine_id = 'CNC-01'
              AND l.shift_date BETWEEN DATE '2024-01-28' AND DATE '2024-02-04'
        ),
        complaint AS (
            SELECT
                'bearing wear' AS event_name,
                'customer complaint' AS cost_type,
                qty_rejected_at_customer AS parts,
                cost_usd,
                TRUE AS avoidable_with_early_warning
            FROM {CATALOG}.cnc_qa.customer_complaints
        ),
        freight AS (
            SELECT
                'bearing wear' AS event_name,
                'expedite freight' AS cost_type,
                1 AS parts,
                freight_usd AS cost_usd,
                TRUE AS avoidable_with_early_warning
            FROM js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders
            WHERE po_id = '4500018821'
        ),
        late_penalty AS (
            SELECT
                'bearing wear' AS event_name,
                'late penalty' AS cost_type,
                1 AS parts,
                late_penalty_usd AS cost_usd,
                TRUE AS avoidable_with_early_warning
            FROM js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders
            WHERE so_id = 'SO-45012'
        ),
        bore_scrap AS (
            SELECT
                'coolant restriction' AS event_name,
                'bore scrap' AS cost_type,
                SUM(n.qty_scrapped) AS parts,
                SUM(n.qty_scrapped * m.unit_cost_usd) AS cost_usd,
                TRUE AS avoidable_with_early_warning
            FROM js_manuf_ice.cnc_qa.ncr n
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_erp_materials m ON m.material_id = n.material_id
            WHERE n.machine_id = 'CNC-01'
              AND n.characteristic = 'BORE_DIA'
              AND n.opened_ts BETWEEN TIMESTAMP '2024-02-13 00:00:00' AND TIMESTAMP '2024-02-15 23:59:59'
        ),
        current_drift AS (
            SELECT
                'current drift' AS event_name,
                'quality impact' AS cost_type,
                0 AS parts,
                0.0 AS cost_usd,
                TRUE AS avoidable_with_early_warning
        ),
        cnc02_imbalance AS (
            SELECT
                'CNC-02 imbalance' AS event_name,
                'roundness scrap' AS cost_type,
                SUM(l.scrap_roundness) AS parts,
                SUM(l.scrap_roundness * m.unit_cost_usd) AS cost_usd,
                FALSE AS avoidable_with_early_warning
            FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_erp_materials m ON m.material_id = l.material_id
            WHERE l.machine_id = 'CNC-02'
              AND l.shift_date >= DATE '2024-04-25'
        )
        SELECT * FROM roundness_scrap
        UNION ALL SELECT * FROM complaint
        UNION ALL SELECT * FROM freight
        UNION ALL SELECT * FROM late_penalty
        UNION ALL SELECT * FROM bore_scrap
        UNION ALL SELECT * FROM current_drift
        UNION ALL SELECT * FROM cnc02_imbalance
    """, "event_cost")

    # 4. order_risk
    run(cur, f"""
        CREATE TABLE {CATALOG}.{SCHEMA}.order_risk AS
        WITH open_orders AS (
            SELECT
                so.so_id,
                so.customer_id,
                so.material_id,
                so.qty,
                so.qty_shipped,
                so.due_date,
                (so.qty - COALESCE(po.qty_good, 0)) AS remaining_qty
            FROM js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders so
            LEFT JOIN js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders po ON po.so_id = so.so_id
            WHERE so.status = 'OPEN'
        ),
        recent_rate AS (
            SELECT
                l.prod_order_id,
                o.so_id,
                o.material_id,
                o.qty,
                o.qty_shipped,
                o.due_date,
                o.remaining_qty,
                AVG(l.qty_good) AS recent_avg_lot_good,
                MAX(l.end_ts) AS last_lot_end
            FROM open_orders o
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders p ON p.so_id = o.so_id
            JOIN js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l ON l.prod_order_id = p.prod_order_id
            WHERE l.end_ts IS NOT NULL
            GROUP BY l.prod_order_id, o.so_id, o.material_id, o.qty, o.qty_shipped, o.due_date, o.remaining_qty
        )
        SELECT
            so_id,
            material_id,
            qty,
            qty_shipped,
            remaining_qty,
            due_date,
            last_lot_end,
            recent_avg_lot_good,
            CAST(CEIL(remaining_qty / NULLIF(recent_avg_lot_good, 0)) AS INTEGER) AS est_days_remaining,
            CAST(DATE_ADD('day', CAST(CEIL(remaining_qty / NULLIF(recent_avg_lot_good, 0)) AS INTEGER), last_lot_end) AS TIMESTAMP) AS projected_finish,
            CAST(DATE_ADD('day', CAST(CEIL(remaining_qty / NULLIF(recent_avg_lot_good, 0)) AS INTEGER) + 1, last_lot_end) AS TIMESTAMP) AS projected_finish_with_8h_stop,
            DATE_DIFF('day', CAST(DATE_ADD('day', CAST(CEIL(remaining_qty / NULLIF(recent_avg_lot_good, 0)) AS INTEGER), last_lot_end) AS DATE), due_date) AS slack_days
        FROM recent_rate
    """, "order_risk")

    # smoke checks
    print("\\nSmoke checks:")
    for tbl in ["lot_context", "cnc_daily_360", "event_cost", "order_risk"]:
        cur.execute(f"SELECT count(*) FROM {CATALOG}.{SCHEMA}.{tbl}")
        print(f"  {tbl}: {cur.fetchone()[0]} rows")

    cur.execute(f"SELECT SUM(cost_usd) FROM {CATALOG}.{SCHEMA}.event_cost WHERE event_name = 'bearing wear' AND avoidable_with_early_warning")
    print(f"  Avoidable bearing cost: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
