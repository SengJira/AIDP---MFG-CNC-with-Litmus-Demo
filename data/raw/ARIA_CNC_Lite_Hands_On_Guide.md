# ARIA Platform — Lightweight Hands-On Guide with Synthetic CNC Test Data

**Document Type:** Interleaved Story + Practical Exercise  
**Version:** v1.0 Lightweight Scenario  
**Scenario:** Manufacturing CNC spindle health monitoring  
**Dataset Resolution:** 1 row per hour  
**Purpose:** A smaller ARIA hands-on scenario that demonstrates upload, baseline anomaly detection, annotation, Label Bank promotion, seeded analysis, cross-equipment transfer, and Ask AI — without using 100k+ row datasets.

---

## How to Use This Lightweight Guide

This version follows the same teaching structure as the larger ARIA hands-on guide:

1. A short story explains what the engineer is trying to discover.
2. A hands-on block gives exact steps to perform on the ARIA platform.
3. The next story builds on what was learned in the previous exercise.

The main difference is dataset size. This package uses hourly rows instead of 1-minute rows, so the analysis remains platform-friendly.

---

## Dataset Package

| File | Rows | Period | Purpose |
|---|---:|---|---|
| `CNC01_SpindleLine_60days_hourly.csv` | 1,440 | 2024-01-01 00:00 to 2024-02-29 23:00 | Session 1 and 2 — baseline analysis, annotation, Label Bank building |
| `CNC01_SpindleLine_Month3_hourly.csv` | 744 | 2024-03-01 00:00 to 2024-03-31 23:00 | Session 3 — seeded rerun on the same equipment |
| `CNC02_SpindleLine_30days_hourly.csv` | 720 | 2024-04-01 00:00 to 2024-04-30 23:00 | Session 4 — cross-equipment seeded first run |
| `ARIA_CNC_Lite_GroundTruth_Key.csv` | 6 | Reference only | Known embedded anomaly windows and suggested annotations |
| `ARIA_CNC_Lite_Datasets.xlsx` | Workbook | Reference only | Excel workbook version of all datasets and the ground-truth key |

**Important:** Upload the three dataset CSV files into ARIA. Do not upload the GroundTruth Key as an ARIA dataset; it is for reference while performing the exercise.

---

## Signal Columns

Each dataset has one timestamp column and 12 numeric signal columns.

| Column | Unit / Meaning | Expected Normal Range |
|---|---|---|
| `SPINDLE_RPM` | rpm | ~8,900–9,100 |
| `SPINDLE_LOAD_PCT` | % | ~40–70 |
| `MOTOR_CURRENT_A` | A | ~25–31 normally, higher during drift |
| `VIB_X_MM_S` | mm/s | ~1.4–2.1 healthy baseline |
| `VIB_Y_MM_S` | mm/s | ~1.1–1.7 healthy baseline |
| `BEARING_TEMP_C` | °C | ~34–47 normally, higher during bearing/coolant issues |
| `COOLANT_FLOW_LPM` | L/min | ~27–29 normally |
| `COOLANT_PRESSURE_BAR` | bar | ~2.4–2.9 normally |
| `FEED_RATE_MM_MIN` | mm/min | ~690–870 |
| `AIR_PRESSURE_BAR` | bar | ~6.0–6.3 |
| `AMBIENT_TEMP_C` | °C | ~25–31 |
| `ACOUSTIC_DB` | dB | ~69–76 normally, higher during mechanical faults |

---

## Embedded Events

