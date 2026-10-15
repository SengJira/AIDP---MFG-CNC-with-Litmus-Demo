# CNC Spindle Health — Dell AIDP Smart Manufacturing Demo

A booth-ready predictive-maintenance demo for CNC spindles on the Dell AI Data Platform (AIDP).

## What it shows

1. Synthetic CNC historian data lands on Dell ObjectScale S3 storage.
2. Starburst/Trino exposes the data through the `js_manuf_ice.smart_mfg` catalog.
3. PySpark anomaly detection (z-score, IQR, EWMA, Isolation Forest) flags early bearing wear, coolant restriction and transmitter drift.
4. Engineers confirm or dismiss events; confirmed patterns become a reusable **Label Bank**.
5. The same seeded profile transfers to a sister machine (CNC-02).
6. Natural-language-to-SQL is demonstrated through the AIDP Analytics MCP Server in a Devin session.

## Prerequisites

- Python 3.11+
- `python3` on PATH (the environment does not provide `python`)
- Environment variables for the AIDP lab:
  - `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
  - `TRINO_USER`, `TRINO_PASS`
  - `ELASTIC_ENDPOINT`, `ELASTIC_API_KEY` (optional)
  - `AIDP_MCP_URL`, `AIDP_MCP_AUTH` (for the Devin MCP demo)

Install the required packages locally:

```bash
pip install --user streamlit plotly pyspark pandas numpy scikit-learn scipy pyarrow boto3 trino elasticsearch pytest mcp
```

If you run the DPE CLI, point `JAVA_HOME` to Java 27 (the CLI rejects Java 21):

```bash
export JAVA_HOME=/home/betalab/workspace/tk/openjdk/jdk-27
export PATH=$JAVA_HOME/bin:$PATH
```

## Quick start

```bash
# full setup (generates data, lands to S3/Trino, runs detections, seeds the Label Bank, indexes knowledge)
make demo-setup

# run tests
make test

# start the dashboard
make dashboard

# offline fallback (no cluster calls)
make offline
```

## Repository layout

```text
app/              Streamlit dashboard
scripts/          generate_synthetic, land_data, seed_label_bank, index_knowledge, reset_demo
jobs/             PySpark detection job
tests/            pytest suite
knowledge/        markdown knowledge docs for the AI assistant
infra/            Dockerfile and docker-compose for deployment
docs/             ENVIRONMENT.md and RUNBOOK.md
data/             raw CSVs and processed Parquet/JSON outputs
```

## Key demo points

- CNC-01 bearing warning first appears at **2024-01-17 12:00**.
- Bearing replacement happened on **2024-02-06**, giving about **20 days** of early warning.
- CNC-02 seeded detection flags VIB-X earlier and as a **smooth** signature, pointing to imbalance/runout rather than bearing spall.

## Offline mode

Set `OFFLINE_MODE=1` to serve the dashboard from cached Parquet and knowledge JSON without any S3, Trino or Elastic calls. Useful for a laptop or a booth with no lab network.
