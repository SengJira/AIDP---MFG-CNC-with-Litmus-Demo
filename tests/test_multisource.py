import os
import time
from datetime import datetime

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
        "js_manuf_ice.cnc_qa.ncr": 41,
        "js_manuf_ice.cnc_qa.customer_complaints": 1,
        "js_manuf_ice.cnc_cmms.assets": 2,
        "js_manuf_ice.cnc_cmms.work_orders": 9,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders": 9,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots": 363,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_downtime_events": 473,
        "js_mysql_mfg.js_mysql_mfg.cnc_mes_material_consumption": 383,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_customers": 3,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_materials": 10,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders": 10,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders": 33,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_spare_parts_stock": 5,
        "js_mysql_mfg.js_mysql_mfg.cnc_erp_cost_rates": 4,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_suppliers": 5,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_approved_sources": 7,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_specs": 4,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_lots": 30,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis": 30,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections": 151,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_scar": 1,
        "js_mysql_mfg.js_mysql_mfg.cnc_sqm_supplier_scorecard": 8,
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
    assert rows[0][0] == "L02-240424-C"


def test_so45060_remaining():
    rows = query(
        "SELECT remaining_qty FROM js_manuf_ice.cnc_analytics.order_risk WHERE so_id='SO-45060'"
    )
    assert rows[0][0] == 296


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


def test_es_supplier_docs_count():
    from elasticsearch import Elasticsearch
    es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"], verify_certs=False, ssl_show_warn=False)
    assert es.count(index="cnc-demo-supplier-docs")["count"] == 30


def test_material_consumption_genealogy():
    rows = query(
        "SELECT l.lot_id, l.qty_produced, COALESCE(SUM(c.qty_consumed), 0) "
        "FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots l "
        "LEFT JOIN js_mysql_mfg.js_mysql_mfg.cnc_mes_material_consumption c ON c.lot_id = l.lot_id "
        "WHERE l.qty_produced > 0 "
        "GROUP BY l.lot_id, l.qty_produced "
        "HAVING COALESCE(SUM(c.qty_consumed), 0) = 0 OR COALESCE(SUM(c.qty_consumed), 0) != l.qty_produced"
    )
    assert rows == [], f"Genealogy mismatch lots: {rows[:5]}"


def test_supplier_vibration_cnc01():
    sup_a_jan = query(
        "SELECT AVG(avg_vib_x) FROM js_manuf_ice.cnc_analytics.lot_context "
        "WHERE machine_id='CNC-01' AND main_supplier_id='SUP-A' "
        "AND start_ts >= TIMESTAMP '2024-01-01 00:00:00' AND end_ts < TIMESTAMP '2024-01-15 00:00:00'"
    )[0][0]
    assert abs(sup_a_jan - 1.62) < 0.02, f"SUP-A Jan mean VIB_X was {sup_a_jan}"
    sup_b_jan = query(
        "SELECT AVG(avg_vib_x) FROM js_manuf_ice.cnc_analytics.lot_context "
        "WHERE machine_id='CNC-01' AND main_supplier_id='SUP-B' "
        "AND start_ts >= TIMESTAMP '2024-01-15 00:00:00' AND end_ts < TIMESTAMP '2024-02-03 00:00:00'"
    )[0][0]
    assert abs(sup_b_jan - 2.87) < 0.07, f"SUP-B Jan mean VIB_X was {sup_b_jan}"
    sup_a_feb = query(
        "SELECT AVG(avg_vib_x) FROM js_manuf_ice.cnc_analytics.lot_context "
        "WHERE machine_id='CNC-01' AND main_supplier_id='SUP-A' "
        "AND start_ts >= TIMESTAMP '2024-02-06 00:00:00' AND end_ts < TIMESTAMP '2024-03-24 00:00:00'"
    )[0][0]
    assert abs(sup_a_feb - 1.63) < 0.05, f"SUP-A post-bearing mean VIB_X was {sup_a_feb}"
    sup_b_mar = query(
        "SELECT AVG(avg_vib_x) FROM js_manuf_ice.cnc_analytics.lot_context "
        "WHERE machine_id='CNC-01' AND main_supplier_id='SUP-B' "
        "AND start_ts >= TIMESTAMP '2024-03-24 00:00:00' AND end_ts < TIMESTAMP '2024-04-01 00:00:00'"
    )[0][0]
    assert abs(sup_b_mar - 1.98) < 0.05, f"SUP-B trial mean VIB_X was {sup_b_mar}"


