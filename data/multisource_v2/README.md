# Smart Manufacturing multi-source demo data (synthetic)

All data is synthetic. Companies, suppliers and people are fictional. Timestamps are plant local time, no time zone.
Currency is USD. Rebuild with `python3 generate.py <CNC01 csv> data` and then `python3 generate_sqm.py data` (seeds 42 and 7).

Plant `PLANT-1000`, line `SP-1`, two horizontal machining centers: `CNC-01` (Jan–Mar 2024) and `CNC-02` (Apr 2024).
Three 8-hour shifts: A 06:00–14:00, B 14:00–22:00, C 22:00–06:00. One MES lot = one machine × one shift.

## Join keys

| Key | Links |
|---|---|
| `machine_id` / `asset_id` (`CNC-01`, `CNC-02`) | historian file name, MES, QA, CMMS, logbook |
| time window | telemetry hour falls inside MES lot `start_ts`–`end_ts`; downtime `start_ts`–`end_ts`; WO `started_ts`–`completed_ts` |
| `lot_id` (e.g. `L01-240130-A`) | MES lots ↔ downtime ↔ material consumption ↔ QA inspections ↔ NCR |
| `material_lot_id` (e.g. `ML-24-0007`) | MES material consumption ↔ SQM material lots ↔ CoA ↔ incoming inspections ↔ SCAR |
| `supplier_id` | SQM suppliers ↔ approved sources ↔ material lots ↔ scorecard ↔ SCAR |
| `po_id` | SQM material lots ↔ ERP purchase orders |
| `prod_order_id` | MES lots ↔ MES production orders |
| `so_id` | MES production orders ↔ ERP sales orders ↔ QA complaints |
| `material_id` | ERP materials ↔ MES ↔ QA ↔ SQM specs ↔ CMMS parts ↔ ERP purchase orders |
| `customer_id` | ERP sales orders ↔ ERP customers ↔ QA complaints |
| `wo_id` | CMMS ↔ ERP purchase orders (`ref_work_order`) ↔ MES downtime text |

## Files

| Folder (suggested system) | File | Rows | Contents |
|---|---|---:|---|
| historian/ | `CNC01_SpindleLine_60days_hourly_mes_aligned.csv` | 1,440 | Original CNC-01 file; the 8 bearing-replacement hours (2024-02-05 22:00 to 02-06 05:00) set to machine-stopped values |
| | `CNC01_SpindleLine_Month3_hourly.csv` | 744 | CNC-01 March; vibration and current rise from 2024-03-25 |
| | `CNC02_SpindleLine_30days_hourly.csv` | 720 | CNC-02 April; step on 2024-04-10 16:00 (toolholder change), then smooth progressive rise |
| mes/ | `production_orders.csv` | 9 | Production orders per sales order |
| | `production_lots.csv` | 363 | Per shift: run time, produced/good/scrap by reason, OEE |
| | `downtime_events.csv` | 473 | Planned/unplanned stops with reason codes |
| | `material_consumption.csv` | 383 | Lot genealogy: supplier material lot(s) consumed by each MES lot |
| erp/ | `customers.csv` | 3 | Fictional customers |
| | `materials.csv` | 10 | Finished goods, raw castings/billets, toolholder, spare parts |
| | `sales_orders.csv` | 10 | Due, ship, days late, late penalty |
| | `purchase_orders.csv` | 33 | Raw material, toolholder and spare-part POs (incl. expedited bearing) |
| | `spare_parts_stock.csv` | 5 | On-hand snapshots |
| | `cost_rates.csv` | 4 | Machine hour, labour, complaint handling rates |
| qa/ | `cmm_inspections.csv` | 5,370 | 5 samples per lot × bore diameter, roundness, surface Ra |
| | `ncr.csv` | 41 | Non-conformance reports with scrap cost |
| | `customer_complaints.csv` | 1 | Escaped roundness defects found by customer |
| sqm/ (supplier quality) | `suppliers.csv` | 5 | Suppliers, approval status, incoming inspection level |
| | `approved_sources.csv` | 7 | Approved supplier per material, priority |
| | `material_specs.csv` | 4 | Purchased-material specs (hardness HB, toolholder balance grade) |
| | `material_lots.csv` | 30 | Goods receipts: heat number, PO, release decision, status |
| | `certificates_of_analysis.csv` | 30 | Supplier-claimed hardness, chemistry, test location, balance grade |
| | `incoming_inspections.csv` | 151 | Receiving and audit hardness readings; skipped inspections |
| | `scar.csv` | 1 | Supplier corrective action request with 8D root cause and cost claim |
| | `supplier_scorecard.csv` | 8 | Monthly ppm, on-time delivery, rating |
| | `coa_documents/*.md` | 30 | Certificate text per lot (for the Data Search Engine) |
| cmms/ | `assets.json` | 2 | Asset master (nested spindle info) |
| | `work_orders.jsonl` | 9 | PM, corrective, calibration, inspection WOs (nested parts) |
| logbook/ | `shift_logbook.jsonl` | 220 | Free-text operator, setter, QA and maintenance notes |