| Event | Dataset | Signals | Period | Severity |
|---|---|---|---|---|
| Spindle bearing wear — drive end | `CNC01_SpindleLine_60days_hourly.csv` | `VIB_X_MM_S`, `VIB_Y_MM_S`, `BEARING_TEMP_C`, `ACOUSTIC_DB`, `MOTOR_CURRENT_A` | 2024-01-16 to 2024-02-06, peak 2024-01-29 to 2024-02-04 | High |
| Coolant filter restriction | `CNC01_SpindleLine_60days_hourly.csv` | `COOLANT_FLOW_LPM`, `COOLANT_PRESSURE_BAR`, `BEARING_TEMP_C` | 2024-02-13 to 2024-02-16 | Medium |
| Motor current transmitter drift | `CNC01_SpindleLine_60days_hourly.csv` | `MOTOR_CURRENT_A` only | 2024-02-20 to 2024-02-25 | Medium, instrumentation |
| Early spindle imbalance | `CNC01_SpindleLine_Month3_hourly.csv` | `VIB_X_MM_S`, `VIB_Y_MM_S`, `ACOUSTIC_DB` | 2024-03-25 to 2024-03-31 | Low–Medium |
| Cross-equipment spindle imbalance | `CNC02_SpindleLine_30days_hourly.csv` | `VIB_X_MM_S`, `VIB_Y_MM_S`, `BEARING_TEMP_C`, `ACOUSTIC_DB` | 2024-04-11 to 2024-04-30 | Medium |

---

# PART 1 — First Contact: Upload and Baseline Analysis

---

## The Story

It is Monday morning. Mei, a maintenance engineer responsible for a CNC machining cell, is asked to evaluate whether ARIA can detect developing spindle issues before the existing alarm thresholds trigger.

The CNC machine, `CNC-01`, has been producing precision components continuously. Operators have occasionally reported a faint high-pitched sound, but the standard machine alarms show nothing unusual. Mei exports 60 days of historian data at hourly resolution.

The dataset is intentionally small: only 1,440 rows. It is enough to demonstrate anomaly detection, but light enough that the platform should not hang.

Mei has one piece of ground truth from maintenance: the drive-end spindle bearing was inspected and replaced in early February. She wants to know whether ARIA can see the developing bearing issue earlier.

---

## Hands-On Activity 1 — Upload the CNC-01 Baseline Dataset

**Estimated time:** 3–5 minutes

### Step 1.1 — Navigate to Datasets

1. Log in to ARIA.
2. Go to **Anomaly Detection → Datasets**.
3. Click **Upload Dataset**.

### Step 1.2 — Upload the file

Upload:

`CNC01_SpindleLine_60days_hourly.csv`

Verify the preview shows:

| Item | Expected Value |
|---|---|
| Rows detected | 1,440 |
| Columns detected | 13 |
| Timestamp column | `Timestamp` |
| First timestamp | `2024-01-01 00:00:00` |
| Last timestamp | `2024-02-29 23:00:00` |

### Step 1.3 — Configure dataset metadata

| Field | Value |
|---|---|
| Dataset Name | `CNC-01 Spindle Line — 60 Days Hourly` |
| Description | `Synthetic CNC spindle historian export. Hourly resolution. Includes spindle bearing wear, coolant restriction, and current transmitter drift.` |
| Equipment Type | `CNC Machining Center` |
| Equipment ID | `CNC-01` |

### Step 1.4 — Confirm column types

Make sure `Timestamp` is the timestamp column and all other columns are numeric.

Click **Save Dataset**.

---

## The Story Continued

The dataset uploads quickly. Mei notices that `VIB_X_MM_S` and `VIB_Y_MM_S` are the most important signals for spindle health, but she also keeps `BEARING_TEMP_C`, `ACOUSTIC_DB`, and `MOTOR_CURRENT_A` because mechanical faults often affect multiple signals together.

She is now ready to run the first analysis.

---

## Hands-On Activity 2 — Create a Lightweight Baseline Analysis

**Estimated time:** 5–10 minutes depending on selected algorithms

### Step 2.1 — Create a new analysis

Go to **Anomaly Detection → New Analysis**.

| Field | Value |
|---|---|
| Analysis Name | `CNC-01 Baseline — 60 Days Hourly` |
| Dataset | `CNC-01 Spindle Line — 60 Days Hourly` |
| Timestamp Column | `Timestamp` |
| Signal Columns | Select all 12 numeric signals |

