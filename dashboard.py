"""
dashboard.py — Marasoft KPI Dashboard
Lancement (base réelle) : streamlit run dashboard.py
Lancement (mock)        : streamlit run dashboard.py -- --mock
"""

import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

MOCK_MODE = "--mock" in sys.argv

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Marasoft KPI",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* App background — crème */
    .stApp { background-color: #F4F1EC; }

    /* Main content padding */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

    /* Gros titres — vert foncé Atlantis */
    h1, h2, h3 { color: #3D6657 !important; }

    /* Metric cards Streamlit (sections certificats etc.) */
    div[data-testid="stMetric"] {
        background: #ffffff;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    div[data-testid="stMetricValue"] { font-size: 1.6rem !important; }

    /* Dataframe */
    [data-testid="stDataFrame"] { border-radius: 6px; }

    /* Tables HTML inline */
    table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
    th { background: #3D6657; color: #F4F1EC; padding: 6px 10px; text-align: left; }
    td { padding: 5px 10px; border-bottom: 1px solid #e0dbd2; background-color: #F4F1EC; }
    tr:hover td { background: #eae6df; }
</style>
""", unsafe_allow_html=True)


# ─── Données ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data():
    if MOCK_MODE:
        return _mock_data()
    return _pg_data()


def _pg_data():
    from sqlalchemy import create_engine, text
    url = os.environ.get("DATABASE_URL", "postgresql://marasoft_etl:password@localhost:5432/marasoft_kpi")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        kpi     = pd.read_sql(text("SELECT * FROM mv_kpi_vessel_daily ORDER BY vessel_name"), conn)
        certs   = pd.read_sql(text("""
            SELECT c.*, v.name AS vessel_name
            FROM certificates c JOIN vessels v USING (vessel_id)
            ORDER BY c.expires_at ASC NULLS LAST
        """), conn)
        jobs    = pd.read_sql(text("""
            SELECT mj.*, v.name AS vessel_name
            FROM maintenance_jobs mj JOIN vessels v USING (vessel_id)
            WHERE mj.status != 'done'
            ORDER BY mj.due_date ASC NULLS LAST
        """), conn)
        hours   = pd.read_sql(text("""
            SELECT rhs.vessel_id, v.name AS vessel_name,
                   comp.name AS component_name,
                   rhs.recorded_at, rhs.hours_value, rhs.delta_hours
            FROM running_hours_snapshots rhs
            JOIN vessels v USING (vessel_id)
            JOIN components comp ON comp.component_id = rhs.component_id
            ORDER BY rhs.recorded_at DESC
        """), conn)
        violations = pd.read_sql(text("""
            SELECT rhv.*, cm.first_name || ' ' || cm.last_name AS crew_name,
                   cm.rank, v.name AS vessel_name
            FROM rest_hours_violations rhv
            JOIN crew_members cm ON cm.crew_member_id = rhv.crew_member_id
            JOIN vessels v ON v.vessel_id = cm.vessel_id
            WHERE rhv.period_date >= CURRENT_DATE - 30
            ORDER BY rhv.period_date DESC
        """), conn)
        parts   = pd.read_sql(text("""
            SELECT p.*, v.name AS vessel_name
            FROM parts p JOIN vessels v USING (vessel_id)
            WHERE p.below_minimum
            ORDER BY p.quantity ASC
        """), conn)
        qhse    = pd.read_sql(text("""
            SELECT qr.*, v.name AS vessel_name
            FROM qhse_reports qr JOIN vessels v USING (vessel_id)
            WHERE qr.status != 'closed'
            ORDER BY qr.due_date ASC NULLS LAST
        """), conn)
    return dict(kpi=kpi, certs=certs, jobs=jobs, hours=hours,
                violations=violations, parts=parts, qhse=qhse)


def _mock_data():
    today = date.today()

    kpi = pd.DataFrame([
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", kpi_date=today,
             engine_hours_total=15660.5, engine_hours_last_7d=23.5,
             jobs_open=1, jobs_overdue=1,
             certs_valid=1, certs_expiring_30d=0, certs_expiring_7d=1, certs_expired=0,
             rest_violations_30d=2, crew_onboard=3, parts_below_min=2, qhse_open=1, qhse_overdue=1),
        dict(vessel_id="V002", vessel_name="Nordic Star", kpi_date=today,
             engine_hours_total=8800.0, engine_hours_last_7d=0.0,
             jobs_open=0, jobs_overdue=0,
             certs_valid=0, certs_expiring_30d=0, certs_expiring_7d=0, certs_expired=1,
             rest_violations_30d=0, crew_onboard=1, parts_below_min=0, qhse_open=0, qhse_overdue=0),
    ])

    certs = pd.DataFrame([
        dict(cert_id="CERT001", vessel_id="V001", vessel_name="Atlantic Pioneer",
             cert_type="SOLAS", cert_name="Safety Certificate",
             issued_at=date(2024,1,1), expires_at=date(2026,6,5),
             status="critical", days_until_expiry=(date(2026,6,5)-today).days),
        dict(cert_id="CERT002", vessel_id="V001", vessel_name="Atlantic Pioneer",
             cert_type="MARPOL", cert_name="Oil Record Book",
             issued_at=date(2023,6,1), expires_at=date(2027,6,1),
             status="valid", days_until_expiry=(date(2027,6,1)-today).days),
        dict(cert_id="CERT003", vessel_id="V002", vessel_name="Nordic Star",
             cert_type="MLC", cert_name="MLC Certificate",
             issued_at=date(2022,1,1), expires_at=date(2026,5,10),
             status="expired", days_until_expiry=(date(2026,5,10)-today).days),
    ])

    jobs = pd.DataFrame([
        dict(job_id="J001", vessel_id="V001", vessel_name="Atlantic Pioneer",
             job_name="Oil change", status="open", due_date=date(2026,6,15),
             maintenance_type="preventive", component_id="C001"),
        dict(job_id="J002", vessel_id="V001", vessel_name="Atlantic Pioneer",
             job_name="Filter check", status="overdue", due_date=date(2026,4,1),
             maintenance_type="preventive", component_id="C002"),
    ])

    hours = pd.DataFrame([
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Main Engine",
             recorded_at=datetime(2026,5,28,8,0), hours_value=12450.5, delta_hours=None),
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Main Engine",
             recorded_at=datetime(2026,5,29,8,0), hours_value=12474.0, delta_hours=23.5),
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Aux Generator",
             recorded_at=datetime(2026,5,28,8,0), hours_value=3210.0, delta_hours=None),
        dict(vessel_id="V002", vessel_name="Nordic Star",      component_name="Main Engine",
             recorded_at=datetime(2026,5,29,8,0), hours_value=8800.0, delta_hours=None),
    ])

    violations = pd.DataFrame([
        dict(crew_member_id="CM001", vessel_name="Atlantic Pioneer", crew_name="Erik Hansen",
             rank="Master", period_date=date(2026,5,28),
             rest_hours_actual=8.5, rest_hours_required=10.0, deficit_hours=1.5, severity="major"),
        dict(crew_member_id="CM002", vessel_name="Atlantic Pioneer", crew_name="Anna Lindqvist",
             rank="Chief Officer", period_date=date(2026,5,28),
             rest_hours_actual=9.0, rest_hours_required=10.0, deficit_hours=1.0, severity="minor"),
    ])

    parts = pd.DataFrame([
        dict(part_id="P002", vessel_id="V001", vessel_name="Atlantic Pioneer",
             part_name="Fuel Filter", part_number="FF-456",
             quantity=1, min_quantity=3, below_minimum=True, unit="pcs"),
        dict(part_id="P003", vessel_id="V001", vessel_name="Atlantic Pioneer",
             part_name="V-Belt", part_number="VB-789",
             quantity=0, min_quantity=2, below_minimum=True, unit="pcs"),
    ])

    qhse = pd.DataFrame([
        dict(report_id="Q001", vessel_id="V001", vessel_name="Atlantic Pioneer",
             report_type="Near Miss", title="Slippery deck incident",
             due_date=date(2026,6,10), status="open", priority="high", closed_at=None),
        dict(report_id="Q002", vessel_id="V001", vessel_name="Atlantic Pioneer",
             report_type="Inspection", title="PSC Inspection prep",
             due_date=date(2026,4,1), status="overdue", priority="critical", closed_at=None),
    ])

    return dict(kpi=kpi, certs=certs, jobs=jobs, hours=hours,
                violations=violations, parts=parts, qhse=qhse)


# ─── Helpers UI ──────────────────────────────────────────────────────────────

STATUS_COLORS = {
    "expired":      "#dc3545",
    "critical":     "#fd7e14",
    "expiring_soon":"#ffc107",
    "valid":        "#198754",
    "overdue":      "#dc3545",
    "open":         "#0d6efd",
    "due_soon":     "#ffc107",
    "done":         "#6c757d",
    "closed":       "#6c757d",
}

SEVERITY_COLORS = {"minor": "#ffc107", "major": "#fd7e14", "critical": "#dc3545"}

# Palette graphes Plotly (Atlantis touch)
PLOTLY_COLORS = ["#3D6657", "#C8AF82", "#2E5045", "#A08B5A", "#1E3530", "#D4C4A0"]

def _badge(text: str, color: str) -> str:
    return (f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.78rem;font-weight:600">{text}</span>')

def _status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6c757d")
    return _badge(status.replace("_", " ").upper(), color)


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/80/anchor.png", width=48)
    st.title("Marasoft KPI")
    if MOCK_MODE:
        st.info("Mode démo — données mockées", icon="🧪")
    st.markdown("---")

    data = load_data()
    vessels = ["Tous"] + sorted(data["kpi"]["vessel_name"].tolist())
    selected_vessel = st.selectbox("Navire", vessels)
    st.markdown("---")
    st.caption(f"Mis à jour : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    if not MOCK_MODE and st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()


# ─── Filtrage ─────────────────────────────────────────────────────────────────

def _filter(df: pd.DataFrame, col="vessel_name") -> pd.DataFrame:
    if selected_vessel == "Tous" or col not in df.columns:
        return df
    return df[df[col] == selected_vessel]


kpi_df   = _filter(data["kpi"])
certs_df = _filter(data["certs"])
jobs_df  = _filter(data["jobs"])
hours_df = _filter(data["hours"])
viol_df  = _filter(data["violations"])
parts_df = _filter(data["parts"])
qhse_df  = _filter(data["qhse"])


# ─── En-tête ─────────────────────────────────────────────────────────────────

st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0 4px 0">
    <div>
        <span style="font-size:1.8rem;font-weight:700;color:#3D6657">⚓ Dashboard KPI Flotte</span><br>
        <span style="font-size:0.85rem;color:#777">
            Flotte : <strong>{len(data['kpi'])} navires</strong> · Date KPI : {date.today().strftime('%d %B %Y')}
        </span>
    </div>
    <div style="display:flex;align-items:center;gap:20px">
        <img src="https://storage.googleapis.com/hostinger-horizons-assets-prod/d98c5fe9-b190-4a07-870f-677606696e62/d19a2551d7b59db361ce672d20503ff4.png"
             alt="Atlantis Software" style="height:44px;object-fit:contain">
        <img src="https://marad.com/wp-content/uploads/2025/06/marad-logo-full-colour.png"
             alt="Marad" style="height:36px;object-fit:contain">
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")


# ─── KPI Cards ───────────────────────────────────────────────────────────────

total_engine   = int(kpi_df["engine_hours_total"].sum())
jobs_overdue   = int(kpi_df["jobs_overdue"].sum())
certs_critical = int(kpi_df["certs_expiring_7d"].sum()) + int(kpi_df["certs_expired"].sum())
violations_30d = int(kpi_df["rest_violations_30d"].sum())
parts_alert    = int(kpi_df["parts_below_min"].sum())
qhse_overdue   = int(kpi_df["qhse_overdue"].sum())

def _kpi_card(col, icon: str, label: str, value, alert: bool = False, subtitle: str = ""):
    val_int = int(value) if str(value).replace(" ", "").isdigit() else 1
    border = "#dc3545" if alert and val_int > 0 else "#3D6657"
    sub_color = "#dc3545" if val_int > 0 else "#999"
    sub_text = subtitle if subtitle and val_int > 0 else ""
    val_str = str(value)
    font_size = "1.4rem" if len(val_str) >= 6 else "1.8rem"
    col.markdown(f"""
<div style="background:#fff;border-radius:8px;padding:12px 14px;
            box-shadow:0 1px 3px rgba(0,0,0,0.08);
            border-left:4px solid {border};
            min-height:110px;">
    <div style="font-size:0.79rem;color:#555;font-weight:600;line-height:1.3;margin-bottom:8px">{icon} {label}</div>
    <div style="font-size:{font_size};font-weight:700;color:#1E3530;line-height:1;margin-bottom:6px">{value}</div>
    <div style="font-size:0.73rem;color:{sub_color};min-height:1em">{sub_text}</div>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4, c5, c6 = st.columns(6)
_kpi_card(c1, "⚙️", "Heures moteur",       f"{total_engine:,}".replace(",", " "))
_kpi_card(c2, "🔧", "Jobs en retard",       jobs_overdue,   alert=True, subtitle="à traiter")
_kpi_card(c3, "📋", "Certif. critiques",    certs_critical, alert=True, subtitle="action requise")
_kpi_card(c4, "😴", "Violations MLC (30j)", violations_30d, alert=True)
_kpi_card(c5, "⚠️", "QHSE en retard",       qhse_overdue,   alert=True)
_kpi_card(c6, "🔩", "Stock critique",       parts_alert,    alert=True, subtitle="pièces sous seuil")

st.markdown("---")


# ─── Heures moteur ───────────────────────────────────────────────────────────

st.subheader("⚙️ Heures moteur par composant")

tab_chart, tab_table = st.tabs(["Évolution", "Derniers relevés"])

with tab_chart:
    if hours_df.empty:
        st.info("Aucune donnée d'heures moteur disponible.")
    else:
        hours_df["recorded_at"] = pd.to_datetime(hours_df["recorded_at"])
        hours_df["label"] = hours_df["vessel_name"] + " — " + hours_df["component_name"]
        fig = px.line(
            hours_df.sort_values("recorded_at"),
            x="recorded_at", y="hours_value", color="label",
            labels={"recorded_at": "Date", "hours_value": "Heures cumulées", "label": "Composant"},
            markers=True,
            color_discrete_sequence=PLOTLY_COLORS,
        )
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=20, b=0),
                          paper_bgcolor="#F4F1EC", plot_bgcolor="#F4F1EC",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

with tab_table:
    latest = (
        hours_df.sort_values("recorded_at", ascending=False)
        .groupby(["vessel_name", "component_name"], as_index=False)
        .first()[["vessel_name", "component_name", "hours_value", "delta_hours", "recorded_at"]]
    )
    latest.columns = ["Navire", "Composant", "Heures totales", "Δ dernière mesure", "Relevé le"]
    st.dataframe(latest, use_container_width=True, hide_index=True)


# ─── Maintenance ─────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("🔧 Jobs de maintenance")

if jobs_df.empty:
    st.success("Aucun job ouvert ou en retard.")
else:
    jobs_display = jobs_df.copy()
    jobs_display["Statut"] = jobs_display["status"].apply(lambda s: _status_badge(s))
    jobs_display["Échéance"] = pd.to_datetime(jobs_display["due_date"]).dt.strftime("%d/%m/%Y")
    st.markdown(
        jobs_display[["vessel_name", "job_name", "maintenance_type", "Statut", "Échéance"]]
        .rename(columns={"vessel_name": "Navire", "job_name": "Tâche", "maintenance_type": "Type"})
        .to_html(escape=False, index=False),
        unsafe_allow_html=True
    )


# ─── Certificats ─────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("📋 Certificats")

col_kpi_cert, col_pie, col_table = st.columns([1, 1, 2])

with col_kpi_cert:
    n_valid    = int(certs_df[certs_df["status"] == "valid"].shape[0])          if not certs_df.empty else 0
    n_expiring = int(certs_df[certs_df["status"] == "expiring_soon"].shape[0])  if not certs_df.empty else 0
    n_critical = int(certs_df[certs_df["status"] == "critical"].shape[0])       if not certs_df.empty else 0
    n_expired  = int(certs_df[certs_df["status"] == "expired"].shape[0])        if not certs_df.empty else 0
    st.metric("✅ Valides",          n_valid)
    st.metric("🟡 Expirent < 30j",  n_expiring)
    st.metric("🟠 Expirent < 7j",   n_critical)
    st.metric("🔴 Expirés",         n_expired)

with col_pie:
    if not certs_df.empty:
        counts = certs_df["status"].value_counts().reset_index()
        counts.columns = ["Statut", "Nombre"]
        colors = [STATUS_COLORS.get(s, "#aaa") for s in counts["Statut"]]
        fig = go.Figure(go.Pie(
            labels=counts["Statut"], values=counts["Nombre"],
            marker_colors=colors, hole=0.45,
            textinfo="label+value",
        ))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                          paper_bgcolor="#F4F1EC",
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

with col_table:
    if certs_df.empty:
        st.info("Aucun certificat.")
    else:
        display = certs_df.copy()
        display["Statut"] = display["status"].apply(lambda s: _status_badge(s))
        display["Expiration"] = pd.to_datetime(display["expires_at"]).dt.strftime("%d/%m/%Y")
        display["Jours restants"] = display["days_until_expiry"].apply(
            lambda d: f"{int(d)}j" if pd.notna(d) else "—"
        )
        st.markdown(
            display.sort_values("days_until_expiry")
            [["vessel_name", "cert_name", "cert_type", "Statut", "Expiration", "Jours restants"]]
            .rename(columns={"vessel_name": "Navire", "cert_name": "Certificat", "cert_type": "Type"})
            .to_html(escape=False, index=False),
            unsafe_allow_html=True
        )


# ─── Heures de repos (MLC) ───────────────────────────────────────────────────

st.markdown("---")
st.subheader("😴 Violations heures de repos — MLC 2006 (30 derniers jours)")

if viol_df.empty:
    st.success("Aucune violation détectée sur les 30 derniers jours.")
else:
    col_bar, col_viol = st.columns([1, 2])

    with col_bar:
        by_crew = (
            viol_df.groupby(["crew_name", "vessel_name"], as_index=False)
            .agg(nb=("deficit_hours", "count"), total_deficit=("deficit_hours", "sum"))
            .sort_values("total_deficit", ascending=False)
        )
        fig = px.bar(by_crew, x="crew_name", y="total_deficit",
                     color="vessel_name",
                     labels={"crew_name": "Marin", "total_deficit": "Heures manquantes", "vessel_name": "Navire"},
                     text_auto=".1f",
                     color_discrete_sequence=PLOTLY_COLORS)
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0),
                          paper_bgcolor="#F4F1EC", plot_bgcolor="#F4F1EC",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

    with col_viol:
        viol_display = viol_df.copy()
        viol_display["Sévérité"] = viol_display["severity"].apply(
            lambda s: _badge(s.upper(), SEVERITY_COLORS.get(s, "#999"))
        )
        viol_display["Date"] = pd.to_datetime(viol_display["period_date"]).dt.strftime("%d/%m/%Y")
        st.markdown(
            viol_display[["vessel_name", "crew_name", "rank", "Date",
                           "rest_hours_actual", "deficit_hours", "Sévérité"]]
            .rename(columns={
                "vessel_name": "Navire", "crew_name": "Marin", "rank": "Grade",
                "rest_hours_actual": "Heures repos", "deficit_hours": "Déficit (h)",
            })
            .to_html(escape=False, index=False),
            unsafe_allow_html=True
        )


# ─── QHSE ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("⚠️ Rapports QHSE ouverts")
if qhse_df.empty:
    st.success("Aucun rapport QHSE ouvert.")
else:
    qhse_display = qhse_df.copy()
    qhse_display["Statut"] = qhse_display["status"].apply(lambda s: _status_badge(s))
    qhse_display["Échéance"] = pd.to_datetime(qhse_display["due_date"]).dt.strftime("%d/%m/%Y")
    st.markdown(
        qhse_display[["vessel_name", "title", "report_type", "priority", "Statut", "Échéance"]]
        .rename(columns={"vessel_name": "Navire", "title": "Titre",
                         "report_type": "Type", "priority": "Priorité"})
        .to_html(escape=False, index=False),
        unsafe_allow_html=True
    )


# ─── Stock pièces ────────────────────────────────────────────────────────────

st.markdown("---")
st.subheader("🔩 Stock pièces critique")
if parts_df.empty:
    st.success("Tous les stocks sont au-dessus du seuil minimum.")
else:
    parts_display = parts_df[["vessel_name", "part_name", "part_number", "quantity", "min_quantity", "unit"]].copy()
    parts_display.columns = ["Navire", "Pièce", "Référence", "Qté", "Min requis", "Unité"]
    st.dataframe(
        parts_display.style.apply(
            lambda row: ["background-color: #fff3cd" if row["Qté"] > 0
                         else "background-color: #f8d7da"] * len(row), axis=1
        ),
        use_container_width=True, hide_index=True
    )


# ─── Vue flotte complète ─────────────────────────────────────────────────────

st.markdown("---")
with st.expander("📊 Vue flotte complète (tableau KPI)", expanded=False):
    fleet = data["kpi"].copy()
    fleet = fleet.rename(columns={
        "vessel_name": "Navire",
        "engine_hours_total": "Heures moteur",
        "engine_hours_last_7d": "Δ 7j",
        "jobs_open": "Jobs ouverts",
        "jobs_overdue": "Jobs retard",
        "certs_valid": "Certif. valides",
        "certs_expiring_30d": "Certif. 30j",
        "certs_expiring_7d": "Certif. 7j",
        "certs_expired": "Certif. expirés",
        "rest_violations_30d": "Violations MLC",
        "crew_onboard": "Équipage",
        "parts_below_min": "Stock critique",
        "qhse_open": "QHSE ouverts",
        "qhse_overdue": "QHSE retard",
    })
    st.dataframe(
        fleet[["Navire", "Heures moteur", "Δ 7j", "Jobs ouverts", "Jobs retard",
               "Certif. valides", "Certif. 7j", "Certif. expirés",
               "Violations MLC", "Stock critique", "QHSE retard"]],
        use_container_width=True, hide_index=True
    )
