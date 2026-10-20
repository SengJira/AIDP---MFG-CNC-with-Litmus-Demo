# Spindle to Customer — Runbook

## What the demo proves
The Dell AI Data Platform federates six synthetic plant systems (OT historian, MES, ERP, QA, CMMS, shift logbook) without copying the operational data. Starburst joins Iceberg lakehouse, MySQL business-system and Elasticsearch in place. The headline is a single CNC-01 bearing event that warned on 17 Jan, produced the first QA reject on 28 Jan, and cost USD 11,328 in avoidable scrap, escaped parts, air freight, and a late penalty.

## Environment
- Source environment variables with `source scripts/setup_env.sh`.
- TLS verification is disabled for the lab endpoints only (user approved).
- All credentials come from Devin Secrets / the loaded environment; no secrets are committed.

## 10-minute demo script

### 1. Sources (1 min)
Open the dashboard **Sources** tab. Point out the six tiles:
- OT, QA, CMMS live in `js_manuf_ice` (Iceberg on Dell ObjectScale).
- MES and ERP live in `js_mysql_mfg` (operational MySQL).
- Shift logbook lives in Elasticsearch.
Each tile shows the live `count(*)` and the fully-qualified table name. Emphasise the counts are current, yet the data has not been copied out of the source systems.

### 2. 360° View (3 min)
Switch to **360°**. Select `CNC-01`.
- The blue line is average VIB_X per day.
- Red bars are scrap parts per day.
- Red X markers show days when an NCR was opened.
Scroll to January: the VIB_X line rises around 17 Jan, then scrap bars and NCR markers appear after 28 Jan. This is the bearing-wear signature.
Switch to `CNC-02` to show the April imbalance / runout story building toward `SO-45060`.

### 3. Impact & Cost (3 min)
Open **Impact**.
- The top card shows **Avoidable bearing cost = USD 11,328**.
- The table lists every cost line: roundness scrap, bore scrap, air freight, late penalty, escaped complaint.
- The cross-source timeline lists the same event from the perspective of historian, logbook, QA, MES, CMMS and ERP.
- Scroll to the control-case panel: motor-current drift in Feb had zero quality impact because the root cause was a failed cabinet fan, not a real process issue.

### 4. Ask AI (2 min)
Open **Ask AI**. Click any of the four buttons, for example:
- *Why did SO-45012 ship late, and what did it cost?*
- *Should we stop CNC-02 for 8 hours this week, and will SO-45060 still ship on time?*
Each answer is transparent: it shows the plain-language conclusion, the SQL it ran, the MCP query IDs, and the cited work-order or logbook IDs. In the live booth demo, the same four questions are answered by a Devin session through the AIDP MCP Server.

### 5. Federated SQL close (1 min)
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
To restore the seeded state:
```bash
source scripts/setup_env.sh
python3 scripts/load_multisource.py
python3 scripts/create_analytics_views.py
python3 -m pytest tests/test_multisource.py -q
```
This reloads the raw data from the `data/multisource/` archive, recreates the Iceberg and MySQL tables, rebuilds the `cnc_analytics` tables, and re-runs the acceptance tests.

## Running the dashboard
Ask the user which host to bind. Then:
```bash
python3 -m streamlit run app/multisource_dashboard.py --server.address <host> --server.port 8501
```
To run offline without lab calls:
```bash
OFFLINE_MODE=1 python3 -m streamlit run app/multisource_dashboard.py --server.address <host> --server.port 8501
```
Do not expose the app outside the lab network.

## Fallbacks
- If the MCP Server is unavailable, the Ask AI tab uses the deterministic `cache/ask_ai/` JSON files.
- If Trino is unavailable, set `OFFLINE_MODE=1` to serve the dashboard from `cache/cnc_daily_360.parquet`, `cache/event_cost.parquet`, `cache/order_risk.parquet` and `cache/source_counts.json`.
- If Elasticsearch is unavailable, logbook citations still appear from the cached answer files.

## Acceptance tests
```bash
source scripts/setup_env.sh
python3 -m pytest tests/test_multisource.py -q
```
All 12 tests must pass before the demo is declared booth-ready.