### Step 2.2 — Select algorithms

For the lightweight first run, select:

| Algorithm | Why |
|---|---|
| Z-Score | Fast statistical baseline |
| IQR | Robust outlier detection |
| EWMA | Good for gradual drift and progressive degradation |
| Isolation Forest | Good multivariate anomaly detector |

Optional, if your platform handles it comfortably:

| Optional Algorithm | Why |
|---|---|
| LOF | Useful for local density anomalies |
| LSTM Autoencoder | Useful for temporal patterns, but slower |

**Recommended for training/demo:** start with 4 algorithms first. After confirming the platform performs well, repeat with 5–6 algorithms.

### Step 2.3 — Advanced options

Leave the following disabled for the first run:

| Option | Setting |
|---|---|
| Equipment Group Seeding | Disabled |
| Experience-Guided Detection / HitL | Disabled |
| Per-Signal Anomaly Rate | Disabled |

Click **Run Analysis**.

---

# PART 2 — Reading the First Results

---

## The Story

The analysis completes quickly because the dataset has only 1,440 rows. Mei opens the Results page.

She expects random noise, but the ranking table shows something meaningful: `VIB_X_MM_S`, `VIB_Y_MM_S`, `ACOUSTIC_DB`, and `BEARING_TEMP_C` are near the top. The anomaly windows cluster around late January and early February.

This is exactly what she hoped ARIA would catch: the bearing wear signature before replacement.

---

## Hands-On Activity 3 — Explore the Baseline Results

**Estimated time:** 10–15 minutes

### Step 3.1 — Review the ranking / consensus table

Look for the top-ranked signals. You should typically see stronger anomaly behavior in:

| Signal | Expected Interpretation |
|---|---|
| `VIB_X_MM_S` | Strongest bearing wear signature |
| `VIB_Y_MM_S` | Correlated vibration axis |
| `ACOUSTIC_DB` | Mechanical noise increases with vibration |
| `BEARING_TEMP_C` | Thermal response during wear |
| `MOTOR_CURRENT_A` | Mixed signal: real bearing load increase plus later transmitter drift |

### Step 3.2 — Inspect `VIB_X_MM_S`

Open the chart for `VIB_X_MM_S`.

Expected pattern:

| Period | What to See |
|---|---|
| 2024-01-01 to 2024-01-12 | Clean baseline, mostly around 1.4–2.1 mm/s |
| 2024-01-16 onward | Gradual vibration increase begins |
| 2024-01-29 to 2024-02-04 | Peak anomaly cluster with impulsive spikes |
| After 2024-02-06 | Return toward baseline after simulated bearing replacement |

### Step 3.3 — Inspect `COOLANT_FLOW_LPM` and `COOLANT_PRESSURE_BAR`

Look at 2024-02-13 to 2024-02-16.

Expected pattern:

| Signal | Expected Behavior |
|---|---|
| `COOLANT_FLOW_LPM` | Drops sharply |
| `COOLANT_PRESSURE_BAR` | Rises at the same time |
| `BEARING_TEMP_C` | Mild increase |

Interpretation: likely coolant filter restriction or blocked strainer.

### Step 3.4 — Inspect `MOTOR_CURRENT_A`

Look at 2024-02-20 to 2024-02-25.

Expected pattern:

- `MOTOR_CURRENT_A` rises and then returns.
- `SPINDLE_LOAD_PCT`, `SPINDLE_RPM`, and vibration do not show a matching operational change.

Interpretation: likely current transmitter drift, not a true process or mechanical anomaly.

---

# PART 3 — Annotation and Label Bank

---

## The Story

Mei now has useful findings, but they only matter if she records them. ARIA becomes more valuable when engineering judgement is converted into reusable labels.

She decides to annotate three kinds of knowledge:

1. Confirmed mechanical anomaly: bearing wear.
2. Confirmed process/utility anomaly: coolant restriction.
3. Dismissed normal / instrumentation artifact: current transmitter drift.

