# Changelog

## [2.0.0] - Add supplier quality (SQM) to Spindle to Customer

### Added

- `jobs/ingest_raw.py` — idempotent v2 loader supporting `--pack data/multisource_v2 --tables <groups>` and full Elasticsearch support.
- SQM source tables in `js_mysql_mfg.js_mysql_mfg`: `cnc_sqm_suppliers`, `cnc_sqm_approved_sources`, `cnc_sqm_material_specs`, `cnc_sqm_material_lots`, `cnc_sqm_certificates_of_analysis`, `cnc_sqm_incoming_inspections`, `cnc_sqm_scar`, `cnc_sqm_supplier_scorecard`.
- `cnc_mes_material_consumption` in MySQL for lot genealogy.
- `cnc-demo-supplier-docs` Elasticsearch index with 30 CoA markdown documents.
- Analytics tables: `supplier_lot_impact` and `supplier_vibration_summary`.
- Dashboard **Supplier** tab with vibration chart, hardness table, SCAR-24-003 panel, scorecard, and certificate/MES-lot drill-down.
- Ask AI cache questions 5 and 6 covering SUP-B castings and the CNC-02 toolholder counterexample.
- Acceptance tests for SQM row counts, lot genealogy, supplier vibration, hardness gap, toolholder SKIPPED inspection, and CNC-02 timing.
- `scripts/backup_v1.py` and `scripts/rollback_v1.py` for v1 backup/restore.

### Changed

- Replaced v1 source data with `data/multisource_v2/`; CNC-01 Jan/Feb data remains byte-identical.
- Updated `lot_context` to include `main_material_lot_id`, `main_supplier_id` and `raw_material_id`.
- Updated `event_cost` to attribute the USD 4,264 CNC-02 scrap to toolholder TH-0007 (SUP-C), not SUP-E.
- Updated `order_risk` to compute a daily good rate; `SO-45060` now shows 296 parts remaining and a finish around 6 May.
- Updated `docs/RUNBOOK_MULTISOURCE.md` to a 12-minute demo script with a 2-minute Supplier beat and Ask AI questions 1, 5 and 6.

### Fixed

- `cnc_daily_360` no longer extends beyond the telemetry date range because it starts from `telemetry_day` with `LEFT JOIN`s.

## [1.0.0] - Multi-source Spindle to Customer demo

- Initial six-source federation (OT historian, MES, ERP, QA, CMMS, shift logbook) with 360° views, `event_cost`, `order_risk`, Ask AI cache, dashboard, and 12 acceptance tests.
