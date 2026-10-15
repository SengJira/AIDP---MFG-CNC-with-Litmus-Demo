# CNC Spindle Health — AIDP Environment Discovery

Date: 2026-10-15
Scope: Non-destructive reachability and capability check of the Dell AIDP lab environment for the `cnc-demo` / `smart_mfg` scope.

---

## 1. Storage Engine — ObjectScale / S3

| Item | Value |
|---|---|
| Endpoint | `http://172.18.11.31:9020` |
| Reachable | Yes (HTTP 200 from `list_buckets`) |
| Credentials location | Environment variables `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`. Never commit. |
| Existing bucket | `js-demo` |
| Demo prefix | `s3://js-demo/cnc-demo/raw/` |

Observations:
- Raw CSVs (`CNC01`, `CNC01 Month3`, `CNC02`) are uploaded under `s3://js-demo/cnc-demo/raw/`.

## 2. Data Analytics Engine — Starburst / Trino + MCP

### 2a. Trino SQL

| Item | Value |
|---|---|
| Web UI / Gateway | `https://ddae.lab9bgp.com/` |
| Python client | `trino` installed |
| Connection | `trino.dbapi.connect(host='ddae.lab9bgp.com', port=443, http_scheme='https', auth=BasicAuthentication(...), catalog='js_manuf_ice', verify=False)` |
| Credentials location | `TRINO_USER` / `TRINO_PASS` (never commit) |

Discovered catalogs:
- `js_financial_ice`
- `js_manuf_ice`  ← manufacturing Iceberg catalog
- `js_mysql_customer360`
- `system`
- `tpch`

Created:
- Schema: `js_manuf_ice.smart_mfg` with explicit S3 location `s3://js-demo/cnc-demo/warehouse/smart_mfg`.
- Tables: `sensor_readings`, `equipment`, `anomaly_scores`, `anomaly_events`, `labels`, `label_bank`.
- Verified counts: `CNC-01` 2,184 rows, `CNC-02` 720 rows.

### 2b. MCP Server — `https://ddae.lab9bgp.com/mcp`

| Item | Value |
|---|---|
| Server name | `Starburst Enterprise MCP Server` v1.0.0 |
| Transport | Streamable HTTP (stateless authenticated endpoint) |
| Auth | HTTP Basic Auth with Trino credentials |
| Required headers | `Accept: text/event-stream, application/json`; `Content-Type: application/json`; `mcp-session-id: <uuid>` after initialize |
| Credentials location | `AIDP_MCP_AUTH` (Basic base64) or `AIDP_MCP_USER`/`AIDP_MCP_PASS` (never commit) |
| Client package | `mcp` (official Python SDK) installed |

Discovered tools:

1. **`queryReadOnly`**
   - Input schema: `{"query": <string>}`
   - Description: read-only Trino SQL executor; accepts `SELECT`, `SHOW`, `DESCRIBE`.
   - Tested: `SHOW CATALOGS` returned the expected catalogs and `SELECT ... FROM smart_mfg.sensor_readings` returns counts.

2. **`searchDataProducts`**
   - Input schema: `{"query": <string>}`
   - Description: search available Starburst Data Products.

## 3. Data Processing Engine — Spark / DPE

| Item | Value |
|---|---|
| API endpoint | `https://ddpe-http.ddpe.lab9bgp.com` |
| CLI binary | `~/jirawut/dell-data-processing-engine/bin/dell-data-processing-engine` (v`250-476-e-RC2`) |
| Java requirement | Requires Java 22+ (class file version 66.0); the default system Java 21 fails |
| Working Java home | `/home/betalab/workspace/tk/openjdk/jdk-27` |
| Credentials location | Same as Trino, via `dell-data-processing-engine config set` |

Observations:
- The DPE CLI is present and works with Java 27.
- The demo uses local PySpark as a ready-to-run fallback.

## 4. Data Search Engine — Elasticsearch

| Item | Value |
|---|---|
| Kibana URL | `https://kibana-https.ddse.lab9bgp.com/app/home` |
| Elasticsearch URL | `https://elasticsearch-https.ddse.lab9bgp.com` |
| Reachable | Yes (HTTP 200 with API key) |
| Version | `9.3.0` |
| Credentials location | `ELASTIC_ENDPOINT` / `ELASTIC_API_KEY` environment variables (never commit) |
| Python client | `elasticsearch` installed |

Observations:
- Basic auth with the Trino-style username/password returns HTTP 401; the API key is required.
- `scripts/index_knowledge.py` will index the `knowledge/` markdown docs when the Elastic env vars are set.

## 5. Ask AI / LLM Endpoint

| Item | Value |
|---|---|
| Lab OpenAI-compatible endpoint | Not provided |
| Status | No LLM base available |

Decision: no Python Ask AI agent is built. The NL-to-SQL demo is delivered via the Devin Ask panel with the AIDP Analytics MCP Server.

## 6. Local Tooling

| Tool | Status |
|---|---|
| `python3` | 3.11.9 |
| `pip` | 26.2.1 (user site) |
| `make` | present |
| `git` | present, not yet initialized as a repo |
| `docker` | 27.5.1; `docker compose` not installed locally |
| Java 27 | `/home/betalab/workspace/tk/openjdk/jdk-27/bin/java` |
| `streamlit` | installed |
| `plotly` | installed |
| `pyspark` | installed |
| `pandas` / `numpy` | installed |
| `scikit-learn` | installed |
| `scipy` | installed |
| `pyarrow` | installed |
| `boto3` | installed |
| `trino` | installed |
| `elasticsearch` | installed |
| `pytest` | installed |
| `mcp` | installed |

## 7. Datasets

| File | Rows | Notes |
|---|---|---|
| `data/raw/CNC01_SpindleLine_60days_hourly.csv` | 1,440 | 2024-01-01 00:00 to 2024-02-29 23:00 |
| `data/raw/CNC01_SpindleLine_Month3_hourly.csv` | 744 | Generated, clean then smooth rise from 2024-03-25 |
| `data/raw/CNC02_SpindleLine_30days_hourly.csv` | 720 | Generated, 15–20% higher baseline, smooth rise from 2024-04-11 |

## 8. Proposed & Implemented Fallbacks

- **Offline mode (`OFFLINE_MODE=1`)**: serve data from generated Parquet files and cached knowledge JSON with no cluster calls.
- **Local PySpark** for the detection job until a DPE cluster submission is wired in.
- **Local TF-IDF knowledge index** (`data/processed/knowledge_index.json`) for offline search; Elasticsearch upload when `ELASTIC_ENDPOINT` is set.
- **Static Ask AI tab** in the Streamlit dashboard with the three scripted questions, SQL and citations.
