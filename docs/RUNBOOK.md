# CNC Spindle Health — Demo Runbook

## 11-minute booth script

| Time | Step | What to say / do |
|------|------|------------------|
| 0:00 | **Set the scene** | "We are monitoring two CNC spindles on the Dell AI Data Platform. All data is synthetic." Open the dashboard Overview tab. |
| 0:30 | **Show the architecture** | Point to the architecture strip: green = live Dell component, grey = local fallback. Mention ObjectScale, Starburst/Trino, MCP, DPE, Elastic. |
| 1:30 | **Detect on CNC-01** | Go to Detect. Select CNC-01, click Run detection. While it runs: "The detection uses z-score, IQR, EWMA and Isolation Forest and produces a consensus score." |
| 3:00 | **First warning** | Point to the yellow marker at 2024-01-17 12:00. "This is where the 6-hour rolling VIB_X mean crossed baseline+3σ." |
| 4:00 | **Anomaly events** | Show the consensus ranking table. Highlight the high-severity impulsive bearing event and the smooth coolant event. |
| 5:30 | **Investigate** | Switch to Investigate, pick a bearing event and a coolant event, show the linked multi-signal charts. |
| 7:00 | **Label Bank** | Open Label Bank. Show the pre-seeded bank. Select an event, confirm, note root cause, promote to Label Bank. Try to promote an Instrumentation label and show it is blocked. |
| 8:30 | **Fleet transfer** | Open Fleet. Compare CNC-02 seeded vs unseeded: first flag is earlier with the seed, and the signature is smooth. |
| 9:30 | **Ask AI via Devin MCP** | Switch to Ask AI or use the Devin Ask panel with the AIDP Analytics MCP Server. Ask the three scripted questions; show SQL + citations. |
| 10:30 | **Reset for next demo** | Click Reset demo (or run `make demo-reset`). Confirm the dashboard returns to the pre-seeded state. |

## Reset steps

```bash
make demo-reset
```

This removes any session labels and dashboard run outputs and re-executes `scripts/seed_label_bank.py`.

To fully rebuild from scratch:

```bash
make demo-setup
```

This also re-creates the Trino schema and re-uploads the raw CSVs to S3.

## Failure fallbacks

### No lab network

```bash
make offline
```

The dashboard serves data from `data/processed/*.parquet` and the Ask AI tab shows cached SQL/answers. Detection still runs locally with PySpark because it reads the local Parquet cache.

### Trino or S3 unavailable

The dashboard marks the component grey. The Detect, Investigate, Fleet and Ask AI (static) tabs still work if the run outputs were produced by `make demo-setup` earlier.

### Streamlit unavailable

Run the detection and inspection from the command line:

```bash
python3 jobs/detect.py --equipment-id CNC-01 --run-id cnc01_baseline
python3 -m pytest -q
```

## Key timestamps to verify

- CNC-01 first rolling VIB_X warning: **2024-01-17 12:00**
- CNC-01 bearing replacement: **2024-02-06**
- CNC-02 smooth rise begins: around **2024-04-11**