def test_sup_b_hardness_gap():
    rows = query(
        "SELECT MIN(measured), MAX(measured) FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections "
        "WHERE material_lot_id IN (SELECT material_lot_id FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_lots WHERE supplier_id='SUP-B') "
        "AND inspection_type='AUDIT' AND (characteristic='HARDNESS' OR characteristic='HARDNESS_HB')"
    )[0]
    assert rows[0] == 238, f"SUP-B min measured hardness {rows[0]}"
    assert rows[1] == 261, f"SUP-B max measured hardness {rows[1]}"
    coa = query(
        "SELECT MIN(hardness_hb_claimed), MAX(hardness_hb_claimed) "
        "FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis "
        "WHERE supplier_id='SUP-B' AND issued_date >= DATE '2024-01-01' AND issued_date < DATE '2024-02-01'"
    )[0]
    assert coa[0] == 211.0
    assert coa[1] == 212.0


def test_toolholder_ml_24_0901():
    coa = query("SELECT balance_grade_claimed FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis WHERE material_lot_id='ML-24-0901'")[0][0]
    assert abs(coa - 6.3) < 0.01
    spec = query(
        "SELECT usl FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_specs "
        "WHERE material_id='TH-HSK63-SF' AND characteristic='BALANCE_GRADE_G'"
    )
    assert len(spec) > 0
    assert spec[0][0] == 2.5
    skipped = query(
        "SELECT result FROM js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections "
        "WHERE material_lot_id='ML-24-0901' AND inspection_type='RECEIVING'"
    )[0][0]
    assert skipped == "SKIPPED"


def test_cnc02_first_alert_timing():
    first_alert = query(
        "WITH baseline AS ("
        "  SELECT AVG(VIB_X_MM_S) AS m, STDDEV(VIB_X_MM_S) AS s "
        "  FROM js_manuf_ice.cnc_historian.sensor_readings "
        "  WHERE equipment_id='CNC-02' AND ts < TIMESTAMP '2024-04-10 14:00:00'"
        "), "
        "rolling AS ("
        "  SELECT ts, AVG(VIB_X_MM_S) OVER (ORDER BY ts ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) AS vib6 "
        "  FROM js_manuf_ice.cnc_historian.sensor_readings "
        "  WHERE equipment_id='CNC-02' AND ts >= TIMESTAMP '2024-04-10 14:00:00'"
        ") "
        "SELECT MIN(r.ts) FROM rolling r JOIN baseline b ON 1=1 "
        "WHERE r.vib6 > b.m + 3*b.s"
    )[0][0]
    assert first_alert is not None
    assert first_alert >= datetime.fromisoformat("2024-04-10 21:00:00"), f"first alert {first_alert}"
    assert first_alert < datetime.fromisoformat("2024-04-10 22:00:00"), f"first alert {first_alert}"
    first_e = query(
        "SELECT MIN(issued_ts) FROM js_mysql_mfg.js_mysql_mfg.cnc_mes_material_consumption "
        "WHERE machine_id='CNC-02' AND supplier_id='SUP-E'"
    )[0][0]
    assert first_e > first_alert, f"SUP-E first consumption {first_e} should be after first alert {first_alert}"


def test_cnc02_scrap_cost():
    rows = query(
        "SELECT SUM(cost_usd) FROM js_manuf_ice.cnc_analytics.event_cost WHERE event_name LIKE 'CNC-02 imbalance%'"
    )[0][0]
    assert abs(rows - 4264.0) < 0.01
