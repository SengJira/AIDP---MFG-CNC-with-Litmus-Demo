import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DELL_BLUE = "#0076CE"
DELL_NAVY = "#00447C"

st.set_page_config(page_title="Spindle to Customer | Dell AIDP", layout="wide")

OFFLINE = os.environ.get("OFFLINE_MODE") == "1"


def trino_query(sql):
    if OFFLINE:
        raise RuntimeError("OFFLINE_MODE: no live Trino calls")
    import trino
    from trino.auth import BasicAuthentication
    conn = trino.dbapi.connect(
        host=os.environ["TRINO_HOST"],
        port=int(os.environ.get("TRINO_PORT", 443)),
        http_scheme="https",
        auth=BasicAuthentication(os.environ["TRINO_USER"], os.environ["TRINO_PASS"]),
        verify=False,
    )
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)


def load_table(fqn, cache_file, fallback_query=None):
    if OFFLINE:
        return pd.read_parquet(f"cache/{cache_file}")
    query = fallback_query or f"SELECT * FROM {fqn}"
    return trino_query(query)


@st.cache_data(ttl=30)
def source_counts():
    if OFFLINE:
        with open("cache/source_counts.json") as f:
            return json.load(f)
    sources = {
        "OT Historian": ("js_manuf_ice.cnc_historian.sensor_readings", "Iceberg"),
        "QA CMM": ("js_manuf_ice.cnc_qa.cmm_inspections", "Iceberg"),
        "QA NCR": ("js_manuf_ice.cnc_qa.ncr", "Iceberg"),
        "QA Complaints": ("js_manuf_ice.cnc_qa.customer_complaints", "Iceberg"),
        "CMMS Assets": ("js_manuf_ice.cnc_cmms.assets", "Iceberg"),
        "CMMS Work Orders": ("js_manuf_ice.cnc_cmms.work_orders", "Iceberg"),
        "MES Orders": ("js_mysql_mfg.js_mysql_mfg.cnc_mes_production_orders", "MySQL"),
        "MES Lots": ("js_mysql_mfg.js_mysql_mfg.cnc_mes_production_lots", "MySQL"),
        "MES Downtime": ("js_mysql_mfg.js_mysql_mfg.cnc_mes_downtime_events", "MySQL"),
        "MES Material Consumption": ("js_mysql_mfg.js_mysql_mfg.cnc_mes_material_consumption", "MySQL"),
        "ERP Customers": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_customers", "MySQL"),
        "ERP Materials": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_materials", "MySQL"),
        "ERP Sales": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_sales_orders", "MySQL"),
        "ERP POs": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_purchase_orders", "MySQL"),
        "ERP Stock": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_spare_parts_stock", "MySQL"),
        "ERP Rates": ("js_mysql_mfg.js_mysql_mfg.cnc_erp_cost_rates", "MySQL"),
        "SQM Suppliers": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_suppliers", "MySQL"),
        "SQM Approved Sources": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_approved_sources", "MySQL"),
        "SQM Material Specs": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_specs", "MySQL"),
        "SQM Material Lots": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_lots", "MySQL"),
        "SQM CoAs": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis", "MySQL"),
        "SQM Inspections": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections", "MySQL"),
        "SQM SCARs": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_scar", "MySQL"),
        "SQM Scorecard": ("js_mysql_mfg.js_mysql_mfg.cnc_sqm_supplier_scorecard", "MySQL"),
    }
    counts = {name: (fqn, store, trino_query(f"SELECT count(*) FROM {fqn}").iloc[0, 0]) for name, (fqn, store) in sources.items()}
    # Elasticsearch counts
    if not OFFLINE:
        from elasticsearch import Elasticsearch
        es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"], verify_certs=False, ssl_show_warn=False)
        counts["Logbook"] = ("cnc-demo-shift-logbook", "Elasticsearch", es.count(index="cnc-demo-shift-logbook")["count"])
        counts["Supplier Docs"] = ("cnc-demo-supplier-docs", "Elasticsearch", es.count(index="cnc-demo-supplier-docs")["count"])
    return counts


