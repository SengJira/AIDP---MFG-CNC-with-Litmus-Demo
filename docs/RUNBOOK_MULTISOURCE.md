# Spindle to Customer — Runbook

## What the demo proves

The Dell AI Data Platform federates seven synthetic plant systems (OT historian, MES, ERP, QA, CMMS, SQM, and shift logbook) without copying the operational data. Starburst joins Iceberg lakehouse, MySQL business-system and Elasticsearch in place. The headline is a single CNC-01 bearing event that warned on 17 Jan, produced the first QA reject on 28 Jan, and cost USD 11,328 in avoidable scrap, escaped parts, air freight, and a late penalty. A second storyline shows CNC-02's April imbalance: the root cause is a SUP-C toolholder (TH-0007) installed on 10 Apr, not the SUP-E steel billets that arrive on 13 Apr.

## Environment

- Source the lab environment before any script or test run.
- TLS verification is disabled for the lab endpoints only (user approved).
- All credentials come from Devin Secrets / the loaded environment; no secrets are committed.

## 12-minute demo script

### 1. Sources (1 min)

Open the dashboard **Sources** tab. Point out the seven tiles:

- OT, QA, CMMS live in `js_manuf_ice` (Iceberg on Dell ObjectScale).
- MES and ERP live in `js_mysql_mfg` (operational MySQL).
- SQM lives in `js_mysql_mfg` (operational MySQL) with certificate text in Elasticsearch.
- Shift logbook lives in Elasticsearch.

Each tile shows the live `count(*)` and the fully-qualified table name. Emphasise the counts are current, yet the data has not been copied out of the source systems.

### 2. 360° View (2 min)

Switch to **360°**. Select `CNC-01`.

- The blue line is average VIB_X per day.
- Red bars are scrap parts per day.
- Red dashed lines show days when an NCR was opened.

Scroll to January: the VIB_X line rises around 17 Jan, then scrap bars and NCR markers appear after 28 Jan. This is the bearing-wear signature. Switch to `CNC-02` to show the April imbalance building toward `SO-45060`.

### 3. Supplier (2 min)

Open **Supplier**.

- The grouped bar chart shows `supplier_vibration_summary`: mean VIB_X by machine, supplier, and period, with the bearing replacement and the toolholder change marked. Point out SUP-B before/after the bearing replacement and the March trial-lots repeat.
- The hardness table highlights the SUP-B gap: CoA claims HB 211–212 while the audit measured HB 238–261. SKIPPED inspections are shaded red.
- The SCAR-24-003 panel shows the USD 14,178 claim.
- The scorecard summarises supplier performance.
- Drill into a supplier lot to see the certificate text from `cnc-demo-supplier-docs` and the MES lots that consumed it.

### 4. Impact & Cost (3 min)

Open **Impact**.

- The top card shows **Avoidable bearing cost = USD 11,328**.
- The table lists every cost line: roundness scrap, bore scrap, air freight, late penalty, escaped complaint, and the CNC-02 toolholder scrap of USD 4,264.
- The cross-source timeline lists the same event from the perspective of historian, logbook, QA, MES, CMMS, ERP and SQM. Call out the SQM lane: SUP-B released 12 Jan, issued to CNC-01 on 15 Jan, audit and SCAR on 3 Feb, closed 15 Feb, trial lots back on 24 Mar, and TH-0007 received on 8 Apr.
- Scroll to the control-case panel: motor-current drift in Feb had zero quality impact because the root cause was a failed cabinet fan, not a real process issue.

### 5. Ask AI (3 min)

Open **Ask AI**. Walk through questions 1, 5 and 6.

- *Why did SO-45012 ship late, and what did it cost?* — bearing wear and coolant restriction; 5 days late; USD 1,920 late penalty; 400 roundness scrap and 217 bore scrap.
- *Is a supplier material linked to the CNC-01 vibration?* — yes, SUP-B castings. 1.62 mm/s on SUP-A vs 2.87 mm/s on SUP-B in January; it repeats at 1.98 mm/s in March with a new bearing. Certificate CoA-ML-24-0007 claims HB 211–212 measured on a test bar; the actual castings measured HB 238–261. SCAR-24-003 claim is USD 14,178.
- *Are CNC-02's new steel billets from SUP-E causing its vibration?* — no. The first alert is at 2024-04-10 21:00, while CNC-02 is still on SUP-A castings. The first SUP-E billet is consumed at 2024-04-13 22:00. SUP-E hardness is in-spec. Toolholder lot ML-24-0901 certificate COA-ML-24-0901 shows balance grade G6.3 against a G2.5 spec, and the receiving balance/runout check was SKIPPED.

Each answer is transparent: it shows the plain-language conclusion, the SQL it ran, the MCP query IDs, and the cited certificate, logbook and work-order IDs. In the live booth demo the same questions are answered by a Devin session through the AIDP MCP Server.

### 6. Federated SQL close (1 min)

Optional: in a Devin session, run a cross-catalog query to reinforce the point:

```sql
SELECT h.day, h.avg_vib_x, s.downtime_minutes, nc.ncr_count
FROM js_manuf_ice.cnc_analytics.cnc_daily_360 h
LEFT JOIN js_mysql_mfg.js_mysql_mfg.cnc_mes_downtime_events s
  ON h.machine_id = s.machine_id AND h.day = DATE(s.start_ts)
LEFT JOIN js_manuf_ice.cnc_qa.ncr n
  ON h.machine_id = n.machine_id AND h.day = DATE(n.opened_ts)
WHERE h.machine_id = 'CNC-01'
ORDER BY h.day;
```

Show that a single Starburst SQL joins Iceberg, MySQL and aggregated QA.

## Reset steps

To restore the seeded v2 state:

```bash
python3 jobs/ingest_raw.py --pack data/multisource_v2
python3 scripts/create_analytics_views.py
python3 -m pytest tests/test_multisource.py -q
```

This reloads the v2 data pack, recreates the Iceberg and MySQL tables, rebuilds the `cnc_analytics` tables, and re-runs the acceptance tests.

## Running the dashboard

Ask the user which host to bind. Then:

```bash
python3 -m streamlit run app/multisource_dashboard.py --server.address <host> --server.port 8502
```

To run offline without lab calls:

```bash
OFFLINE_MODE=1 python3 -m streamlit run app/multisource_dashboard.py --server.address <host> --server.port 8502
```

Do not expose the app outside the lab network.

## Fallbacks

- If the MCP Server is unavailable, the Ask AI tab uses the deterministic `cache/ask_ai/` JSON files.
- If Trino is unavailable, set `OFFLINE_MODE=1` to serve the dashboard from `cache/cnc_daily_360.parquet`, `cache/event_cost.parquet`, `cache/order_risk.parquet`, `cache/supplier_*.parquet`, `cache/sqm_*.parquet` and `cache/source_counts.json`.
- If Elasticsearch is unavailable, logbook and supplier-doc citations still appear from the cached answer files.

## Acceptance tests

```bash
python3 -m pytest tests/test_multisource.py -q
```

All 19 tests must pass before the demo is declared booth-ready.
