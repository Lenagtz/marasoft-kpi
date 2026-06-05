"""
dashboard_v3.py — Marasoft KPI Dashboard · Version 3
Architecture : 2 onglets (Vue d'ensemble | Détail des indicateurs)
Cliquer un KPI bascule automatiquement sur l'onglet Détail et scrolle à la section.
Lancement mock : streamlit run dashboard_v3.py -- --mock
"""

import os, sys, io
import streamlit.components.v1 as components
from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

MOCK_MODE = "--mock" in sys.argv

st.set_page_config(
    page_title="Marasoft KPI v3",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Palette Atlantis ─────────────────────────────────────────────────────────
C_GREEN  = "#3D6657"
C_BEIGE  = "#C8AF82"
C_CREAM  = "#F4F1EC"
C_DARK   = "#1E3530"
C_RED    = "#C0392B"
C_ORANGE = "#D35400"
C_YELLOW = "#D4AC0D"
C_BLUE   = "#2471A3"
C_GRAY   = "#7F8C8D"
PLOTLY_COLORS = [C_GREEN, C_BEIGE, "#2E5045", "#A08B5A", C_DARK, "#D4C4A0"]

st.markdown(f"""
<style>
    .stApp {{ background-color: {C_CREAM}; }}
    .block-container {{ padding-top: 0 !important; padding-bottom: 1rem; max-width: 100% !important; }}
    section[data-testid="stSidebar"] {{ display: none; }}
    header[data-testid="stHeader"] {{ display: none; }}

    /* Section titles */
    h2, h3 {{ color: {C_GREEN} !important; border-bottom: 2px solid {C_BEIGE}; padding-bottom: 4px; }}

    /* Tables */
    table {{ border-collapse: collapse; width: 100%; font-size: 0.84rem; }}
    th {{ background: {C_GREEN}; color: white; padding: 7px 10px; text-align: left; font-weight: 600; }}
    td {{ padding: 6px 10px; border-bottom: 1px solid #e8e3db; background: white; }}
    tr:hover td {{ background: #f0ece5; }}

    /* Alert boxes */
    .alert-ok   {{ background:#e8f5e9; border-left:4px solid #43a047; padding:8px 12px; border-radius:4px; font-size:0.84rem; }}
    .alert-warn {{ background:#fff8e1; border-left:4px solid {C_YELLOW}; padding:8px 12px; border-radius:4px; font-size:0.84rem; }}
    .alert-crit {{ background:#fdecea; border-left:4px solid {C_RED};   padding:8px 12px; border-radius:4px; font-size:0.84rem; }}

    /* Metric mini */
    div[data-testid="stMetric"] {{ background: white; border-radius: 6px; padding: 8px 12px; }}
    div[data-testid="stMetricValue"] {{ font-size:1.4rem !important; color:{C_DARK} !important; }}

    /* ── Fond opaque continu derrière tout le header fixe ── */
    body::before {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 170px;
        background: {C_CREAM};
        z-index: 998;
        pointer-events: none;
    }}

    /* ── Header fixe ──
       Structure DOM réelle dans v3 (vérifiée par inspection getBoundingClientRect) :
       child 1 : élément vide Streamlit interne
       child 2 : titre + logos  → fixed top:0
       child 3 : selectbox      → fixed top:60px
       child 4 : trait doré     → fixed top:155px + box-shadow
       child 5 : onglets        → padding-top uniquement (PAS fixed)
    */
    .block-container > div[data-testid="stVerticalBlock"] > div:nth-child(2) {{
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 1002;
        background: {C_CREAM};
        padding: 0 1.5rem;
    }}
    .block-container > div[data-testid="stVerticalBlock"] > div:nth-child(3) {{
        position: fixed;
        top: 60px; left: 0; right: 0;
        z-index: 1001;
        background: {C_CREAM};
        padding: 0 1.5rem;
    }}
    .block-container > div[data-testid="stVerticalBlock"] > div:nth-child(4) {{
        position: fixed;
        top: 155px; left: 0; right: 0;
        z-index: 1000;
        background: {C_CREAM};
        padding: 0 1.5rem;
        box-shadow: 0 4px 10px rgba(0,0,0,0.08);
    }}
    /* child 5 : onglets — décalage pour dégager le header fixe */
    .block-container > div[data-testid="stVerticalBlock"] > div:nth-child(5) {{
        padding-top: 170px;
    }}

    /* Onglets — style Atlantis */
    div[data-testid="stTabs"] > div:first-child {{
        border-bottom: 2px solid {C_BEIGE};
        margin-bottom: 0;
    }}
    button[data-baseweb="tab"] {{
        font-size: 1rem !important;
        font-weight: 600 !important;
        color: {C_GRAY} !important;
        padding: 10px 28px !important;
        background: transparent !important;
        border: none !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {C_GREEN} !important;
        border-bottom: 3px solid {C_GREEN} !important;
    }}
    button[data-baseweb="tab"]:hover {{
        color: {C_GREEN} !important;
        background: rgba(61,102,87,0.06) !important;
        border-radius: 6px 6px 0 0 !important;
    }}

    /* KPI cards — hauteur uniforme + hover effect */
    .kpi-link {{
        text-decoration: none;
        display: flex;          /* stretch pour égaliser les hauteurs */
        height: 100%;
    }}
    .kpi-card-inner {{
        display: flex !important;
        flex-direction: column;
        height: 148px;          /* hauteur fixe identique pour toutes les cartes */
        box-sizing: border-box;
    }}
    .kpi-link:hover .kpi-card-inner {{
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.12) !important;
    }}

    /* Selectbox label masqué */
    div[data-testid="stAppViewBlockContainer"] > div:first-child .stSelectbox label {{
        display: none;
    }}
</style>
""", unsafe_allow_html=True)


# ─── Données ──────────────────────────────────────────────────────────────────

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
        certs   = pd.read_sql(text("SELECT c.*, v.name AS vessel_name FROM certificates c JOIN vessels v USING (vessel_id) ORDER BY c.expires_at ASC NULLS LAST"), conn)
        jobs    = pd.read_sql(text("SELECT mj.*, v.name AS vessel_name FROM maintenance_jobs mj JOIN vessels v USING (vessel_id) WHERE mj.status != 'done' ORDER BY mj.due_date ASC NULLS LAST"), conn)
        hours   = pd.read_sql(text("SELECT rhs.vessel_id, v.name AS vessel_name, comp.name AS component_name, rhs.recorded_at, rhs.hours_value, rhs.delta_hours FROM running_hours_snapshots rhs JOIN vessels v USING (vessel_id) JOIN components comp ON comp.component_id = rhs.component_id ORDER BY rhs.recorded_at DESC"), conn)
        violations = pd.read_sql(text("SELECT rhv.*, cm.first_name || ' ' || cm.last_name AS crew_name, cm.rank, v.name AS vessel_name FROM rest_hours_violations rhv JOIN crew_members cm ON cm.crew_member_id = rhv.crew_member_id JOIN vessels v ON v.vessel_id = cm.vessel_id WHERE rhv.period_date >= CURRENT_DATE - 30 ORDER BY rhv.period_date DESC"), conn)
        parts   = pd.read_sql(text("SELECT p.*, v.name AS vessel_name FROM parts p JOIN vessels v USING (vessel_id) WHERE p.below_minimum ORDER BY p.quantity ASC"), conn)
        qhse    = pd.read_sql(text("SELECT qr.*, v.name AS vessel_name FROM qhse_reports qr JOIN vessels v USING (vessel_id) WHERE qr.status != 'closed' ORDER BY qr.due_date ASC NULLS LAST"), conn)
        voyages = pd.read_sql(text("""
            SELECT vg.*, v.name AS vessel_name,
                   CASE WHEN vg.arrival_date IS NULL THEN 'active' ELSE 'completed' END AS status
            FROM voyages vg JOIN vessels v USING (vessel_id)
            ORDER BY vg.departure_date DESC
        """), conn)
        crew = pd.read_sql(text("""
            SELECT cm.*, v.name AS vessel_name,
                   cm.first_name || ' ' || cm.last_name AS crew_name
            FROM crew_members cm LEFT JOIN vessels v USING (vessel_id)
            WHERE cm.contract_end IS NOT NULL
            ORDER BY cm.contract_end ASC
        """), conn)
    return dict(kpi=kpi, certs=certs, jobs=jobs, hours=hours, violations=violations,
                parts=parts, qhse=qhse, voyages=voyages, crew=crew)

def _mock_data():
    today = date.today()
    kpi = pd.DataFrame([
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", kpi_date=today,
             engine_hours_total=15660.5, engine_hours_last_7d=23.5,
             jobs_open=1, jobs_overdue=1, certs_valid=1, certs_expiring_30d=0,
             certs_expiring_7d=1, certs_expired=0, rest_violations_30d=2,
             crew_onboard=3, parts_below_min=2, qhse_open=1, qhse_overdue=1),
        dict(vessel_id="V002", vessel_name="Nordic Star", kpi_date=today,
             engine_hours_total=8800.0, engine_hours_last_7d=0.0,
             jobs_open=0, jobs_overdue=0, certs_valid=0, certs_expiring_30d=0,
             certs_expiring_7d=0, certs_expired=1, rest_violations_30d=0,
             crew_onboard=1, parts_below_min=0, qhse_open=0, qhse_overdue=0),
    ])
    certs = pd.DataFrame([
        dict(cert_id="CERT001", vessel_id="V001", vessel_name="Atlantic Pioneer", cert_type="SOLAS",
             cert_name="Safety Certificate", issued_at=date(2024,1,1), expires_at=date(2026,6,5),
             status="critical", days_until_expiry=(date(2026,6,5)-today).days),
        dict(cert_id="CERT002", vessel_id="V001", vessel_name="Atlantic Pioneer", cert_type="MARPOL",
             cert_name="Oil Record Book", issued_at=date(2023,6,1), expires_at=date(2027,6,1),
             status="valid", days_until_expiry=(date(2027,6,1)-today).days),
        dict(cert_id="CERT003", vessel_id="V002", vessel_name="Nordic Star", cert_type="MLC",
             cert_name="MLC Certificate", issued_at=date(2022,1,1), expires_at=date(2026,5,10),
             status="expired", days_until_expiry=(date(2026,5,10)-today).days),
    ])
    jobs = pd.DataFrame([
        dict(job_id="J001", vessel_id="V001", vessel_name="Atlantic Pioneer", job_name="Oil change",
             status="open", due_date=date(2026,6,15), maintenance_type="preventive", component_id="C001"),
        dict(job_id="J002", vessel_id="V001", vessel_name="Atlantic Pioneer", job_name="Filter check",
             status="overdue", due_date=date(2026,4,1), maintenance_type="preventive", component_id="C002"),
    ])
    hours = pd.DataFrame([
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Main Engine",
             recorded_at=datetime(2026,5,28,8,0), hours_value=12450.5, delta_hours=None),
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Main Engine",
             recorded_at=datetime(2026,5,29,8,0), hours_value=12474.0, delta_hours=23.5),
        dict(vessel_id="V001", vessel_name="Atlantic Pioneer", component_name="Aux Generator",
             recorded_at=datetime(2026,5,28,8,0), hours_value=3210.0, delta_hours=None),
        dict(vessel_id="V002", vessel_name="Nordic Star", component_name="Main Engine",
             recorded_at=datetime(2026,5,29,8,0), hours_value=8800.0, delta_hours=None),
    ])
    violations = pd.DataFrame([
        dict(crew_member_id="CM001", vessel_name="Atlantic Pioneer", crew_name="Erik Hansen",
             rank="Master", period_date=date(2026,5,28), rest_hours_actual=8.5,
             rest_hours_required=10.0, deficit_hours=1.5, severity="major"),
        dict(crew_member_id="CM002", vessel_name="Atlantic Pioneer", crew_name="Anna Lindqvist",
             rank="Chief Officer", period_date=date(2026,5,28), rest_hours_actual=9.0,
             rest_hours_required=10.0, deficit_hours=1.0, severity="minor"),
    ])
    parts = pd.DataFrame([
        dict(part_id="P002", vessel_id="V001", vessel_name="Atlantic Pioneer", part_name="Fuel Filter",
             part_number="FF-456", quantity=1, min_quantity=3, below_minimum=True, unit="pcs"),
        dict(part_id="P003", vessel_id="V001", vessel_name="Atlantic Pioneer", part_name="V-Belt",
             part_number="VB-789", quantity=0, min_quantity=2, below_minimum=True, unit="pcs"),
    ])
    qhse = pd.DataFrame([
        dict(report_id="Q001", vessel_id="V001", vessel_name="Atlantic Pioneer", report_type="Near Miss",
             title="Slippery deck incident", due_date=date(2026,6,10), status="open", priority="high"),
        dict(report_id="Q002", vessel_id="V001", vessel_name="Atlantic Pioneer", report_type="Inspection",
             title="PSC Inspection prep", due_date=date(2026,4,1), status="overdue", priority="critical"),
    ])
    voyages = pd.DataFrame([
        dict(voyage_id="V001-01", vessel_id="V001", vessel_name="Atlantic Pioneer",
             departure_port="Le Havre", arrival_port="Rotterdam",
             departure_date=datetime(2026,5,25,6,0), arrival_date=None,
             duration_days=None, voyage_type="sea", status="active"),
        dict(voyage_id="V001-02", vessel_id="V001", vessel_name="Atlantic Pioneer",
             departure_port="Rotterdam", arrival_port="Hamburg",
             departure_date=datetime(2026,5,20,14,0), arrival_date=datetime(2026,5,22,9,0),
             duration_days=1.8, voyage_type="sea", status="completed"),
        dict(voyage_id="V002-01", vessel_id="V002", vessel_name="Nordic Star",
             departure_port="Oslo", arrival_port="Bergen",
             departure_date=datetime(2026,5,28,8,0), arrival_date=None,
             duration_days=None, voyage_type="sea", status="active"),
    ])
    crew = pd.DataFrame([
        dict(crew_member_id="CM001", vessel_id="V001", vessel_name="Atlantic Pioneer",
             crew_name="Erik Hansen", rank="Master", nationality="Norwegian",
             contract_start=date(2026,1,15), contract_end=date(2026,6,15)),
        dict(crew_member_id="CM002", vessel_id="V001", vessel_name="Atlantic Pioneer",
             crew_name="Anna Lindqvist", rank="Chief Officer", nationality="Swedish",
             contract_start=date(2026,2,1), contract_end=date(2026,8,1)),
        dict(crew_member_id="CM003", vessel_id="V001", vessel_name="Atlantic Pioneer",
             crew_name="Marco Rossi", rank="Engineer", nationality="Italian",
             contract_start=date(2026,3,1), contract_end=date(2026,6,20)),
        dict(crew_member_id="CM004", vessel_id="V002", vessel_name="Nordic Star",
             crew_name="Lars Eriksen", rank="Master", nationality="Danish",
             contract_start=date(2026,4,1), contract_end=date(2026,10,1)),
    ])
    return dict(kpi=kpi, certs=certs, jobs=jobs, hours=hours, violations=violations,
                parts=parts, qhse=qhse, voyages=voyages, crew=crew)


