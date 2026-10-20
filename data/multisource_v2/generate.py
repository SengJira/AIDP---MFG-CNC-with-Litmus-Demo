"""Generate a synthetic multi-source Smart Manufacturing dataset aligned with CNC spindle telemetry.

Sources produced (all synthetic, fictional companies):
  historian/  CNC telemetry (hourly)          -> Iceberg on ObjectScale
  mes/        production orders, lots, stops  -> PostgreSQL
  erp/        customers, materials, SOs, POs  -> MySQL / SQL Server
  qa/         CMM inspections, NCRs, complaints -> CSV files on PowerScale/S3
  cmms/       assets + maintenance work orders  -> JSON on ObjectScale
  logbook/    free-text shift notes             -> Data Search Engine

Usage: python3 generate.py <path to CNC01_SpindleLine_60days_hourly.csv> <out dir>
Deterministic (seed 42).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
for d in ["historian", "mes", "erp", "qa", "cmms", "logbook"]:
    (OUT / d).mkdir(parents=True, exist_ok=True)

COLS = ["SPINDLE_RPM", "SPINDLE_LOAD_PCT", "MOTOR_CURRENT_A", "VIB_X_MM_S", "VIB_Y_MM_S",
        "BEARING_TEMP_C", "COOLANT_FLOW_LPM", "COOLANT_PRESSURE_BAR", "FEED_RATE_MM_MIN",
        "AIR_PRESSURE_BAR", "AMBIENT_TEMP_C", "ACOUSTIC_DB"]
ROUND = {"SPINDLE_RPM": 1, "SPINDLE_LOAD_PCT": 2, "MOTOR_CURRENT_A": 3, "VIB_X_MM_S": 3,
         "VIB_Y_MM_S": 3, "BEARING_TEMP_C": 2, "COOLANT_FLOW_LPM": 3, "COOLANT_PRESSURE_BAR": 3,
         "FEED_RATE_MM_MIN": 1, "AIR_PRESSURE_BAR": 3, "AMBIENT_TEMP_C": 2, "ACOUSTIC_DB": 2}

# Bearing replacement stop on CNC-01 (C shift of 5 Feb): telemetry hours 22:00..05:00
REPLACE_START = pd.Timestamp("2024-02-05 22:00")
REPLACE_END = pd.Timestamp("2024-02-06 06:00")

# ---------------------------------------------------------------- telemetry
cnc01 = pd.read_csv(SRC, parse_dates=["Timestamp"]).set_index("Timestamp")


def stopped_rows(idx, ambient):
    n = len(idx)
    hrs = np.arange(n)
    return pd.DataFrame({
        "SPINDLE_RPM": 0.0, "SPINDLE_LOAD_PCT": 0.0,
        "MOTOR_CURRENT_A": rng.normal(3.5, 0.15, n),
        "VIB_X_MM_S": rng.normal(0.15, 0.02, n), "VIB_Y_MM_S": rng.normal(0.12, 0.02, n),
        "BEARING_TEMP_C": ambient + (40 - ambient) * np.exp(-hrs / 2.5) + rng.normal(0, 0.2, n),
        "COOLANT_FLOW_LPM": 0.0, "COOLANT_PRESSURE_BAR": 0.0, "FEED_RATE_MM_MIN": 0.0,
        "AIR_PRESSURE_BAR": rng.normal(6.15, 0.02, n), "AMBIENT_TEMP_C": ambient,
        "ACOUSTIC_DB": rng.normal(58, 0.8, n)}, index=idx)


aligned = cnc01.copy()
stop_idx = aligned.loc[REPLACE_START:REPLACE_END - pd.Timedelta(hours=1)].index
aligned.loc[stop_idx, COLS] = stopped_rows(stop_idx, aligned.loc[stop_idx, "AMBIENT_TEMP_C"].values)[COLS].values

# clean template days from CNC-01 (no events)
clean_days = list(pd.date_range("2024-01-01", "2024-01-14")) + list(pd.date_range("2024-02-08", "2024-02-12")) \
    + list(pd.date_range("2024-02-27", "2024-02-29"))


def synth_month(start, days, vib_scale=1.0, temp_add=0.0, cur_add=0.0):
    parts = []
    for i in range(days):
        d = clean_days[rng.integers(len(clean_days))]
        block = cnc01.loc[d: d + pd.Timedelta(hours=23)].copy()
        block.index = pd.date_range(start + pd.Timedelta(days=i), periods=24, freq="h")
        parts.append(block)
    df = pd.concat(parts)
    jitter = {c: df[c].std() * 0.05 for c in COLS}
    for c in COLS:
        df[c] = df[c] + rng.normal(0, jitter[c], len(df))
    df["VIB_X_MM_S"] *= vib_scale
    df["VIB_Y_MM_S"] *= vib_scale
    df["BEARING_TEMP_C"] += temp_add
    df["MOTOR_CURRENT_A"] += cur_add
    return df


def ramp(df, start, deltas, power=1.3):
    t = df.index
    frac = np.clip((t - pd.Timestamp(start)) / (t[-1] - pd.Timestamp(start)), 0, 1) ** power
    for c, a in deltas.items():
        df[c] = df[c] + a * frac + (rng.normal(0, abs(a) * 0.04, len(df)) * (frac > 0))
    return df


m3 = synth_month(pd.Timestamp("2024-03-01"), 31)
m3 = ramp(m3, "2024-03-25", {"VIB_X_MM_S": 0.85, "VIB_Y_MM_S": 0.55, "ACOUSTIC_DB": 2.5, "BEARING_TEMP_C": 1.5})
c2 = synth_month(pd.Timestamp("2024-04-01"), 30, vib_scale=1.18, temp_add=1.5, cur_add=0.8)
c2 = ramp(c2, "2024-04-11", {"VIB_X_MM_S": 1.7, "VIB_Y_MM_S": 1.15, "ACOUSTIC_DB": 5.5, "BEARING_TEMP_C": 4.0})
# Deterministic (no rng) additions used by the SQM story:
# CNC-02: step when toolholder TH-0007 (balance G6.3) goes in after the 10 Apr setup
_step = c2.index >= pd.Timestamp("2024-04-10 16:00")
c2.loc[_step, "VIB_X_MM_S"] += 0.30
c2.loc[_step, "VIB_Y_MM_S"] += 0.20
c2.loc[_step, "ACOUSTIC_DB"] += 1.0
# CNC-01 March: small current rise while Supplier B castings run (from 25 Mar), like January
_f = np.clip((m3.index - pd.Timestamp("2024-03-25")) / (m3.index[-1] - pd.Timestamp("2024-03-25")), 0, 1) ** 1.3
m3["MOTOR_CURRENT_A"] = m3["MOTOR_CURRENT_A"] + 0.6 * _f


def write_tel(df, name):
    out = df[COLS].copy()
    for c in COLS:
        out[c] = out[c].round(ROUND[c])
    out.index.name = "Timestamp"
    out.to_csv(OUT / "historian" / name, date_format="%Y-%m-%d %H:%M:%S")


write_tel(aligned, "CNC01_SpindleLine_60days_hourly_mes_aligned.csv")
write_tel(m3, "CNC01_SpindleLine_Month3_hourly.csv")
write_tel(c2, "CNC02_SpindleLine_30days_hourly.csv")
telemetry = {"CNC-01": pd.concat([aligned, m3]), "CNC-02": c2}

# ---------------------------------------------------------------- master data
customers = pd.DataFrame([
    ["C100245", "Kestrel Automotive Components (fictional)", "Automotive", "Tier 1", "NET45"],
    ["C100311", "Aurora Hydraulics (fictional)", "Industrial hydraulics", "Key account", "NET30"],
    ["C100402", "Meridian Fluid Power (fictional)", "Fluid power", "Standard", "NET30"],
], columns=["customer_id", "customer_name", "industry", "segment", "payment_terms"])

materials = pd.DataFrame([
    # id, desc, type, unit_cost, unit_price, cycle_min, bore_nominal, lead_time_days
    ["VB-2210", "Valve body, 25 mm main bore", "FINISHED_GOOD", 18.40, 32.00, 9.5, 25.000, None],
    ["PH-3140", "Pump housing, 40 mm bore", "FINISHED_GOOD", 27.50, 46.00, 12.0, 40.000, None],
    ["MB-5120", "Manifold block, 32 mm bore", "FINISHED_GOOD", 41.00, 72.00, 14.0, 32.000, None],
    ["SP-BRG-7014", "Spindle bearing set, drive end", "SPARE_PART", 2850.00, None, None, None, 7],
    ["SP-FLT-220", "Coolant filter cartridge", "SPARE_PART", 85.00, None, None, None, 3],
    ["SP-FAN-080", "Electrical cabinet fan 80 mm", "SPARE_PART", 42.00, None, None, None, 2],
], columns=["material_id", "description", "material_type", "unit_cost_usd", "unit_price_usd",
            "ideal_cycle_min", "bore_nominal_mm", "std_lead_time_days"])
MAT = materials.set_index("material_id")

MACHINE_RATE = 85.0  # USD per machine hour
COMPLAINT_HANDLING = 25.0  # USD per escaped part (sort, freight, admin)

so_plan = {
    "CNC-01": [("SO-45001", "C100245", "VB-2210", 1600), ("SO-45004", "C100311", "PH-3140", 1100),
               ("SO-45012", "C100245", "VB-2210", 2400), ("SO-45019", "C100311", "PH-3140", 1300),
               ("SO-45025", "C100245", "VB-2210", 1800), ("SO-45031", "C100311", "PH-3140", 1200),
               ("SO-45038", "C100245", "VB-2210", 2000), ("SO-45044", "C100311", "PH-3140", 1400)],
    "CNC-02": [("SO-45052", "C100245", "VB-2210", 1500), ("SO-45060", "C100402", "MB-5120", 1600)],
}
WINDOWS = {"CNC-01": (pd.Timestamp("2024-01-01 06:00"), pd.Timestamp("2024-04-01 06:00")),
           "CNC-02": (pd.Timestamp("2024-04-01 06:00"), pd.Timestamp("2024-05-01 06:00"))}
CYCLE_ADJ = {"CNC-01": 1.0, "CNC-02": 1.03}  # older machine is slightly slower
SHIFTS = [("A", 6), ("B", 14), ("C", 22)]
PLANNED_MIN = 450  # 480 min shift minus 30 min break
CHANGEOVER_MIN = 120
NOMINAL_PERF = 0.92


def shift_starts(m):
    s, e = WINDOWS[m]
    t = s
    while t < e:
        yield t
        t += pd.Timedelta(hours=8)


def shift_code(ts):
    return {6: "A", 14: "B", 22: "C"}[ts.hour]


# ---- planning pass (nominal capacity, no events) -> due dates
due = {}
for m, sos in so_plan.items():
    i, remaining, first = 0, None, True
    for st in shift_starts(m):
        if i >= len(sos):
            break
        so, cust, mat, qty = sos[i]
        avail = PLANNED_MIN
        if remaining is None:
            remaining = qty
            if not first:
                avail -= CHANGEOVER_MIN
            first = False
        cap = math.floor(avail * NOMINAL_PERF / (MAT.loc[mat, "ideal_cycle_min"] * CYCLE_ADJ[m]) * 0.995)
        remaining -= cap
        if remaining <= 0:
            due[so] = (st + pd.Timedelta(hours=8)).normalize() + pd.Timedelta(days=2)
            i, remaining = i + 1, None
    for so, *_ in sos[i:]:
        due.setdefault(so, pd.Timestamp("2024-05-10"))
due["SO-45060"] = pd.Timestamp("2024-05-08")

# ---- event windows that drive behaviour
def in_window(ts, a, b):
    return pd.Timestamp(a) <= ts < pd.Timestamp(b)


MINOR_REASONS = [("TOOL_CHANGE", "Insert changed after wear limit"), ("MATERIAL_WAIT", "Waiting for blanks from saw"),
                 ("CHIP_CLEARING", "Chips cleared from fixture"), ("PROGRAM_EDIT", "Offset adjusted by setter"),
                 ("GAUGE_CHECK", "Air gauge re-mastered")]

prod_orders, lots, stops, inspections, ncrs = [], [], [], [], []
so_actual = {}
escapes_by_so = {}
stop_id = 1
insp_id = 1
ncr_id = 1
po_counter = {"CNC-01": 70110, "CNC-02": 70410}

for m, sos in so_plan.items():
    tel = telemetry[m]
    i, po, cum_good, first = 0, None, 0, True
    po_rec = None
    for st in shift_starts(m):
        en = st + pd.Timedelta(hours=8)
        sc = shift_code(st)
        lot_id = f"L{m[-2:]}-{st:%y%m%d}-{sc}"
        w = tel.loc[st: en - pd.Timedelta(hours=1)]
        running = w[w.SPINDLE_RPM > 1000]
        if i >= len(sos):
            break
        so, cust, mat, qty = sos[i]
        if po is None:
            po_counter[m] += 1
            po = f"PO-{po_counter[m]}"
            po_rec = {"prod_order_id": po, "so_id": so, "material_id": mat, "machine_id": m,
                      "qty_target": qty, "actual_start": st, "qty_good": 0, "qty_scrap": 0}
            prod_orders.append(po_rec)
            cum_good = 0
        avail = PLANNED_MIN
        shift_stops = []
        if not first and po_rec["actual_start"] == st:
            shift_stops.append(("Planned", "CHANGEOVER", f"Changeover to {mat}", CHANGEOVER_MIN))
            avail -= CHANGEOVER_MIN
        first = False
        # planned events
        if m == "CNC-02" and st == pd.Timestamp("2024-04-10 14:00"):
            shift_stops.append(("Planned", "SETUP", "Spindle toolholder HSK-A63 #7 replaced; runout check skipped (gauge out for calibration)", 90))
            avail -= 90
        if sc == "A" and st.weekday() == 0 and st.day <= 7:
            shift_stops.append(("Planned", "PM", "Monthly spindle lubrication PM", 60))
            avail -= 60
        # unplanned
        if in_window(st, REPLACE_START, REPLACE_END):
            shift_stops.append(("Unplanned", "SPINDLE_BEARING_REPLACEMENT", "Drive-end spindle bearing replaced (WO-24-0117)", 480))
            avail = 0
        else:
            for _ in range(rng.poisson(1.2)):
                rc, txt = MINOR_REASONS[rng.integers(len(MINOR_REASONS))]
                shift_stops.append(("Unplanned", rc, txt, int(rng.integers(5, 21))))
            if m == "CNC-01" and in_window(st, "2024-02-13 06:00", "2024-02-15 22:00"):
                shift_stops.append(("Unplanned", "CHIP_PACKING", "Chips packing in bore, weak coolant at nozzle", int(rng.integers(25, 46))))
            if m == "CNC-01" and in_window(st, "2024-01-29 06:00", "2024-02-05 22:00") and rng.random() < 0.6:
                shift_stops.append(("Unplanned", "QUALITY_HOLD", "Lot on hold waiting for CMM result", int(rng.integers(15, 35))))
        unplanned = sum(s[3] for s in shift_stops if s[0] == "Unplanned" and s[2] != "")
        unplanned = min(unplanned, 450)
        run_min = max(avail - sum(s[3] for s in shift_stops if s[0] == "Unplanned"), 0) if avail > 0 else 0
        perf = float(np.clip(rng.normal(NOMINAL_PERF, 0.02), 0.85, 0.97))
        cyc = MAT.loc[mat, "ideal_cycle_min"] * CYCLE_ADJ[m]
        n_parts = math.floor(run_min * perf / cyc) if run_min > 0 else 0

        # quality model driven by telemetry of the shift
        if len(running):
            vib = running.VIB_X_MM_S.mean()
            flow = running.COOLANT_FLOW_LPM.mean()
            btemp = running.BEARING_TEMP_C.mean()
        else:
            vib, flow, btemp = 1.63, 28.0, 39.2
        mu_r = 1.9 + 1.3 * max(vib - 1.63, 0)
        mu_ra = 0.55 + 0.12 * max(vib - 1.63, 0) + 0.06 * max(28 - flow, 0)
        mu_d = 3.0 * max(28 - flow, 0) + 0.4 * (btemp - 39.2)
        need = qty - cum_good
        parts = []
        for k in range(n_parts):
            d = rng.normal(mu_d, 2.2)
            r = max(rng.normal(mu_r, 0.5), 0.4)
            ra = max(rng.normal(mu_ra, 0.08), 0.2)
            bore_bad = abs(d) > 10
            parts.append((d, r, ra, bore_bad))
            good_so_far = sum(1 for p in parts if not p[3])
            if good_so_far >= need + 3:  # small overrun allowance for sorting losses
                break
        produced = len(parts)
        scrap_bore = sum(p[3] for p in parts)
        survivors = [p for p in parts if not p[3]]
        nom = MAT.loc[mat, "bore_nominal_mm"]
        sample_idx = np.linspace(0, len(survivors) - 1, 5).round().astype(int) if len(survivors) >= 5 else []
        sample_fail = False
        insp_ts = en + pd.Timedelta(minutes=40)
        for sn, j in enumerate(sample_idx, 1):
            d, r, ra, _ = survivors[j]
            for ch, nomv, lsl, usl, val, unit in [
                ("BORE_DIA", nom, nom - 0.010, nom + 0.010, round(nom + d / 1000, 4), "mm"),
                ("ROUNDNESS", 0.0, None, 5.0, round(r, 2), "um"),
                ("SURFACE_RA", 0.0, None, 1.2, round(ra, 3), "um")]:
                bad = (usl is not None and val > usl) or (lsl is not None and val < lsl)
                sample_fail |= bad and ch != "BORE_DIA"
                inspections.append({"inspection_id": f"QI-{insp_id:06d}", "lot_id": lot_id, "machine_id": m,
                                    "material_id": mat, "sample_no": sn, "inspect_ts": insp_ts,
                                    "characteristic": ch, "nominal": nomv, "lsl": lsl, "usl": usl,
                                    "measured": val, "unit": unit, "result": "FAIL" if bad else "PASS",
                                    "gauge": "CMM-02"})
                insp_id += 1
        round_bad = [p for p in survivors if p[1] > 5.0 or p[2] > 1.2]
        if sample_fail:
            scrap_r = sum(1 for p in survivors if p[1] > 5.0)
            scrap_ra = sum(1 for p in survivors if p[1] <= 5.0 and p[2] > 1.2)
            escaped = 0
        else:
            scrap_r = scrap_ra = 0
            escaped = len(round_bad)
        scrap = scrap_bore + scrap_r + scrap_ra
        good = produced - scrap
        cum_good += good
        po_rec["qty_good"] += good
        po_rec["qty_scrap"] += scrap
        escapes_by_so[so] = escapes_by_so.get(so, 0) + escaped
        if sample_fail or (produced and scrap_bore / produced > 0.05):
            ch = "ROUNDNESS" if sample_fail else "BORE_DIA"
            ncrs.append({"ncr_id": f"NCR-24-{ncr_id:04d}", "lot_id": lot_id, "machine_id": m, "material_id": mat,
                         "opened_ts": insp_ts + pd.Timedelta(minutes=20), "characteristic": ch,
                         "defect_code": {"ROUNDNESS": "D-RND-OOT", "BORE_DIA": "D-DIA-OOT"}[ch],
                         "qty_sorted": len(survivors) if sample_fail else produced,
                         "qty_scrapped": (scrap_r + scrap_ra) if sample_fail else scrap_bore,
                         "disposition": "SCRAP",
                         "scrap_cost_usd": round(((scrap_r + scrap_ra) if sample_fail else scrap_bore) * MAT.loc[mat, "unit_cost_usd"], 2)})
            ncr_id += 1
        # downtime events with timestamps inside the shift
        cursor = st + pd.Timedelta(minutes=10)
        for cat, rc, txt, dur in shift_stops:
            if rc == "SPINDLE_BEARING_REPLACEMENT":
                s0 = st
            elif rc in ("CHANGEOVER", "PM", "SETUP"):
                s0 = st
            else:
                s0 = st + pd.Timedelta(minutes=int(rng.integers(30, 420)))
            stops.append({"stop_id": f"DT-{stop_id:05d}", "machine_id": m, "lot_id": lot_id, "start_ts": s0,
                          "end_ts": s0 + pd.Timedelta(minutes=int(dur)), "duration_min": int(dur), "category": cat,
                          "reason_code": rc, "reason_text": txt})
            stop_id += 1
        unpl = sum(s[3] for s in shift_stops if s[0] == "Unplanned")
        plan_dt = sum(s[3] for s in shift_stops if s[0] == "Planned")
        run_actual = max(PLANNED_MIN - plan_dt - unpl, 0)
        availability = run_actual / max(PLANNED_MIN - plan_dt, 1)
        performance = (produced * cyc / run_actual) if run_actual else 0
        quality = good / produced if produced else 0
        lots.append({"lot_id": lot_id, "prod_order_id": po, "machine_id": m, "material_id": mat,
                     "shift_date": st.date(), "shift": sc, "start_ts": st, "end_ts": en,
                     "planned_production_min": PLANNED_MIN - plan_dt, "run_min": run_actual,
                     "unplanned_downtime_min": unpl, "qty_produced": produced, "qty_good": good,
                     "qty_scrap": scrap, "scrap_bore_dia": scrap_bore, "scrap_roundness": scrap_r,
                     "scrap_surface_ra": scrap_ra, "ideal_cycle_min": round(cyc, 2),
                     "availability": round(availability, 3), "performance": round(min(performance, 1), 3),
                     "quality": round(quality, 3),
                     "oee": round(availability * min(performance, 1) * quality, 3)})
        if cum_good >= qty:
            po_rec["actual_end"] = en
            po_rec["status"] = "COMPLETED"
            so_actual[so] = en
            i, po = i + 1, None
    if po is not None:
        po_rec["status"] = "IN_PROCESS"
        po_rec["actual_end"] = None

prod_orders = pd.DataFrame(prod_orders)
lots = pd.DataFrame(lots)
stops = pd.DataFrame(stops)
inspections = pd.DataFrame(inspections)
ncrs = pd.DataFrame(ncrs)
prod_orders["planned_finish"] = prod_orders.so_id.map(lambda s: due[s] - pd.Timedelta(days=2))

# Promise dates: planners re-promise later orders from the actual start of production
# (nominal duration + 2 days buffer); the original plan date stands when it is later.
po_start = prod_orders.set_index("so_id")["actual_start"]
for m, sos in so_plan.items():
    for so, cust, mat, qty in sos:
        if so in po_start.index and so != "SO-45060":
            cap_day = 3 * math.floor(PLANNED_MIN * NOMINAL_PERF / (MAT.loc[mat, "ideal_cycle_min"] * CYCLE_ADJ[m]) * 0.995)
            replan = (po_start[so] + pd.Timedelta(days=qty / cap_day)).normalize() + pd.Timedelta(days=2)
            due[so] = max(due[so], replan)
prod_orders["planned_finish"] = prod_orders.so_id.map(lambda s: due[s] - pd.Timedelta(days=2))

# ---------------------------------------------------------------- ERP
so_rows = []
for m, sos in so_plan.items():
    for so, cust, mat, qty in sos:
        price = MAT.loc[mat, "unit_price_usd"]
        dd = due[so]
        if so in so_actual:
            ship = so_actual[so].normalize() + pd.Timedelta(days=1, hours=10)
            late = max((ship.normalize() - dd).days, 0)
            status = "SHIPPED"
            shipped = qty
        else:
            ship, late, status, shipped = None, None, "OPEN", 0
        value = qty * price
        pen = round(min(late * 0.005, 0.05) * value, 2) if late else 0.0
        so_rows.append({"so_id": so, "customer_id": cust, "material_id": mat, "qty": qty, "unit_price_usd": price,
                        "order_value_usd": round(value, 2), "order_date": min(dd - pd.Timedelta(days=35), (po_start[so] - pd.Timedelta(days=5)) if so in po_start.index else pd.Timestamp("2024-03-01")).date(),
                        "due_date": dd.date(), "ship_date": ship, "qty_shipped": shipped, "status": status,
                        "days_late": late, "late_penalty_usd": pen,
                        "penalty_terms": "0.5% of order value per day late, max 5%"})
sales_orders = pd.DataFrame(so_rows)

purchase_orders = pd.DataFrame([
    {"po_id": "4500018821", "material_id": "SP-BRG-7014", "vendor": "Precision Bearings Distribution (fictional)",
     "qty": 1, "unit_price_usd": 2850.00, "freight_usd": 1180.00, "expedited": True,
     "order_date": pd.Timestamp("2024-01-30 11:20"), "promised_date": pd.Timestamp("2024-02-05"),
     "received_ts": pd.Timestamp("2024-02-05 16:10"), "std_lead_time_days": 7, "ref_work_order": "WO-24-0117",
     "note": "Air freight; no stock on hand"},
    {"po_id": "4500019034", "material_id": "SP-FLT-220", "vendor": "FluidCare Supplies (fictional)",
     "qty": 6, "unit_price_usd": 85.00, "freight_usd": 0.0, "expedited": False,
     "order_date": pd.Timestamp("2024-02-15 15:00"), "promised_date": pd.Timestamp("2024-02-19"),
     "received_ts": pd.Timestamp("2024-02-19 09:30"), "std_lead_time_days": 3, "ref_work_order": "WO-24-0152",
     "note": "Restock after emergency use"},
    {"po_id": "4500019120", "material_id": "SP-FAN-080", "vendor": "ElectroParts Asia (fictional)",
     "qty": 2, "unit_price_usd": 42.00, "freight_usd": 0.0, "expedited": False,
     "order_date": pd.Timestamp("2024-02-26 10:00"), "promised_date": pd.Timestamp("2024-02-28"),
     "received_ts": pd.Timestamp("2024-02-28 14:00"), "std_lead_time_days": 2, "ref_work_order": "WO-24-0166",
     "note": ""},
])
spare_stock = pd.DataFrame([
    ["SP-BRG-7014", "PLANT-1000", 0, 1, "2024-01-01", "Last unit used Oct 2023 (CNC-02)"],
    ["SP-BRG-7014", "PLANT-1000", 0, 1, "2024-04-01", "Expedited unit consumed by WO-24-0117"],
    ["SP-FLT-220", "PLANT-1000", 1, 4, "2024-01-01", ""],
    ["SP-FLT-220", "PLANT-1000", 5, 4, "2024-04-01", ""],
    ["SP-FAN-080", "PLANT-1000", 1, 2, "2024-04-01", ""],
], columns=["material_id", "plant", "qty_on_hand", "reorder_point", "as_of_date", "note"])
cost_rates = pd.DataFrame([
    ["MACHINE_HOUR", "CNC-01", 85.0, "USD per machine hour (burden rate)"],
    ["MACHINE_HOUR", "CNC-02", 78.0, "USD per machine hour (burden rate)"],
    ["TECH_LABOUR_HOUR", "MAINT", 32.0, "USD per technician hour"],
    ["COMPLAINT_HANDLING", "QA", COMPLAINT_HANDLING, "USD per escaped part (sort, freight, admin)"],
], columns=["rate_type", "scope", "value_usd", "description"])

# ---------------------------------------------------------------- QA complaint (escapes)
complaints = []
for so, n in escapes_by_so.items():
    if n >= 10 and so in so_actual:
        row = sales_orders.set_index("so_id").loc[so]
        recv = pd.Timestamp(row.ship_date).normalize() + pd.Timedelta(days=4)
        complaints.append({"complaint_id": f"CC-24-{len(complaints) + 1:03d}", "customer_id": row.customer_id,
                           "so_id": so, "material_id": row.material_id, "received_date": recv.date(),
                           "qty_rejected_at_customer": int(n),
                           "description": "Incoming inspection found bore roundness above 5 um on parts from this shipment; parts returned for credit; 8D requested.",
                           "cost_usd": round(n * (MAT.loc[row.material_id, "unit_cost_usd"] + COMPLAINT_HANDLING), 2),
                           "status": "8D_OPEN"})
complaints = pd.DataFrame(complaints)

# ---------------------------------------------------------------- CMMS
assets = [
    {"asset_id": "CNC-01", "description": "Horizontal machining center, 630 mm pallet", "manufacturer": "Generic HMC (fictional)",
     "install_year": 2019, "location": "PLANT-1000 / Line SP-1 / Cell 1", "criticality": "A",
     "spindle": {"max_rpm": 12000, "taper": "HSK-A63", "de_bearing_last_replaced": "2022-03-14"}},
    {"asset_id": "CNC-02", "description": "Horizontal machining center, 630 mm pallet", "manufacturer": "Generic HMC (fictional)",
     "install_year": 2014, "location": "PLANT-1000 / Line SP-1 / Cell 2", "criticality": "A",
     "spindle": {"max_rpm": 12000, "taper": "HSK-A63", "de_bearing_last_replaced": "2023-10-09"}},
]
wos = [
    {"wo_id": "WO-22-0214", "asset_id": "CNC-01", "type": "CORRECTIVE", "priority": 1, "status": "CLOSED",
     "created_ts": "2022-03-12 09:00", "started_ts": "2022-03-14 06:00", "completed_ts": "2022-03-14 15:00",
     "failure_code": "BRG-WEAR", "problem": "Spindle noise and vibration", "cause": "Drive-end bearing wear",
     "remedy": "Replaced drive-end bearing set", "labour_hours": 9.0,
     "parts": [{"material_id": "SP-BRG-7014", "qty": 1}], "technician": "Maintenance team B"},
]
pm_id = 100
for m, (s, e) in WINDOWS.items():
    for d in pd.date_range(s.normalize(), e.normalize() - pd.Timedelta(days=1)):
        if d.weekday() == 0 and d.day <= 7:
            pm_id += 1
            wos.append({"wo_id": f"WO-24-{pm_id:04d}", "asset_id": m, "type": "PREVENTIVE", "priority": 3, "status": "CLOSED",
                        "created_ts": f"{(d - pd.Timedelta(days=7)):%Y-%m-%d} 08:00", "started_ts": f"{d:%Y-%m-%d} 06:00",
                        "completed_ts": f"{d:%Y-%m-%d} 07:00", "failure_code": None,
                        "problem": "Monthly spindle lubrication PM", "cause": None,
                        "remedy": "Lubricated spindle, checked drawbar force, checked coolant concentration (7.5%)",
                        "labour_hours": 1.0, "parts": [], "technician": "Maintenance team A"})
wos += [
    {"wo_id": "WO-24-0117", "asset_id": "CNC-01", "type": "CORRECTIVE", "priority": 1, "status": "CLOSED",
     "created_ts": "2024-01-30 08:10", "started_ts": "2024-02-05 22:00", "completed_ts": "2024-02-06 06:00",
     "failure_code": "BRG-WEAR", "problem": "Loud spindle whine, roundness rejects from QA lab",
     "cause": "Drive-end bearing outer race spalling; grease degraded",
     "remedy": "Replaced drive-end bearing set, run-in program, vibration re-baselined",
     "labour_hours": 9.0, "parts": [{"material_id": "SP-BRG-7014", "qty": 1}], "technician": "Maintenance team B",
     "notes": "No spare in stock; expedited PO 4500018821 by air freight."},
    {"wo_id": "WO-24-0152", "asset_id": "CNC-01", "type": "CORRECTIVE", "priority": 2, "status": "CLOSED",
     "created_ts": "2024-02-15 11:00", "started_ts": "2024-02-15 17:40", "completed_ts": "2024-02-15 18:30",
     "failure_code": "COOL-RESTR", "problem": "Low coolant flow at spindle nozzle, bore diameter rejects",
     "cause": "Coolant filter cartridge clogged with fines; strainer partly blocked",
     "remedy": "Replaced filter cartridge SP-FLT-220, cleaned strainer", "labour_hours": 0.8,
     "parts": [{"material_id": "SP-FLT-220", "qty": 1}], "technician": "Maintenance team A"},
    {"wo_id": "WO-24-0166", "asset_id": "CNC-01", "type": "CALIBRATION", "priority": 3, "status": "CLOSED",
     "created_ts": "2024-02-23 09:00", "started_ts": "2024-02-26 10:00", "completed_ts": "2024-02-26 11:30",
     "failure_code": "INST-DRIFT", "problem": "Spindle motor current on HMI reads high; clamp meter shows normal current",
     "cause": "Current transmitter thermal drift; electrical cabinet fan failed",
     "remedy": "Replaced cabinet fan SP-FAN-080, recalibrated current transmitter (offset -3.4 A)", "labour_hours": 1.5,
     "parts": [{"material_id": "SP-FAN-080", "qty": 1}], "technician": "Instrument technician"},
    {"wo_id": "WO-24-0241", "asset_id": "CNC-02", "type": "INSPECTION", "priority": 3, "status": "OPEN",
     "created_ts": "2024-04-26 15:00", "started_ts": None, "completed_ts": None,
     "failure_code": None, "problem": "Chatter marks and roundness rejects on MB-5120; check spindle and toolholder",
     "cause": None, "remedy": None, "labour_hours": None, "parts": [], "technician": None,
     "notes": "Scheduled for next planned PM (2024-05-06)"},
]

# ---------------------------------------------------------------- logbook (unstructured)
ROUTINE = ["Shift handover, no issues.", "Insert changed on T12 roughing tool.", "Blanks topped up, pallet 2 loaded.",
           "Coolant concentration checked, 7.5%.", "First-off part checked OK on air gauge.",
           "Chip conveyor emptied.", "Running to plan.", "Setter adjusted wear offset on T05 by 2 um."]
KEY = [
    ("2024-01-19 23:40", "CNC-01", "operator", "Faint high-pitched whine from spindle at 9000 rpm, goes away at lower speed. Will keep an eye on it."),
    ("2024-01-24 15:20", "CNC-01", "operator", "Spindle whine is louder than last week. Told maintenance verbally, no work order raised."),
    ("2024-01-29 10:05", "CNC-01", "QA", "CMM roundness above 5 um on VB-2210 sample. Lot quarantined and sorted."),
    ("2024-01-30 07:55", "CNC-01", "operator", "Spindle noise very loud now, more roundness rejects. Raised work order with maintenance."),
    ("2024-01-30 11:30", "CNC-01", "maintenance", "Checked spindle, vibration high on drive end. Bearing set needed, none in stores. Ordered by air."),
    ("2024-02-06 06:20", "CNC-01", "maintenance", "Drive-end bearing replaced overnight. Run-in done, vibration settling."),
    ("2024-02-14 02:10", "CNC-01", "operator", "Chips packing in the bore, coolant at nozzle looks weak."),
    ("2024-02-15 10:40", "CNC-01", "QA", "Bore diameter oversize on VB-2210, air gauge rejecting more parts than usual."),
    ("2024-02-21 16:00", "CNC-01", "operator", "HMI shows spindle current higher than normal but machine sounds and cuts normally."),
    ("2024-04-10 15:30", "CNC-02", "setter", "Changed spindle toolholder to HSK #7. Runout gauge away for calibration, skipped runout check."),
    ("2024-04-16 03:15", "CNC-02", "operator", "Slight vibration felt on the guard, more than usual for this old machine."),
    ("2024-04-24 20:45", "CNC-02", "operator", "Chatter marks visible on MB-5120 bore wall. Surface still in spec per gauge."),
    ("2024-04-26 14:30", "CNC-02", "QA", "Roundness rejects on MB-5120 since 24 Apr, lots sorted. Billet hardness is in spec. Asked maintenance to check the spindle and toolholder."),
]
notes = []
nid = 1
for m in WINDOWS:
    for st in shift_starts(m):
        if rng.random() < 0.55:
            ts = st + pd.Timedelta(minutes=int(rng.integers(20, 470)))
            notes.append({"note_id": f"LB-{nid:05d}", "ts": ts, "machine_id": m, "shift": shift_code(st),
                          "author_role": "operator", "text": ROUTINE[rng.integers(len(ROUTINE))]})
            nid += 1
for ts, m, role, txt in KEY:
    t = pd.Timestamp(ts)
    sc = "A" if 6 <= t.hour < 14 else ("B" if 14 <= t.hour < 22 else "C")
    notes.append({"note_id": f"LB-{nid:05d}", "ts": t, "machine_id": m, "shift": sc, "author_role": role, "text": txt})
    nid += 1
notes = sorted(notes, key=lambda r: r["ts"])

# ---------------------------------------------------------------- write
def iso(df):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


iso(prod_orders[["prod_order_id", "so_id", "material_id", "machine_id", "qty_target", "planned_finish",
                 "actual_start", "actual_end", "qty_good", "qty_scrap", "status"]]).to_csv(OUT / "mes/production_orders.csv", index=False)
iso(lots).to_csv(OUT / "mes/production_lots.csv", index=False)
iso(stops).to_csv(OUT / "mes/downtime_events.csv", index=False)
customers.to_csv(OUT / "erp/customers.csv", index=False)
materials.to_csv(OUT / "erp/materials.csv", index=False)
iso(sales_orders).to_csv(OUT / "erp/sales_orders.csv", index=False)
iso(purchase_orders).to_csv(OUT / "erp/purchase_orders.csv", index=False)
spare_stock.to_csv(OUT / "erp/spare_parts_stock.csv", index=False)
cost_rates.to_csv(OUT / "erp/cost_rates.csv", index=False)
iso(inspections).to_csv(OUT / "qa/cmm_inspections.csv", index=False)
iso(ncrs).to_csv(OUT / "qa/ncr.csv", index=False)
complaints.to_csv(OUT / "qa/customer_complaints.csv", index=False)
with open(OUT / "cmms/assets.json", "w") as f:
    json.dump(assets, f, indent=2)
with open(OUT / "cmms/work_orders.jsonl", "w") as f:
    for w in sorted(wos, key=lambda r: r["created_ts"]):
        f.write(json.dumps(w) + "\n")
with open(OUT / "logbook/shift_logbook.jsonl", "w") as f:
    for n in notes:
        n = dict(n, ts=n["ts"].strftime("%Y-%m-%d %H:%M:%S"))
        f.write(json.dumps(n) + "\n")
print("done")
