# Data pack v2: supplier quality (SQM)

v2 adds supplier quality data and the lot genealogy that links it to production. Compared with v1, everything else is identical, except the rows listed here.

## New files
| File | Rows | Lands in |
|---|---:|---|
| `mes/material_consumption.csv` | 383 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_mes_material_consumption` |
| `sqm/suppliers.csv` | 5 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_suppliers` |
| `sqm/approved_sources.csv` | 7 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_approved_sources` |
| `sqm/material_specs.csv` | 4 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_specs` |
| `sqm/material_lots.csv` | 30 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_lots` |
| `sqm/certificates_of_analysis.csv` | 30 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis` |
| `sqm/incoming_inspections.csv` | 151 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections` |
| `sqm/scar.csv` | 1 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_scar` |
| `sqm/supplier_scorecard.csv` | 8 | MySQL `js_mysql_mfg.js_mysql_mfg.cnc_sqm_supplier_scorecard` |
| `sqm/coa_documents/*.md` | 30 docs | Elasticsearch `cnc-demo-supplier-docs` |

## Changed files
| File | What changed | Why |
|---|---|---|
| `historian/CNC02_SpindleLine_30days_hourly.csv` | VIB_X +0.30, VIB_Y +0.20, ACOUSTIC_DB +1.0 from 2024-04-10 16:00 (488 rows) | Imbalance step when toolholder TH-0007 goes in |
| `historian/CNC01_SpindleLine_Month3_hourly.csv` | MOTOR_CURRENT_A ramps up to +0.6 A from 2024-03-25 01:00 (167 rows) | Same pattern as January while SUP-B castings run |
| `mes/production_lots.csv`, `mes/production_orders.csv` | CNC-02 rows only (row count unchanged) | Recomputed from the new CNC-02 telemetry |
| `qa/cmm_inspections.csv`, `qa/ncr.csv` | CNC-02 rows only; NCRs 33 → 41 | Recomputed from the new CNC-02 telemetry |
| `erp/materials.csv` | +4 rows: RM-2210, RM-3140, RM-5120, TH-HSK63-SF | Purchased materials |
| `erp/purchase_orders.csv` | +30 rows (existing 3 unchanged) | One PO per supplier material lot |
| `cmms/work_orders.jsonl` | WO-24-0241 `problem` text | Mentions roundness rejects and the toolholder |
| `logbook/shift_logbook.jsonl` | LB-00220 `text` | QA note: rejects since 24 Apr, billets in spec |

All CNC-01 rows in MES and QA are byte-identical to v1. So are downtime events, sales orders, customers, cost rates, spare stock, complaints, assets, and the CNC-01 Jan–Feb telemetry.

## Expected values that change
| Check | v1 | v2 |
|---|---|---|
| ncr rows | 33 | 41 |
| materials rows | 6 | 10 |
| purchase_orders rows | 3 | 33 |
| First CNC-02 NCR lot | L02-240425-B | L02-240424-C |
| CNC-02 roundness scrap | USD 1,107 | USD 4,264 |
| SO-45060 remaining qty | 219 | 296 (finishes about 5 May, due 8 May) |
| CNC-02 first vibration alert | 2024-04-14 15:00 | 2024-04-10 21:00 |