# ─── Helpers ──────────────────────────────────────────────────────────────────

STATUS_COLORS = {"expired": C_RED, "critical": C_ORANGE, "expiring_soon": C_YELLOW,
                 "valid": "#27AE60", "overdue": C_RED, "open": C_BLUE,
                 "due_soon": C_YELLOW, "done": C_GRAY, "closed": C_GRAY}
SEVERITY_COLORS = {"minor": C_YELLOW, "major": C_ORANGE, "critical": C_RED}

def _badge(text, color):
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.76rem;font-weight:700">{text}</span>'

def _status_badge(s):
    return _badge(s.replace("_"," ").upper(), STATUS_COLORS.get(s, C_GRAY))


# ─── Chargement & filtre ──────────────────────────────────────────────────────

data = load_data()
vessels = ["Tous"] + sorted(data["kpi"]["vessel_name"].tolist())


# ─── HEADER FIXE ─────────────────────────────────────────────────────────────

# Ligne 1 : titre + logos
st.markdown(f"""
<div style="background:{C_CREAM};padding:12px 8px 0 8px;
            display:flex;align-items:center;justify-content:space-between;">
    <div>
        <span style="color:{C_GREEN};font-size:1.5rem;font-weight:700">⚓ Dashboard KPI Flotte</span>
        <span style="color:{C_GRAY};font-size:0.78rem;margin-left:14px">
            Mise à jour : {datetime.now().strftime("%d/%m/%Y %H:%M")}
            {"&nbsp;·&nbsp;🧪 Mode démo" if MOCK_MODE else ""}
        </span>
    </div>
    <div style="display:flex;align-items:center;gap:16px">
        <img src="https://storage.googleapis.com/hostinger-horizons-assets-prod/d98c5fe9-b190-4a07-870f-677606696e62/d19a2551d7b59db361ce672d20503ff4.png"
             style="height:38px;object-fit:contain">
        <img src="https://marad.com/wp-content/uploads/2025/06/marad-logo-full-colour.png"
             style="height:28px;object-fit:contain">
    </div>
</div>
""", unsafe_allow_html=True)