@st.cache_data(ttl=30)
def daily_360():
    return load_table("js_manuf_ice.cnc_analytics.cnc_daily_360", "cnc_daily_360.parquet")


@st.cache_data(ttl=30)
def event_cost():
    return load_table("js_manuf_ice.cnc_analytics.event_cost", "event_cost.parquet")


@st.cache_data(ttl=30)
def order_risk():
    return load_table("js_manuf_ice.cnc_analytics.order_risk", "order_risk.parquet")


@st.cache_data(ttl=30)
def supplier_vibration_summary():
    return load_table("js_manuf_ice.cnc_analytics.supplier_vibration_summary", "supplier_vibration_summary.parquet")


@st.cache_data(ttl=30)
def supplier_lot_impact():
    return load_table("js_manuf_ice.cnc_analytics.supplier_lot_impact", "supplier_lot_impact.parquet")


@st.cache_data(ttl=30)
def lot_context():
    return load_table("js_manuf_ice.cnc_analytics.lot_context", "lot_context.parquet")


@st.cache_data(ttl=30)
def sqm_scorecard():
    return load_table("js_mysql_mfg.js_mysql_mfg.cnc_sqm_supplier_scorecard", "sqm_scorecard.parquet")


@st.cache_data(ttl=30)
def sqm_material_lots():
    return load_table("js_mysql_mfg.js_mysql_mfg.cnc_sqm_material_lots", "sqm_material_lots.parquet")


@st.cache_data(ttl=30)
def sqm_certificates():
    return load_table("js_mysql_mfg.js_mysql_mfg.cnc_sqm_certificates_of_analysis", "sqm_certificates.parquet")


@st.cache_data(ttl=30)
def sqm_incoming_inspections():
    return load_table("js_mysql_mfg.js_mysql_mfg.cnc_sqm_incoming_inspections", "sqm_incoming_inspections.parquet")


@st.cache_data(ttl=30)
def scar():
    return load_table("js_mysql_mfg.js_mysql_mfg.cnc_sqm_scar", "sqm_scar.parquet")


def es_supplier_doc(material_lot_id):
    from elasticsearch import Elasticsearch
    es = Elasticsearch(os.environ["ELASTIC_ENDPOINT"], api_key=os.environ["ELASTIC_API_KEY"], verify_certs=False, ssl_show_warn=False)
    res = es.search(index="cnc-demo-supplier-docs", body={"query": {"term": {"material_lot_id.keyword": material_lot_id}}})
    hits = res["hits"]["hits"]
    return hits[0]["_source"]["text"] if hits else None


def title(text):
    st.markdown(f"<h1 style='color:{DELL_NAVY};font-size:2.4rem;font-weight:700;'>{text}</h1>", unsafe_allow_html=True)


def badge(text):
    st.markdown(f"<div style='display:inline-block;background:{DELL_BLUE};color:white;padding:6px 14px;border-radius:20px;font-size:1.1rem;'>{text}</div>", unsafe_allow_html=True)


def reset_demo():
    # Delegated to the idempotent v2 loader and analytics rebuild.
    os.system("python3 jobs/ingest_raw.py --pack data/multisource_v2 --no-s3 && python3 scripts/create_analytics_views.py")
    st.success("Demo reset triggered. Refresh the page.")