She also labels a clean baseline window as confirmed normal so future analyses know what healthy spindle vibration looks like.

---

## Hands-On Activity 4 — Annotate the Bearing Wear Event

**Estimated time:** 10 minutes

### Step 4.1 — Filter the anomaly list

Set filters:

| Filter | Value |
|---|---|
| Signal | `VIB_X_MM_S` |
| Date range | `2024-01-29` to `2024-02-04` |
| Severity | High, or top anomaly rows |

Select the visible high-confidence anomaly rows.

### Step 4.2 — Batch annotate `VIB_X_MM_S`

Use:

| Field | Value |
|---|---|
| Label Type | `Confirmed Anomaly` |
| Confidence | `0.90` |
| Note | `Drive-end spindle bearing wear. Progressive vibration increase with impulsive spike pattern. Correlated with BEARING_TEMP_C and ACOUSTIC_DB. Bearing replacement simulated after 2024-02-06.` |
| Root Cause Category | `Mechanical` |
| Root Cause Note | `Drive-end spindle bearing wear. Use as reusable spindle mechanical-fault label.` |

### Step 4.3 — Repeat for `VIB_Y_MM_S`

Set signal to `VIB_Y_MM_S`, keep the same date range.

Use:

| Field | Value |
|---|---|
| Label Type | `Confirmed Anomaly` |
| Confidence | `0.85` |
| Note | `Correlated Y-axis vibration response from the same drive-end spindle bearing wear event. Lower amplitude than VIB_X_MM_S but same timing.` |
| Root Cause Category | `Mechanical` |
| Root Cause Note | `Same bearing wear event as VIB_X_MM_S.` |

---

## Hands-On Activity 5 — Annotate Other Events

### Step 5.1 — Coolant restriction

Filter:

| Filter | Value |
|---|---|
| Signal | `COOLANT_FLOW_LPM` |
| Date range | `2024-02-13` to `2024-02-16` |

Annotate:

| Field | Value |
|---|---|
| Label Type | `Confirmed Anomaly` |
| Confidence | `0.85` |
| Note | `Coolant flow restriction. Flow drops while coolant pressure rises. Consistent with partially blocked filter or strainer.` |
| Root Cause Category | `Process / Utility` |
| Root Cause Note | `Coolant filter restriction or blocked strainer.` |

Optional: repeat for `COOLANT_PRESSURE_BAR`.

### Step 5.2 — Motor current transmitter drift

Filter:

| Filter | Value |
|---|---|
| Signal | `MOTOR_CURRENT_A` |
| Date range | `2024-02-20` to `2024-02-25` |

Annotate:

| Field | Value |
|---|---|
| Label Type | `Dismissed Normal` |
| Confidence | `0.95` |
| Note | `Motor current transmitter drift. Current changes without matching spindle load, RPM, vibration, or process changes. Treat as instrumentation artifact, not a true machine fault.` |
| Root Cause Category | `Instrumentation` |
| Root Cause Note | `Current transmitter thermal drift or calibration issue.` |

### Step 5.3 — Confirmed normal baseline

Filter:

| Filter | Value |
|---|---|
| Signal | `VIB_X_MM_S` |
| Date range | `2024-01-01` to `2024-01-12` |

Select 15–25 stable rows and annotate:

| Field | Value |
|---|---|
| Label Type | `Confirmed Normal` |
| Confidence | `0.95` |
| Note | `Clean baseline window before bearing wear onset. VIB_X_MM_S stable in healthy operating range.` |

Repeat for `VIB_Y_MM_S`.

---

## Hands-On Activity 6 — Create and Promote to Label Bank

### Step 6.1 — Create an equipment group / Label Bank session

Navigate to **Anomaly Detection → Label Bank**.

Create:

| Field | Value |
|---|---|
| Session Name | `CNC Spindle Family — Horizontal Machining Centers` |
| Description | `Reusable labels for CNC spindle vibration, coolant, acoustic, and mechanical anomaly patterns. Built from synthetic CNC-01 hands-on data.` |
| Equipment Type Tag | `CNC Machining Center — Spindle` |

### Step 6.2 — Promote only reusable labels

Promote the following:

| Label | Promote? | Reason |
|---|---|---|
| `VIB_X_MM_S` bearing wear Confirmed Anomaly | Yes | Reusable mechanical fault pattern |
| `VIB_Y_MM_S` bearing wear Confirmed Anomaly | Yes | Reusable correlated axis pattern |
| `VIB_X_MM_S` Confirmed Normal baseline | Yes | Reusable healthy baseline |
| `VIB_Y_MM_S` Confirmed Normal baseline | Yes | Reusable healthy baseline |
| Coolant restriction labels | Optional | Promote only if you want utility/process faults in the same session |
| `MOTOR_CURRENT_A` transmitter drift | No | Instrumentation artifact specific to this sensor |

---

# PART 4 — Seeded Same-Equipment Rerun

---

## The Story

It is now one month later. CNC-01 has continued running after the simulated bearing replacement. Mei receives a new March dataset.

The machine looks mostly healthy, but operators mention a slight vibration after a toolholder change. Mei wants to see whether the Label Bank can make ARIA more sensitive to new spindle-related issues.

---

## Hands-On Activity 7 — Upload CNC-01 Month 3

Upload:

`CNC01_SpindleLine_Month3_hourly.csv`

Configure:

| Field | Value |
|---|---|
| Dataset Name | `CNC-01 Spindle Line — Month 3 Hourly` |
| Description | `Post-maintenance CNC-01 hourly dataset. Mostly clean operation with early spindle imbalance in the final week.` |
| Equipment Type | `CNC Machining Center` |
| Equipment ID | `CNC-01` |

Verify:

| Item | Expected Value |
|---|---|
| Rows | 744 |
| First timestamp | `2024-03-01 00:00:00` |
| Last timestamp | `2024-03-31 23:00:00` |

---

## Hands-On Activity 8 — Run Seeded Analysis on CNC-01 Month 3

Create a new analysis:

| Field | Value |
|---|---|
| Analysis Name | `CNC-01 Month 3 — Seeded Lightweight` |
| Dataset | `CNC-01 Spindle Line — Month 3 Hourly` |
| Signal Columns | All 12 numeric signals |

Algorithm selection:

- Z-Score
- IQR
- EWMA
- Isolation Forest

Optional:

- LOF
- LSTM Autoencoder

Enable:

| Option | Value |
|---|---|
| Equipment Group Seeding | On |
| Label Bank Session | `CNC Spindle Family — Horizontal Machining Centers` |
| Seeding Mode | Tier 1 Only |
| Experience-Guided Detection / HitL | On, if available |

Run the analysis.

Expected result:

| Signal | Expected Pattern |
|---|---|
| `VIB_X_MM_S` | Smooth increase in final week |
| `VIB_Y_MM_S` | Correlated but lower-amplitude increase |
| `ACOUSTIC_DB` | Mild increase |
| `BEARING_TEMP_C` | Slight increase |

Interpretation: possible spindle imbalance or toolholder runout, lower urgency than bearing wear because there are no impulsive spikes.

---

# PART 5 — Cross-Equipment Seeded Analysis

---

## The Story

Mei now tries the same approach on a sister machine: `CNC-02`. This machine is older, so its vibration baseline is slightly higher. It has no prior labels of its own.

This is where the Label Bank becomes useful. CNC-02 can benefit from CNC-01 knowledge before Mei has annotated anything on CNC-02.

---

## Hands-On Activity 9 — Upload CNC-02 First Run

Upload:

`CNC02_SpindleLine_30days_hourly.csv`

Configure:

