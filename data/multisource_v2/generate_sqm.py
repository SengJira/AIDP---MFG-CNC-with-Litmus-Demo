"""Add Supplier Quality Management (SQM) data to the multi-source pack.

Run after generate.py:  python3 generate_sqm.py <data dir>
Deterministic (seed 7). Reads MES lots and adds:
  sqm/       suppliers, approved_sources, material_specs, material_lots, certificates_of_analysis,
             incoming_inspections, scar, supplier_scorecard
  sqm/coa_documents/*.md   certificate PDFs as text (for the Data Search Engine)
  mes/material_consumption.csv   lot genealogy: which supplier lot went into which MES lot
  erp/purchase_orders.csv        + raw-material and toolholder POs
  erp/materials.csv              + purchased materials

Embedded story: Supplier B (second source) castings, released on reduced inspection,
are harder than spec although their certificates claim otherwise. CNC-01 vibration
rises within a day each time Supplier B castings are issued (15 Jan and 24 Mar).
CNC-02's April vibration is NOT linked to castings; it follows a toolholder from
Supplier C whose own certificate shows balance grade G6.3 against a G2.5 spec.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
D = Path(sys.argv[1])
(D / "sqm" / "coa_documents").mkdir(parents=True, exist_ok=True)

lots = pd.read_csv(D / "mes/production_lots.csv", parse_dates=["start_ts", "end_ts"])

suppliers = pd.DataFrame([
    ["SUP-A", "Chao Phraya Castings (fictional)", "TH", "Iron castings", "APPROVED", "NORMAL", "2016-05-01"],
    ["SUP-B", "Eastern Metal Foundry (fictional)", "TH", "Iron castings", "CONDITIONAL_SECOND_SOURCE", "REDUCED_COA_BASED", "2023-12-04"],
    ["SUP-C", "Precision Tooling Asia (fictional)", "MY", "Toolholders", "APPROVED", "REDUCED_COA_BASED", "2021-02-15"],
    ["SUP-E", "Rayong Steel Service (fictional)", "TH", "Steel bar and billet", "APPROVED", "NORMAL", "2018-09-10"],
    ["SUP-F", "Precision Bearings Distribution (fictional)", "TH", "Bearings (distributor)", "APPROVED", "NORMAL", "2019-01-20"],
], columns=["supplier_id", "supplier_name", "country", "commodity", "approval_status", "incoming_inspection_level", "approved_since"])

specs = pd.DataFrame([
    ["RM-2210", "Valve body casting, ductile iron EN-GJS-500-7", "HARDNESS_HB", 170, 230, "HB", "Brinell 10/3000 on casting body"],
    ["RM-3140", "Pump housing casting, grey iron EN-GJL-250", "HARDNESS_HB", 180, 240, "HB", "Brinell 10/3000 on casting body"],
    ["RM-5120", "Manifold billet, steel C45 normalised", "HARDNESS_HB", 170, 220, "HB", "Brinell 10/3000"],
    ["TH-HSK63-SF", "Shrink-fit toolholder HSK-A63", "BALANCE_GRADE_G", None, 2.5, "G (ISO 21940-11) at 25,000 rpm", "Balancing machine"],
], columns=["material_id", "description", "characteristic", "lsl", "usl", "unit", "method"])

approved = pd.DataFrame([
    ["RM-2210", "SUP-A", 1, "Primary"], ["RM-2210", "SUP-B", 2, "Second source, conditional until 6 good lots"],
    ["RM-3140", "SUP-A", 1, "Primary"], ["RM-3140", "SUP-B", 2, "Second source, conditional until 6 good lots"],
    ["RM-5120", "SUP-E", 1, "Primary"], ["TH-HSK63-SF", "SUP-C", 1, "Primary"],
    ["SP-BRG-7014", "SUP-F", 1, "Distributor"],
], columns=["material_id", "supplier_id", "priority", "note"])

RAW = {"VB-2210": "RM-2210", "PH-3140": "RM-3140", "MB-5120": "RM-5120"}
B_WINDOWS = [(pd.Timestamp("2024-01-15 22:00"), pd.Timestamp("2024-02-03 14:00")),
             (pd.Timestamp("2024-03-24 22:00"), pd.Timestamp("2024-04-01 06:00"))]


def supplier_for(row):
    rm = RAW[row.material_id]
    if rm == "RM-5120":
        return "SUP-E"
    if row.machine_id == "CNC-01" and any(a <= row.start_ts < b for a, b in B_WINDOWS):
        return "SUP-B"
    return "SUP-A"


lots["raw_material_id"] = lots.material_id.map(RAW)
lots["supplier_id"] = lots.apply(supplier_for, axis=1)
lots = lots.sort_values("start_ts")

LOT_SIZE = {"RM-2210": 600, "RM-3140": 480, "RM-5120": 400}
HEAT_PREFIX = {"SUP-A": "CPC", "SUP-B": "EMF", "SUP-E": "RSS"}
queues, mlots, consumption = {}, [], []
seq = 0


def new_lot(rm, sup, first_use):
    global seq
    seq += 1
    if sup == "SUP-B" and first_use < pd.Timestamp("2024-03-01"):
        received = pd.Timestamp("2024-01-12 10:00")
        campaign = "B-JAN"
    elif sup == "SUP-B":
        received = pd.Timestamp("2024-03-21 09:30")
        campaign = "B-MAR"
    else:
        received = (first_use - pd.Timedelta(days=int(rng.integers(3, 9)))).normalize() + pd.Timedelta(hours=10)
        campaign = "STD"
    lot = {"material_lot_id": f"ML-24-{seq:04d}", "material_id": rm, "supplier_id": sup,
           "supplier_heat_no": f"{HEAT_PREFIX[sup]}-{received:%y%m}-{int(rng.integers(10, 99))}",
           "qty_received": LOT_SIZE[rm], "received_ts": received, "qty_remaining": LOT_SIZE[rm],
           "campaign": campaign}
    mlots.append(lot)
    return lot


for r in lots.itertuples():
    need = int(r.qty_produced)
    key = (r.raw_material_id, r.supplier_id, "B-MAR" if (r.supplier_id == "SUP-B" and r.start_ts > pd.Timestamp("2024-03-01")) else "")
    while need > 0:
        q = queues.get(key)
        if q is None or q["qty_remaining"] == 0:
            q = new_lot(r.raw_material_id, r.supplier_id, r.start_ts)
            queues[key] = q
        take = min(need, q["qty_remaining"])
        q["qty_remaining"] -= take
        need -= take
        consumption.append({"lot_id": r.lot_id, "machine_id": r.machine_id, "material_lot_id": q["material_lot_id"],
                            "raw_material_id": r.raw_material_id, "supplier_id": r.supplier_id,
                            "qty_consumed": take, "issued_ts": r.start_ts})

# Supplier B January lot that was in stores but never used -> quarantined with the rest
extra = new_lot("RM-2210", "SUP-B", pd.Timestamp("2024-01-20"))
mlots = pd.DataFrame(mlots)
mlots["status"] = np.where(mlots.qty_remaining == 0, "CONSUMED", "IN_STOCK")
b_jan = mlots.campaign == "B-JAN"
mlots.loc[b_jan & (mlots.qty_remaining > 0), "status"] = "QUARANTINED"
mlots["release_decision"] = np.select(
    [mlots.campaign == "B-JAN", mlots.campaign == "B-MAR"],
    ["Released on CoA (reduced inspection, skip-lot)", "Released under deviation DEV-24-012: SUP-B requalification trial on CNC-01 after SCAR closure"],
    "Released after incoming inspection")
mlots.loc[mlots.supplier_id == "SUP-E", "release_decision"] = "Released after incoming inspection"

# toolholder for CNC-02
th = {"material_lot_id": "ML-24-0901", "material_id": "TH-HSK63-SF", "supplier_id": "SUP-C",
      "supplier_heat_no": "PTA-SN-24-0007", "qty_received": 1, "received_ts": pd.Timestamp("2024-04-08 14:20"),
      "qty_remaining": 0, "campaign": "TOOL", "status": "IN_USE_CNC-02",
      "release_decision": "Released on certificate; balancing check skipped (balancing machine out for calibration)"}
mlots = pd.concat([mlots, pd.DataFrame([th])], ignore_index=True)

# ---------------- certificates of analysis + measured hardness
coa, insp = [], []
iid = 0


def hb_measured(row):
    if row.campaign == "B-JAN":
        return {"RM-2210": (242, 4), "RM-3140": (256, 4)}[row.material_id]
    if row.campaign == "B-MAR":
        return {"RM-2210": (225, 2), "RM-3140": (235, 2)}[row.material_id]
    return {"RM-2210": (206, 6), "RM-3140": (212, 7), "RM-5120": (192, 6)}[row.material_id]


for r in mlots.itertuples():
    if r.material_id == "TH-HSK63-SF":
        coa.append({"coa_id": f"COA-{r.material_lot_id}", "material_lot_id": r.material_lot_id, "supplier_id": r.supplier_id,
                    "issued_date": "2024-04-05", "hardness_hb_claimed": None, "balance_grade_claimed": 6.3,
                    "cu_pct": None, "mn_pct": None, "tensile_mpa": None, "test_location": "Balancing report BR-0007",
                    "conforms_claimed": True})
        iid += 1
        insp.append({"inspection_id": f"IQ-{iid:05d}", "material_lot_id": r.material_lot_id, "inspect_ts": r.received_ts + pd.Timedelta(hours=2),
                     "inspection_type": "RECEIVING", "characteristic": "BALANCE_GRADE_G", "sample_no": None, "measured": None,
                     "lsl": None, "usl": 2.5, "result": "SKIPPED", "note": "Balancing machine out for calibration; released on certificate"})
        continue
    spec = specs.set_index("material_id").loc[r.material_id]
    mu, sd = hb_measured(r)
    if r.campaign == "B-JAN":
        claimed = int(rng.integers(208, 217))
        cu, mn, loc = round(rng.uniform(0.58, 0.66), 2), round(rng.uniform(0.40, 0.45), 2), "Separately cast test bar"
    elif r.campaign == "B-MAR":
        claimed = int(rng.integers(218, 225))
        cu, mn, loc = round(rng.uniform(0.44, 0.48), 2), round(rng.uniform(0.35, 0.38), 2), "Casting body (per 8D)"
    else:
        claimed = int(round(mu + rng.normal(0, 3)))
        cu, mn, loc = round(rng.uniform(0.26, 0.34), 2), round(rng.uniform(0.28, 0.33), 2), "Casting body"
        if r.material_id == "RM-5120":
            cu = None
    coa.append({"coa_id": f"COA-{r.material_lot_id}", "material_lot_id": r.material_lot_id, "supplier_id": r.supplier_id,
                "issued_date": (r.received_ts - pd.Timedelta(days=2)).date(), "hardness_hb_claimed": claimed,
                "balance_grade_claimed": None, "cu_pct": cu, "mn_pct": mn,
                "tensile_mpa": int(rng.integers(510, 560)) if r.material_id == "RM-2210" else int(rng.integers(255, 290)) if r.material_id == "RM-3140" else int(rng.integers(630, 680)),
                "test_location": loc, "conforms_claimed": True})
    def add_samples(ts, itype, note):
        global iid
        for k in range(1, 6):
            iid += 1
            v = int(round(rng.normal(mu, sd)))
            insp.append({"inspection_id": f"IQ-{iid:05d}", "material_lot_id": r.material_lot_id, "inspect_ts": ts,
                         "inspection_type": itype, "characteristic": "HARDNESS_HB", "sample_no": k, "measured": v,
                         "lsl": spec.lsl, "usl": spec.usl, "result": "PASS" if spec.lsl <= v <= spec.usl else "FAIL", "note": note})
    if r.campaign == "B-JAN":
        iid += 1
        insp.append({"inspection_id": f"IQ-{iid:05d}", "material_lot_id": r.material_lot_id, "inspect_ts": r.received_ts + pd.Timedelta(hours=3),
                     "inspection_type": "RECEIVING", "characteristic": "HARDNESS_HB", "sample_no": None, "measured": None,
                     "lsl": spec.lsl, "usl": spec.usl, "result": "SKIPPED", "note": "Reduced inspection: released on CoA"})
        add_samples(pd.Timestamp("2024-02-03 09:00"), "AUDIT", "Hardness audit after roundness rejects; retained castings / stock")
    elif r.campaign == "B-MAR":
        add_samples(r.received_ts + pd.Timedelta(hours=3), "RECEIVING", "Normal inspection after SCAR-24-003 closure")
    else:
        add_samples(r.received_ts + pd.Timedelta(hours=3), "RECEIVING", "")

coa = pd.DataFrame(coa)
insp = pd.DataFrame(insp)
# B-MAR: accepted on deviation even though some readings exceed 240
bmar = mlots.loc[mlots.campaign == "B-MAR", "material_lot_id"]

# ---------------- SCAR and scorecard
b_jan_lots = mlots.loc[mlots.campaign == "B-JAN", "material_lot_id"].tolist()
scar = pd.DataFrame([{
    "scar_id": "SCAR-24-003", "supplier_id": "SUP-B", "material_ids": "RM-2210; RM-3140",
    "material_lot_ids": "; ".join(b_jan_lots), "opened_ts": pd.Timestamp("2024-02-03 10:00"),
    "problem": "Audit hardness HB 238-261 vs spec max 230 (RM-2210) / 240 (RM-3140); CoAs claimed HB 211-212 on a separately cast test bar",
    "containment": "Quarantine remaining SUP-B stock; issue SUP-A castings from 3 Feb B shift",
    "root_cause_8d": "New automatic moulding line: early shakeout caused chilled carbides in thin walls. CoA hardness was measured on a separately cast test bar, not on the casting.",
    "corrective_action": "Shakeout time +12 min; hardness measured on casting body; Cu reduced to 0.45%",
    "status": "CLOSED", "closed_ts": pd.Timestamp("2024-03-15 16:00"),
    "cost_claim_usd": 14178.00, "cost_claim_basis": "Avoidable cost USD 11,328 (scrap, escapes, freight, penalty) + bearing set USD 2,850",
    "claim_status": "NEGOTIATING"}])

score = []
for sup in ["SUP-A", "SUP-B", "SUP-C", "SUP-E"]:
    for mth in ["2024-01", "2024-02", "2024-03", "2024-04"]:
        m = mlots[(mlots.supplier_id == sup) & (mlots.received_ts.dt.strftime("%Y-%m") == mth)]
        n = len(m)
        if n == 0:
            continue
        bad = 0
        if sup == "SUP-B" and mth == "2024-01":
            bad = n
        ppm = {"SUP-A": 150, "SUP-B": 0, "SUP-C": 0, "SUP-E": 90}[sup]
        if sup == "SUP-B" and mth == "2024-01":
            ppm = 1_000_000
        score.append({"supplier_id": sup, "month": mth, "lots_received": n, "lots_nonconforming": bad,
                      "ppm_defective": ppm, "on_time_delivery_pct": {"SUP-A": 86.0, "SUP-B": 97.0, "SUP-C": 100.0, "SUP-E": 95.0}[sup],
                      "rating": "RED" if bad else ("AMBER" if sup == "SUP-A" and mth == "2024-01" else "GREEN"),
                      "comment": {"SUP-A": "Late deliveries in January caused second-source use"}.get(sup, "") if mth == "2024-01" else ""})
score = pd.DataFrame(score)
score.loc[(score.supplier_id == "SUP-B") & (score.month == "2024-03"), ["rating", "comment"]] = ["AMBER", "Requalification trial under deviation DEV-24-012; hardness near upper limit"]

# ---------------- ERP additions (materials, purchase orders)
mat = pd.read_csv(D / "erp/materials.csv")
mat = mat[~mat.material_id.isin(specs.material_id)]
add = pd.DataFrame([
    ["RM-2210", "Valve body casting, ductile iron EN-GJS-500-7", "RAW_MATERIAL", 9.80, None, None, None, 10],
    ["RM-3140", "Pump housing casting, grey iron EN-GJL-250", "RAW_MATERIAL", 14.20, None, None, None, 10],
    ["RM-5120", "Manifold billet, steel C45 normalised", "RAW_MATERIAL", 21.50, None, None, None, 7],
    ["TH-HSK63-SF", "Shrink-fit toolholder HSK-A63, balanced G2.5 at 25,000 rpm", "TOOLING", 410.00, None, None, None, 14],
], columns=mat.columns)
pd.concat([mat, add], ignore_index=True).to_csv(D / "erp/materials.csv", index=False)

po = pd.read_csv(D / "erp/purchase_orders.csv", dtype={"po_id": str})
po = po[po.material_id.isin(["SP-BRG-7014", "SP-FLT-220", "SP-FAN-080"])]
cost = add.set_index("material_id").unit_cost_usd
sup_name = suppliers.set_index("supplier_id").supplier_name
new_po, po_of = [], {}
for i, r in enumerate(mlots.sort_values("received_ts").itertuples(), 1):
    pid = f"45000{17000 + i}"
    po_of[r.material_lot_id] = pid
    new_po.append({"po_id": pid, "material_id": r.material_id, "vendor": sup_name[r.supplier_id], "qty": r.qty_received,
                   "unit_price_usd": cost[r.material_id], "freight_usd": 0.0, "expedited": False,
                   "order_date": r.received_ts - pd.Timedelta(days=12), "promised_date": r.received_ts.normalize(),
                   "received_ts": r.received_ts, "std_lead_time_days": int(add.set_index("material_id").std_lead_time_days[r.material_id]),
                   "ref_work_order": None, "note": "Second source (SUP-A late)" if r.supplier_id == "SUP-B" else ""})
po = pd.concat([po, pd.DataFrame(new_po)], ignore_index=True)
mlots["po_id"] = mlots.material_lot_id.map(po_of)

# ---------------- CoA documents (unstructured, for the Data Search Engine)
for r in coa.merge(mlots[["material_lot_id", "material_id", "supplier_heat_no", "qty_received"]], on="material_lot_id").itertuples():
    sname = sup_name[r.supplier_id]
    lines = [f"# Certificate of Analysis {r.coa_id}", "", f"Supplier: {sname}", f"Material: {r.material_id}",
             f"Heat / serial: {r.supplier_heat_no}", f"Quantity: {r.qty_received}", f"Issued: {r.issued_date}", ""]
    if r.material_id == "TH-HSK63-SF":
        lines += ["Balancing report BR-0007", f"Residual unbalance: balance grade G{r.balance_grade_claimed} at 25,000 rpm",
                  "Runout at gauge line: 3 um", "Statement: Product conforms to order."]
    else:
        lines += [f"Brinell hardness (10/3000): HB {int(r.hardness_hb_claimed)}", f"Test location: {r.test_location}",
                  f"Tensile strength: {int(r.tensile_mpa)} MPa"]
        if not pd.isna(r.cu_pct):
            lines += [f"Chemistry: Cu {r.cu_pct}%, Mn {r.mn_pct}%"]
        lines += ["Statement: Material conforms to the purchase specification."]
    (D / "sqm/coa_documents" / f"{r.coa_id}.md").write_text("\n".join(lines) + "\n")

# ---------------- write
def iso(df):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


suppliers.to_csv(D / "sqm/suppliers.csv", index=False)
approved.to_csv(D / "sqm/approved_sources.csv", index=False)
specs.to_csv(D / "sqm/material_specs.csv", index=False)
iso(mlots[["material_lot_id", "material_id", "supplier_id", "supplier_heat_no", "po_id", "qty_received", "received_ts",
           "qty_remaining", "status", "release_decision"]]).to_csv(D / "sqm/material_lots.csv", index=False)
coa.to_csv(D / "sqm/certificates_of_analysis.csv", index=False)
iso(insp).to_csv(D / "sqm/incoming_inspections.csv", index=False)
iso(scar).to_csv(D / "sqm/scar.csv", index=False)
score.to_csv(D / "sqm/supplier_scorecard.csv", index=False)
iso(pd.DataFrame(consumption)).to_csv(D / "mes/material_consumption.csv", index=False)
iso(po).to_csv(D / "erp/purchase_orders.csv", index=False)
print("sqm done")