# Ligne 2 : selectbox
col_sel, col_info = st.columns([2, 5])
with col_sel:
    selected_vessel = st.selectbox(
        f"🚢 Flotte : {len(data['kpi'])} navires",
        vessels,
    )
with col_info:
    if not MOCK_MODE:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir"):
            st.cache_data.clear(); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# Ligne 3 : trait doré
st.markdown(f"<hr style='border:none;border-top:3px solid {C_BEIGE};margin:4px 0 0 0'>",
            unsafe_allow_html=True)

# ─── Filtre ───────────────────────────────────────────────────────────────────

def _f(df, col="vessel_name"):
    return df if selected_vessel == "Tous" or col not in df.columns else df[df[col] == selected_vessel]

kpi_df     = _f(data["kpi"]);       certs_df   = _f(data["certs"])
jobs_df    = _f(data["jobs"]);      hours_df   = _f(data["hours"])
viol_df    = _f(data["violations"]); parts_df  = _f(data["parts"])
qhse_df    = _f(data["qhse"]);      voyages_df = _f(data["voyages"])
crew_df    = _f(data["crew"])


# ─── Valeurs KPI ─────────────────────────────────────────────────────────────

total_engine   = int(kpi_df["engine_hours_total"].sum())
jobs_overdue   = int(kpi_df["jobs_overdue"].sum())
certs_expired  = int(kpi_df["certs_expired"].sum())
certs_critical = int(kpi_df["certs_expiring_7d"].sum()) + certs_expired
violations_30d = int(kpi_df["rest_violations_30d"].sum())
qhse_overdue   = int(kpi_df["qhse_overdue"].sum())
parts_alert    = int(kpi_df["parts_below_min"].sum())
crew_onboard   = int(kpi_df["crew_onboard"].sum())
voyages_active = int(voyages_df[voyages_df["status"] == "active"].shape[0]) if not voyages_df.empty else 0
today_plus30   = date.today() + timedelta(days=30)
contracts_expiring = int(crew_df[crew_df["contract_end"].apply(
    lambda x: pd.notna(x) and pd.to_datetime(x).date() <= today_plus30)].shape[0]) if not crew_df.empty else 0


