# Spindle to Customer — AIDP Environment Discovery

Date: 2026-10-20 03:45:11 UTC
Scope: Non-destructive reachability and inventory for the multi-source CNC demo.
TLS: verification disabled for this lab demo only (`verify=False` / `--insecure`).

## 1. ObjectScale / S3

Reachable: yes (1 buckets)
Buckets: js-demo
cnc-demo/ prefix objects seen: 20
Write permission on s3://js-demo/cnc-demo/: yes

## 2. Starburst / Trino

Reachable: yes
Catalogs: js_financial_ice, js_manuf_ice, js_mysql_customer360, system, tpch
js_manuf_ice schemas: information_schema, schema_discovery, smart_mfg, system
  js_manuf_ice.information_schema: applicable_roles, columns, enabled_roles, roles, schemata, table_privileges, tables, views
  js_manuf_ice.schema_discovery: discovery, shallow_discovery
  js_manuf_ice.smart_mfg: anomaly_events, anomaly_scores, equipment, label_bank, labels, sensor_readings
  js_manuf_ice.system: iceberg_tables, materialized_view_refreshes
js_mysql_customer360 schemas: customer360, information_schema, performance_schema
  js_mysql_customer360.customer360: customers
  js_mysql_customer360.information_schema: applicable_roles, columns, enabled_roles, roles, schemata, table_privileges, tables, views
  js_mysql_customer360.performance_schema: (empty)

## 3. DDAE MCP Server

Endpoint: https://ddae.lab9bgp.com/mcp
MCP auth header is configured from TRINO credentials (Basic base64).
Read-only SQL tool will be discovered in Step 4 (Ask AI).
For Step 0 inventory the Trino client was used to list catalogs, schemas, and tables.

## 4. Data Processing Engine (DPE) CLI

CLI path: /home/betalab/jirawut/dell-data-processing-engine/bin/dell-data-processing-engine
--help exit code: 0
```
Usage: dell-data-processing-engine [-h] [--insecure] [--format=<displayMode>]
                                   [--log-level=<logLevel>]
                                   [--logLevel=<messagingMode>] [-p=<profile>]
                                   [--cert=<path>]... [--keystore=<path:
                                   password>]... [COMMAND]
Use this application to manage Spark
  -h, --help                Show usage help and exit. Note: must be the last
                              argument.

Global Options
  -p, --profile=<profile>   Configuration profile to use (default profile is
                              used if not specified)
      --log-level=<logLevel>
                            Change the output/logging level: standard, debug
      --cert=<path>         Path to an X509 client certificate (PEM format) or
                              a directory of X509 client certificates
      --keystore=<path:password>
                            Path to a KeyStore containing client certificates
                              and the KeyStore password
      --insecure            Skip SSL certificate validation. WARNING! This
                              should only be used for testing.
      --logLevel=<messagingMode>
                            DEPRECATED - use --log-level instead
      --format=<displayMode>
                            For commands that produce a result, changes how the
                              result is formatted: table, simple, json,
                              prettyJson, raw
Commands:
  config                  Commands to configure this application
  login                   Login, start a new session, and set/change the
                            default profile
  login-with-credentials  Login, start a new session, and set/change the
                            default profile using your username and password
  submit                  Emulation of Spark's spark-submit script
  notebook                Notebook management
  instance                Instance management
  uploads                 Commands to manage file uploads and secrets
  profile                 Commands to get or set the default profile
  version                 Show the current version
  admin                   Commands that require an admin role

```
version subcommand exit code: 0
version stdout: 250-476-e-RC2

## 5. Elasticsearch / Data Search Engine

Reachable: yes
Cluster name: ddse-0
Version: 9.3.0
Cluster status: green
Existing indices: 39
Trained models: none found
ELSER/semantic_text availability: will be tested by creating a temporary index during Step 1 logbook indexing.
Index-creation privilege: yes

## 6. Input data

Expected input: data/multisource/ from aidp_multisource_data.zip
Status: unzipped.
Files present:
- historian/: 3 telemetry CSVs
- mes/: production_orders.csv, production_lots.csv, downtime_events.csv
- erp/: customers.csv, materials.csv, sales_orders.csv, purchase_orders.csv, spare_parts_stock.csv, cost_rates.csv
- qa/: cmm_inspections.csv, ncr.csv, customer_complaints.csv
- cmms/: assets.json, work_orders.jsonl
- logbook/: shift_logbook.jsonl
- generate.py, README.md
README.md read; join keys and embedded timeline captured.

## 7. Summary and plan

What works:
- ObjectScale (S3): reachable, js-demo bucket present, cnc-demo/ prefix writable.
- Starburst/Trino: reachable; catalogs, schemas and tables listed above.
- DPE CLI: present, help/version output recorded above.
- Elasticsearch: reachable, cluster healthy, index-creation privilege confirmed.
- Input data: unzipped and ready.

TLS note: Python clients and DPE CLI use `--insecure` / `verify=False` for this lab demo only.

Proposed implementation plan:
1. Step 1: land telemetry/QA/CMMS in Iceberg, MES/ERP in MySQL via staging, logbook in Elasticsearch.
2. Step 2: create federated views lot_context, cnc_daily_360, event_cost, order_risk in js_manuf_ice.cnc_analytics.
3. Step 3: optional data product.
4. Step 4: build MCP Ask AI agent with read-only SQL and logbook search; cache answers.
5. Step 5: Streamlit dashboard Sources/360/Impact/Ask AI.
6. Step 6: acceptance tests and screenshots.

STOPPED after Step 0 — awaiting approval to begin Step 1.