def tab_sources():
    title("Sources")
    counts = source_counts()
    grouped = {
        "OT Historian": [("Sensor readings", counts["OT Historian"][0], counts["OT Historian"][1], counts["OT Historian"][2])],
        "QA": [
            ("CMM inspections", counts["QA CMM"][0], counts["QA CMM"][1], counts["QA CMM"][2]),
            ("NCRs", counts["QA NCR"][0], counts["QA NCR"][1], counts["QA NCR"][2]),
            ("Customer complaints", counts["QA Complaints"][0], counts["QA Complaints"][1], counts["QA Complaints"][2]),
        ],
        "CMMS": [
            ("Assets", counts["CMMS Assets"][0], counts["CMMS Assets"][1], counts["CMMS Assets"][2]),
            ("Work orders", counts["CMMS Work Orders"][0], counts["CMMS Work Orders"][1], counts["CMMS Work Orders"][2]),
        ],
        "MES": [
            ("Production orders", counts["MES Orders"][0], counts["MES Orders"][1], counts["MES Orders"][2]),
            ("Production lots", counts["MES Lots"][0], counts["MES Lots"][1], counts["MES Lots"][2]),
            ("Downtime events", counts["MES Downtime"][0], counts["MES Downtime"][1], counts["MES Downtime"][2]),
            ("Material consumption", counts["MES Material Consumption"][0], counts["MES Material Consumption"][1], counts["MES Material Consumption"][2]),
        ],
        "ERP": [
            ("Customers", counts["ERP Customers"][0], counts["ERP Customers"][1], counts["ERP Customers"][2]),
            ("Materials", counts["ERP Materials"][0], counts["ERP Materials"][1], counts["ERP Materials"][2]),
            ("Sales orders", counts["ERP Sales"][0], counts["ERP Sales"][1], counts["ERP Sales"][2]),
            ("Purchase orders", counts["ERP POs"][0], counts["ERP POs"][1], counts["ERP POs"][2]),
            ("Spare parts stock", counts["ERP Stock"][0], counts["ERP Stock"][1], counts["ERP Stock"][2]),
            ("Cost rates", counts["ERP Rates"][0], counts["ERP Rates"][1], counts["ERP Rates"][2]),
        ],
        "SQM": [
            ("Suppliers", counts["SQM Suppliers"][0], counts["SQM Suppliers"][1], counts["SQM Suppliers"][2]),
            ("Approved sources", counts["SQM Approved Sources"][0], counts["SQM Approved Sources"][1], counts["SQM Approved Sources"][2]),
            ("Material specs", counts["SQM Material Specs"][0], counts["SQM Material Specs"][1], counts["SQM Material Specs"][2]),
            ("Material lots", counts["SQM Material Lots"][0], counts["SQM Material Lots"][1], counts["SQM Material Lots"][2]),
            ("CoAs", counts["SQM CoAs"][0], counts["SQM CoAs"][1], counts["SQM CoAs"][2]),
            ("Inspections", counts["SQM Inspections"][0], counts["SQM Inspections"][1], counts["SQM Inspections"][2]),
            ("SCARs", counts["SQM SCARs"][0], counts["SQM SCARs"][1], counts["SQM SCARs"][2]),
            ("Scorecards", counts["SQM Scorecard"][0], counts["SQM Scorecard"][1], counts["SQM Scorecard"][2]),
            ("Supplier docs", counts["Supplier Docs"][0], counts["Supplier Docs"][1], counts["Supplier Docs"][2]),
        ],
    }
    cols = st.columns(len(grouped))
    for col, (system, tables) in zip(cols, grouped.items()):
        with col:
            st.markdown(f"<h3 style='color:{DELL_BLUE};'>{system}</h3>", unsafe_allow_html=True)
            for tname, fqn, store, cnt in tables:
                st.metric(tname, f"{cnt:,}")
                st.caption(f"{store} — `{fqn}`")