# ─── Composant KPI ───────────────────────────────────────────────────────────

def _kpi_card_v3(icon, label, value, alert=False, subtitle="", anchor=""):
    """Carte KPI pour la grille 3×3 de l'onglet Vue d'ensemble."""
    val_int = value if isinstance(value, int) else 1
    border  = C_RED if alert and val_int > 0 else C_GREEN
    accent  = C_RED if alert and val_int > 0 else C_GREEN
    sub     = (f'<div style="font-size:0.75rem;color:{C_RED};margin-top:3px;font-weight:500">'
               f'{subtitle}</div>') if subtitle and val_int > 0 else ""
    val_str = str(value)
    fsize   = "1.6rem" if len(val_str) < 6 else "1.2rem"
    hint    = (f'<div style="font-size:0.67rem;color:{C_BEIGE};margin-top:6px;letter-spacing:0.3px">'
               f'↗ voir le détail</div>') if anchor else ""
    data_attr = f'data-scroll-to="{anchor}" style="cursor:pointer"' if anchor else ""
    return (
        f'<div {data_attr} class="kpi-link">'
        f'<div style="background:white;border-radius:10px;padding:16px 18px;'
        f'border-left:5px solid {border};width:100%;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.07);'
        f'transition:transform 0.18s ease,box-shadow 0.18s ease" class="kpi-card-inner">'
        f'<div style="font-size:0.78rem;color:#555;font-weight:600;line-height:1.3;'
        f'margin-bottom:8px;display:flex;align-items:center;gap:6px">'
        f'<span style="font-size:1.1rem">{icon}</span> {label}</div>'
        f'<div style="font-size:{fsize};font-weight:800;color:{accent};line-height:1">'
        f'{value}</div>'
        f'{sub}{hint}'
        f'</div>'
        f'</div>'
    )


# ─── GÉNÉRATEUR PDF ──────────────────────────────────────────────────────────

