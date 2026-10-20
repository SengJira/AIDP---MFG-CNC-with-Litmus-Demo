#!/usr/bin/env python3
"""CNC Spindle Health — Streamlit dashboard for Dell AIDP demo."""

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import trino
from trino.auth import BasicAuthentication

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
CATALOG = "js_manuf_ice"
SCHEMA = "smart_mfg"
SIGNALS = [
    "SPINDLE_RPM", "SPINDLE_LOAD_PCT", "MOTOR_CURRENT_A", "VIB_X_MM_S",
    "VIB_Y_MM_S", "BEARING_TEMP_C", "COOLANT_FLOW_LPM", "COOLANT_PRESSURE_BAR",
    "FEED_RATE_MM_MIN", "AIR_PRESSURE_BAR", "AMBIENT_TEMP_C", "ACOUSTIC_DB",
]

OFFLINE = os.environ.get("OFFLINE_MODE", "0") == "1"

st.set_page_config(page_title="CNC Spindle Health", layout="wide")
st.markdown(
    """
    <style>
    .big-title { font-size: 2.4rem; font-weight: 700; color: #007db8; }
    .kpi { font-size: 2rem; font-weight: 700; color: #1f2937; }
    .kpi-label { font-size: 0.9rem; color: #5f6368; }
    .live { color: #00c853; font-weight: 700; }
    .fallback { color: #9e9e9e; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { font-size: 1.1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def trino_conn():
    if OFFLINE:
        return None
    return trino.dbapi.connect(
        host=os.environ.get("TRINO_HOST", "ddae.lab9bgp.com"),
        port=int(os.environ.get("TRINO_PORT", "443")),
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        catalog=CATALOG,
        verify=False,
    )


def trino_query(sql):
    conn = trino_conn()
    if conn is None:
        return pd.DataFrame()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def load_sensor(equipment_id=None):
    if OFFLINE:
        df = pd.read_parquet(PROCESSED / "sensor_readings.parquet")
    else:
        df = trino_query(f"SELECT * FROM {CATALOG}.{SCHEMA}.sensor_readings")
    if equipment_id:
        df = df[df["equipment_id"] == equipment_id]
    time_col = "Timestamp" if "Timestamp" in df.columns else "ts"
    df["ts"] = pd.to_datetime(df[time_col])
    # Trino normalizes unquoted identifiers to lowercase; offline Parquet keeps the original uppercase signal names
    for c in list(df.columns):
        if c.upper() in SIGNALS:
            df = df.rename(columns={c: c.upper()})
    return df.sort_values("ts").reset_index(drop=True)


def load_equipment():
    if OFFLINE:
        return pd.read_parquet(PROCESSED / "equipment.parquet")
    return trino_query(f"SELECT * FROM {CATALOG}.{SCHEMA}.equipment")


def load_events(run_id):
    path = PROCESSED / run_id / "anomaly_events.parquet"
    if path.exists():
        return pd.read_parquet(path)
    if not OFFLINE:
        df = trino_query(f"SELECT * FROM {CATALOG}.{SCHEMA}.anomaly_events WHERE run_id = '{run_id}'")
        if not df.empty:
            for c in ["start_ts", "end_ts", "peak_ts"]:
                df[c] = pd.to_datetime(df[c])
        return df
    return pd.DataFrame()


def load_scores(run_id):
    path = PROCESSED / run_id / "anomaly_scores.parquet"
    if path.exists():
        return pd.read_parquet(path)
    if not OFFLINE:
        df = trino_query(f"SELECT * FROM {CATALOG}.{SCHEMA}.anomaly_scores WHERE run_id = '{run_id}'")
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"])
        return df
    return pd.DataFrame()


def save_label_offline(record, promote):
    PROCESSED.mkdir(parents=True, exist_ok=True)
    labels_path = PROCESSED / "session_labels.json"
    bank_path = PROCESSED / "session_label_bank.json"
    labels = json.loads(labels_path.read_text()) if labels_path.exists() else []
    bank = json.loads(bank_path.read_text()) if bank_path.exists() else []
    labels.append(record)
    with open(labels_path, "w") as f:
        json.dump(labels, f, indent=2)
    if promote:
        bank.append({
            "session_name": "session",
            "equipment_type_tag": "CNC Machining Center",
            "label_id": record["label_id"],
            "signal": record["signal"],
            "feature_profile": json.dumps({
                "label_type": record["label_type"],
                "start_ts": str(record["start_ts"]),
                "end_ts": str(record["end_ts"]),
                "root_cause_category": record["root_cause_category"],
                "note": record["note"],
            }),
            "promoted_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        })
        with open(bank_path, "w") as f:
            json.dump(bank, f, indent=2)


def sql_literal(value, kind="string"):
    if kind == "string":
        return "NULL" if value is None else f"'{str(value).replace(chr(39), chr(39)+chr(39))}'"
    if kind == "float":
        return str(float(value)) if value is not None else "NULL"
    return f"'{value}'"


def save_label_trino(record, promote):
    conn = trino_conn()
    if conn is None:
        return
    cur = conn.cursor()
    vals = (
        sql_literal(record["label_id"]),
        sql_literal(record["equipment_id"]),
        sql_literal(record["signal"]),
        f"TIMESTAMP '{record['start_ts']}'",
        f"TIMESTAMP '{record['end_ts']}'",
        sql_literal(record["label_type"]),
        sql_literal(record["confidence"], "float"),
        sql_literal(record["root_cause_category"]),
        sql_literal(record["note"]),
        sql_literal(record["author"]),
        f"TIMESTAMP '{record['created_at']}'",
    )
    cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.labels VALUES ({', '.join(vals)})")
    if promote:
        bank_vals = (
            sql_literal("session"),
            sql_literal("CNC Machining Center"),
            sql_literal(record["label_id"]),
            sql_literal(record["signal"]),
            sql_literal(json.dumps({
                "label_type": record["label_type"],
                "start_ts": record["start_ts"],
                "end_ts": record["end_ts"],
                "root_cause_category": record["root_cause_category"],
                "note": record["note"],
            })),
            f"TIMESTAMP '{record['created_at']}'",
        )
        cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.label_bank VALUES ({', '.join(bank_vals)})")


def run_detection_local(equipment_id, run_id, seed_session=None):
    cmd = [sys.executable, "jobs/detect.py", "--equipment-id", equipment_id, "--run-id", run_id]
    if seed_session:
        cmd += ["--seed-session", seed_session]
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)


def reset_demo():
    for p in PROCESSED.glob("dashboard_*"):
        if p.is_dir():
            for f in p.iterdir():
                f.unlink()
            p.rmdir()
    for f in ["session_labels.json", "session_label_bank.json"]:
        path = PROCESSED / f
        if path.exists():
            path.unlink()
    subprocess.run([sys.executable, "scripts/seed_label_bank.py"], cwd=str(ROOT))
    return True


def component_status(name, env_keys, fallback_reason):
    if OFFLINE:
        return name, "fallback", fallback_reason
    for k in env_keys:
        if not os.environ.get(k):
            return name, "fallback", f"{k} not set"
    return name, "live", "Connected"


def render_header():
    c1, c2 = st.columns([0.8, 0.2])
    c1.markdown("<div class='big-title'>CNC Spindle Health — Predictive Maintenance</div>", unsafe_allow_html=True)
    mode = "OFFLINE" if OFFLINE else "LIVE"
    c2.markdown(f"<div style='text-align:right; font-size:1.2rem;'><b>Mode:</b> {mode}</div>", unsafe_allow_html=True)


def render_overview():
    st.subheader("Overview")
    components = [
        component_status("Dell ObjectScale Storage", ["S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"], "S3 env not configured"),
        component_status("DDAE / Starburst", ["TRINO_USER", "TRINO_PASS"], "Trino env not configured"),
        component_status("DDAE MCP Server", ["AIDP_MCP_URL", "AIDP_MCP_AUTH"], "MCP env not configured"),
        component_status("DPE / Spark", [], "Local PySpark fallback in use"),
        component_status("Data Search / Elastic", ["ELASTIC_ENDPOINT", "ELASTIC_API_KEY"], "Elastic env not configured"),
    ]
    cols = st.columns(len(components))
    for col, (name, status, reason) in zip(cols, components):
        color = "live" if status == "live" else "fallback"
        col.markdown(f"<div style='text-align:center;'><b>{name}</b><br><span class='{color}'>{status.upper()}</span><br><small>{reason}</small></div>", unsafe_allow_html=True)

    eq = load_equipment()
    baseline_events = load_events("cnc01_baseline")
    cnc02_events = load_events("cnc02_seeded")
    n_machines = len(eq) if not eq.empty else 2
    n_events = len(baseline_events) + len(cnc02_events)
    warning_days = 20
    k1, k2, k3 = st.columns(3)
    k1.markdown(f"<div class='kpi'>{n_machines}</div><div class='kpi-label'>Machines monitored</div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi'>{n_events}</div><div class='kpi-label'>Events found</div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi'>{warning_days}</div><div class='kpi-label'>Days of early warning</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Offline fallback:** All cached Parquet results and knowledge docs are served from `data/processed/`.")


def render_detect():
    st.subheader("Detect")
    eq = load_equipment()
    equip_list = eq["equipment_id"].tolist() if not eq.empty else ["CNC-01", "CNC-02"]
    equipment = st.selectbox("Equipment", equip_list, key="detect_equip")
    available_runs = sorted([p.name for p in PROCESSED.iterdir() if (p / "anomaly_events.parquet").exists()])
    current = st.session_state.get("detect_run_id", "")
    default_idx = available_runs.index(current) if current in available_runs else 0
    existing = st.selectbox("Existing run", available_runs, index=default_idx, key="detect_run_select")
    custom = st.text_input("Or custom run ID for new detection", value="")
    run_id = custom.strip() if custom.strip() else existing
    st.session_state["detect_run_id"] = run_id
    seed = st.selectbox("Seed session", ["", "cnc01_baseline"], index=0, key="detect_seed")
    if st.button("Run detection", type="primary"):
        with st.spinner("Running local detection..."):
            result = run_detection_local(equipment, run_id, seed or None)
        st.text(result.stdout[-1000:] if result.stdout else "")
        if result.returncode != 0:
            st.error(result.stderr[-800:])
            return
        st.success("Detection complete")

    events = load_events(run_id)
    scores = load_scores(run_id)
    if events.empty:
        st.info("No events for this run. Run detection first.")
        return

    st.markdown("**Consensus ranking**")
    display = events[["event_id", "start_ts", "end_ts", "severity", "signature", "signals"]].copy()
    display["signals"] = display["signals"].apply(lambda s: ", ".join(s) if isinstance(s, (list, tuple)) else str(s))
    st.dataframe(display, use_container_width=True)

    df = load_sensor(equipment)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["ts"], y=df["VIB_X_MM_S"], name="VIB_X_MM_S", line=dict(color="#00b4d8")))
    fig.add_trace(go.Scatter(x=df["ts"], y=df["VIB_Y_MM_S"], name="VIB_Y_MM_S", line=dict(color="#90e0ef")))
    baseline = df[df["ts"] < "2024-01-13"]["VIB_X_MM_S"]
    threshold = float(baseline.mean() + 3 * baseline.std())
    fig.add_hline(y=threshold, line_dash="dash", line_color="#ff6b6b", annotation_text="VIB_X baseline + 3σ")
    for _, ev in events.iterrows():
        if ev["severity"] in ("high", "medium"):
            fig.add_vrect(x0=ev["start_ts"], x1=ev["end_ts"], fillcolor="red", opacity=0.15, line_width=0)
    if equipment == "CNC-01":
        fig.add_vline(x="2024-01-17 12:00:00", line_color="#ffeb3b", line_dash="dot", annotation_text="First warning")
    fig.update_layout(template="plotly_white", title="Vibration X & Y with anomaly shading", height=450)
    st.plotly_chart(fig, use_container_width=True)

    if not scores.empty:
        top = scores[scores["is_anomaly"] == True].groupby("signal").size().sort_values(ascending=False).head(10)
        st.markdown("**Top anomalous signals by flag count**")
        st.bar_chart(top)


def render_investigate():
    st.subheader("Investigate")
    available_runs = sorted([p.name for p in PROCESSED.iterdir() if (p / "anomaly_events.parquet").exists()])
    default = st.session_state.get("detect_run_id", "cnc01_baseline")
    if default not in available_runs:
        default = "cnc01_baseline" if "cnc01_baseline" in available_runs else (available_runs[0] if available_runs else None)
    run_id = st.selectbox("Select run", available_runs, index=available_runs.index(default) if default in available_runs else 0, key="inv_run")
    events = load_events(run_id)
    if events.empty:
        st.info(f"No events loaded for run {run_id}.")
        return
    ev_id = st.selectbox("Select event", events["event_id"], key="inv_event")
    ev = events[events["event_id"] == ev_id].iloc[0]
    equipment_id = ev["equipment_id"]
    df = load_sensor(equipment_id)
    mask = (df["ts"] >= ev["start_ts"]) & (df["ts"] <= ev["end_ts"])
    w = df[mask]
    if w.empty:
        st.warning("No data in event window.")
        return

    def mini(title, cols):
        st.markdown(f"**{title}**")
        fig = go.Figure()
        for c in cols:
            if c in w.columns:
                fig.add_trace(go.Scatter(x=w["ts"], y=w[c], name=c))
        fig.update_layout(template="plotly_white", height=300, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        mini("Vibration & Acoustic", ["VIB_X_MM_S", "VIB_Y_MM_S", "ACOUSTIC_DB"])
    with c2:
        mini("Bearing & Ambient", ["BEARING_TEMP_C", "AMBIENT_TEMP_C"])
    c3, c4 = st.columns(2)
    with c3:
        mini("Coolant loop", ["COOLANT_FLOW_LPM", "COOLANT_PRESSURE_BAR"])
    with c4:
        mini("Motor & Load", ["MOTOR_CURRENT_A", "SPINDLE_LOAD_PCT"])


def render_label_bank():
    st.subheader("Label Bank")
    events = load_events("cnc01_baseline")
    if events.empty:
        st.info("No events to label. Run detection for CNC-01.")
        return

    seed_bank_path = PROCESSED / "seed_label_bank.json"
    seed_labels_path = PROCESSED / "seed_labels.json"
    session_bank_path = PROCESSED / "session_label_bank.json"
    session_labels_path = PROCESSED / "session_labels.json"

    st.markdown("**Pre-seeded bank**")
    seed_bank = json.loads(seed_bank_path.read_text()) if seed_bank_path.exists() else []
    seed_labels = json.loads(seed_labels_path.read_text()) if seed_labels_path.exists() else []
    for row in seed_bank:
        st.caption(f"{row['label_id']} ({row['signal']}) — promoted {row['promoted_at']}")

    st.markdown("---")
    st.markdown("**Label an event**")
    ev_id = st.selectbox("Select event", events["event_id"], key="lb_event")
    ev = events[events["event_id"] == ev_id].iloc[0]
    st.write(ev.to_dict())

    with st.form("label_form"):
        label_type = st.selectbox("Decision", ["confirmed_anomaly", "confirmed_normal", "dismissed"], key="lb_type")
        confidence = st.slider("Confidence", 0.0, 1.0, 0.9, key="lb_conf")
        root_cause = st.selectbox("Root cause", ["Mechanical", "Process/Utility", "Instrumentation"], key="lb_root")
        note = st.text_area("Note", key="lb_note")
        promote = st.checkbox("Promote to Label Bank", value=False, key="lb_promote")
        submitted = st.form_submit_button("Save label")

    if submitted:
        can_promote = promote and (root_cause != "Instrumentation")
        record = {
            "label_id": str(uuid.uuid4()),
            "equipment_id": ev["equipment_id"],
            "signal": ev["signals"][0] if ev["signals"] else "ALL",
            "start_ts": str(ev["start_ts"]),
            "end_ts": str(ev["end_ts"]),
            "label_type": label_type,
            "confidence": float(confidence),
            "root_cause_category": root_cause,
            "note": note,
            "author": "session" if OFFLINE else "jirawut",
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_label_offline(record, can_promote)
        if not OFFLINE:
            save_label_trino(record, can_promote)
        if promote and root_cause == "Instrumentation":
            st.warning("Instrumentation labels cannot be promoted to the Label Bank.")
        st.success("Label saved")

    if session_labels_path.exists():
        st.markdown("**Session labels**")
        st.json(json.loads(session_labels_path.read_text()))


def render_fleet():
    st.subheader("Fleet — CNC-02 seeded vs unseeded")
    seeded_events = load_events("cnc02_seeded")
    unseeded_events = load_events("cnc02_unseeded")
    seeded_scores = load_scores("cnc02_seeded")
    unseeded_scores = load_scores("cnc02_unseeded")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Seeded**")
        if not seeded_events.empty:
            first = seeded_events["start_ts"].min()
            smooth = len(seeded_events[seeded_events["signature"] == "smooth"])
            imp = len(seeded_events[seeded_events["signature"] == "impulsive"])
            st.metric("First event", str(first))
            st.metric("Smooth / Impulsive", f"{smooth} / {imp}")
            st.dataframe(seeded_events[["start_ts", "end_ts", "severity", "signature", "signals"]], use_container_width=True)
        else:
            st.info("No seeded output. Run make demo-setup.")
    with c2:
        st.markdown("**Unseeded**")
        if not unseeded_events.empty:
            first = unseeded_events["start_ts"].min()
            smooth = len(unseeded_events[unseeded_events["signature"] == "smooth"])
            imp = len(unseeded_events[unseeded_events["signature"] == "impulsive"])
            st.metric("First event", str(first))
            st.metric("Smooth / Impulsive", f"{smooth} / {imp}")
            st.dataframe(unseeded_events[["start_ts", "end_ts", "severity", "signature", "signals"]], use_container_width=True)
        else:
            st.info("No unseeded output. Run make demo-setup.")

    if not seeded_scores.empty and not unseeded_scores.empty:
        s = seeded_scores[(seeded_scores["signal"] == "VIB_X_MM_S") & (seeded_scores["is_anomaly"] == True)]["ts"].min()
        u = unseeded_scores[(unseeded_scores["signal"] == "VIB_X_MM_S") & (unseeded_scores["is_anomaly"] == True)]["ts"].min()
        st.markdown(f"**First VIB_X flag:** seeded `{s}` — unseeded `{u}`")


def render_ask_ai():
    st.subheader("Ask AI — scripted NL-to-SQL examples")
    st.info("Use the Devin Ask panel with the AIDP Analytics MCP Server; this tab shows the intended SQL and answers.")
    questions = [
        {
            "q": "Which machine shows vibration behaviour most like the CNC-01 bearing failure, and when did it start?",
            "sql": """SELECT equipment_id, min(ts) AS first_flag FROM js_manuf_ice.smart_mfg.anomaly_scores WHERE signal IN ('VIB_X_MM_S', 'VIB_Y_MM_S') AND is_anomaly AND detector = 'zscore' GROUP BY equipment_id ORDER BY first_flag;""",
            "answer": "CNC-02 shows the closest smooth vibration rise. The seeded run flags VIB_X first around 2024-04-12, several days earlier than the unseeded run, thanks to the CNC-01 bearing-wear profile in the Label Bank.",
            "citations": ["knowledge/spindle_bearing_wear.md", "knowledge/imbalance_runout.md"],
        },
        {
            "q": "CNC-02's vibration rises smoothly with no impulsive spikes. What failure mode does that suggest, and how urgent is it compared with CNC-01?",
            "sql": """SELECT run_id, signature, min(start_ts), count(*) FROM js_manuf_ice.smart_mfg.anomaly_events WHERE equipment_id = 'CNC-02' GROUP BY run_id, signature;""",
            "answer": "A smooth, progressive rise without impulsive peaks points to imbalance, toolholder runout or alignment rather than a spalled bearing. Urgency is lower than the impulsive CNC-01 bearing fault, but the rise should be addressed before it becomes a secondary bearing wear. Check tool concentricity, balance and recent tool changes.",
            "citations": ["knowledge/imbalance_runout.md", "knowledge/vibration_severity_zones.md"],
        },
        {
            "q": "How many days of warning did we have before the CNC-01 bearing replacement?",
            "sql": """SELECT min(ts) FROM js_manuf_ice.smart_mfg.anomaly_scores WHERE equipment_id = 'CNC-01' AND signal = 'VIB_X_MM_S' AND is_anomaly AND detector = 'zscore';""",
            "answer": "The first rolling 6-hour VIB_X warning appeared at 2024-01-17 12:00. The bearing was replaced on 2024-02-06. That is about 20 days of early warning.",
            "citations": ["knowledge/cnc01_maintenance_log.md"],
        },
    ]
    for item in questions:
        with st.expander(item["q"]):
            st.markdown(f"**SQL:** `{item['sql']}`")
            st.markdown(f"**Answer:** {item['answer']}")
            st.markdown(f"**Citations:** {', '.join(item['citations'])}")


def main():
    render_header()

    with st.sidebar:
        st.markdown("### Demo controls")
        st.caption(f"OFFLINE_MODE={'1' if OFFLINE else '0'}")
        if st.button("Reset demo", type="secondary"):
            with st.spinner("Resetting..."):
                reset_demo()
            st.success("Demo reset. Rerun to refresh.")
        st.markdown("---")
        st.markdown("**Shortcuts**")
        st.markdown("- `make demo-setup` — full setup")
        st.markdown("- `make demo-reset` — reset")
        st.markdown("- `make test` — pytest")
        st.markdown("- `streamlit run app/dashboard.py`")

    tabs = st.tabs(["Overview", "Detect", "Investigate", "Label Bank", "Fleet", "Ask AI"])
    with tabs[0]:
        render_overview()
    with tabs[1]:
        render_detect()
    with tabs[2]:
        render_investigate()
    with tabs[3]:
        render_label_bank()
    with tabs[4]:
        render_fleet()
    with tabs[5]:
        render_ask_ai()


if __name__ == "__main__":
    main()
