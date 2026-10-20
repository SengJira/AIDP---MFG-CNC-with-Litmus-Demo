import os
import time

import pytest
import trino
from trino.auth import BasicAuthentication


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
        return cur.fetchall()


def test_row_counts():
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
    for table, n in expected.items():
        rows = query(f"SELECT count(*) FROM {table}")
        assert rows[0][0] == n, f"{table}: got {rows[0][0]}, expected {n}"


def test_cnc01_roundness_scrap():
    rows = query(
        "SELECT SUM(scrap_roundness) FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots "
        "WHERE machine_id='CNC-01' AND shift_date BETWEEN DATE '2024-01-28' AND DATE '2024-02-04'"
    )
    assert rows[0][0] == 400


def test_cnc01_bore_scrap():
    rows = query(
        "SELECT SUM(qty_scrapped) FROM js_manuf_ice.cnc_qa.ncr "
        "WHERE machine_id='CNC-01' AND characteristic='BORE_DIA'"
    )
    assert rows[0][0] == 217


def test_so45012():
    rows = query(
        "SELECT days_late, late_penalty_usd FROM js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders WHERE so_id='SO-45012'"
    )
    days, penalty = rows[0]
    assert days == 5
    assert abs(penalty - 1920.0) < 0.01


def test_complaint():
    rows = query("SELECT qty_rejected_at_customer, cost_usd FROM js_manuf_ice.cnc_qa.customer_complaints WHERE complaint_id='CC-24-001'")
    qty, cost = rows[0]
    assert qty == 20
    assert abs(cost - 868.0) < 0.01


def test_po_freight():
    rows = query("SELECT freight_usd FROM js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders WHERE po_id='4500018821'")
    assert abs(rows[0][0] - 1180.0) < 0.01


def test_event_cost_bearing():
    rows = query(
        "SELECT SUM(cost_usd) FROM js_manuf_ice.cnc_analytics.event_cost "
        "WHERE event_name='bearing wear' AND avoidable_with_early_warning"
    )
    assert abs(rows[0][0] - 11328.0) < 0.01


def test_zero_ncr_current_drift():
    rows = query(
        "SELECT count(*) FROM js_manuf_ice.cnc_qa.ncr "
        "WHERE machine_id='CNC-01' "
        "AND opened_ts >= TIMESTAMP '2024-02-19 00:00:00' "
        "AND opened_ts < TIMESTAMP '2024-02-27 00:00:00'"
    )
    assert rows[0][0] == 0


def test_first_cnc02_ncr_lot():
    rows = query(
        "SELECT lot_id FROM js_manuf_ice.cnc_qa.ncr "
        "WHERE machine_id='CNC-02' ORDER BY opened_ts LIMIT 1"
    )
    assert rows[0][0] == "L02-240425-B"


def test_so45060_remaining():
    rows = query(
        "SELECT remaining_qty FROM js_manuf_ice.cnc_analytics.order_risk WHERE so_id='SO-45060'"
    )
    assert rows[0][0] == 219


def test_lot_l01_240205_c_stopped():
    rows = query(
        "SELECT run_min FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots WHERE lot_id='L01-240205-C'"
    )
    assert rows[0][0] == 0
    rows = query(
        "SELECT COUNT(*) FROM js_manuf_ice.cnc_historian.sensor_readings "
        "WHERE equipment_id='CNC-01' AND ts >= TIMESTAMP '2024-02-05 22:00:00' "
        "AND ts < TIMESTAMP '2024-02-06 05:00:00' AND SPINDLE_RPM = 0"
    )
    assert rows[0][0] == 7


def test_cnc_daily_360_performance():
    t0 = time.time()
    rows = query("SELECT count(*) FROM js_manuf_ice.cnc_analytics.cnc_daily_360")
    elapsed = time.time() - t0
    assert rows[0][0] > 0
    assert elapsed < 10, f"cnc_daily_360 took {elapsed:.2f}s"