def _build_pdf(sections: list, vessel_label: str) -> bytes:
    from fpdf import FPDF

    def _safe(txt):
        if txt is None: return "-"
        return (str(txt)
                .replace("—", "-").replace("–", "-")
                .replace("'", "'").replace(""", '"').replace(""", '"')
                .encode("latin-1", errors="replace").decode("latin-1"))

    GREEN  = (61,  102,  87)
    DARK   = (30,   53,  48)
    RED    = (192,  57,  43)
    LGRAY  = (245, 245, 242)

    class KpiPDF(FPDF):
        def header(self):
            self.set_fill_color(*GREEN)
            self.rect(0, 0, 210, 18, 'F')
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(255, 255, 255)
            self.set_xy(8, 4)
            self.cell(0, 10, "Dashboard KPI Flotte - Marasoft", ln=False)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(200, 175, 130)
            self.set_xy(0, 5)
            self.cell(202, 8, datetime.now().strftime("%d/%m/%Y %H:%M"), align="R", ln=False)
            self.ln(14)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, _safe(f"Atlantis Software - {vessel_label} - Page {self.page_no()}"), align="C")

    def section_title(pdf, title):
        pdf.set_fill_color(*GREEN)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, _safe(title), ln=True, fill=True)
        pdf.ln(2)
        pdf.set_text_color(*DARK)

    def kpi_row(pdf, label, value, alert=False):
        col = RED if alert and str(value) not in ("0","") else GREEN
        pdf.set_fill_color(*LGRAY)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*DARK)
        pdf.cell(100, 7, _safe(label), fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*col)
        pdf.cell(0, 7, _safe(str(value)), ln=True, fill=True)
        pdf.set_text_color(*DARK)

    def table_header(pdf, cols, widths):
        pdf.set_fill_color(*GREEN)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        for col, w in zip(cols, widths):
            pdf.cell(w, 6, _safe(col), border=0, fill=True)
        pdf.ln()

    def table_row(pdf, vals, widths, bg=False):
        pdf.set_fill_color(*(LGRAY if bg else (255, 255, 255)))
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "", 8)
        for v, w in zip(vals, widths):
            pdf.cell(w, 5, _safe(str(v)[:28]), border=0, fill=True)
        pdf.ln()

    pdf = KpiPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if "resume" in sections:
        section_title(pdf, ">> Resume des KPIs")
        kpi_row(pdf, "Heures moteur totales", f"{total_engine:,}".replace(",", " "))
        kpi_row(pdf, "Jobs en retard",        jobs_overdue,   alert=True)
        kpi_row(pdf, "Certificats critiques", certs_critical, alert=True)
        kpi_row(pdf, "Violations MLC (30j)",  violations_30d, alert=True)
        kpi_row(pdf, "QHSE en retard",        qhse_overdue,   alert=True)
        kpi_row(pdf, "Stock critique",        parts_alert,    alert=True)
        pdf.ln(4)

    if "maintenance" in sections and not jobs_df.empty:
        section_title(pdf, "Maintenance")
        cols   = ["Navire","Tache","Statut","Echeance"]
        widths = [50, 70, 30, 40]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(jobs_df.iterrows()):
            table_row(pdf, [r.get("vessel_name",""), r.get("job_name",""),
                            r.get("status","").upper(), str(r.get("due_date",""))[:10]],
                      widths, bg=i%2==0)
        pdf.ln(4)

    if "certificats" in sections and not certs_df.empty:
        section_title(pdf, "Certificats")
        d = certs_df.sort_values("days_until_expiry").copy()
        cols   = ["Navire","Certificat","Type","Statut","Expiration","Jours"]
        widths = [40, 48, 22, 28, 28, 18]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(d.iterrows()):
            j = f"{int(r['days_until_expiry'])}j" if pd.notna(r.get('days_until_expiry')) else "-"
            table_row(pdf, [r.get("vessel_name",""), r.get("cert_name",""), r.get("cert_type",""),
                            r.get("status",""), str(r.get("expires_at",""))[:10], j],
                      widths, bg=i%2==0)
        pdf.ln(4)

    if "mlc" in sections and not viol_df.empty:
        section_title(pdf, "Violations MLC (30 jours)")
        cols   = ["Navire","Marin","Grade","Date","Repos (h)","Deficit (h)","Severite"]
        widths = [36, 36, 24, 22, 20, 22, 22]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(viol_df.iterrows()):
            table_row(pdf, [r.get("vessel_name",""), r.get("crew_name",""), r.get("rank",""),
                            str(r.get("period_date",""))[:10],
                            str(r.get("rest_hours_actual","")), str(r.get("deficit_hours","")),
                            r.get("severity","")], widths, bg=i%2==0)
        pdf.ln(4)

    if "qhse" in sections and not qhse_df.empty:
        section_title(pdf, "Rapports QHSE")
        cols   = ["Navire","Titre","Type","Priorite","Statut","Echeance"]
        widths = [36, 52, 26, 22, 22, 26]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(qhse_df.iterrows()):
            table_row(pdf, [r.get("vessel_name",""), r.get("title",""), r.get("report_type",""),
                            r.get("priority",""), r.get("status",""),
                            str(r.get("due_date",""))[:10]], widths, bg=i%2==0)
        pdf.ln(4)

    if "stock" in sections and not parts_df.empty:
        section_title(pdf, "Stock critique")
        cols   = ["Navire","Piece","Reference","Qte","Min requis","Unite"]
        widths = [44, 44, 34, 18, 26, 18]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(parts_df.iterrows()):
            table_row(pdf, [r.get("vessel_name",""), r.get("part_name",""),
                            r.get("part_number",""), r.get("quantity",""),
                            r.get("min_quantity",""), r.get("unit","")],
                      widths, bg=i%2==0)
        pdf.ln(4)

    if "voyages" in sections and not voyages_df.empty:
        section_title(pdf, "Voyages")
        cols   = ["Navire","Depart de","Arrivee a","Depart","Arrivee","Duree","Statut"]
        widths = [36, 30, 30, 30, 30, 18, 20]
        table_header(pdf, cols, widths)
        for i, (_, r) in enumerate(voyages_df.iterrows()):
            dep = pd.to_datetime(r.get("departure_date","")).strftime("%d/%m/%y %H:%M") \
                  if pd.notna(r.get("departure_date")) else "-"
            arr = pd.to_datetime(r.get("arrival_date","")).strftime("%d/%m/%y %H:%M") \
                  if pd.notna(r.get("arrival_date")) else "En cours"
            dur = f"{r['duration_days']:.1f}j" if pd.notna(r.get("duration_days")) else "-"
            table_row(pdf, [r.get("vessel_name",""), r.get("departure_port",""),
                            r.get("arrival_port",""), dep, arr, dur, r.get("status","")],
                      widths, bg=i%2==0)
        pdf.ln(4)

    if "contrats" in sections and not crew_df.empty:
        section_title(pdf, "Equipage & Contrats")
        cols   = ["Navire","Marin","Grade","Nationalite","Debut","Fin contrat","Jours rest."]
        widths = [34, 34, 24, 24, 24, 24, 22]
        table_header(pdf, cols, widths)
        today_dt = date.today()
        for i, (_, r) in enumerate(crew_df.iterrows()):
            end   = pd.to_datetime(r.get("contract_end")) if pd.notna(r.get("contract_end")) else None
            jours = str((end.date() - today_dt).days) + "j" if end else "-"
            table_row(pdf, [r.get("vessel_name",""), r.get("crew_name",""), r.get("rank",""),
                            r.get("nationality",""), str(r.get("contract_start",""))[:10],
                            str(r.get("contract_end",""))[:10], jours],
                      widths, bg=i%2==0)
        pdf.ln(4)

    return bytes(pdf.output())