## Embedded cross-source story

| Date (2024) | Source | What it shows |
|---|---|---|
| 12 Jan | SQM / ERP | SUP-A castings late; 5 lots from second source SUP-B received and released on CoA (reduced inspection, no hardness check) |
| 15 Jan 22:00 | MES / SQM | CNC-01 starts consuming SUP-B castings |
| 17 Jan 12:00 | Historian | CNC-01 VIB_X 6-hour mean first exceeds baseline + 3σ |
| 19 Jan, 24 Jan | Logbook | Operator hears spindle whine; no WO |
| 28 Jan B shift | QA | First roundness reject on VB-2210 |
| 29 Jan–4 Feb | MES / QA | 400 parts scrapped for roundness (USD 7,360); OEE falls to 0.43 |
| 30 Jan | CMMS / ERP | WO-24-0117 raised; no bearing in stock; PO 4500018821 by air (USD 1,180 freight) |
| 3 Feb | SQM | Hardness audit: SUP-B castings HB 238–261 vs spec max 230/240 (CoAs claimed 211–212, measured on a separate test bar). SCAR-24-003 opened; SUP-B stock quarantined; back to SUP-A |
| 5 Feb 22:00–6 Feb 06:00 | MES / Historian | 8 h stop for bearing replacement; vibration returns to baseline |
| 13–15 Feb | Historian / MES / QA | Coolant restriction; 217 parts scrapped for bore diameter (USD 3,993) — not supplier related |
| 20 Feb | ERP | SO-45012 ships 5 days late, USD 1,920 penalty |
| 20–25 Feb | Historian / QA / CMMS | Motor current drift, zero quality impact; failed cabinet fan |
| 24 Feb | QA | Customer complaint CC-24-001: 20 escaped parts (USD 868) |
| 15 Mar | SQM | SCAR-24-003 closed (8D: early shakeout → chilled carbides); claim USD 14,178 negotiating |
| 21–24 Mar | SQM / MES | SUP-B requalification trial lots (HB 225–237, inside spec but near the limit) issued to CNC-01 from 24 Mar 22:00 |
| 27 Mar 11:00 | Historian | CNC-01 vibration alert again, with a new bearing — repeat signal linked to SUP-B castings |
| 8–10 Apr | SQM / MES / Logbook | CNC-02 toolholder TH-0007 from SUP-C received with certificate balance grade G6.3 (spec G2.5); balancing check skipped; installed 10 Apr, runout check skipped |
| 10 Apr 21:00 | Historian | CNC-02 vibration alert, while still machining SUP-A castings |
| 13 Apr | MES / SQM | CNC-02 switches to SUP-E steel billets (hardness in spec) — a coincidence, not the cause |
| 24–30 Apr | QA | CNC-02 roundness NCRs, USD 4,264 scrap |
| 30 Apr | ERP / CMMS | SO-45060 (due 8 May) has 296 parts left; inspection WO-24-0241 open |

Supplier analysis in one line: CNC-01 average VIB_X is 1.62 mm/s on SUP-A castings and 2.87 mm/s on SUP-B castings (Jan–Feb); with a new bearing in March it is 1.63 on SUP-A and 1.98 on SUP-B.
The January SUP-B period overlaps the bearing failure, so the March repeat is what makes the supplier link convincing.
CNC-02 shows the opposite: the jump starts with the toolholder, before any SUP-E billet is used.

Note: hours right after the bearing restart keep the original telemetry values (run-in).