| Field | Value |
|---|---|
| Dataset Name | `CNC-02 Spindle Line — 30 Days Hourly` |
| Description | `Synthetic sister-machine CNC dataset. Older machine with higher vibration baseline and progressive spindle imbalance from mid-month.` |
| Equipment Type | `CNC Machining Center` |
| Equipment ID | `CNC-02` |

Verify:

| Item | Expected Value |
|---|---|
| Rows | 720 |
| First timestamp | `2024-04-01 00:00:00` |
| Last timestamp | `2024-04-30 23:00:00` |

---

## Hands-On Activity 10 — Run Cross-Equipment Seeded Analysis

Create a new analysis:

| Field | Value |
|---|---|
| Analysis Name | `CNC-02 First Run — Cross-Equipment Seeded` |
| Dataset | `CNC-02 Spindle Line — 30 Days Hourly` |
| Signal Columns | All 12 numeric signals |

Enable:

| Option | Value |
|---|---|
| Equipment Group Seeding | On |
| Label Bank Session | `CNC Spindle Family — Horizontal Machining Centers` |
| Seeding Mode | Tier 1 Only |
| Experience-Guided Detection / HitL | On, if available |

Expected result:

| Signal | Expected Pattern |
|---|---|
| `VIB_X_MM_S` | Progressive increase from around 2024-04-11 |
| `VIB_Y_MM_S` | Correlated increase |
| `BEARING_TEMP_C` | Mild thermal response |
| `ACOUSTIC_DB` | Correlated acoustic increase |

Key teaching point:

- CNC-01 bearing wear had impulsive spikes.
- CNC-02 imbalance has a smoother progressive vibration increase.
- Both are mechanical, but their signatures are different.

---

# PART 6 — Ask AI

---

## The Story

Mei can see that CNC-02's vibration pattern is not identical to CNC-01's bearing wear. It rises smoothly, without sharp impulses. She wants a second opinion.

She opens Ask AI from the CNC-02 Results page.

---

## Hands-On Activity 11 — Ask AI Diagnostic Question

Ask:

> The CNC-02 VIB_X_MM_S and VIB_Y_MM_S anomaly cluster shows a smooth progressive increase starting around 2024-04-11. It does not show the impulsive spikes that were present in the CNC-01 bearing wear event. ACOUSTIC_DB and BEARING_TEMP_C also increase mildly. What failure mode does this pattern suggest, and how urgent is it compared with the CNC-01 bearing wear event?

Expected AI response should mention:

- The pattern is more consistent with spindle imbalance, toolholder runout, rotor imbalance, or alignment issue.
- It is different from bearing wear because it lacks impulsive spikes.
- It should be monitored and investigated, but the urgency is usually lower than a high-amplitude impulsive bearing fault.
- Recommended next checks:
  - vibration spectrum,
  - toolholder inspection,
  - spindle runout check,
  - recent tool or fixture change review.

---

# PART 7 — Summary of What This Lightweight Scenario Demonstrates

| ARIA Capability | Demonstrated By |
|---|---|
| Dataset upload and parsing | Activity 1 |
| Fast anomaly analysis on small datasets | Activity 2 |
| Multi-signal anomaly interpretation | Activity 3 |
| Annotation and root cause capture | Activities 4–5 |
| Label Bank creation | Activity 6 |
| Tier 1 seeded analysis | Activities 8 and 10 |
| Cross-equipment knowledge transfer | Activity 10 |
| Ask AI contextual diagnosis | Activity 11 |

---

## Recommended Demo Flow for Customers

For a live demo, use this shorter path:

1. Upload `CNC01_SpindleLine_60days_hourly.csv`.
2. Run 4 algorithms: Z-Score, IQR, EWMA, Isolation Forest.
3. Show the `VIB_X_MM_S` bearing wear cluster.
4. Annotate the peak window.
5. Promote to Label Bank.
6. Upload `CNC02_SpindleLine_30days_hourly.csv`.
7. Run seeded analysis.
8. Show that CNC-02 benefits from CNC-01 knowledge.

This keeps the demonstration focused, fast, and less likely to overload the platform.