def tab_360():
    title("360° View")
    df = daily_360()
    if "machine_id" in df.columns:
        machines = sorted(df["machine_id"].unique())
    else:
        machines = sorted(df["equipment_id"].unique())
    machine = st.selectbox("Machine", machines)
    d = df[df["machine_id" if "machine_id" in df.columns else "equipment_id"] == machine].copy()
    d["day"] = pd.to_datetime(d["day"])
    d = d.sort_values("day")

    fig = make_subplots(specs=[[{"secondary_y": True}]], subplot_titles=[f"Daily 360 — {machine}"])
    fig.add_trace(
        go.Scatter(x=d["day"], y=d["avg_vib_x"], name="VIB_X mm/s", mode="lines+markers",
                   line=dict(color=DELL_BLUE, width=3), marker=dict(size=6)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(x=d["day"], y=d["scrap"], name="scrap parts", marker_color="#ff6b6b", opacity=0.5, width=24*60*60*1000),
        secondary_y=True,
    )
    ncr = d[d["ncr_count"] > 0]
    for day in ncr["day"]:
        fig.add_vline(x=day, line_color="red", line_dash="dash", line_width=1, opacity=0.6)
    fig.add_trace(
        go.Scatter(x=[None], y=[None], mode="lines", line=dict(color="red", dash="dash", width=1), name="NCR opened"),
        secondary_y=False,
    )
    fig.update_layout(
        height=650,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
        xaxis=dict(tickangle=-45, tickformat="%b %d", dtick=7*24*60*60*1000),
    )
    fig.update_yaxes(title_text="VIB_X mm/s", autorange=True, rangemode="normal", secondary_y=False)
    fig.update_yaxes(title_text="scrap parts", autorange=True, rangemode="tozero", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(d.sort_values("day"), use_container_width=True)


def tab_genealogy():
    title("Lot Genealogy — Material & Supplier to Machine")
    df = lot_context()
    if df.empty:
        st.warning("No lot context data available.")
        return

    machines = sorted(df["machine_id"].dropna().unique())
    machine = st.selectbox("Machine", ["All"] + list(machines))
    d = df[df["machine_id"] == machine] if machine != "All" else df

    chart = d[d["avg_vib_x"].notna()].copy()
    if not chart.empty and "start_ts" in chart.columns:
        fig = px.scatter(
            chart,
            x="start_ts",
            y="avg_vib_x",
            color="main_supplier_id",
            size="qty_produced",
            hover_data=["lot_id", "material_id", "main_material_lot_id", "raw_material_id", "qty_scrap", "scrap_usd"],
            title=f"Vibration by supplier lot ({machine})",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig.update_layout(template="plotly_white", height=500)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"<h3 style='color:{DELL_NAVY};'>MES lots and the supplier material they consumed</h3>", unsafe_allow_html=True)
    cols = ["lot_id", "machine_id", "shift_date", "material_id", "main_material_lot_id",
            "main_supplier_id", "raw_material_id", "qty_produced", "qty_scrap",
            "avg_vib_x", "scrap_usd", "ncr_id", "start_ts"]
    present = [c for c in cols if c in d.columns]
    if "start_ts" in d.columns:
        d = d.sort_values("start_ts")
    st.dataframe(d[present], use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("Lots by supplier")
        st.dataframe(
            d.groupby("main_supplier_id")["lot_id"].count().reset_index(name="lot_count").sort_values("lot_count", ascending=False),
            use_container_width=True,
        )
    with c2:
        st.markdown("Mean VIB_X by supplier")
        st.dataframe(
            d.groupby("main_supplier_id")["avg_vib_x"].mean().reset_index(name="avg_vib_x").sort_values("avg_vib_x", ascending=False),
            use_container_width=True,
        )


def tab_supplier():
    title("Supplier Quality")
    # 1. Vibration summary chart
    vib = supplier_vibration_summary()
    if vib.empty:
        st.warning("No supplier vibration summary available.")
        return
    fig = px.bar(vib, x="period", y="avg_vib_x", color="main_supplier_id", barmode="group",
                 facet_col="machine_id", facet_col_wrap=2,
                 labels={"avg_vib_x": "mean VIB_X mm/s", "period": "period", "main_supplier_id": "supplier"},
                 color_discrete_sequence=[DELL_BLUE, "#ff6b6b", "#2ecc71", "#f1c40f"])
    for ann in fig.layout.annotations:
        ann.text = ann.text.split("=")[-1]
    fig.update_layout(height=450, template="plotly_white",
                      legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"<h3 style='color:{DELL_NAVY};'>Claimed vs measured hardness</h3>", unsafe_allow_html=True)
        cert = sqm_certificates()
        insp = sqm_incoming_inspections()
        if not cert.empty and not insp.empty:
            # only material lots with hardness CoA and hardness inspections
            hard = insp[(insp["characteristic"].str.upper().str.contains("HARDNESS")) | (insp["characteristic"].str.upper() == "HARDNESS_HB")]
            hard_agg = hard.groupby("material_lot_id").agg(
                measured_min=("measured", "min"),
                measured_max=("measured", "max"),
                skipped=("result", lambda x: (x == "SKIPPED").any()),
            ).reset_index()
            merged = cert.drop(columns=["supplier_id"], errors="ignore").merge(hard_agg, on="material_lot_id", how="inner")
            merged = merged.merge(sqm_material_lots()[["material_lot_id", "supplier_id", "material_id"]], on="material_lot_id", how="left")
            merged = merged[["material_lot_id", "supplier_id", "material_id", "hardness_hb_claimed", "measured_min", "measured_max", "skipped"]]
            merged = merged.sort_values("measured_max", ascending=False)
            def highlight_skipped(row):
                return ["background-color: #ffe6e6" if row["skipped"] else "" for _ in row]
            st.dataframe(merged.style.apply(highlight_skipped, axis=1), use_container_width=True)

    with c2:
        st.markdown(f"<h3 style='color:{DELL_NAVY};'>SCAR-24-003</h3>", unsafe_allow_html=True)
        s = scar()
        if not s.empty:
            row = s.iloc[0]
            st.markdown(f"**Supplier:** {row['supplier_id']}")
            st.markdown(f"**Problem:** {row['problem']}")
            st.markdown(f"**8D root cause:** {row['root_cause_8d']}")
            st.markdown(f"**Claim:** USD {row['cost_claim_usd']:,.2f}")
        st.markdown(f"<h3 style='color:{DELL_NAVY};'>Supplier scorecard</h3>", unsafe_allow_html=True)
        st.dataframe(sqm_scorecard(), use_container_width=True)

    st.markdown(f"<h3 style='color:{DELL_NAVY};'>Lot drill-down</h3>", unsafe_allow_html=True)
    lots = supplier_lot_impact()
    if not lots.empty:
        selected = st.selectbox("Select a supplier material lot", lots["material_lot_id"].unique(), key="supplier_lot_select")
        lot = lots[lots["material_lot_id"] == selected].iloc[0]
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(f"**Supplier:** {lot['supplier_id']}")
            st.markdown(f"**Material:** {lot['material_id']}")
            st.markdown(f"**MES lots consumed:** {lot['mes_lots']}")
            st.markdown(f"**Machines:** {lot['machines']}")
            st.markdown(f"**Claimed hardness HB:** {lot['hardness_hb_claimed']}")
            st.markdown(f"**Measured hardness HB:** {lot['measured_hardness_min']:.0f}–{lot['measured_hardness_max']:.0f}")
            st.markdown(f"**Balance grade claimed:** {lot['balance_grade_claimed']}")
            st.markdown(f"**SKIPPED inspection:** {bool(lot['inspection_skipped'])}")
        with c2:
            text = es_supplier_doc(selected)
            if text:
                st.markdown("**Certificate text**")
                st.markdown(text)
            else:
                st.write("No certificate text found.")


def tab_impact():
    title("Impact & Cost")
    df = event_cost()
    c1, c2, c3 = st.columns(3)
    avoid = df[df["avoidable_with_early_warning"] == True]["cost_usd"].sum()
    c1.metric("Avoidable bearing cost", f"${avoid:,.2f}")
    c2.metric("Roundness scrap", int(df[df["cost_type"].str.contains("roundness", case=False, na=False)]["parts"].sum()))
    c3.metric("Bore scrap", int(df[df["cost_type"].str.contains("bore", case=False, na=False)]["parts"].sum()))
    st.dataframe(df, use_container_width=True)
    st.markdown(f"<h3 style='color:{DELL_NAVY};'>CNC-01 Cross-Source Timeline</h3>", unsafe_allow_html=True)
    timeline = [
        ("2024-01-12", "SQM", "SUP-B lots released on CoA"),
        ("2024-01-15", "SQM", "SUP-B castings issued to CNC-01"),
        ("2024-01-17 12:00", "Historian", "VIB_X first exceeds baseline + 3σ"),
        ("2024-01-19 23:40", "Logbook", "LB-00208: faint high-pitched whine"),
        ("2024-01-24 15:20", "Logbook", "LB-00209: whine louder, told maintenance"),
        ("2024-01-28 B", "QA", "NCR-24-0001 first roundness reject"),
        ("2024-01-30", "CMMS", "WO-24-0117 raised"),
        ("2024-02-03", "SQM", "Hardness audit, SCAR-24-003 opened"),
        ("2024-02-05 22:00", "MES", "8-hour bearing stop, SPINDLE_RPM = 0"),
        ("2024-02-15", "SQM", "SCAR-24-003 closed"),
        ("2024-02-20", "ERP", "SO-45012 ships 5 days late, penalty $1,920"),
        ("2024-02-24", "QA", "CC-24-001 complaint: 20 escaped parts"),
        ("2024-03-24", "SQM", "SUP-B trial lots return"),
        ("2024-04-08", "SQM", "Toolholder TH-0007 received"),
    ]
    for ts, lane, note in timeline:
        col1, col2 = st.columns([1, 4])
        col1.markdown(f"**{lane}**")
        col2.markdown(f"{ts} — {note}")
    st.markdown("---")
    st.markdown(f"<h4 style='color:{DELL_BLUE};'>Control case: motor-current drift (20–25 Feb)</h4>", unsafe_allow_html=True)
    st.write("CNC-01 had a motor-current alarm but zero NCRs and zero scrap. WO-24-0166 traced it to a failed cabinet fan and transmitter drift.")


def tab_ask():
    title("Ask AI")
    questions = {
        "Why did SO-45012 ship late, and what did it cost?": "q1_so45012",
        "When did any system first show the CNC-01 bearing problem?": "q2_first_bearing",
        "Was the motor-current alarm on 20–25 Feb a real problem?": "q3_motor_drift",
        "Should we stop CNC-02 for 8 hours this week, and will SO-45060 still ship on time?": "q4_cnc02_stop",
        "Is a supplier material linked to the CNC-01 vibration?": "q5_supplier_b",
        "Are CNC-02's new steel billets from SUP-E causing its vibration?": "q6_cnc02_steel",
    }
    for q, fname in questions.items():
        if st.button(q, use_container_width=True):
            with open(f"cache/ask_ai/{fname}.json") as f:
                data = json.load(f)
            st.markdown(f"<h4 style='color:{DELL_NAVY};'>{data['question']}</h4>", unsafe_allow_html=True)
            st.write(data["answer"])
            with st.expander("SQL & citations"):
                for i, sql in enumerate(data["sql"]):
                    st.code(sql, language="sql")
                st.write("MCP query IDs:", ", ".join(data["mcp_query_ids"]))
                for c in data["citations"]:
                    st.write(f"- {c['type']}: `{c['id']}`")


def main():
    st.sidebar.image("https://www.dell.com/_astro/logo.dell.4d3b0.svg", width=120)
    st.sidebar.title("Spindle to Customer")
    if OFFLINE:
        st.sidebar.warning("OFFLINE MODE: cached data only")
    badge("synthetic data")
    st.sidebar.markdown("---")
    if st.sidebar.button("Reset demo"):
        reset_demo()
    tab = st.sidebar.radio("Tab", ["Sources", "360°", "Genealogy", "Supplier", "Impact", "Ask AI"])
    if tab == "Sources":
        tab_sources()
    elif tab == "360°":
        tab_360()
    elif tab == "Genealogy":
        tab_genealogy()
    elif tab == "Supplier":
        tab_supplier()
    elif tab == "Impact":
        tab_impact()
    else:
        tab_ask()


if __name__ == "__main__":
    main()