# ─── ONGLETS ──────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📊  Vue d'ensemble", "📈  Détail des indicateurs"])


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET 1 — Vue d'ensemble
# ══════════════════════════════════════════════════════════════════════════════

with tab1:

    # ── JS : clic sur carte → basculer onglet 2 + scroll ancre ───────────────
    components.html("""
<script>
(function() {
    var lockTarget = null;
    var lockUntil  = 0;

    function setup() {
        var doc    = window.parent.document;
        var stMain = doc.querySelector('section[data-testid="stMain"]');
        if (!stMain) { setTimeout(setup, 300); return; }

        // Polling : scroll lock + scroll différé après changement d'onglet
        setInterval(function() {
            // Scroll différé stocké dans sessionStorage parent
            var pending = window.parent.sessionStorage.getItem('kpiPendingScroll');
            if (pending) {
                var target = doc.getElementById(pending);
                if (target) {
                    window.parent.sessionStorage.removeItem('kpiPendingScroll');
                    var offset   = 180;
                    var top      = Math.max(0, target.getBoundingClientRect().top
                                              + stMain.scrollTop - offset - 12);
                    stMain.scrollTop = top;
                    lockTarget = top;
                    lockUntil  = Date.now() + 2500;
                }
            }
            // Maintien du scroll pendant 2.5s après le clic
            if (lockTarget !== null && Date.now() < lockUntil) {
                if (Math.abs(stMain.scrollTop - lockTarget) > 30) {
                    stMain.scrollTop = lockTarget;
                }
            } else {
                lockTarget = null;
            }
        }, 100);

        // Clic sur une carte KPI
        doc.addEventListener('click', function(e) {
            var card = e.target.closest('[data-scroll-to]');
            if (!card) return;
            var targetId = card.getAttribute('data-scroll-to');

            // Mémoriser la cible de scroll
            window.parent.sessionStorage.setItem('kpiPendingScroll', targetId);

            // Trouver le bouton de l'onglet 2 et cliquer dessus
            var tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length >= 2) {
                tabs[1].click();
            }
        });
    }
    setTimeout(setup, 600);
})();
</script>
""", height=1)

    # ── Titre ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='color:{C_GREEN};font-size:1rem;font-weight:700;"
        f"margin:8px 0 16px 0;letter-spacing:0.2px'>"
        f"Vue d'ensemble · {len(kpi_df)} navire(s) sélectionné(s)</div>",
        unsafe_allow_html=True,
    )

    # ── Grille 3 × 3 ─────────────────────────────────────────────────────────
    kpi_cards = [
        ("⚙️", "Heures moteur",      f"{total_engine:,}".replace(",", " "),
                                     False, "",               "section-moteur"),
        ("🔧", "Jobs en retard",      jobs_overdue,
                                     True,  "à traiter",      "section-maintenance"),
        ("📋", "Certif. critiques",   certs_critical,
                                     True,  "action requise", "section-certifs"),
        ("😴", "Violations MLC (30j)",violations_30d,
                                     True,  "",               "section-mlc"),
        ("⚠️", "QHSE en retard",      qhse_overdue,
                                     True,  "",               "section-qhse"),
        ("🔩", "Stock critique",      parts_alert,
                                     True,  "pièces sous seuil","section-stock"),
        ("👥", "Équipage à bord",     crew_onboard,
                                     False, "",               "section-contrats"),
        ("🚢", "Voyages actifs",      voyages_active,
                                     False, "",               "section-voyages"),
        ("📝", "Contrats < 30j",      contracts_expiring,
                                     True,  "à renouveler",   "section-contrats"),
    ]

    # Rendu en CSS grid — toutes les cartes ont la même hauteur par ligne
    cards_html = "".join(
        _kpi_card_v3(icon, label, value, alert, subtitle, anchor)
        for icon, label, value, alert, subtitle, anchor in kpi_cards
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        f'gap:16px;padding:8px 0 20px 0">{cards_html}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Tableau flotte ────────────────────────────────────────────────────────
    with st.expander("📊 Vue flotte complète", expanded=False):
        fleet = data["kpi"].rename(columns={
            "vessel_name":"Navire","engine_hours_total":"Heures moteur",
            "engine_hours_last_7d":"Δ 7j","jobs_open":"Jobs ouverts",
            "jobs_overdue":"Jobs retard","certs_valid":"Certif. valides",
            "certs_expiring_7d":"Certif. 7j","certs_expired":"Certif. expirés",
            "rest_violations_30d":"Violations MLC","crew_onboard":"Équipage",
            "parts_below_min":"Stock critique","qhse_open":"QHSE ouverts",
            "qhse_overdue":"QHSE retard",
        })
        st.dataframe(
            fleet[["Navire","Heures moteur","Δ 7j","Jobs ouverts","Jobs retard",
                   "Certif. valides","Certif. 7j","Certif. expirés",
                   "Violations MLC","Stock critique","QHSE retard"]],
            use_container_width=True, hide_index=True,
        )

    # ── Export PDF ────────────────────────────────────────────────────────────
    with st.expander("📥 Télécharger un rapport PDF", expanded=False):
        vessel_label = selected_vessel if selected_vessel != "Tous" else "Flotte complète"
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        st.markdown(
            f"<div style='font-size:0.85rem;color:{C_GRAY};margin-bottom:12px'>"
            f"Rapport pour : <b>{vessel_label}</b> · {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>",
            unsafe_allow_html=True,
        )

        col_pdf1, _ = st.columns([1, 3])
        with col_pdf1:
            pdf_full = _build_pdf(
                ["resume","maintenance","certificats","mlc","qhse","stock","voyages","contrats"],
                vessel_label,
            )
            st.download_button(
                label="📄 Rapport complet",
                data=pdf_full,
                file_name=f"rapport_kpi_{ts}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        st.markdown(
            f"<div style='color:{C_GREEN};font-size:0.8rem;font-weight:600;"
            f"margin:12px 0 6px'>Rapports par KPI :</div>",
            unsafe_allow_html=True,
        )

        kpi_items = [
            ("🔧 Maintenance", ["resume","maintenance"], f"maintenance_{ts}.pdf"),
            ("📋 Certificats", ["resume","certificats"], f"certificats_{ts}.pdf"),
            ("😴 MLC",         ["resume","mlc"],         f"mlc_{ts}.pdf"),
            ("⚠️ QHSE",        ["resume","qhse"],        f"qhse_{ts}.pdf"),
            ("🔩 Stock",       ["resume","stock"],        f"stock_{ts}.pdf"),
            ("🚢 Voyages",     ["resume","voyages"],      f"voyages_{ts}.pdf"),
            ("👥 Contrats",    ["resume","contrats"],     f"contrats_{ts}.pdf"),
        ]
        cols_pdf = st.columns(7)
        for col, (label, sects, fname) in zip(cols_pdf, kpi_items):
            with col:
                pdf_bytes = _build_pdf(sects, vessel_label)
                st.download_button(
                    label=label, data=pdf_bytes, file_name=fname,
                    mime="application/pdf", use_container_width=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET 2 — Détail des indicateurs
# ══════════════════════════════════════════════════════════════════════════════

with tab2:

    # ── Heures moteur ─────────────────────────────────────────────────────────
    st.markdown('<div id="section-moteur"></div>', unsafe_allow_html=True)
    st.markdown("### ⚙️ Heures moteur")
    if not hours_df.empty:
        hours_df["recorded_at"] = pd.to_datetime(hours_df["recorded_at"])
        hours_df["label"] = hours_df["vessel_name"] + " — " + hours_df["component_name"]
        fig = px.area(
            hours_df.sort_values("recorded_at"),
            x="recorded_at", y="hours_value", color="label",
            labels={"recorded_at":"Date","hours_value":"Heures cumulées","label":"Composant"},
            color_discrete_sequence=PLOTLY_COLORS,
        )
        fig.update_traces(opacity=0.75)
        fig.update_layout(
            height=280, margin=dict(l=0,r=0,t=10,b=0),
            paper_bgcolor="white", plot_bgcolor="#fafaf8",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font_size=11),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucune donnée disponible.")

    st.markdown("---")

    # ── Maintenance ───────────────────────────────────────────────────────────
    st.markdown('<div id="section-maintenance"></div>', unsafe_allow_html=True)
    st.markdown("### 🔧 Maintenance")
    if jobs_df.empty:
        st.markdown('<div class="alert-ok">✅ Aucun job ouvert ou en retard.</div>',
                    unsafe_allow_html=True)
    else:
        d = jobs_df.copy()
        d["Statut"]   = d["status"].apply(_status_badge)
        d["Échéance"] = pd.to_datetime(d["due_date"]).dt.strftime("%d/%m/%Y")
        st.markdown(
            d[["vessel_name","job_name","Statut","Échéance"]]
            .rename(columns={"vessel_name":"Navire","job_name":"Tâche"})
            .to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Certificats ───────────────────────────────────────────────────────────
    st.markdown('<div id="section-certifs"></div>', unsafe_allow_html=True)
    st.markdown("### 📋 Certificats")
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        if not certs_df.empty:
            counts = certs_df["status"].value_counts().reset_index()
            counts.columns = ["Statut","Nombre"]
            fig = go.Figure(go.Pie(
                labels=counts["Statut"], values=counts["Nombre"],
                marker_colors=[STATUS_COLORS.get(s,"#aaa") for s in counts["Statut"]],
                hole=0.55, textinfo="label+value",
            ))
            fig.update_layout(height=220, margin=dict(l=0,r=0,t=0,b=0),
                              paper_bgcolor="white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with col_c2:
        if not certs_df.empty:
            d = certs_df.copy()
            d["Statut"]     = d["status"].apply(_status_badge)
            d["Expiration"] = pd.to_datetime(d["expires_at"]).dt.strftime("%d/%m/%Y")
            d["Jours"]      = d["days_until_expiry"].apply(
                lambda x: f"{int(x)}j" if pd.notna(x) else "—")
            st.markdown(
                d.sort_values("days_until_expiry")
                [["vessel_name","cert_name","cert_type","Statut","Expiration","Jours"]]
                .rename(columns={"vessel_name":"Navire","cert_name":"Certificat","cert_type":"Type"})
                .to_html(escape=False, index=False),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── MLC + QHSE côte à côte ────────────────────────────────────────────────
    col_mlc, col_qhse = st.columns(2)

    with col_mlc:
        st.markdown('<div id="section-mlc"></div>', unsafe_allow_html=True)
        st.markdown("### 😴 Violations MLC (30j)")
        if viol_df.empty:
            st.markdown('<div class="alert-ok">✅ Aucune violation.</div>',
                        unsafe_allow_html=True)
        else:
            d = viol_df.copy()
            d["Sévérité"] = d["severity"].apply(
                lambda s: _badge(s.upper(), SEVERITY_COLORS.get(s,"#999")))
            d["Date"] = pd.to_datetime(d["period_date"]).dt.strftime("%d/%m/%Y")
            st.markdown(
                d[["vessel_name","crew_name","rank","Date",
                   "rest_hours_actual","deficit_hours","Sévérité"]]
                .rename(columns={"vessel_name":"Navire","crew_name":"Marin","rank":"Grade",
                                 "rest_hours_actual":"Repos (h)","deficit_hours":"Déficit (h)"})
                .to_html(escape=False, index=False),
                unsafe_allow_html=True,
            )

    with col_qhse:
        st.markdown('<div id="section-qhse"></div>', unsafe_allow_html=True)
        st.markdown("### ⚠️ Rapports QHSE")
        if qhse_df.empty:
            st.markdown('<div class="alert-ok">✅ Aucun rapport ouvert.</div>',
                        unsafe_allow_html=True)
        else:
            d = qhse_df.copy()
            d["Statut"]   = d["status"].apply(_status_badge)
            d["Échéance"] = pd.to_datetime(d["due_date"]).dt.strftime("%d/%m/%Y")
            st.markdown(
                d[["vessel_name","title","report_type","priority","Statut","Échéance"]]
                .rename(columns={"vessel_name":"Navire","title":"Titre",
                                 "report_type":"Type","priority":"Priorité"})
                .to_html(escape=False, index=False),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Stock ─────────────────────────────────────────────────────────────────
    st.markdown('<div id="section-stock"></div>', unsafe_allow_html=True)
    st.markdown("### 🔩 Stock pièces critique")
    if parts_df.empty:
        st.markdown('<div class="alert-ok">✅ Tous les stocks sont au-dessus du seuil.</div>',
                    unsafe_allow_html=True)
    else:
        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            fig = px.bar(
                parts_df, x="part_name", y="quantity",
                color="vessel_name", color_discrete_sequence=PLOTLY_COLORS,
                text="quantity",
                labels={"part_name":"Pièce","quantity":"Qté","vessel_name":"Navire"},
            )
            fig.add_hline(y=parts_df["min_quantity"].max(), line_dash="dot",
                          line_color=C_RED, annotation_text="seuil min")
            fig.update_layout(height=220, margin=dict(l=0,r=0,t=10,b=0),
                              paper_bgcolor="white", plot_bgcolor="white", showlegend=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        with col_s2:
            d = parts_df[["vessel_name","part_name","part_number",
                          "quantity","min_quantity","unit"]].copy()
            d.columns = ["Navire","Pièce","Référence","Qté","Min requis","Unité"]
            st.dataframe(
                d.style.apply(lambda row: [
                    "background-color:#fdecea" if row["Qté"] == 0
                    else "background-color:#fff8e1"
                ] * len(row), axis=1),
                use_container_width=True, hide_index=True,
            )

    st.markdown("---")

    # ── Voyages ───────────────────────────────────────────────────────────────
    st.markdown('<div id="section-voyages"></div>', unsafe_allow_html=True)
    st.markdown("### 🚢 Voyages")
    if voyages_df.empty:
        st.markdown('<div class="alert-ok">✅ Aucun voyage enregistré.</div>',
                    unsafe_allow_html=True)
    else:
        d = voyages_df.copy()
        d["Départ"]  = pd.to_datetime(d["departure_date"]).dt.strftime("%d/%m/%Y %H:%M")
        d["Arrivée"] = d["arrival_date"].apply(
            lambda x: pd.to_datetime(x).strftime("%d/%m/%Y %H:%M") if pd.notna(x) else "En cours")
        d["Durée"]  = d["duration_days"].apply(lambda x: f"{x:.1f}j" if pd.notna(x) else "—")
        d["Statut"] = d["status"].apply(
            lambda s: _badge("EN COURS", C_GREEN) if s == "active" else _badge("TERMINÉ", C_GRAY))
        st.markdown(
            d[["vessel_name","departure_port","arrival_port","Départ","Arrivée","Durée","Statut"]]
            .rename(columns={"vessel_name":"Navire","departure_port":"Départ de",
                             "arrival_port":"Arrivée à"})
            .to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Équipage & contrats ───────────────────────────────────────────────────
    st.markdown('<div id="section-contrats"></div>', unsafe_allow_html=True)
    st.markdown("### 👥 Équipage & Contrats")
    if crew_df.empty:
        st.markdown('<div class="alert-ok">✅ Aucun membre d\'équipage.</div>',
                    unsafe_allow_html=True)
    else:
        today_dt = date.today()
        d = crew_df.copy()
        d["contract_end_dt"] = pd.to_datetime(d["contract_end"]).dt.date
        d["Fin contrat"]     = pd.to_datetime(d["contract_end"]).dt.strftime("%d/%m/%Y")
        d["Jours restants"]  = d["contract_end_dt"].apply(
            lambda x: (x - today_dt).days if pd.notna(x) else None)

        def _contract_badge(days):
            if days is None: return _badge("N/A", C_GRAY)
            if days < 0:     return _badge("EXPIRÉ", C_RED)
            if days <= 30:   return _badge(f"{days}j", C_ORANGE)
            if days <= 60:   return _badge(f"{days}j", C_YELLOW)
            return _badge(f"{days}j", C_GREEN)

        d["Statut"] = d["Jours restants"].apply(_contract_badge)
        st.markdown(
            d[["vessel_name","crew_name","rank","nationality",
               "contract_start","Fin contrat","Statut"]]
            .rename(columns={"vessel_name":"Navire","crew_name":"Marin","rank":"Grade",
                             "nationality":"Nationalité","contract_start":"Début"})
            .to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )


