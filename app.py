"""
PSM — Predictive Staffing Model  v6
McKinsey-grade editorial design.

New in v6:
  1. Load-band optimizer — target pts/APC range; FTE derived monthly from demand
  2. Attrition-as-burnout function — overwork amplifies attrition
  3. Stress test tab — volume shock with comparison overlay
  4. Marginal APC analysis — cost of one more APC, payback, months saved
  5. Hire calendar tab — explicit post/start/independent dates per hire event
  6. Attrition sensitivity slider — overload factor control
"""

import streamlit as st
import streamlit.components.v1 as _components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
# No external API needed — executive summary generated from simulation data
from plotly.subplots import make_subplots
from simulation import (ClinicConfig, SupportStaffConfig, simulate_policy,
                        simulate_stress, compare_marginal_fte, optimize,
                        MONTH_TO_QUARTER, QUARTER_NAMES, QUARTER_LABELS)

# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
INK      = "#0F1923"
NAVY     = "#003366"
NAVY_MID = "#1A4D7A"
SLATE    = "#4A5568"
MUTED    = "#7A8799"
RULE     = "#E2E8F0"
RULE_LT  = "#F1F5F9"
CANVAS   = "#FFFFFF"
SURFACE  = "#F8FAFC"
C_DEMAND = "#003366"
C_ACTUAL = "#C84B11"
C_BARS   = "#C5D4E3"
C_GREEN  = "#0A6B4A"
C_YELLOW = "#92600A"
C_RED    = "#B91C1C"
C_STRESS = "#6D28D9"
C_GOLD   = "#7A6200"          # Sunshine Gold — logo accent
C_GOLD_BG= "#FDFAED"          # Gold wash for backgrounds

Q_COLORS       = [NAVY, C_GREEN, C_YELLOW, NAVY_MID]
Q_BG           = ["rgba(26,58,92,0.05)","rgba(10,117,84,0.04)",
                   "rgba(154,100,0,0.04)","rgba(46,95,138,0.05)"]
Q_MONTH_GROUPS = [[0,1,2],[3,4,5],[6,7,8],[9,10,11]]

HIRE_COLORS = {
    "growth":            NAVY,
    "attrition_replace": NAVY_MID,
    "winter_ramp":       C_GREEN,
    "floor_protect":     C_YELLOW,
    "shed_pause":        C_YELLOW,
    "shed_passive":      "#D97706",
    "freeze_flu":        SLATE,
    "none":              RULE,
}
ZONE_COLORS = {"Green": C_GREEN, "Yellow": C_YELLOW, "Red": C_RED}
MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]


def mk_layout(**kw):
    base = dict(
        template="plotly_white", paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="'DM Sans', sans-serif", size=11, color=SLATE),
        title_font=dict(family="'EB Garamond', Georgia, serif", size=14, color=INK),
        margin=dict(t=52, b=60, l=56, r=48),
        legend=dict(orientation="h", y=-0.22, x=0,
                    font=dict(size=11, color=MUTED),
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
        xaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=11, color=MUTED),
                   linecolor=RULE, linewidth=1, ticks="outside", ticklen=4),
        yaxis=dict(showgrid=True, gridcolor=RULE_LT, gridwidth=1,
                   zeroline=False, tickfont=dict(size=11, color=MUTED),
                   linecolor=RULE, linewidth=1),
    )
    base.update(kw)
    return base


def fte_for_band(visits, load_target, cfg):
    if load_target <= 0: return 0.0
    return (visits / load_target) * cfg.fte_per_shift_slot


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG & CSS
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="PSM — Staffing Optimizer", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── BASE ─────────────────────────────────────────────────────── */
html, body, [class*="css"] {{
    font-family: 'DM Sans', system-ui, sans-serif;
    background-color: {SURFACE};
    color: {INK};
}}

/* ── SIDEBAR ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: {CANVAS} !important;
    border-right: 1px solid {RULE} !important;
}}
[data-testid="stSidebar"] > div {{ padding-top: 0 !important; }}
[data-testid="stSidebar"] * {{ color: {SLATE} !important; }}

/* Sidebar tooltip icons */
[data-testid="stSidebar"] button[data-testid="tooltipHoverTarget"],
[data-testid="stSidebar"] .stTooltipIcon svg {{
    color: {MUTED} !important;
    fill: {MUTED} !important;
    opacity: 1 !important;
}}

/* Sidebar inputs */
[data-testid="stSidebar"] input, [data-testid="stSidebar"] select {{
    background: {SURFACE} !important;
    border: 1px solid {RULE} !important;
    color: {INK} !important;
    -webkit-text-fill-color: {INK} !important;
    border-radius: 3px;
    font-size: 0.92rem !important;
    font-weight: 500 !important;
}}
[data-testid="stSidebar"] input:focus, [data-testid="stSidebar"] select:focus {{
    background: {CANVAS} !important;
    border-color: {NAVY} !important;
    outline: none !important;
}}
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="base-input"] > div {{
    background: {SURFACE} !important;
}}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] [data-baseweb="base-input"] input,
[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
[data-testid="stSidebar"] div[class*="InputContainer"] input,
[data-testid="stSidebar"] div[class*="stNumberInput"] input {{
    background: {SURFACE} !important;
    color: {INK} !important;
    -webkit-text-fill-color: {INK} !important;
    font-weight: 500 !important;
}}

/* Sidebar labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stExpander summary p {{
    font-size: 0.67rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.11em !important;
    color: {MUTED} !important;
}}

/* Sidebar expander headers — gold underline accent */
[data-testid="stSidebar"] .stExpander {{
    border: none !important;
    border-bottom: 1px solid {RULE} !important;
}}
[data-testid="stSidebar"] .stExpander summary {{
    padding: 0.65rem 0 !important;
    border-bottom: 2px solid {C_GOLD} !important;
}}

/* Run button */
[data-testid="stSidebar"] .stButton > button {{
    background: {NAVY} !important;
    color: #D6E6F2 !important;
    border: none;
    border-radius: 3px;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase;
    padding: 0.7rem 1rem !important;
    width: 100% !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {NAVY_MID} !important;
}}

/* ── MAIN AREA ─────────────────────────────────────────────────── */
.main .block-container {{
    background: {SURFACE};
    padding: 2rem 2.5rem 3rem;
    max-width: 1440px;
}}

/* ── TYPOGRAPHY ───────────────────────────────────────────────── */
h1 {{
    font-family: 'EB Garamond', Georgia, serif !important;
    font-size: 1.9rem !important;
    font-weight: 500 !important;
    color: {INK} !important;
    letter-spacing: -0.01em;
    line-height: 1.15;
    margin-bottom: 0 !important;
}}
h2 {{
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.63rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.18em !important;
    color: {MUTED} !important;
    border: none !important;
    border-bottom: 1px solid {RULE} !important;
    padding-bottom: 0.4rem !important;
    margin-top: 2rem !important;
    margin-bottom: 0.85rem !important;
}}

/* ── METRICS ──────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {CANVAS};
    border: 1px solid {RULE};
    border-top: 3px solid {NAVY};
    border-radius: 3px;
    padding: 1rem 1.25rem 0.85rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}}
[data-testid="stMetricLabel"] p {{
    font-size: 0.63rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.13em !important;
    color: {MUTED} !important;
}}
[data-testid="stMetricValue"] {{
    font-family: 'EB Garamond', Georgia, serif !important;
    font-size: 1.8rem !important;
    font-weight: 500 !important;
    color: {INK} !important;
    line-height: 1.1 !important;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.72rem !important;
}}

/* ── TABS ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    border-bottom: none;
    gap: 1px;
    background: {NAVY};
    padding: 0.4rem 0.4rem 0;
    border-radius: 6px 6px 0 0;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    scrollbar-width: thin !important;
    scrollbar-color: rgba(255,255,255,0.25) transparent !important;
    flex-wrap: nowrap !important;
}}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{
    height: 4px;
}}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-thumb {{
    background: rgba(255,255,255,0.25);
    border-radius: 2px;
}}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-track {{
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    font-size: 0.62rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
    color: #A8BDD4 !important;
    padding: 0.5rem 0.75rem !important;
    border: 1px solid transparent !important;
    border-bottom: none !important;
    border-radius: 4px 4px 0 0 !important;
    margin-bottom: 0 !important;
    background: transparent !important;
    white-space: nowrap !important;
    transition: background 0.15s, color 0.15s !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    background: rgba(255,255,255,0.10) !important;
    color: #FFFFFF !important;
}}
.stTabs [aria-selected="true"] {{
    color: {NAVY} !important;
    background: #FFFFFF !important;
    border-color: rgba(255,255,255,0.15) rgba(255,255,255,0.15) #FFFFFF !important;
    font-weight: 700 !important;
}}

/* ── ALERTS ───────────────────────────────────────────────────── */
[data-testid="stSuccess"] {{
    background: #F0FDF6;
    border-left: 3px solid {C_GREEN};
    font-size: 0.84rem;
    color: #064E3B;
}}
[data-testid="stError"] {{
    background: #FEF2F2;
    border-left: 3px solid {C_RED};
    font-size: 0.84rem;
}}
[data-testid="stInfo"] {{
    background: {C_GOLD_BG};
    border-left: 3px solid {C_GOLD};
    font-size: 0.84rem;
    color: #4A3800;
}}
[data-testid="stWarning"] {{
    background: #FFFBEB;
    border-left: 3px solid {C_YELLOW};
    font-size: 0.84rem;
}}

/* ── DIVIDERS ─────────────────────────────────────────────────── */
hr {{ border-color: {RULE} !important; }}

/* ── DATAFRAME ────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border: 1px solid {RULE};
    border-radius: 3px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}

/* ── DOWNLOAD BUTTON ──────────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {{
    background: transparent !important;
    border: 1px solid {RULE} !important;
    color: {SLATE} !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.10em !important;
    text-transform: uppercase;
    border-radius: 3px;
    padding: 0.45rem 0.9rem !important;
}}
[data-testid="stDownloadButton"] > button:hover {{
    border-color: {C_GOLD} !important;
    color: {C_GOLD} !important;
}}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
for k, v in dict(optimized=False, best_policy=None, manual_policy=None, all_policies=[]).items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"""
    <div style='padding:1.4rem 1.1rem 1.1rem;border-bottom:2px solid {C_GOLD};margin-bottom:0.5rem;background:{CANVAS};'>
      <div style='font-size:0.58rem;font-weight:700;text-transform:uppercase;letter-spacing:0.20em;color:{MUTED};margin-bottom:0.4rem;'>Predictive Staffing Model</div>
      <div style='font-family:"EB Garamond",Georgia,serif;font-size:1.25rem;font-weight:500;color:{INK};line-height:1.2;letter-spacing:-0.01em;'>Staffing Optimizer</div>
      <div style='margin-top:6px;width:28px;height:2px;background:{C_GOLD};border-radius:1px;'></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Getting Started tile ─────────────────────────────────────────────────
    _gs_pdf_b64 = "JVBERi0xLjQKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSIC9GMiAzIDAgUiAvRjMgNiAwIFIgL0Y0IDcgMCBSIC9GNSAxNCAwIFIgL0Y2IDE2IDAgUgo+PgplbmRvYmoKMiAwIG9iago8PAovQmFzZUZvbnQgL0hlbHZldGljYSAvRW5jb2RpbmcgL1dpbkFuc2lFbmNvZGluZyAvTmFtZSAvRjEgL1N1YnR5cGUgL1R5cGUxIC9UeXBlIC9Gb250Cj4+CmVuZG9iagozIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhLUJvbGQgL0VuY29kaW5nIC9XaW5BbnNpRW5jb2RpbmcgL05hbWUgL0YyIC9TdWJ0eXBlIC9UeXBlMSAvVHlwZSAvRm9udAo+PgplbmRvYmoKNCAwIG9iago8PAovQ29udGVudHMgMjMgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNSAwIG9iago8PAovQ29udGVudHMgMjQgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNiAwIG9iago8PAovQmFzZUZvbnQgL0hlbHZldGljYS1PYmxpcXVlIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMyAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0Jhc2VGb250IC9TeW1ib2wgL05hbWUgL0Y0IC9TdWJ0eXBlIC9UeXBlMSAvVHlwZSAvRm9udAo+PgplbmRvYmoKOCAwIG9iago8PAovQ29udGVudHMgMjUgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKOSAwIG9iago8PAovQ29udGVudHMgMjYgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKMTAgMCBvYmoKPDwKL0NvbnRlbnRzIDI3IDAgUiAvTWVkaWFCb3ggWyAwIDAgNjEyIDc5MiBdIC9QYXJlbnQgMjIgMCBSIC9SZXNvdXJjZXMgPDwKL0ZvbnQgMSAwIFIgL1Byb2NTZXQgWyAvUERGIC9UZXh0IC9JbWFnZUIgL0ltYWdlQyAvSW1hZ2VJIF0KPj4gL1JvdGF0ZSAwIC9UcmFucyA8PAoKPj4gCiAgL1R5cGUgL1BhZ2UKPj4KZW5kb2JqCjExIDAgb2JqCjw8Ci9Db250ZW50cyAyOCAwIFIgL01lZGlhQm94IFsgMCAwIDYxMiA3OTIgXSAvUGFyZW50IDIyIDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iagoxMiAwIG9iago8PAovQ29udGVudHMgMjkgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKMTMgMCBvYmoKPDwKL0NvbnRlbnRzIDMwIDAgUiAvTWVkaWFCb3ggWyAwIDAgNjEyIDc5MiBdIC9QYXJlbnQgMjIgMCBSIC9SZXNvdXJjZXMgPDwKL0ZvbnQgMSAwIFIgL1Byb2NTZXQgWyAvUERGIC9UZXh0IC9JbWFnZUIgL0ltYWdlQyAvSW1hZ2VJIF0KPj4gL1JvdGF0ZSAwIC9UcmFucyA8PAoKPj4gCiAgL1R5cGUgL1BhZ2UKPj4KZW5kb2JqCjE0IDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhLUJvbGRPYmxpcXVlIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GNSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjE1IDAgb2JqCjw8Ci9Db250ZW50cyAzMSAwIFIgL01lZGlhQm94IFsgMCAwIDYxMiA3OTIgXSAvUGFyZW50IDIyIDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iagoxNiAwIG9iago8PAovQmFzZUZvbnQgL1phcGZEaW5nYmF0cyAvTmFtZSAvRjYgL1N1YnR5cGUgL1R5cGUxIC9UeXBlIC9Gb250Cj4+CmVuZG9iagoxNyAwIG9iago8PAovQ29udGVudHMgMzIgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1BhcmVudCAyMiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKMTggMCBvYmoKPDwKL0NvbnRlbnRzIDMzIDAgUiAvTWVkaWFCb3ggWyAwIDAgNjEyIDc5MiBdIC9QYXJlbnQgMjIgMCBSIC9SZXNvdXJjZXMgPDwKL0ZvbnQgMSAwIFIgL1Byb2NTZXQgWyAvUERGIC9UZXh0IC9JbWFnZUIgL0ltYWdlQyAvSW1hZ2VJIF0KPj4gL1JvdGF0ZSAwIC9UcmFucyA8PAoKPj4gCiAgL1R5cGUgL1BhZ2UKPj4KZW5kb2JqCjE5IDAgb2JqCjw8Ci9Db250ZW50cyAzNCAwIFIgL01lZGlhQm94IFsgMCAwIDYxMiA3OTIgXSAvUGFyZW50IDIyIDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iagoyMCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDIyIDAgUiAvVHlwZSAvQ2F0YWxvZwo+PgplbmRvYmoKMjEgMCBvYmoKPDwKL0F1dGhvciAoXChhbm9ueW1vdXNcKSkgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDMwNTAxMDExNCswMCcwMCcpIC9DcmVhdG9yIChcKHVuc3BlY2lmaWVkXCkpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDMwNTAxMDExNCswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0IChcKHVuc3BlY2lmaWVkXCkpIC9UaXRsZSAoXChhbm9ueW1vdXNcKSkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iagoyMiAwIG9iago8PAovQ291bnQgMTIgL0tpZHMgWyA0IDAgUiA1IDAgUiA4IDAgUiA5IDAgUiAxMCAwIFIgMTEgMCBSIDEyIDAgUiAxMyAwIFIgMTUgMCBSIDE3IDAgUiAKICAxOCAwIFIgMTkgMCBSIF0gL1R5cGUgL1BhZ2VzCj4+CmVuZG9iagoyMyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCA3ODkKPj4Kc3RyZWFtCkdhdG05OWxKYE4mQUBaY2siKThRaD0lYjRNK1QzcyNST1RyakNXdDpOaiwnODdUS0o6QkBeRDxLTDQwOlhEQ0AlXTVQRj9YOUVRSl9TOS5VXmY6SC5eJ0c4X09wcV1BMWFMWyw6J05vZk4xMjVZKUFuTVtZJHRkKjNHQW9PZ0hrKGI+PEx0VSQkP0hBJGYlbW8uNGQvKUBgcCEoMT9OOChtNFBeREouOjdlRSlvJ1UtQ20kcihtNC5aXmItKEM3WG5uSUBQVjxxSWMyR11uUGZQL2RKal1CL2BeR3RVIVxLWmxPRzVBTEZOLTotTDFZJTsxUidaQDpiJ1FaP2ZXUmkvdCleMkVcSnBsTiJRVFArRWAnM2stSSRZQE1tTTokXz9bKV5XKF1ATUctS2JbT3BkaVs0KTRDb108SGVsWTI0V01JPFxyPlpPblszMGRALXFGXTAjNTVoX0s5SXBCUEF1YVpEXk1cXi9mMlkpbyo3Zi0rTHJXLmdgPHJEIydNVmtuUzFoO2IzUCNNQWBXW2NXamFbcGMwP0spWmEwLF5gJy5FYWwiNi1HPkY4RlZDajRJMCY/KSZYcjNcPTRyWlczRFpQNjdVJSMxRScoaFBrazN1Xz1aUlxSPk01LmpOajxRM3VOQ0dPUTFvNXQ3M0toL2JyXCwuKDJyITt1MC9BNzEzQ1dPW0dXdXBaLzYwKy1SbXFRMz40JURfPjJFdFNWRF9ZSHVWJ3R1Nk9RZlxNbSEhMC09IV1xcFk/KDE1Xi5wRXRdNWZCc2JRTFdhW1RxMCU5OlIwbVxFUllOVS9cNytga29mT25gNjpCZVYjUmFwS2BzXG0xPmZIVFYrWE85M0YidWI3Xl9WclVCXS9aKDAqWDo/RiRyP3Eua2dYMDstNm9fc2UiLG9zbDhJMUtFTmdMTkA3aE4mSk5vPE0+IW1qTy4xJCFROzU+SCYpWWowK2E1L1tUY0FiYzk4JW8rcD9PLlVBKzxFJEc5SXJYR0tUUEZpQXVoYU1iKkhfaEtEWDRERzErPiJILiFUSm9hQUh+PmVuZHN0cmVhbQplbmRvYmoKMjQgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjg3Ngo+PgpzdHJlYW0KR2F0bT0+PnM5SSc3SjMxa2ExKk8+RzExNEhmIylnSkxyTDcvV3JfKz89W2JkLyEyXG0/I1tIYXAmNFVRb11UYGRbWGdcQUpaNyZARkFKT3NkbGVfKEZTbiNHY1l1MkJoUFlRPiRvMU5JVmUiR0s6Jlk7KnImPVlnZDwpOzwxTXRTNElTW0hMVWAjSjIzWSg4WDJecFkzOjEmKGFgQ0ElaFkkQj9HOltHQF9WVyFcTSlndGZWT180PDBON04/Z0Fya1ZdOnVZND89Ri4uYVkuOU8qY2dBOT83aU1FN1EiWHRmUk9eP1VIKExgJllcUU4wX3NvJiNJbWgyamtqbkxgRTk1UiQ1UTowMnI5Pk00P0NxXVtoTklvMHInMSNQazBFXlQ+KXE6RiVGUTZOMEtlLixqWmhUYlRzaV8pJHM2cSpvI0g9TVpQXmImcTFEV0JHXVM8cGZGWHRSRCRNc0UlNDpWTDgqYk4pbTI8JCdvXChGSkcva3A/ZVspTzRAZUVocidDJV87N3BpVC1WOiYoJSc1OiNjIURdRy8tPmwsOEhaVV5jRV9eNyZPOGtKWjQrQUUra2lkR1Y3V2IyZG5LUnM2akVGPktTU3BNbGNnXUxQTDs/UUZcWnRvQ11WXSElIWM/RSlTXGk/cD9lVVU3UDs0T0pLT0g8Wm9fQHReP2ZqWEdyXURnU1FTUDc1Lj5nMmJuJm1SLmMibEIkWylBbFdoZTUvcitVPkdnJTJhXjlqTykhUEsqQnFWJz5HMiE1PEtOcWQlL2c2WnQ/OiVuOHVcIkg+ak9GO0hHVE8/VXBFbk0qRGU1J19ycUQpNGtnYzlXKWtrVUl1Sl1LWUZdJUlzWGh1Qj5BSTwnTzQpPlcwM2c0SlFVJDtea1NmJzpsbzUjSnFVR3ReXnBFcE1ZPkNqLT82UGlXUV0nJld0KlgzV3FNRjZJM1ZHRjFfKUIoMC5AL289ZiNdJzJBQD5gQTtbXTxKWVN1LVJgQEZcUj47dDA4LzkpZSJfRitCWE9lV1dfJzNBSEBOIi5CMV9EdDAscjJQOydac1hCX2JDVz9XM1QrWkFaKDVbJ0FuXzJPK1Isck5RU21ISSktcDdAZ0osMz1WLWxFVm82VXFXRl0nSkBHIm1hZ1pKZ0VlYlIkJUJULCxCO145XWtabEBVOFs/PFsrSycsdVw5RFZzMC0nXVpHZlgqSyU5N2lSNDBTLkZcP0hgJFQjVl40IT5WQFlYOHU0MDtbdXUkQFM7V1Y1QjlKPS5QWyssYmBKKFU0WmE8VHVpL2o3YDRzTllaMENSZlNvITZRMEFLSDQ4QDRDZF8vUnJITyZbYklaIS4oUzxQQlx1ISZBb2giTlxEbTovL1MxOEJOaGVJMnM3azxVPXE/UjEiSmlDZ1BCUFlnKlpqZlI5I1klNV5eIk1KWlhxZFdYMkYlLWUvZyhQKWxiNGA5XkF0LmdkQGxDQz5gU01uaXA1WFZzUD80UiJ0X2lhJGs/XF1sSTRfNkY6OkUlWCxVQTVyYVBBKzJQXzwsOCpOPy41MnFyP1dKO0VcVy0zMS8lbDNhImFSX0NMVjAhUWgsQm1ZJzA8VDZuVEAtMCFaMyliQl1WNiVgXVlYQTFHa2lhcVVjPWJaUVJWLG5tNWEpXzhmYCEvZElnWidGKUQiXkBQSmlCRWQ4TUUhL3EpR0ctTzlnbUc7L3NqUEYhMVNlWi1qaiFrUSQnJUcxTjVhTE1bNnRKXD85Km4jajNxVFlaaDhFTUcycXUpRSpeVmU6QFdoXGpbNStMUDcvLiJiZTZHRi8rUSYiW1EvMiJiPUZlQUA6L3VRR0dIJWxoVCo8Nls9Z3QrTjJlP3BXQSgtUk1NK2onPCs8Y1ZSXXJSTVAjbWI4TUkrNi44WldcN1YlMVhiIzlZJV9mIkZkQjt1U2khcXAldHEycDhYYChyJ3UhbWRAPlxzNGMzRGtVK0YtOkx0N2ZgNls+KFlfWFQydVw2Xz1pKT1cUlJqO004MiRGKWBmTiI9VChLJGNDNyFuYExOOHVnOCdUJjwvPWlLbSYrdW1zbkVEKThUbm4kOTdbVVlKXUFvViVlSlkhWjM7ZGNMWElLQzpcSG1bMUVEYy9hN2tQImo9MDQ7cUhbWGxlLmgtLHFUbEQ3bWFAKWxfcGFjUSohZyszay1vKzxoWEZpRlYzVSVaUS5rZG4wOzVbZ19cXElqcGciJ3BKbilPVVJFaGhASyRlbSlhOXMzMklaPERDKkJKUDBOb0ZRPGVDaWRQNDNbWWNnQGVHV1QpaDUvMSliJ0FcWjZ1T1s2b1I1IldSRGw5W205N2FeZl1AOWRWUDhUbktVKEszcCw9ZWg4MUc9LzdjUXRJYSYlM2ZHKidbJSs1ZFg5RUtgQT0naUtWaHNVKzVAb01rMXJQZD5LTyhmSDImY1ZjUzRKOi4oPztJS1dQOllXYVgoTD8+THF0W0NqSWZfRjw6Q2QmbjQ9QT5pKyFAMUFhcUNyal9dcXNdMUVnbV0nYkohMHFTUSlYJDcrKy1AcHIuTigkWmVbM11mX1k4SVtUT2YrNmFlRVFLa0hqanAwNWFVKShybjU3bHFMIV4yRXNcZWphOFk8I3JKYztVSTkjO0E3ITJwcTMmXSJTcksmXV9XX0NNPDkoVDoicV0lbFhXL3R0NUUxOHJWYFInITg9Qld0ZGQhVkNnM2cmWWBTbE1HRmVrOV1ocypQTUBvOWk6YiluRnFrcVhhT0k/cGxCb1FjJFlpcGlxZGQ6YSg8TjRKQ1pyW1YvOGNVaG9uMFkqNkIqPixkKm1VV2IuZ1h1L1dHPTsqKloxdV8kSixpSmVTLC1FYV5pTkVWN0g9QztuailxMDQjW2RISHBkM1E0aTYrRj9dTVBxb1AnJTtEIzYpOktbVitiSm1mIVhAXjVnTjhgZ2BWWktlVm1HSjgpQFptPT0uUy1SWEktXihrSyI5UHNJV2lRQ1ZNXWlbPlhNbS47cEs7RShsRWlfL05LPVtpSi4lbiRHPihEV09MO1c9U2RtKEwzJDFVIiEmV1dsVTVAIXFkPDhIQ2YxQFI3K1M0MWRmaVlnJDFRJz85U2A2Py51XGFiQDleLlhecmlWbzMkbGtlWEU0cE9UcURLMSUwZihyNkMyYmVHcz8scEwtLCwzcyQyQDNjRDRmdT0zOFxNVThDI2UjdFE1TkpEUTYjaW5PR1tlbitDMHBpVERNdDE4SC1sdGxNPDpCcTApbF4rKCZFJUZSME8sbjFFOC5bci9JJD9oJFwhXkB0MG4+VjkjZl1iM1dWOXNuWVE3IV5MOkpAb0xwbCsqdTFPLyIxMUc4cCFuTFVaOitEPGpPZCZwdSY1aElHbEM9Z0xKMFsnUTBBITJqVFIxKVk6VEdaWipLOlApaUgwKiktN19sckwvYCI/J25HclRIIiVcIjg1I1BiY1xzI0tRUWY1UnJEUFxGKkVIYjBlbGxYYjM5bWhzSlVjWVRZIzA1WDU9MkFTcXNNbWE7VD8sI190UWJoYDtbJnFyLEojRmEoO1RDaktqJF82NnErZyIrKWtnN2ZsbFRrXGFjTUxsbnREKldUZkE+bigmOHEiP3JOM1M2ZzgxUGY3KnVxWTdsQTtULjEnVTpIcHNyS19vTExnYmNdcDdRLm8wWFpbPnM6a2BJR1lrOmw1czgrVTc1aWpDITorTi4rYD9OQzRrLTplaW9Pc0ZaYSpaQ3UjKVYpNVVVaWdHPWlZRG0xJFc/W1wiMUw6U01lJmQxV3VQMmYlL1NZPkA1X0FYWV8qLFpZaDs7aDJwMEQ+ImBVK2UySjpIb11IMTY7Rklxfj5lbmRzdHJlYW0KZW5kb2JqCjI1IDAgb2JqCjw8Ci9GaWx0ZXIgWyAvQVNDSUk4NURlY29kZSAvRmxhdGVEZWNvZGUgXSAvTGVuZ3RoIDI3MTEKPj4Kc3RyZWFtCkdiISNdQ0pYITMnKWcrWlciNCpKbGpBXi9OaiNoJCRCc3Jybl0zJjNlT1koJVMuPihMQSo8W2hQTDlAIXBKZm1tNixLaU4mY2I0aGgsVzlSbExfJmpLNjcjMGxAMWM/M1hZKj9mSEEpLT9xPyRTZmJCclQtZVM9YlN1K1RvVkoyNmtxYj5vOzhNX3BERjwmSGtwQ1tvLiorKmQvYEJfVmJXKGJZL0dEcmVTZHI3bWIlSCNeKlVtXHJXQjhcS040aVhRLi4uXGQyQ3FWaGZZLjpyU2NZXjdqN2lNRTpRIl5YXGw2U0RKSChMXWUwa3NDQURaPj1QSW1pKmZuIk9zWFxJPkRZWyNVM24vbDFdalduZl04Tklubm9wbW49ZGZETy1zamQ8YyFPUVAyTWlGKjBKcyouPXVnMjloRllSPSppOkhDZVdBbWhlWUZQOmhXSUZkZztSRj9RPF8mZWJvL2IoTWFvMChfIU43aylsZVY2JztiKzpfPmNjMChGaC4mKjRcRyhBNEkqSFxzOUBxazE5RkNWSTBJLERCPTlWanFfKnNlLCw8QVEqa1hWKWNoRU9mVGk4QC1PIjFqcDhkNV50R1pkbDFIY1lrZ0llKm4sQl0mSSVaW0lpUUZKWFk5JD50IUYoWikyTDwxNyI0V2tiTCwkIUZdKDtOdWZzZ0VMJztASnBNR2MxUldvOmBTc2djTDgwJSU5bnNlW2Q/ZCJ1YW1hO1NtcWVRaF5DInJLVXUpLCtmdE48YFIvNS1BRklVOWRgWURQYVQ3JlJyR1c4cWw0JDpFbUF1UW01IUN0cV4zaVVNYUB1PkxXM1E5QnVgLGRDdFAlJEYmLiQiVCc6MVg2ZEIobUs4JGpRTDo4NGU5Jis+VnEvUUJdUnNMc2RSI1c6TS48QmYtV2I2ciY/YE5wc0orLVE8I2E/ZTglMVcoPkNJTGFJcDtQJWcuaTQ6VGJ1Nkp0LlkwL08jKjsqTmFiYGU7NnVRZkc9TjoxUip0S1ZPclhAW29oZ18pRkJOQDNqbCFZLllNWmZDYzJoPkNQSGNhYFs2JFFvR2o+RW5vXmkjSk0mbltRaHFGQ2JudEwlZSpTM0xUWTZnSj44Syk9JUcoL11KVkxvLGNAcXVtdVsmSkM9V2YuL3MjYEFkI008LiVeZUNWTzdvbltyVjl1SF1GKHUqPksqWVZaPWRMV1lqUExVSmBHSjUtOW4nR2csS19VVW1pYyYzIkZcUFxoT1ZKaT9KZUU8XTopJUsycHJnZUo+czwhI15TQFQkZyJAJkpOQ2tdMFFzQT5gTCtlSyMwOmRxIysjXzZsNlpmYm9qOixVRSJwL106WCl1NERaIURHMDNXVjhhVGdkXzYjSF8iYjIkOl91UTUwUUMtLCRPTENnNS1kZCpicVxQdURyI0ZrJiRbM0NxbVVrXGNRbTFSOGRuci04UWM3XjYqVUw8W21VK0V1VUkqbUQuNnEqPz4yRz0tSWpVaE84YVZkaE9jUTRbKG84bE8mdGxdb1guM111LUFQcj4qMmVqUTRuJ0M7T25nRFJPWzFJOShzUCEpTFhGbTQzXiEhU1xZLDM1VjI0QjU5Iy1XQUlEZUdPQmgrRTdxKilYWko8M08mYTpAdWUzVCtQTlVpOV06UF9oYHBKZGAnOWg8TmxRaE1XJzYqVEduP2lZdW8zaj5gPGA3OUhBPU5hZEU2WkIwa2VBQGUvdCw4KiM1N3UubzInUUhdU2VzT2YwR0pGNzhpSjxBZEEyYitQOV1zdF5dZStzWksjWSg/Wz1aQ1FYY0ZsRDAhNmdaZSs5YmJGKjJxWyFHUVcrJXNoa1lmPjYuampcSCRpPGJxVTNITDdhP0pCR2lWMFwvXlMpTC5SZ0hwJElsbWZdLWs+bkE9VkdTKjsqISRqJ09fNlIjSDo1J3EoRDB1cCU8MytjPmlVKFAlaDImUm8saXU8WThbR1tYUHVKTjFPY0QvIS10NmomLSQjbnRXUDRZQDY8UmZwPylxRzhFanEwbGAnaG45RXFMS01fdGYtSGpWJzpLMzxqNVBVM1ZqdFlaXyVdM0xoXFo2OTJjdFxobi5oJyRaVDQ6NFEyYDVOM3I+Pz1rZSZwXTBKIT82RXQ/MSJOPiorRzYpclRyJ00ybnRNa2VJPTNbSW0zUDNnLyVmUls4b19uQFFecCM1Q3FbXC0qcmREX25BMz4jREs8IUVMVUw1LHJMJyxEVCRyTGxFLVZvV1dgQzEhXUhFQ19Db1FHPjdnKlFwJHEpN2BUNXBiZkovX01hLGMlZmYrdHRMKjFzIVQ6IVJbOFwkI2wla1hfOFh0Nm0rcS48ZmtsaFooWmpQUl0nPl9pZU5DPW0jPURBRF1mRGFAaFFjVjxOQWhhVy1dcStvaElRYUNXW2EibCthLD1rL0lTKGBsMzNxTE5GSSU4ZFsndDkwXmktI0AoSCw0TzUyWCciRm4ycVttUCdXaCxkKSRTZm4nVyxtKGwjVlhgXEdPLjZaUDx1NChHOVZUJHI9XlFJXk1SW3EzUjMhMmlpZTVwJ2cpT3RZajtdNiFCP11HWDVLY0Y8TiJONS1yTUZWaSFOJCo3TE9OPzFmb0xsT05QWmIsPFUyUFNbVDhLcHMoY2AhQyFsLERfMyY3TV1VIzJpa3RjW2ZlSV00SGU0bUJsWCZhU0ZKdWg/PTpuZjNwX0hLZVpwP2EuSW5CSFE3alMyajtsMEw9Q2FyXEZkLzZhMyZLZWdaIlpjMHRpZFtHdCsvKFFdXlhEdChYM2dSTlY2XDhjaGtlYy9YTWo4JypTJmA/X09TbzYyQHFyYWxrcyI7WTU9Zl0pXGxVPUtiaHNYJ08+OWNXRTZRbURUbkQ2QllTMTlqdURSJFNZSjlCaD5TVENDWj1IaUheYSJhPCxjaGxCS0V1OT8lZ2hfWSZsQSJvcWRtZUkpbzMjajBlSkpqXjw/JT4iQlokVHNnLCciTUxkTFFzSWhxbDhuY1pNTlRDcTdrQlUzNGQ4Zy5UbUBmSUdzUVkxPS9oKVJBMEBRbSJ1N1g7aT1faXU/WC1hMkgkKDYkMSNSTCpgLTMyZWdnQiVLZGswbktbTEJYJ0omPShuaW5uXyFPLDNnUm4qOSY6aDxFPk1YLENsWVpKVHRGXCdcPEIhbCpOLSRtN2UxW1tZRUVZMiJ0O3JPb2gxJk4hVlJSTG1QY2cmbSM+aVJUIlQyOEtcXUovKF5sRlsmZVdAWmFBQmw2cWFvcm1jQ2pFVipOb3FoZ2REMUMyLidlcEVYXTMjakoxOz4hQkM5KFZWbWV0NkJSYSRKMSQ6XE5fK3E0LSNvSC9nRVFjLnBdSi9gaEtSbko/Y2hmXzJVVSpAWnNdWjxOLEMtakYhMWtpMCRqZyEoJj5YZGlWPGg5ZSc/Xz9kRkc3IjhVYm9HTTktLVJLPz4zKkNONjYwJEZzM11MP1hlWnVXZVVEPy4kI0dvL1daKVVmRWJldWAsKUUyYVJxNk9wZ2VNak1ubG9CbGVCZ2llMEUzWjA4JyNzJGA6RUAxMmc7Y0xFYUMvJy9xYi4qNVZvTCFRQTBPRWZzNz9yajliP2tLX2ZQTm9yVSc4OW1KUyxJV0RfPX4+ZW5kc3RyZWFtCmVuZG9iagoyNiAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAyMzE3Cj4+CnN0cmVhbQpHYiFTbj4+czlHJ1JvNEhTLVJLKigpRiU/SD4kcWJAYV0/IlxAMGdcQihALywnaXFydDNrQFQzbCZZOW5YLEBFQVRqX2JfVkQtWVttJ0dtQUljJVtjKiI7YyxxREZpSFM6dHAuY0BNR3ItR1hKMTZoaC5HaVBERG9BaVJNQ2c7JlpfMmxsdXJbbGksWitNVHFYOnRUZ2prKDhNQ1FBSk1NSkUtcyJZbF4tJF5oYiglTChESzolKG9jY0dgQFs4I1xgbFhHYmowYVBWXWRHbUNCckhIR0phcGV1RFN0MmQ6NjtuMyMhRFBhXU07QlE9LkMmJjtqPF4pMSliMDEyK1tLQ2VdRFFaKGdBbExqWiY5KmtRTm4tPC4yZyUuUy1RPUMrVyNOalsvSGFqPElJXzVuWEQ6YEQ/OkxRdWhScGQucylVcFxVTFRmW11xbVdiYUNbLCMwNCpaTHFuNDVbK0A9ZFVxKmNEUy5XIjZnVHBXaGhtbzUnWiFhPzZjVjcuXCxUTmR0OTgyWCxYPSxJLnFnN0NYT2gxaVg9PlxMLzFDLnFlQDBiMSIrKmYldG5TVT9UZCZQWUwrTzs1V3NXRGlycEFXYyE3LkA2WEVkOGsuM2YhLjQrVl5FSUNIRGdNYmk2JG5MUEdoOjtkQ083cXAkciZbZSw/b0IpaTcmQnUwWCkuOFBFPGglJ0RfIlFfNEwyQ0AxSEYtL0ZyJjI/MXFxZz44Q3FDN04ibEQpPEZOSDAyaCZJUCZmNzBIcGpHP2RzRzskaFpXKkNtXCR0ZGlBLmIzJXMiMmVbKF11XUlwZ1lIYkduKiI2Ny8zblhWdFlLUGN0XVovNlsqNFM+U1xLQEBAdFpbMWlmImJzVmJnZEF0UlgoW3IqMFReZFVzQzpKdWExa0dPYGpcSmFvITM8Ry5nV1IiPEsmJis/MWsiRTowVDZJUElgOSZkJiIkL0xrb2QpVzpfOjxVcnUmUjtRXClpKGopYWMySSRaUDduZGk3aUM0ajlkLycsX0ssKWMrMj0iWm9KQHJYJCk4dD5tUCgyNCdzTnQrQ2dtIyleVjUtTk1nPl9wT2VyOmE2XSZnYUJnXCY/bURxTywxcyFmPCw+YzswS0hQM0FdSStIQnU7OFIrUG03Nl80PnA5KihXSDJELW1qR3UpJiw3TFE/KCxcRFcubGZMQ1RPKWklI0VNZGhOXXNCa0xJLWQjQSU5RkQ+SlBIJS9NYEhhQVsuKzcyLTdyPzlGPnEoJSwkbENFdG11LiwqRShdTjYoISliWElxdEVCYW0lU0svQl5Za0NYIlNRT3RkIjg/SSNiYz1zMWNVPzhlPityVTIxLyc1WmBmK0M9VDtsdWZmOV9vSjoxQlcnLkUySz1hc11ndXInQiNzY287NTBRJkRZcVstNVJjNEY4JF0qWyU6N0FCJmFcWCRWdU1HcUdJczJuTEVbaUBhL0hDT2QnJDIsLC49YSlRXXM1JW8lJ1taXm9aNClXRTJCc3NfZTUvSSEpOWAqLihfW2ZxRjNBbigvPVZsX3Fya2dHKUtcSDs5Qy5mWEZMYj1aRTV0NywsKmdIZihIJFlBTFRyZGZZK21tWGBLb0JKLG5DT0BiJEcxKk1bJV03Ki8xSHFbMUJcKzdXU2kpKUBAVkwwI2dDZ3U4QFY8aG0tJTxqZS9ec0hyRkQzQChobzU7NXREREFUbCxmX2hhOCp1Nks1RThOWUgiOj87TW85MWBWKVRdbEZ1ckRkbFdJRydjdGI+cSo3IiJiTCNpPykoWiJEKkpOPl9gLEptKkswYGhsUCZKRVcnU0p1RFpubTdyTDRIJipodHFoL3M2YjEyIlEvUVxmKk1VJFlDO0w0Jy5kOzUmPGJJUmw1J1doNTZjZTVPUkQmXkYlPy5NaFQ8c2c+PWM7JEVRJWYoLzZUPClzb1lmWk9GaFhUW2s7YyhkRzwuPGxFJWNgcV9fOkpuZEBSIzA+RmBpK0VtQSRBYktHJElRPVRWJ0puRHEsLmZlMG1GbWI4YlxDcj8oImNnajUhPUdYXDRqazpgUkFkMTwucGMxa2VjRTFWPiE9KERVT0xyNDolYztaNWhOZy5XIjJJODZvTF1yaVh0bzxjQTFpKjsvY3BXRUo6THJcYGImYHJ1Yi51N11hVlBqWFI/YEZzZjtgUStfSTgtdU8+WXBfUColXzgyXDtwKlIxSGA3Z3BjcTlqXVZnZS9GRVpRSGZRSWVdbUB0RTo9XjFwPmZJZSZDYTEwSkZOKTFsVmlBczw/ZiZcPFdPTXNQYGE6YE4sLkVNYkZfRlVpNk0xI19VRzcxb2JgaHBaKy1LTzwxV20lUzJZLVAmdF1MZ2osIyRlNVQ7WSZbWFxJJipSQC0nSiplVGZDK0A5XXNCS2cvPlxwb2lQKVY9IkptWmAnJzZCcEtyMEo4JCYuOEpJTEBtZlFSOmEuUVZeOSZqLkEjWm5vNlJNYTk+cmFuX1BicWxHc1czMmpZNjBJSGhrIWpaY1w+by9URWYnKCgmbTA6LzVELkE0cHJJS0MoW1JNIUhkMStYSyxyQHQ7KG9acTtyLig5Nz9NJHRgYm5UWG01N04uaVQsY2tjKyhHc0FHO09XWW0nQTJnLzBYRzAkJXNANiUpW2w0XVlUUTNgNT5OQjNgUjQxIVktamRWWTMkMnFZJmY8RHFYKFRkOSNQIVM/PlRFZCVub2tsbEQ6R0xESFpxTScyZ283JFZnQkJHNEVvOzohUzRRUyldcFFTLF1AaUBvM0teISYqXlNcOEs2OjM3JEJTSidPVlAmY0ZyUkJHaG08SlY9PjVQRCIwXm5FQT07aj0kTy0vUSRYSmosXiMycXM+al83JCwpMHVcMC5zL0NTWkEpSWNkP28kVy1mLD0lKygrX25wMjcudF8qNHAiSFxsc01SJy9ZMT1KPVJWXic8PjNyb01KS15LVlkxJHVVIkFRLS8pOVZsLyMpMmFxKTtPP3JoQSchYCFZZExMSU5zLC5wQSgkV0FvZkdZLHQnc2RZbUBKL1sxWzBJTSVQI1dzQk0pSU5KTyZfSC44V0JpRzdhLnRqIXRQOzZaaUgtSH4+ZW5kc3RyZWFtCmVuZG9iagoyNyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAyMDUyCj4+CnN0cmVhbQpHYiFTbWdKU3RcJjpOXmxxQjhVQmBzZD0wNFFKZEZAP2ZiYEMkaC5jR1QhazUxcytUOl0uM3JKTyYsTjo3MDguSTtdbz4iUCNiYjBWTC8wMGwtaGVfQCxTNWZoa3FwPT8zSWtGLUM+UToxR0JqMzVdZC5IQl48aFcxWWErVyorMjVRKGo2Mi9bIWcsPzYhXEE+MzdyRkJrKC85aUQkcmlfIU9GXkVgWFhUTCI2UHVFQio/I09kKGlIIzBuKTQoQydTR0QoQU1FJ2tgJUMlMj01YUFCREtALGg5aSo+SkN1UWtGaG1gRyg+dSwqW2EtO0AhPDMraiVFSE1BUE1vKDlQQSJvUzBLT0lpYS9BZ1BVWHAoVSJqbjlYXjBVPjlVVUZybE5YPHBQOVtoJD5Ha0MlUjEkV3VhMUdLNGVRSlc0SkxzMk8qRUFaSStwRSlwJl9cSTVERkJqYkowRldmIUBwJXJBTmMwKSwwcSpYJmxySGdKXUJBKlNTKG81QS9UZ0gxMydxNShnODBrcTtJZ05UaiNBOVI+SVkkRV1xKzFHWDYrQWcuc1s9a2g+Tys9YSNlVzFNckQlQUExRE1OXGZJZiJJYlNGYmtxQSRkbk9pb05iLzU8XzI7UV9GSm5jMTVWSi9ZLVU1MWk5VWRbOSYsKUFpZGZTLipMLkJdbi1mLVVXVFN1I1NeVlBnLVBDJV5RUmJRUWleKEBXMXFtbVAob1JpRWArR3IuXlxpUzAtXzBxaWA1cGoiV0AybkEkNi9gOSFDbTNfPzdUP3VtP25lX2AvbmYiOmE+anE8LjFgKXRnUjInakU2N2NfKCcyWnBXTGIuRF5uZj5BLitVYUZackwoZixhQ2Q8Jko1PCk7Vy1DNT5WZlM2VThUS2ZTYDFrJEpLUSpYVUtvQ15wSi1NW0pCY1BCJWRkMFIzPVJgKyVBP2Nhc2BRPztAXzsiU1okPipRJUZNUXBqMlBKJ1U+KmNJV0d1ZDc4UVBFYTIuLlhZVjB0UzcjZUdvYl0nOy5EcV8hVFNTbVtGZjIzXmdhIlJHL1E3W21OMEtPKyMrRHEvbzgrUyZpZT42MTdPMz5qa0BwbCYrMGojTGFOLD1TbE5qanJLWTxLaSMtLEBQWVV1LEMzNF0oRiEvZG9ca1ZbUXM1QlBob1txVTJXNz9zTUk7Ylo2PVoiOzVPZT90KCgyT2lcc1NJKl5KZTBKZGJhYV5BalgiQjtjQlxUVj8kdXNtZDFEYWZQdUJASkRWZUFSbUhXKy0iJzFJVktsPmpcQU1fLkhRb2Y+aCpUNTs5Wi82K3JbR1hrbGxRNW9kNShUOSNqaj9CJGNHcmlgbSM1NDZITT9FKUlaQ2xBbjQqLWpBMyJuLkJmNixvPUY3Q11jYCVKN01dSWhrUEJVZGRnRV1zMXI+OiltaEJzQ0tBVGlkLz82cD9gaXQxX3BMTW1qTy5ZNiFEZE1zRVdOTyJSV1xENSwvKlIvTlhPKW1BVEU8OnFSVmRNZipDPEAlPC1lSz4vVEI/NDUsOHVdWGFqMWtjKj9qKU03S19sPE1CRFRMZ2g6TFApaE9uRkg8dSRjNVlTJ2ArUTtWOTVrWFxqR0k7ME08XiRgYz1JPHBZNEBmJVYpVkBpKk5OQVorIjRmN24tOD1ja2x1Lmo2LSo+K2M4Q11xZXJOcVclQUlNdU1GT0trMEgkSFVuQys6NG9fSG4nTm4uXFowOjlyZj1dUWQnIyQlTEFbMDxgbFBmbmddJ09rNkMqUl0yWmVXM1BXLmEoXT81ay9TNlxdXSpIWG5gOmJhdStiZTcvLkkrUjonZzxLKC9qSzZgcjxNb1BwRiRaOkg1Yk1QYltmIk1rSWNYWEcoS1hjSCMub0JpZj1jWDQuIURBMmVMYlcqJ2BzKjRkbDIybnJyYlIpTTxBW0Q3N2RDSD0oQTZsVzJWPjwvODNXMWNTX2xuIzs0O2YsLVQ0J2o8TDYiOW1abTk4ZF1wQG5IYDpwTWImcnFqSk51XydgaSJgW2FdYWRlXl9VXD4uO0xkclM/MSlNKj1KZk5ZPkIjOmE5YFFpUzZYQUNyWzZKVmpiPSxPMldnOUkrRGdSISpsbHRVQlZMK0VnZmkwJEU9UCMtOFs4cW9dR0RAJXVfPWUubkIyNE1KcTEjRGlkc24raVw0OmpEJzI4YFw5S28rRlZgJHUrTDYrSnJTaDZvL1dqJTdvOE9MNUlqQipocT5oRiFAYyF1bSNFNyRZWS9GUi1GMnBmcz82SzYlSztoaio2NC5dWTxtOkNrSycnKDIqLzFXb1JfM3JBaDtJL2A0NylSakBIcGQ4UTBwcHBUTm9OQkhLaD1yb15hPzYyTSJWJ2NmRV9nSlNIQ25XcXVXLHRQPitZS2QhVXUuJFk1SlJETyhORkw3VixgQW9dQVhFMkM1Q0w0YiUpVSEjKmZLP2wnVHAmZi9hRD4tQVReNScmdVpAS1dfKEh1UHNrXVkzWkY0PipjKFc2KkAtRidWJCQsXnFZQ1dOYV0uZ2pbb1A+Xy11My8xXXVgQy1ERDQpIyE6ZTVUUi4jSHIpQGNWQD4iYiheNkxCYjIiYnFEXi9wWHNmXDhcT1ZYTz5UVW0zIVkmR3UyK1pQXGNFPyxAL29Xaj8yXGZrdEpkIzRSVEAtVjUjXlVobyZOPVJna29wXWdpN288KT1PQSxQO0xBOWs5ayt0dF1EN2RdZjBoZ1oxckBnbk5icEw+fj5lbmRzdHJlYW0KZW5kb2JqCjI4IDAgb2JqCjw8Ci9GaWx0ZXIgWyAvQVNDSUk4NURlY29kZSAvRmxhdGVEZWNvZGUgXSAvTGVuZ3RoIDI3NjYKPj4Kc3RyZWFtCkdiIVNsZ04pJTwmcTBMVW9VRyowI2lVNVBlTlNkSSxxQ00jTVNxSz4uX1VkaytVSk1aJjZxV1BbMykkaTFFYFYoYnImU1ozM2NeJD9zajElRjFWNz1tXWpqTzU+MXM3KElZIykqP0pFcWZlZitbalZmYUdjPWY9Y3A7XHUsb1lTc3VhWTlMOkY8V0lrLWE1YXBXbkZddVA2M0huSS5CIz5ZcWA7QjIjUmAlU0IvLWQxMGNAI2MmYD5xMTMnZGsnNko8XkRMc1deO28kdSVoUk1OZ1Y/OSdUbT01V0VsUkxBTkAhLF1DPlJDUFUjVmcqXEtDZDlxNy9uRGsrKClaREg4ZzozVSEoUipuYVlrVSc3MFFUcCVba1c5ZzciZC1pU00ma0QpTUljXTI3ZyUqdT5fIS40NTItWzklS29nP1V1JD9uJW5OJGY4cyIrKGlKblM6Ml1wJTdxUE5dQT4pNF5eZWIrOjBhQkxdWkhDWD5NRScjL2k9Y0BJZVlnMCc1NC00QzRrRGpaUz5DMSlzWFFsLjlZc283Z1FYSSQoUkptIi00LHBwUzg1M1A/bEFvUS0udVQ6WmlCKTMuK1ZkLzErPyhbNVI4aDFyJDFePmcqKSdsOGkhTWpZampjSlclQDI9JlhSXVBaRVU7blVhJzk2VnFTVV1CTSxZVCtDPSFIM0VAJl9EK0pWbTtKMi9GVjg9QltRQzBUWDNrMCchSGI1QXFWLWQqYC1NKE40c0soYENZamFLJiJHZTI1QUA4P2hDLDwoVjxkLSo7K3EkQjVdaGxwPkcwdT07OiJhZFRgKTNDNU80MVxZb2ZAZFlSNUNUSnRMOVYpOWpmVSoxdUYzPksqI0g8ci48QFpSSk45Z01vWmdzRUYsTipWcUk2VXJnJm1kbjRAMDxrPSo2cFRRM3I1b0MqP1VOVDQ7cWVOVkkrKzBxRj1gbUc0KmxnQi1WVW9zXTRadEwhPkl0bk9vSDJxLUYxQy1aYGRoQyxCUGFkbz83Ij0mNSYocz9TamNrMiFKIiViMFhdRVZVSUFvZEcjay1mcD05Z2tXX0k2WGhtJGtNWyhhZHFOKSFZW1UwPUc3OWhBWm0tNUdgLlAkLShRMUdzLS5HIWJZXVM4NGVTQk1ZNzpnJT1DXUsuMCRfNj9LZThjTHQ9VjdAOnNYOkFuaTc1X19hJUpibSJmP0pWa0tCbC1lUyJzMEsnVDRIPyYhVydzaGFXQzFCcTZIai5lLUJVOWk4JGtEUTonKzpdXkBoOXNOYVpdTVFGaTtAIk8+SkpiTVxQREVfOmFcIkI9XDBSOUlaRHIsJS1OVFVKVUktYkRVbkJkNzE+cTleI11dVFtOR0o2SmZuQiRrSzJrOzhQIikxM0Y/Q0VfY3UxQjE4RGRkX24tQUJEUlhrPlY4LT5ZUEJFWkAwVyNsbCsiJmJLXm5AVTVnO3JzV0M+TkgkbVVAQmZUXi1RVCldNWVhOGpzP1E9TlNcIz0lPGpNNzxzKmhIQSQ4P0Qqa1YwNEhZJVBRcFl1MDlrVTo/JnJGWy1gbyRjUSMmXCFbSEJDXCk6YEBaLDJeM1pMNGtLViEpSE8wMmlqUmlEX1VMJk5XUyN1QC5sdEw0UW9AZGc2QyUjUyIrJTJBJCNnKFUpIXNoJHNpZzgvXCo6YS1cVjJXbDspQypjLTRfUW0xSG0xIipkPF8uSyUzXU5ZRDtrTE5JUiE4SytOJmIqMSY0OjJNODZpZlE2TGU/cTshal5YSWxWTUQkOTBVJVg9cEtbY3I7XT4kbjYyQEElMDNmPWIvYV02cFVjPU0mVzowWWA7S04nR0ZvRDoyWGYxMElTVypTZmMyPkQ5bF9eUWY/TTsoYT5ZNjdmJWNiRnJDRikjPnVZbFMsdTYucD5JdEZVVGFsVnNtVjkxKDQ4Q2JnWTYtX2YmSWgmcjUqX2hHX2c7aCNOazw4cj4sPGBBTGI/K2RyVm1gdVUkSlVeK2g4KTJZW1Y4LFIiVyQwdWs/bVVDRyxKJ2U1cTQyWTslKDU8cCJMKUYpZyNUIyQoJCk+dGtsUV8zcyVRKEBuOkEiXmxRNT9RKXJsYywxN1FbZFgtXG9HWT9CQkk+UUBrLDMlNjFlIW85YExpWSg6NmNGWyMtaWdFVUFdajAuVCNeLVM7OzB0J3NuZilDRyNpamwuKTxPPEssR2hRLFplP29FS1Ayck9IVyNAWVxCcidkbSQtKGo2Tis3KFhFOl9WVWlzKj4jZFckSyZUMFlPMz9VNmAkJiZxPnFwRVVgZCRFYiViT0NxWipgUTdzSDInOEBnLXV1aGpCdSk+LFUtPV1FVi9qNUBNX3JnLSY7VSUqM2I5blg8PkFFWDAzPGN1L0JYWVc1LjM+KSJpWiM3JTFfaUBScTgpVVJkNDhvQVpsZWpPWCQhK01sXktAU1ZyL2Y7PjkyQTFpJydZKU00QXRVdUlITzciXEBmOGNtMlkzdUhGYDlncEIhPW9ZQWMwXiJWXDckSmdGQWdxPDpcMUhpTiRKXyleKUdIbmE6Vi1RRGAhc15MOlw1XWtHUSNPaTc2T180bDJcImsoNmhfOEJzWFAwPEteMj5mKilMXF4rRW9dKDxQLVpzI1o9JydEYnFUYHQhYSosVGxaXU1MOUMhUnNgKjJhbE1MS05qTmNPO2o/XDFvN2kwVj0nXnJtLEM5SzkvLD9eNltpdXAkNTB1NWdaUkU1V0JpUV5rcDgqWyplJkFoczVMO0w+Wz44YVVXLDYhbVVQYl81RmNSLkwscTsnRkwtUSdOajw9blE0WENyU0JybERETklYSDxZcWBdMXFWNEAnW0EoT1Ixc049JFskU0FHajBbM0RkPjQlaGlbcUxlMCUsPTZzKmdiUkxZRz9pRmZWOiYhX1YncGJyaS0oK0EqQGZdJXRhZmRjbitoQGloO2dqKWIva2krakdWampiPmZsaUZWImJodFRVOzdTJTxJSFVtNUdDMjhJOUAxVF4hQ0FDMW8pQDtJamklaVk7LUNhSjIxLi1aTUMlU0NFX09Ca0EnOlVrJyRCVzRfPDBDRmoiOj9jRnBjXHQ3Nj91J05Pal9HaiE8RV1DIShTMUI9UmJQbEVcMERCUDNnXj0mS2pfPERjaVVtU0AtJnJGRzI2R0s2YSNJJDVlZUdyZmcrKCRoQldtNVArbjJ1NGtUUFBaWmtIN2RRXSJjXkhATDQhNmY7OCMuZk40W1c2MitbTGY9JUQ1RCxkcjhzZj9AVlsrImlmNkpJbUp1biNEaVkuPE44T05QdUUrZ28pXWQ6VWcuZV1BTjFRSnJjKHAuKUc9LCIkaS9cWSdFUmhAIShnS2Y1T2MpSUZIZGVMay8iOllKajIyM0kkO2NYM15HQl0lJzZdZlpbcGJlJUJMZFZlKkwnWEgtZVtWXExcaWwjIltnYjZuN2U/Jz1xYEZAa2UpITJcbFFtI2FLLTI0cElYSE4uSFNvZUEpaUJmXiU/MHJjPiYvTDtMNzw7QWhQcmZ0XyJaJlYiWm10UnQ5XVQ2O3UwNGtSQjlKL09QXzswKVVMVG9ATSsrdD43MG1aaSRuI2JRLGdCbmVSNDdXc1puNjRrLDEtdCxJVkNUdGwtYEBQYShpKGApJjI6R25ESCVdQ19mdUZEKHAwWywhMz1CJWtpQltmZ2JnSitaVGVKb2ghSWZ+PmVuZHN0cmVhbQplbmRvYmoKMjkgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjU4MQo+PgpzdHJlYW0KR2IhU21mbEdoLCg0R3BZZ21AOEZHQU4hcVY3Xyk5U1ROUEFnTGIyLG5jRnI4S1BpQ0w1Wyg6bXE9bHJkVV9eLVM9JjZlWW0nOSNYIj40WTRjYlsvUjdrVDZScWpOZDxMRktvIm5dOjtOU1dGWEsrZi9nLjhwQSM7MyxVUGlwYFZaY0U4VXBmRWtFT2JVUFNQYVZhQkRoKUVLVWxCR2dNWFYnU2liNig7OUdIU0lPUzJpUVBuM1dAQ0VlWVonaFwrMD4iMlM7Zmw3aiJnYjQpbD8nTSRMO1hPTWU4cSU/MVF1NUQ6TV0sazdCKj4qWklBRUhQJUs/X1dKK2puWmE1ZERxS1NkWSFhSSVqK1UzcjZ0MyJsdDhxP1Z0OmVuXjdZI2FUTCVXTDZdW2Bjb1hrPEpNInJGLydmOmpTTlgkOSwsK2puRFBmIlgjQU5EbExlJ0IrcjdwRnJCQDJLIzRFV0FbXzJVNCI1X28sYzFpY11pP2M0Kko4JVBMNilKOzsxP29KKyJqRSImOVtbUjlubVZtOigkOD4mS0xpYVdgPGA7QV8/ZV1kNipYanBkJFtDVWlnTWdZUCQ8Jm9BcTJsXWksOFVWOFBGb09iZyUocCphaj9jTmQtIUxvW0w5K05AU2JObWg1M0EpcFM0YzVGOjVCbXFXVDxbSl5ebyMsMWU4SGJnO2VPRkpTVFZzayVFL2xbSFpxWlBCLkhjN1NgViJyWEwiZDhWXl9xXSM+RmdtVkZnRjMySD5oKjRCSmwtXlszWnAoOD5tYC9RSWUuU04obF5dbGoiOWdhXD5NRWdaWDsqPm5dQFovcDE7I3A2KydLcjpfXyNBayFTNWQ9cTswW3AyRlRfL3E3RkJbV05iJ0c3K2BlImFRVnFNPkdbcTMwODNJUFJuVylhMFFfTkw7aUQ5L1w7VE0qIjlATTJMWztPJkJAUFszOjI2RiVIQ1Q3JkFiWj9CNkVBZ2gmPVxXcFxGU0kiQjUvP2JpVVhja2snW2dwNCxURTtIPD5DQVQ8NkhdcGlCLjEkMmdrSSo+OGR0PGA2W2BGJiI7I0VoO2RmQTRxWyInJUoobzxHTE1zKjFHO11wQShgRS9YTDtOTXFUa2srcEE8JUIyPTpnazZQTDsyajNXUycpSCdJZm8iJWQ4KmlaJERYQlEtPUpXZFUxRj1qajQ8QDdJazBLNGZlQVYxTyZFJDxWXSteRlI5LnBhc3VqTGljTDYmY11wTWhDRDtWUFouYFJYTnFCOE0pXmNfOylMNl5aK19WKkc8MEYqLmMvUyJkWk1qMUc7TklVVTc4JE5hak9qWGA3NGJRK1wiL3JCNERlbV5gOUpmQT8+anA1NU48RThdTzEiUz0hdF4iOHIyYW5PL0tGLm9MaGUqLGBMa1cuMlQ6dXQ8bVhOdFUzUV9jdGRmK1UyOjghTTdkMjNpbkNcaDspN29CZitvWCwkWlFycD86P2EvLFoxMnVGMClFI2gwW0hfdEEyTiFGQCpCKGEkbkFGSUswPlUvNFBMKiwoQCxjUGdFb140UE4vc14iMD1cVSJmWkl1KjpMUTVzSjZIO2JWIkRJcGdxJ2hIaGImVXUmUj9aSDFHXStcZGI6QWdbTzBZSTNXYlNlZExVKidWZVE+XS5XQyZtJG0oQVE9QDdcYlgyVGovU29IJ0NSPFlJPy1bRzMhXyp0VT1HLS5OaTg1aFRiXERQbzknZjxyYjReNixSYGlwajtnXUhNIUY7OlM4WGctVTAzMyY2P25ZK21XYVM1ISM0Tj9zPWg7KDdmLUAsZW9mVkJ0Z01VMiFQaWdvRzB1aWs+biYpZ2kvcl01Il0wTC9NaGBjUjxRKi9kZSdaNUVtZDZwTCQwPFE6VXU/XG5GYiduaCYnRFI5OXRCSk5VNDooZmUidWg6P0YsKV51KkllNEVUPjIxJ2shPylWUnJLZXI+M2FwbFFTbDVZNlkqYXFYLClldWxAQiQmV1swVl1hZUUoUyZtXVU0UHFwNTVDXTxeOzRfPzEqPWU1RFUtVyQwaW5xYnJmWSVCTC03SzQoWS1GXkFHKl8rXXJRNFJuWD1lRGVSVkk/S1pYWWFxOGJoWidIVGJbL3BgYEZiXix1S3AocS4wMTdiOTM1L0hRSm40WDtGQ1kpL0ZROSpqZjZdJnUuSFx0QExKRzZkIlY7VUchbS9xLU5UJkFtRTk/WytbXixHcUFOLVpKPig/QFlaUW4sLFE3dClVZlhjUFwjb3FHcyhocEhEOTdCbTdBRS8udV0tcTMxNl1jVW9jVD5bPCZRdW84aVQiNmpZX0JDUTBDW1RLXkZSI2JcX3I8ZkRAUCxBVUxuWiEoLk4rJmYvQGAnLm0kNSFrWmxhLyhuXnUkTSYsK1FPMSNLPVA7JjotXmNHaXEzc1BDb15lNixWYz5tZWZlYi1GMCVDYD9qZWUiISlDND5IPjFhT1g8KWIsJyFpKkhjLDtJZiQzZUF0Ky5ELTpnYTkpVEpNZENrRnQlZ0s0KUVCTnVCOEMiKDA4Z3QkSTlxUEAlMkZXXyg1OSw1RDNbblI+KEE+ckYsVSFoVFhFKCFySDdXWThpaj8hLjxFQk9cX1xxMzBHNlwzJF1HWT1tPFInKS9HTzZjWD1eI1tiPS9RTENsMW04ciRwJ2FsVUFCRWRBcV9IZDMhW0BRb2NxZjU9cV5WRjdhN1ZOSSlqbTdROmFiSzRILUlkMDs/LDglQTEiYS42YEhBRSxFIyZHUVUjQyVlYnFBQXQ8VkJeYE11Mzw1S2AxcFQmdUVYaEZvX1s0NmIlLWBdV1RyLFwubSpgJkFAbkdjPUFBJ2tRU0glVUJxJT9aIkA5KSkzLGhabTBAO0NqbENtdU5oNHAwdFhHXzlPdVhSczEpaSdJM0RwTUtpNT9DZykwMjsqXT4nQC9oZm5KV0ZabVNKQiFZMixUZS9AV1VbQCVsTHVKKD5lbi5XUjJWWj5XLGJzQiQ5SV1VWmdBQ2A7UVdIaDNTazs4T3I9UVBwPHE7MydQNm09YFgsbS5rOE1SOzViSnIkKVohPFo1cjRiKG0uJk0uPTlATl8/ZWhAVi1bLWVqMFg8VXEnYlVPTi9KRmNyPiEuc3BCZEA2bXJudEJuPyQ9P2NjcGI4Z0dqXExmSCQpNG9SOW1XcGgxRzJyIkdYTztqQktubF00ZSlmZWBWOlEkVy5TVTxPRl9oTjhBa2BbWUBWZk9cVzAsajkkKWYqbnFyJVR1ZGk5dD8iWConMUFRQ0s6YSJTLzRXRkNXUldJZyUiZClyUSImaVVBZlBLczEvTDgoZzVaRzQtPFcsIztSMSw/VlEjQGxAXCNLa2RAUzIpKW8vcCo2QThkcmBUVEs4Y2Q8cjFHc0FpQS9ENFtiQW06NCYuQ2ZORDZcXVRXXE4+YF1GXSlQcjpOPlptSklMQzMjK15+PmVuZHN0cmVhbQplbmRvYmoKMzAgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTcxMQo+PgpzdHJlYW0KR2IhU2s+QkE3USdSb01TMyVtdDs5SSJyIm5BNW0uRy5aNERCdTpsQ1dcKTZtPjtEQTMmOCRGaSptJlNvZGFFaSNmayErNWBmQSglcD89WnJPYVpgZ2NaZTg4JGgvTkU6SlE8LCInQU9cN2pOXSozUXI6ZCs4OlItQjM+Y0huYWFtM0YhLHEhIyZ0JmRcTDVgYE5IOjdKSnFkXWE8ZjAzOShpQCxQbi5RcSxULW1xTCxmaS1dXTxPcHRScFwnbGk8KVZmb1A+SjosXC0kcGFjW2JNQF9YLSgpQGNWTEtLK1E/b2dzbT0vS0RGO1xjREw9aTpbJD1pb29NJWpUO1MjN2pmWnMwMkxRZGVhYFM4MmQhX0pgRko0X1hTTCY0QDMiP2olalswXzVLK05ScWFuTy4pQzY5ayZWWmRzVnQ3bUVMO0EsJE10byl0Xi0rUUxtdDtwMidJLz50JjxbYEU4PWgvKmw7Kyd0IiFCPi9LdXIwQywuJWVySDhgcUhlJTV1WDo7WHJHb04hUTMwXnNbZzdzR2hYJ2JEXnUkUm5hWV5JdU8xOS8zUUA5M1RXNDtjMUU0Y0xALUxCJ005Uj5ROCwqMS1gR1luc1YwS0EzMT06Ni5TXypWWkEmX0oySihEalxoLGdNMygpYjhxRlpmNitII1NRPElPJUw9WkctY1pwRG5GN2YpRTRiRz1IVl9BRXRDKDBXVnBpbz1qOVxbdUlFUjdtJSNFLEE/aS5uZSFmSVw9PlolVVVHNltaUWxEVClwWzMrTFwkJj8vX3RZKmFlVztPYWlwS1olO0ItT0JwKDg3SEJhJyJTVV5STyhzWS1PRSFgblc4TmUvO2VXYTNHKyQ6TDZaX1spI1s6UlsvYT9cVz5WJ1A3RSlpbSg5Rm5oLlBQLkFBXV5DPVw2YywqKV9SRlEwcj5KVGl1TXBGP3IvPmE0RzlfQ1Q6ZixhamFESjhlVGJLRDdFXnUpWSlUMDFZTHFlKj8lQlclay9eKyQsdV88W19GZkkqNWszOGRlOTRmMi9IcEQiMDBmSmMha0ArMCo/Kyo9SVhrJWpWW21oa3FHLVtIL2JWLUk0XWlpSDtrXENYSVVtNk9hQmgvKjc4S0MpJUt0KDNtP3BXdV4/aSsjXDslRkZDOGdzNmBdWis4KCFfOGRxckhbU0ZETFVeU1QhR1Q1cWdTKGUoRjM/RDVVODBjTWxST21fZXI1ci11SU8xOThHTUctUGxlLnFqUUU/Q21tSV9WMkQ+UCFKPyUpSy1QKEViZik7WTJSWDRrKUUkKj5DI2Zkb11SXkdhSVM+VkZicGUzNUdCZFg1RzldMjlQQTdkJ2ZWVjM7ZDEjOCQhS3FMQzhxXis+LTlIZmVob3NoRW1hUEw2VlhpYy9ZKmk8O1tTQi1aLSpMVzMwRkQjJkMqMW0uVGctPjtjK1w1a0IrIztONDgsU2dlbywpUWxnUjZeZTBSWTNMTlQ6ZERANFJKOCxkZENUQEEoOSUkOGhuQUQ5dVRWW0hwQW1nRC5DTnEzOGc8OklpNGAsdF42ZykkaFJfWSU/JE1mOkhVRVpJIkZAcl00Lk1RUVJxbSY1KExhazRxNGFYS29hSzcmVkIlLTolMlUpRnVNNSQkbSJBV0xUQ0M8MjcpKVI9USNSLCopN1c+K2tGcUZXc09xUGgiXW9qI0lmZilNcVNlJSE5ZkMsIj5QYkIxYlBrXFtFQVxsXVNQYlNsYz8pZSxKLUI3R1lQOjY8IkVcZDZCUVVHLzlRKjJwN1pXU1stMzQyQEQzcWgoLlFPWlUoO0Zyc3U4bFVcIXIwaypDMUhcVDY2XXBwOCIzP0tPW3RgcjlAcktEWydgJzlGKzVRR2RJPUg8IW8zPk4/UEMraCtvbCs2Olc9dV9TLkgoW3NpN1U7JXEjKSFnSS44U2JnYSRLTmBCKG9qQ00oMVRaIk5xRVRTT1Rfb2pmR2ttWkFPJSs4NSk4ZkZQI0snRHNgUUNYaz9RU2ZFRGxUOFlwMSVia0IpPFM4NkRTM0ZHMlJfSC9ERmwuPmljM1g7dDQpakMoJ2wqUUI2XTdJX1pFI3BRKFlWSS9tQD5cUFY2JjgrbE86K1s5US0xakJJJkZYMThtOThuOzgjMTU4LFA6aVhnP207TC1BNmd0YG0waj9xTSoxQTpAcCRmVEIhPUoyMGpNVTk9QyFISF1FIi43YUI1aVpqL1M4LSckMTpsaWxVT1B1LWRWUC4nXVVAOCRNVC5OZHEuQFUoaWIyNFBmX1omO2QwcjV+PmVuZHN0cmVhbQplbmRvYmoKMzEgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjQ1OQo+PgpzdHJlYW0KR2IhI1xnTiklLCY6TzpTbHBFZzc+OG5wKkhZNUFbM0tZPmteL1w0Z2FcNiJgJltMJkZVZTNzc1NhIjE9KEViLylRPVImPDZfMCZbIXNFZkFtK0U9cFlqZTllSW5yc21kaC8rP2ZqSms8OXUyIkAkX3A/M04iNWhKQCRWVWBnXV86WVUjZVxYQ2FcLzQjSz9YLUw1LGphQFFzUjNkLEI1TE8+LVZDY1N1TkdJOjAydXEsUmNbN2kkUFhTSSk7UF1LMl8pRXNQPF9mRWMsPSxzKE5fVCpOMHFcI1ZzWCFQOiwnRiExZyooPzI7LUhGSioiITwzJlMlWWUnYGxiVzYibVJJL11aXSItalxAUXJFXEdSKzNKJjpEMl0iWUlxPylaZlJhTC1TRVkmK0RXSzI0X0pSU19USFI+aVclLGJHVDosOCxZIkw4MlJIMzwvQypoNFEnUzdCVkNfIV5mS1s0TiFvL0c2PkddYEEyc2dYRm5XOW9pc1dGT0YhXUs4K2lJayZNXz5YLmZFRSdiPW9gVkpOKEc5TmBMXGorKCssdFJfZW02ODNaMz5dbWNCLXEiUmchMSMrPFpPc1pmNGQ9blUyaHNqZl4jOmd0LGlhK3QkSE1DUVA6JlZHW2hXPmVwUlxbUitlPDQzaiMqXUMlNC47MzIpO2NCKiZMWjZwVzByO0w7QTxZQz5dcDdSTW1iYmE8MilPI2AzI1hCPUBiIjYmOlJOL2dnTCVCNEttUCVKZkFfLVNBWDFTKXVcLSREUUhDUio7dE0jLWF1Ll9OM09VO049RCFWL29BZjxORFFySjhwRE9ZLT1kSVY0MzRvbi0pT1ZIb0k+cGAqMF85QkgnI0hNNz9XUGYkI2oqWlA9M1Y8P2BNKEM1c0VpckFXZVwvNjckb3M/bSRkUEk1LXQsK1VYb1IkJ1cjJCU6bS10O2BVZXMqOSpibjhOJ0YiPzs8W1U8P2BrR2hTcj4mYjstV1NmSWk3PzMiLikib21oXDxoJjdiOi9DNHMhLD1XTTZFKGpVSWVMYzNsITJuOy1WMzBiMyZ1ci4zI2lYPTEqS1Y7WWZYQyNFbkt0KCcpYWFkVCpzVlplLTZBWUtfWzBFZWtoIi9hXzYiRUReaT5KZCRXV2VqRHI1RmlTK05xWk0/YmUnLGFyITBnIjQnQSQjblFeXWMkNU4/dDVpSCE+LE5tTXBcOE9MPTllVlNMK0huK24tJyVgNlVUb29ZSElaajBJRjlaRDAiXnFyOEM5RiJ1UWk5XD5Mcl88LDJaa0VPKyQyOS1RQzIkTD80cSk0XCVIX1ZGKERzU11CKmwkMltPJz90VzhJRFduUTBkajVlRkVjOSlkL0hYbG1nPVxUPEFpXHAhSWhjQSdOLGBnWDUiXyRYX0xbX25mRG5adT1USSNJaEdMKmJUUWkyYiksKTUkPWFFJlNcJz5HPTJMbj1gMV9jLDFbKlxwPzwkIjMtQkF0ZzlsJEQlNDJAX1RuQExAPkspbVRhSVJSa2JlOlw+Jktec1BUJUI2XzxrMCY9LTZCbU5qKXNeKkckNWdeTjtycTU8PC9HPjc/VlxLa0A1QypYRmFmWCVhcGRaPCw7OSo/R2k6Q2YnaidMWXM6NixmVyIqZiQ5b3Q8M0hWYTQuclxkJ2wtLTBHWSVLckFzLlwkPklZYkFEXyUqXDZdIiM8PT9nYyhCPz4pYW9PWWYpdSRHZU4lKDBVWGBCc0tXIiVmYys4WiZuaFpWMzgoLVV0NSZWT24wa2lTLlpILW9yPGlEVC1dVE4jOEIoSTxNMmBTbkBUU0NndFM8ZmhMOkhtZGtvY1piT1RHSmktLyREZk87cVk3PT9odUNfWiUvYmRVWWtsMCkiQUFQS2lzQEVVSS9vOFNWSFRfLnFOXFwoXEpmWkAvQ2Y7YEFuJSF1PFNnQWxJSCFNYj9PKEE/ck9DKzdWJDtBbC0mPzgkMDJtcSgoJydsMGE4OjNFbTpocUdgOjI2NCZtW0BUK2JoMzcvdFRHPGhsVDZLXzVtWSQkRmpRdFgoPEx0czVjTVJNT0U1SjlhJTUsKFozL01gL1teISJwTlAwKkdxXk9rP1ZdLkVubC4tYy5TZEVZLStMOlE4KD9IJydaLG5fZW9JYis+PXIncmNfXFM1JGpMPVk3N19lb09ibT9PSCdtS0VibENQSyFlRW1aZ2xOdFAzX1EmMUJsUFQ6dC1iQEsxY3UzTyo3OiU7akgmcyZjO01pdUEnQTljQW5xU0tWImpGcUYwOHQjZU9cLy8iPUQicCtvOmR0ak4tZzhrYSdpcz9iRUFhRWEtZmFYJzhxUmdBLjROVVJQZ2c+PFAqRjdLZm4vVzsnYVdpKmFQdTUwMDhoPGRRVEIsL3U0WTVvbFEtLmxaL2EkK2gnLEpCPEZeXFYpNHNRKmtWbDsqWk8sVzctb2IyKUMyVW5KXj5JKi1RLDdPQTg4P3U6UUZPITdnVEdcbDsrXVNTMGYsNmcsUCJTazclLDNLPVZwQ049LmBxUUFKWFouVjNsLk1lIiIobTtYPDtPN1lTVjwsRydXLCovKEhgXj9KbEAiRlpfMiFxJyEsX04sKmRfNGAvUGhtZFwyXCI8OC51am4zTVNxYjpSR108REJeZEteLmNcSkZOS3N1YUkvSCJOPFkyKSEyUT5KKyJpbCRbRTpfW1lUajNVWFU/OGFKXUpeMC05JSQuNy4kNXNPRzg9WjVmKTlvRzQxImppJEJRYG1VW3E1JSZyXC1aaydGb2ptTl0oU09kLFZrMVRza3BmIyxIQDRsJydbbSNXRkNgSGNrJyNlYSt1USNQQlQhL0kiKG1AJFhOQixHR1FKZzJNSFJ0WWcyOSVJXStpQkc3KWRSQ08xTjFNITdBVTRLNkpaQldrZVp1UENlUlE1KV9gKFBHISZNLy0yLHRkIT85aG9nb1JjMzdCKFo1Qlg1PCNhcW5MRl1UVSZ1KlJNX0xpX0clTGNlajxLPl9IYkRSVkM9ZCZDa0dqPVFzPmY9LyRKbCQ2J1FqY2liU05NIVZodT1mLllxSyUuLCNtUkNYcDssUFFlRT9lbTtrT1g3JFMiUCczW0Q/JChSXUltKGg7UnBpSCtqOzZJXSZSQHEtS3FNRytIJnIsQz5gZCcncEJUYmpEWGhHbGVmRjFEXlwhaFpfb1JIaTRcWClhKUAibSojQjwzTDs5SlI3WDxMVjJwXGMiTzZOaUcuYHVIRScxTEZfRDxdPEwrWW0+Rl07dEpVOWFyKj8kVz0mKW0vfj5lbmRzdHJlYW0KZW5kb2JqCjMyIDAgb2JqCjw8Ci9GaWx0ZXIgWyAvQVNDSUk4NURlY29kZSAvRmxhdGVEZWNvZGUgXSAvTGVuZ3RoIDI3NzIKPj4Kc3RyZWFtCkdiITtlZ04pJT4lWG4oUWkqaXJoQW4uOVI4cFBJajQ3UTo1blE7NktoKCQwOUE1aEtAbHJKQG5VOGUrZDRfV1xfPk9qKyY4aDAuK0Y8VDw7KUU5XUE2UGMqYkJCZSJyLVtJZUpaVi0zLVJxO3QwWTJSZ3EqRjZsYTUrTk9mMl1nXispPFBJRzNZTzgiLWE1YXBNVChGamlrViQjNTVBPUVmTjssWjhxK1ZxQjQ+KC8pNlBqZWJxVSswYDVKUV46IWcmSmdCQ2NvOWBdI09wVzxyWzw/OmpFaFtbYGM9JylIQiFpdC4vaz5Eam5gWWJhcylJNi5yJ0UrRWFxVnBaOXExams9MVJjVjcwLydMbV1WNSk3XVk4WGJOK1JSZGxtRVMrbWVPUnBhMFIucjc+QnUvPGUqQC5yIm4tZWxNPiMuSmVyU2VeVV1gVj06T29ZYlYhNU5TKTpBVD9nT15JLUVbUnFPb15tUD1DWSMraFtRWzQuOyVUT2NhYCMhTFpaLUxsYGJZTlYlKiM7XG1vMi9eLEc1YkBOZjhOWTxrZFU+OHQwc2EkNSFVQUA4NUJXXyEuaFpGZyoyTCU0RU46cmAuTldfMm1UOkpvbmk8QTM3N04vP3AyOSE2J2MrTnJQY3FIKEowSGVfLSREJlx0JW8jSlNSVVZcO0Q7Kz82I0JLdWQ3cXBBV1VUaDxebCNicl1aOy4ycG1WO3JYYUlzbiFGbnIwNUFtYTI2SklRZkwrJG1aPnE/bydiVDlyTiFlWyNyR09TXy8xQkpxanM+TDBlPklDVyJQTF5jUCc7SCpBPUVkZWc6X2RjP2JPY0w0Q0xDJjdfTVpaVEhLJ3I8NDFGMHVjX0thOm9VUz5yRVlCYl9zZC5NcV9gYD9ONCUzTCo3Ri5CLVhZLm5bKCROJWcsVy1BbyQiJl5MbFBNTlVsOmYwPV1BWmQpXk9WSUEyPWosW29fVGknamtWbUhmLWE6LFo8Vm1XPSQqRjotKWpkKj4hS18vLyw6MFVgSTdiKFdNYVJUW2MwNmciUyg1VXFmPG4mbD83Q008K0E4NzVyMWArPjdgZ25RVTJMdXIkX19pSmoqWGVxOFsvbypzKm5cIWFwMGR0Yz8lP1xsJyhVVzxpUyRda0ZTPS0zaE8/bmhbPylfSVJLUT4qLGVLdGk6KChzbDxYN108JSFPKWk1YkhZOkgtQD9sXy5ULCZoJF11XixfRm5KSzRkXHJoRjFQbj4lTWgvQk1rXTtaRkVmJ1k9PVFKakQ5MCYoRykxTWA7YEhmUltzN1REaiRraVJMWlIjJmMhXCdXdGw2VSdOdFkrXmNNUTpBPCFDJV4sSSJwWG1bdHE5I2BBPkBmWiorT0ZBKyg+PSEuIzhidVQuWm1zUWQiZipQRSx1Pj9sV15RRFNgXUFHV04rKnIxVCQiOThgQkhdZ047bkFJJG1gP3UhRjg1YU9UITFoZCFQbjJRa2diJSY+TkNcJmRiM2gmQlQ+T1MoOm1zSGJSczspLCo4J19JajxDWlRtXF5tIzJsI2o4RklYWi5WdWBkJWxRSmU9dDUtJXJjSiUnXTdDX1YwJnRRVWgkRF8xXzBnKDMiQj51aSIwOVJKWC4iLjZrZmVcJmJDdHJULkBMQz8taz9cJ0JgUkxDKzhzaiNbIm85Ok4wZ0ttKiYyQEJHWD06QnQrQE5tdC5oKz5tWnJGbG5gOUdIcFFYaGFmYDlINV49SicjPS9ZLSoiQS4oRHNkaywzVmZrTzQ6XGlMK1hpRGlYal5qTTwncUFrb0o3L0JBS3BwNGY8PiRZN2p1VWM+K1ArTllaRkNwOkBCJGNhc2E8IyMyTzwoVkdTOFNQNT5CaCVfS10rVzIsWGwuZHNpQydtTXEoL2pcTikhVEhcQUFSIiI9amRbQ3NjJWBXZilNTTxuQi0/Ozw5NTYiRSg9WVxuMSNnMTwqSy4tQTcoZTVVWDFCZEEja0RJXFlAbV1ZNi1hb1cyZUNrOVwmPE4xI2lpK3U2Q29EI1RWbXJXOGloVWxFPyxAc1QmMCs1ZTFLYSotS0phKlhaSlJ1L1oxKnJTMi1uSS9UYSdIMThQPUVSYlUoX1crIkplP0VJMShbNiYpS0o5J2ohISopOktIWFpEXFYoK1lWVEk3RlxFSjNCVTYsVXEmIVllJ18qP2g4LzphMSldckxMKixcX2leLyZeRz1IKj88I105blVLaldYQCFKb1pub1BVTy9nMyNHaDpgYW5PZlg0bio9Y2dMMT51QElHPyo0XmVLTmpdQi0xWGhhRHFec1s/S1xeaG1CWCI5MnRjOjwqYHEkVGc1IzFtQGkkNEF0TTlYbzRxQnE1NyloJkFuTCg/YEJcXllzInVLNXJdNG0pP05hMidXJ20lRUNjLT9mYlBBIlVxT0Y+L25aJXFTQ0clYWxTITReR0RhMEFgdUQocURCX3JraStlWjc8ZDVeKWVWJD9nOD01bzUvWEJlZVZpQyIyXSEzUXIoPjc3PU4lZV9RTFc4Z2lKZzg8ayt0QEYma1c6NVYhYUxqRzIsWmQ/NyhcYywibUFdNVdgO1YrNC9VImI9MzE5a3FOLDVLWWtLWj5ePFFlOyMqNT1pZTwrUjQuNWs2R0xZcWc8am8/OW4ndGdpMWpaUUAwbzcuZk9bZGtUQm8iaVRvcGs9SF82ZG5uV3BNOSkoUyM9SUlZTHJmbVU0VFRvYUdHRmsmblU2X19IS0VhNGYjMm8oQEVaMFdzL11lTnJsZUAoJHJuJWNjNls7ciZjK0RjOylCXj1GWmJQNVwzVCZYSCVgPCptWz1BNkhKVDEtMGZlQFdRcSMrIURfPU1KRTtRcDc7Xk9VWTk8SGdDSioyQSRPXltsOjBwTylgbCxAVTspcFAhLU4pbk06N2hySlFVdEFYQ3MmV08iWTAhJmZ1Im81ZDZbazQjSExaVTcpIkhDIU5WMDRrPFd1QG5CZSwhSmJqJGlYZmMqN2k7aVhFWlhTNmE/Nl1rV3I6TUdDcUdmQUs5W2B1RiNILjJrJjVTQll0OzgxMlJRJUFPPjtcWVEqL00uaSRkO19ZKG1tPjhTVk46WmtUKjlCMDtePTtEK3Ujb3NZWGM3RFZzWyxzRWVKUXVKKS0mQmY4WlY7I1kvIz1IcFc4cVI3OFJlIXJrOHU2XXFmSzF0VFVNPmJuUzl1Yzg5X1FdbUdyUWohYlZwTyJQX1ZAYEJzNVtmLGonJXUlY2w5cDgmOl1OYDM5ZkZHUW91PlglTUdvUXApPGA9SThBXD1tNnUlNC1JcUA0SWZZPV5FM1YqVDJvJzlHO2MmXCdaTSVrMVNhUEFKUUdRQ05ERERgQU1vYDZcJ1VKWWtjY1ZzMEtTWjxrV0ZlZi1BWEhFPHEpMkNjTz1jXTY4KzBDXFprQy5KZDFIIU5YZjVfaF5gXTQxQmNYYCcnR11YTThUNUJRYWoyU1JQdDFKYSRtXj5gUDJtZD9XZVEvWklgSDspOCstO11EYCROcDw/WFlqQ3EzO2dnXCVSMkxzdWM/MSReXV4xdVUoWjsvQjlGXlFUYztpUkIqSixAU3EnX141LSFAQzptQTExOVEtbGVMSE1XSmpxOXU+QSFcMU89Tz4tVjYuOTF0VWVhQWI6JCM7ViFoTUU5O1k8cDw1XF1ZQDl0UlFBbUgnNmdwWWQpZ2I7ck0kJSN+PmVuZHN0cmVhbQplbmRvYmoKMzMgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjkwNwo+PgpzdHJlYW0KR2IhO2Q/JCJLOSZxL3FFb0YhVGkoQ1BaR1U/XjwxI1lFKVFKU1xlUWcrJERDQmwpKj45M1I7aCc1RSRwNFp0JTNHMmVraEliNSMzUCIuPVc0bCojM0dFNSpMcl05b1VBM29qJjY4KShSRWE1JixhbWdzVC0/Ji1ubyZUNmVRNXRxKVkidD8oTkdVPG1iT0omPiY1WTYyUCU0IzFMb2NcKS9HKjJLV1daJUdfJj10SVNXR0RbTSpjUF9RNWVNJT5ISmROQ1lYKWEoQFRcLVYyb3VePG5OOU5MI15OI09pQEB0PXU3IVNtMUJEbDdPLHFsQSg/LzgoS11jZnJ0JkhVP18vQFI0KzksXlgzJz5CYWs9OikzZS4yK3EhQmwrcidjZlZHbC4zWUdEMT9vKXUwdEhKYVlRQ1MwP3JYVUg6Z0BFLDdQPV9PQlE3ajJsdG41aTFWYHBiZVVrMy4kKGQtSS5NSCEmYykxLTVnNk8nb2JQMGpFKmtyTkJtVl1fXj4tLm88SGtWb2lPaidsSjRCaEE5amtMa3NJPEFHdGdkYEcsLm5kOi1pMkc0PjY4TzoyYyJeSVAoLC5yLCElRF9jTGlMZGVnPjkkaSplJVMjNUtGcERiXShLOV9PVkdVQ0xPZW40cF9mUT5TMFxEKS5HVys8LlA5UFloZ2RNP0NeMzFePzhMZWc1cE8vblxtaiw9SSROcCUkLVtuPFkwXFRdPl1KTWgwZyNJTUZJaGsrIlw3U3MwV1pPWj0rajYrVjdlZFcjWCw4XFtiWTN0YHFOaCgoLiU+Q0AvMjBRP25mUDspImg4LnQ9b0gvX2c0NVJraEJlWXFfZyxNa0s/VzNKcVY1Vm06ZFlFLWdpZ0czISs2Ulc8QmQiMCpcWSlAbEdDRlFFJjRORSNWPzNnQiNrJkhURlZBRUAvTD8rTldEVUY8XTx0Zk9rXnNMSTZpT0plQUwzTEMoOUUyM0FAY2dYVElxPzgnY0VROU5bXkM6cSRjOFw8TyhiUG8/RElAYl8rbE9PRVQtWUNyL1pWbmwqRTwoNFtZJFVfNCduO0heVlooUU1abFlFK2BMIWU+VGhaSyQ/JUskMU5PUXNfV0Q7JjwpPk8ySTM6WTFILFdwbDUscEsqXyhWLWB0SWtbUFRnSElaQF47LVRbbytjYz1NWVwkXHM4XFhHVHNJO2xaLmM7KlVZS3FWQVI9J3UrbD8zZzIvaFNATyldQCxRL01hQyMvY1wlTyg1ZE5cWl1nZ0xTOiQ6bSZMTFxDRXMzVTEobz0ra2gnTm45clxGbDZlTllLMnJCZyFPdFhWQkI/UkQ4YEIlPiFpPzViPF48JikocVRAP2cyZXBKMzgmXC5pWVBVUS86dG8hamslOSwiP1VeNi80YmQ+YW0oKjgkTlVULipONk9tX2tnKnFaLV88Y15BWVI+Vyg8JFwocHVZRjVHcDZFa1pEcVUoSXJFMTxmRDFtTjhZWDo4a1AlMExnX2VzJHMtJ1R0XHQmaGo0dT1dUikjKmFFWm1yJ2xBO1M1aTw3K25CUDJpLTUrckNLS3IwNFFOdTtmK3NnUzZCZjhpbVA4OXNsLEw7S0FzUTJRL1NVWW5dUE80b05TKDlcazJYSW01T0w9UjBYZ0YrM2ZhTWBjZmJtT2JcY1Y8RFJTTW9IST89QT8jbUJKOFVSJzghbWcrOT00QilJPnRqb0U6Oj1uRC8vOT0qUCohInFdcD4iMDlwJGY/UCY2R04yQW81T0NzLEYhOUU4c1RRUUA9WldGN00lV11IX0huU3NxUjZuL0JfVFVwdVc3Jz5bWFstNCdaOzdHVy1jODpmbSMua0o2QWRLLjQwRURvZDA1NzwybjZhPG1cKCdibyxHJC5BViFUISxnUjEjJ2NlVz5KNThzMyxyaSVbPjh0cyZIWiN1R2o4QD0qMVs4YSVXcnE5OUJxPC9tVElETWFDSkhlTUYnZlRNJDc+R05uWjlVdGJSaHFwImlqTStAMik6Li8oOjEjU0VpJzUvMXEsblBPY2tWTDFGPl1SM2pxI1M4ayVCKmM+cS09bHI1MVNMOF8xVFlqKCg0KkYrZzA+W0dwRSduQi9YQDlkRGFUKEI8Yks7TDZVTVFUQSE0NGhSOFQ6WUdnS15aQi5dMCNHMFtrMGJRWXRPb2pnPSteRVFadUBPaTtSVklAVDA0bDQjTSVaOXU0O2AnRTZdVFMzciZyOkpyK3AoP1ZpQitQWElicikwOTxFRzZsP0I+byVaPnUzMmJyVyoqWD1cPDxUWGFmWVltSW8+NFpQU1ZxWFJmO1paWm4yPlEkMk1aLXU2KXRgaWhCUEYuKzlHRiVWbiRpXHA1JWFJMzg0SjAxYjpTQUpjY2NPLTwlSnFURlpdPF1nJSRbUEkhNWc6U3NjayEuaTc3SypcP2VIQFZeXiQqXicoKmckUFRTUyo8clBndVVucjZbYD4pS0pqKWY5YDhOT3BlL15YMkJhQWk2YTVnXlljYTgiMyo9LSQ5QSNrdEZvN3JcTkVjXUxfIkEhb11wQyJBQFlZbGBuIltQJFIkXS80QUE6Ky9jK3A6LEVyU0I/OypULGw5blxXUEphYFNrdEdCNDgpaFNLUjlnWElzRjkhcTFLaiwoL1Ukbz0iNzJibHJyYCsxP05nSDBnUTtTPVkmPlQjcCNZYWxmb3FObSk7L1Y1RiUhQlBLb140Wj1xUVFmazA1WjdMTi05dS9sZVdvamUqMksxW2s8QU1DL14nckQjMytnXiNaS05eI2FfKlpFJ041UmVdXVxmMCxPR0pFV0w4LFA2ZUBlcSVCIyVmK20mJVs6MEFsck0kbWkpXyUiMTBPWyk8dVRoIk5MJ0YlMTZXaTZrXmlUZ2ZNY1AxZilsTFcsZTk+MnN1YCFrKnNHVHNUWE1tZ2RwZ3U0WS9XcFZiVWwuSGM9bGZESUJAKEdIXFtjXFhebiFYMylaIWc3YDxRWGNNVjhAQ19USyZpaiQzLEMtPW9MYyU9bWlwNTY5RHMucV1MT3RCKGU7VXFJNUxFQC5ebWc0YmgpMD9uYDFzUUFwKW8zaDpkWko7XnMtKnBWX2RUVCNyPEcxP2VkNGtQM05nVGowX3JWUjlDVDtdQXI9JlZvLCM7SCtaXDIhZGRtZyVHTVEkPWJnLiNBbm4hZGMtbihuZUhOPWI9VVw3PT4+bTZMJnRzKFlJcTNkS09oXkBZKyU3SHRkQEomRD9qW0siQHREKC9xZFpbPXM5SmI1N0ducihIZCMqOzwhKT5eZVBYKV5cRmZQdDdJOThlM1M4Zz5sNWpRODZqc0Fabk9zTzBUdWFnOjIqKlVwU0hSRVVmRVZENnBxMCZrVUFeOTFAMWJGLyZbWm5AY3Q0aERhQjo4WDVaVEkvPTNMUmslLm9rJiFwN1M1JENJa09CIURjKk9wQGRscTwmMk08WWxlQmNhK3ArOEdoSEdfdWZCPFwhbERkZ0tWUjlbPSk+YldqPEYnIjJhbGMmYidbcnIhaWdub0I6aERQRGdYKj1pJUIqKiEiLThaamcmbEgjamBWcVJrNjc/dDhpY2gnVjU3VTduSE8xVT5wRWYjKjhGakc5NWdsSi9PWC5NPjJkVWoyV048Xz5cVm0nTjM1OTtMXFk7dWtyaG0/LEVxWk5kI2MyPSFsXlJMY1svI3RYV15jOiouPDtnYlA3QyhmZ3RydHJsOE9vUE91O0oiSE1FYDEnUlpaQy46QGM0YzxNXlxbWS0vcFIqaGkjIVdoV3RMbkM4USdJI0hMbjplYkgyQEVIVz1FSCEwLGNZYmVmcWQqb00iVHAoZVswb3BaWCdjTTI7NkAlQnNHblYiMnV0TCp1K1lwTT1ma1lkJ2tfJ34+ZW5kc3RyZWFtCmVuZG9iagozNCAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAyNDYxCj4+CnN0cmVhbQpHYiE7ZGFgP0UyJyMhVF1vJj1COigqT0EtSnNfP1hZZEkzTzg/c2VvRnVWZ1QsI0JFMCVBN0FjQUNFN1Q1OzA6KGUzXDpSbjZnI1RfJzFZQGxLLChKUU9tXWU9NEZFPjkoWk9ZVmpFIWc3P2BPXEBsUTxVVk1pUkQrJU0oTU5eZj0lTD9YYW1nRiNBQFQmbVBKY10wYXRIYGg4cUJhQClcSmxTcyVxPmlMX0RpI1ZUTnBxaGRMXl9IY0VPRShBPXJYTSJXNURqI0VWKipNZ19kSm5eIzxYPEgiP0VGO2hwKllCVUBYPGpFXFRaXygpO0FdOCU/InJ0PS1uZ3UiJy8wNWAwMDBIIjUoSV88QGdTIkl0WlkucG1WLV5zdEttYjlUYCU7Tk1AbWcoW1I3Z0tXQCkiTmFeLGNFTD0pJDI0JjdEP0AjOUszST9oK29aS2wwPVVyazguQF0lLFomVStXNWdLSzhuaTo2Y1RpXC10V1I7Q1s+SSJJIVE5PUQ0VmZwZF9iWEpfcjJSLlliJzhycStQP0dTT24oJTdnbEA/SFQ4T189Wk5DMGtyZXJEQkFOP2pRSnBiU2JYMi8/OzkhPkpWb2o0V2xNXUpTbjFBaHRqQSp1N0xwTTZ1Y18rIVZdNFZfPUxJREBxUEtDIUVPMHEnYEJtIj5HIWo5ZVBkSyZfRiFiVWhwPV5LP0paWSQsY0YwYzcrMD4mWEllak42PDl1SCdBJENgVzc/bT9fS0g5TjZqcjwmWDM3TSdgNGB0LV4wVSU9Ryk7RlY4W1pBYG9sUjRiSUJLWCtRY11oWS5ubFxqQUJJJytZci0iVjt0ajA6OjNcZiUtI24nNFthWU88UCNxODs3ZVBmZS45L3NVISVWbVdbSiRCZEIsIityZExKXi88T29SNmpFJ29ML0VVNS5WaVMxYGhHL2hyWHA8UG1YKypUWTg7VlEkOmlZLVQiRlY5MTNIQlRfVWwqJUgzYjc5TDEjK0hMMSxkYiUsalBIJyxtczNtKl1JSTZNLmtGTSY1bitUbVIyUWAmYTo2JW5bckpoakRvUGU/IkdZPlY9QThDM2FSZyhjP0BxPjlbQW83J1orMTAvPCZBMClmJTZwSFRgcScuIV1fT1AxWWJSOVs6MDNzPkM4KC1bIl90aVtUaHFTdVxVcUAhNS8wWF4kLVtNI29yJWl1RiZgcFNUTlNGIWZXWGxgVEFhJUBbKmhxZTtTckRrSlAkOU0za2hDVmFbMFZxVGViNk1DXnNvQzlKaFwxKmpwVXNnPV8zRUYuJjBlWjJqSnFHXy1jUDYyWyg3RSNbRSMqXEdsSz81WnRxOGV0TipVZDNLQmJcTG5nbEMsVU1iaGVXV1dASCVNPiNZPyNVZ1JKUFQyWCwwWE01Pk5EYydQVSdkOiFWUkt0JmRMPzhQZjciLVJsQV9qbDBZRVZ0UWJIUldgOj42RTEpOk4+XFo0Yi0lOzFiVm87a1pNO1chJkNWLmEnbSxwXFsyNVJNTDpKR1BCQChrY0FkcU5fbGBmblBYNEQ6XD5DX2xhRnJGK3BBPGduXmpPbk1qKy9ZPEkhOj5eLSQ6aVNqS1ZSV0xgLCVIQGc0YGZgdTpUay5wTTplPSVeNjpRJCMzZmdMSTlDXGBXN1lBMUg8L0EjOG9EZilWJEIrJWhZbVE6aj1DSWBabkc4bmgzKlRuU1pSWnU9JmoiNWw1ZzpeQ2tpMmVoZURKMEglckYsS1VyIUU3V18yXmI9Um5wbzdpRDJeIW1JT3RLRGshQUxuRDFHLUI1InM6WShOWGVzL1NmOiZDP0pBOjJvMjUtdSJUbjFmVTosYC1mXW1dO1t0dUZmNGJWJGxxWzRvSURHUz0ocyc2UUUtPkc7SSs/ZWJGODJVNzQmXDlZPjktJmJdIVhfIXNfU3VVKTk+UlBtbzxBSywxQ2NIaWhrK2FlN05vPCVbWiNLYyxvbS44I01VVSxdcU9fNCI4JWsibzljbWlwYVNHbzQlbjw+MkZ1XCVrPkpkNnI/c0xZW2QnbFUoOlYyT04mMV1wJyotWDxLR2tFdWZEdSdFYGtDa18qQ0MhQEw7PWAzKy03byk/P1BpJWQ8ZGhjNWonJ2gzL05vL1VkPChbUUpfa1AkZzhuazwqaiZKcSk2NjdNZzc2JFhqPE89aG1zRF1wUSFoaElydS5aaDVwbjNLSTJqJXAvKyJiUFx1PmZfJmonMG03RTV1TkVdZEFOW2ZUUGZucVVPWUw1U0VhcGpBXjRaT0s4MWghKGpJWy0ja0FFUGxXN0k+SS5vbENoLipEZCk3JFZKRmBuW3NcN2ZxUEJxLzAsW2ojOCJQRGRVQUt0M15OUGo+XkY6bDVeKEFNMyQwL14tP1M1YVloKCdvZlAtTnF1VEhgLEVLU3FNM2slQyMrTT5mOHMjZjNeRiZUPFwxZGNGXFhBTmpnSGVBUCU7NlhvRjNrLU9fRVsxcVQmTEFfLCVHIiljPSNuLEpMK0xINzNZITprXUJYQkwkck5UIVRwIl9oMmpSN0QpSTBHWENMaXMkWjEkMCVVOU1iX0xHL2Q+ckMoKmVpPmNoImk2VmxsSlUmaWZFZltLQDJxLFpxMilCK1s1WHAtKEcoMm9jWzFUXVh0PTo1PTZkVF9HL1s8Xy8zUXVrME9rajw5OSF0SW9IOEEhLT04cVExTDFaUjpSLDtsSGBNZmBgJCR1JU1aXEpoJjFXMmdzZHE8bE4vRmApVFY7Y0Rla2leP1s7XUhHNWhXJF4sUVtbW2xFPnFQclldUVcmTHNIVXJXUXBEVSNeP2M0SDZpS2VrRjBiVz9TMCVzIU5vPUw7KTNqPEc7UWU4VFFuQWM0PSZUSzxVVl9TdUEiXkxuZSVlQEQockMqKlRpLTs6a0ZxWl81ITteVSt0YCEvN2kyLVtNN0NOLW82NWRHNiZTTDZtWlZlcDMyPzVub1daTUhkWjAsKyQ/b05ESyJcdCcvZSlOWm4oWi1VUyIkREY5aCs1bUdzYVonUSpVQFAyS14vaUZKI0kjam1qcjRqJGYrVHM7QFxKQWokQ1E4PEFkMktBay1dWm5ISzZvYisjKTZrLzJuKGI7LzA9Sz1fT0BHbiVYYD1CQmNaTj1BajBuaTt1X0JdMTdhaD89ZUpwcWxhXGBcWTNpLkZoWmt0W0hmJ2w7LWBkaD1EQm9JbSFiMUdgK0c3O3FHQikkbTNvLjY7PW9BKi4nRUREMWpTSTpZLkUjMEBVJkhoVm1TQ19RUUEnM2RKajI4L2tiIn4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgMzUKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDYxIDAwMDAwIG4gCjAwMDAwMDAxNDQgMDAwMDAgbiAKMDAwMDAwMDI1MSAwMDAwMCBuIAowMDAwMDAwMzYzIDAwMDAwIG4gCjAwMDAwMDA1NTggMDAwMDAgbiAKMDAwMDAwMDc1MyAwMDAwMCBuIAowMDAwMDAwODY4IDAwMDAwIG4gCjAwMDAwMDA5NDUgMDAwMDAgbiAKMDAwMDAwMTE0MCAwMDAwMCBuIAowMDAwMDAxMzM1IDAwMDAwIG4gCjAwMDAwMDE1MzEgMDAwMDAgbiAKMDAwMDAwMTcyNyAwMDAwMCBuIAowMDAwMDAxOTIzIDAwMDAwIG4gCjAwMDAwMDIxMTkgMDAwMDAgbiAKMDAwMDAwMjIzOSAwMDAwMCBuIAowMDAwMDAyNDM1IDAwMDAwIG4gCjAwMDAwMDI1MTkgMDAwMDAgbiAKMDAwMDAwMjcxNSAwMDAwMCBuIAowMDAwMDAyOTExIDAwMDAwIG4gCjAwMDAwMDMxMDcgMDAwMDAgbiAKMDAwMDAwMzE3NyAwMDAwMCBuIAowMDAwMDAzNDU4IDAwMDAwIG4gCjAwMDAwMDM1OTYgMDAwMDAgbiAKMDAwMDAwNDQ3NiAwMDAwMCBuIAowMDAwMDA3NDQ0IDAwMDAwIG4gCjAwMDAwMTAyNDcgMDAwMDAgbiAKMDAwMDAxMjY1NiAwMDAwMCBuIAowMDAwMDE0ODAwIDAwMDAwIG4gCjAwMDAwMTc2NTggMDAwMDAgbiAKMDAwMDAyMDMzMSAwMDAwMCBuIAowMDAwMDIyMTM0IDAwMDAwIG4gCjAwMDAwMjQ2ODUgMDAwMDAgbiAKMDAwMDAyNzU0OSAwMDAwMCBuIAowMDAwMDMwNTQ4IDAwMDAwIG4gCnRyYWlsZXIKPDwKL0lEIApbPGY2Y2JlZjQ3MDFlNzdlNzQ3MjA1MTFjZmQ1ZDEwNGE4PjxmNmNiZWY0NzAxZTc3ZTc0NzIwNTExY2ZkNWQxMDRhOD5dCiUgUmVwb3J0TGFiIGdlbmVyYXRlZCBQREYgZG9jdW1lbnQgLS0gZGlnZXN0IChvcGVuc291cmNlKQoKL0luZm8gMjEgMCBSCi9Sb290IDIwIDAgUgovU2l6ZSAzNQo+PgpzdGFydHhyZWYKMzMxMDEKJSVFT0YK"
    st.markdown(
        f"<a href='data:application/pdf;base64,{_gs_pdf_b64}' download='PSM_Getting_Started.pdf' "
        f"style='text-decoration:none;'>"
        f"<div style='display:flex;align-items:center;gap:0.7rem;"
        f"background:#FFFFFF;border:1px solid #E2E8F0;border-left:3px solid {C_GOLD};"
        f"border-radius:4px;padding:0.55rem 0.8rem;margin-bottom:0.6rem;"
        f"cursor:pointer;transition:background 0.15s;'>"
        f"<span style='font-size:1.1rem;'>📘</span>"
        f"<div>"
        f"<div style='font-size:0.72rem;font-weight:700;color:{INK};'>Getting Started Guide</div>"
        f"<div style='font-size:0.63rem;color:{MUTED};'>Click to download PDF reference</div>"
        f"</div>"
        f"<span style='margin-left:auto;font-size:0.65rem;color:{MUTED};'>↓ PDF</span>"
        f"</div></a>",
        unsafe_allow_html=True)

    with st.expander("BASE DEMAND", expanded=True):
        base_visits = st.number_input("Visits / Day", 1.0, 300.0, 32.0, 1.0,
            help="Average patient visits per day across all shifts. Starting point for all demand calculations.")
        budget_ppp  = st.number_input("Pts / APC / Shift", 10.0, 60.0, 36.0, 1.0,
            help="Budgeted patient throughput per APC per shift. 36 = Green ceiling; above this enters Yellow zone.")
        annual_growth = st.slider("Annual Volume Growth %", 0.0, 30.0, 10.0, 0.5,
            help="Expected year-over-year visit growth, compounded monthly. Drives rising FTE demand in years 2-3, and increases the cost of understaffing since more visits are at risk in later years.")
        peak_factor = 1.0  # removed from UI — use quarterly seasonality for volume adjustments
        _y3_visits = base_visits * (1 + annual_growth/100) ** 2
        st.caption(f"Y1 baseline: **{base_visits:.0f}**/day  →  Y3 projected: **{_y3_visits:.0f}**/day")

    with st.expander("MONTHLY VOLUME DISTRIBUTION", expanded=True):
        st.caption(
            "Volume adjustment vs annual average for each month (seasonality demand changes). "
            "Normalized so base visits/day = annual avg."
        )
        # Classic urgent care defaults: Jan/Feb flu peak, spring flat, Jul dip, fall ramp
        _mo_defaults = [30, 25, 10, 0, -5, -5, -15, -10, 0, 5, 10, 20]
        _mo_names    = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        _mo_vals = []
        # 2×6 grid — left col Jan–Jun, right col Jul–Dec
        _col_a, _col_b = st.columns(2)
        for _mi, (_mn, _md) in enumerate(zip(_mo_names, _mo_defaults)):
            _col = _col_a if _mi < 6 else _col_b
            with _col:
                _mv = st.number_input(
                    f"{_mn} %", -50, 100, _md, 5,
                    key=f"mo_{_mi}",
                    help=f"Volume adjustment for {_mn} vs annual average. 0 = exactly average volume."
                )
            _mo_vals.append(_mv / 100.0)
        # Use raw percentages directly — 0% = base visits/day, no normalization
        quarterly_impacts = _mo_vals  # kept as variable name for chart compatibility
        s_idx = [1.0 + _mo_vals[m] for m in range(12)]
        pv = [base_visits * s_idx[m] * peak_factor for m in range(12)]
        st.caption(f"Range: **{min(pv):.0f}** – **{max(pv):.0f}** visits/day  ·  avg **{sum(pv)/12:.1f}**/day")

    with st.expander("LOAD BAND TARGET", expanded=True):
        st.caption("Optimizer targets a pts/APC range. FTE derived monthly from demand.")
        lb1, lb2c = st.columns(2)
        with lb1:  load_lo     = st.number_input("Band Floor (pts/APC)", 15.0, 50.0, 30.0, 1.0,
            help="Minimum acceptable load. If load drops BELOW this, the optimizer sheds or pauses hiring — you have more staff than demand requires. Set this to your comfortable lower utilization bound (e.g. 28 pts/APC).")
        with lb2c: load_hi     = st.number_input("Band Ceiling (pts/APC)", 20.0, 60.0, 38.0, 1.0,
            help="Maximum acceptable load. If load rises ABOVE this, the optimizer adds flex coverage — demand is exceeding your permanent staff capacity. Set this to just below your Green ceiling (e.g. 36 pts/APC).")
        load_winter = st.number_input("Winter Load Target (pts/APC)", 15.0, 60.0, 36.0, 1.0,
        help="Target load during Nov–Feb flu season. Can be set tighter (lower) to ensure flu surge capacity, or at Green ceiling (36) for efficient use of winter hires.")
        use_band    = st.checkbox("Use Load Band Mode", value=True)
        min_coverage = st.number_input("Minimum Coverage FTE", 0.5, 10.0, 2.33, 0.1,
            help="FTE floor enforced at all times — clinic never drops below this. Default 2.33 = 1 provider × 7 days ÷ 3 shifts/week for 7-day coverage. Use 1.67 for 5-day, 2.0 for 6-day.")
        if use_band:
            st.caption(f"Band: **{load_lo:.0f}** - **{load_hi:.0f}** pts/APC  |  Winter: **{load_winter:.0f}**  |  Min: **{min_coverage:.2f} FTE**")

    with st.expander("SHIFT STRUCTURE"):
        op_days   = st.number_input("Operating Days/Week", 1, 7, 7,
            help="Days per week the clinic is open. Drives total shift slots and FTE-per-slot conversion.")
        shift_hrs = st.number_input("Hours/Shift", 4.0, 24.0, 12.0, 0.5,
            help="Length of each clinical shift in hours. Used to calculate support staff hours and shifts-per-day default.")
        # shifts_per_day is always 1 — the model determines concurrent APC need
        # from volume/budget math. The operator sees the fractional result as
        # shift scheduling guidance (e.g. 1.25 APCs = one 12h + one 4h shift).
        shifts_day = 1
        fte_shifts = st.number_input("Shifts/Week per APC", 1.0, 7.0, 3.0, 0.5,
            help="How many shifts per week each APC is contracted to work. Key driver of FTE-per-slot: 7 days / 3 shifts = 2.33 FTE needed per concurrent slot.")
        fte_frac   = st.number_input("FTE Fraction of Contract", 0.1, 1.0, 0.9, 0.05,
            help="The FTE value assigned to one APC contract. 0.9 = each APC counts as 0.9 FTE for cost purposes. Does not affect scheduling coverage math.")

    with st.expander("STAFFING MODEL"):
        flu_anchor        = st.selectbox("Flu Anchor Month", list(range(1,13)), index=11,
                                         format_func=lambda x: MONTH_NAMES[x-1],
                                         help="The month by which you need fully independent APCs on floor. Drives requisition posting deadline calculation.")
        summer_shed_floor = 85  # removed from UI — load-band optimizer handles shed floor implicitly

    with st.expander("PROVIDER COMPENSATION"):
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#7A8799;padding:0 0 0.35rem;'>"
                    "PROVIDER MIX</div>", unsafe_allow_html=True)

        # APC % slider — physician % auto-derives
        _apc_pct = st.slider("APC coverage %", 0, 100, 100, 5,
            help="Percent of provider hours covered by APCs (NPs/PAs). Physician % = 100 − APC %.")
        _phys_pct = 100 - _apc_pct
        st.caption(f"APC **{_apc_pct}%**  ·  Physician **{_phys_pct}%**")

        _pm1, _pm2 = st.columns(2)
        with _pm1:
            _apc_salary = st.number_input("APC salary — fully loaded ($)",
                100_000, 500_000, 175_000, 5_000, format="%d",
                help="Fully loaded annual cost per APC — base salary, benefits, malpractice.")
        with _pm2:
            _phys_salary = st.number_input("Physician salary — fully loaded ($)",
                100_000, 800_000, 280_000, 10_000, format="%d",
                help="Fully loaded annual cost per physician — base salary, benefits, malpractice.",
                disabled=(_phys_pct == 0))

        # Blended avg = weighted by coverage %
        perm_cost_i = int(_apc_pct/100 * _apc_salary + _phys_pct/100 * _phys_salary)
        if _phys_pct > 0:
            st.caption(f"Blended avg: **${perm_cost_i:,.0f}/yr** per FTE  "
                       f"({_apc_pct}% × ${_apc_salary/1e3:.0f}K + "
                       f"{_phys_pct}% × ${_phys_salary/1e3:.0f}K)")
        else:
            st.caption(f"Blended avg: **${perm_cost_i:,.0f}/yr** per FTE  (APC-only)")
        rev_visit   = st.number_input("Net Revenue/Visit ($)", 50.0, 300.0, 140.0, 5.0,
            help="Net revenue collected per patient visit after payer mix adjustments. Used to estimate lost revenue during Red months when patient throughput is capped.")
        swb_target  = st.number_input("SWB Target ($/Visit)", 5.0, 150.0, 85.0, 1.0,
            help="Salary, wages & benefits cost per visit — your key efficiency metric. Includes APC + support staff costs divided by annual visits. Exceeding this triggers a penalty in the optimizer.")
        fixed_overhead = st.number_input("Monthly Fixed Overhead ($)", 0, 500_000, 0, 5_000, format="%d",
            help="Optional: rent, non-clinical staff, equipment, etc. When $0, output is EBITDA Contribution from Staffing. When > $0, reflects full EBITDA. Does not affect FTE optimizer.")

    with st.expander("SUPPORT STAFF  (SWB only)"):
        st.caption("Costs fold into SWB/visit only — not included in FTE optimizer.")

        flex_cost_i = st.number_input("Premium / Flex APC Cost/Year ($)", 100_000, 600_000, 225_000, 10_000, format="%d",
            help="Annualized cost of a flex or locum APC. Typically 30–50% above perm due to agency fees. Applied when load exceeds Yellow threshold and flex coverage is needed.")

        # ── 1. Comp multipliers ───────────────────────────────────────────────
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#7A8799;padding:0.5rem 0 0.25rem;'>"
                    "COMPENSATION MULTIPLIERS</div>", unsafe_allow_html=True)
        sm1,sm2,sm3=st.columns(3)
        with sm1: benefits_load = st.number_input("Benefits %", 0.0, 60.0, 30.0, 1.0,
            help="Benefits load as % of base wages. Includes health insurance, retirement, PTO accrual. Typically 25–35%.")
        with sm2: bonus_pct_ss  = st.number_input("Bonus %", 0.0, 30.0, 10.0, 1.0,
            help="Annual bonus as % of base wages. Applied uniformly across all support staff roles.")
        with sm3: ot_sick_pct   = st.number_input("OT+Sick %", 0.0, 20.0, 4.0, 0.5,
            help="Overtime and sick leave premium as % of base wages. Accounts for unplanned coverage costs.")
        _mult_preview = 1 + benefits_load/100 + bonus_pct_ss/100 + ot_sick_pct/100
        st.caption(f"Total multiplier: **{_mult_preview:.2f}×** applied to all hourly rates")

        # ── 2. Hourly rates ───────────────────────────────────────────────────
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#7A8799;padding:0.5rem 0 0.25rem;'>"
                    "HOURLY RATES  (base, before multiplier)</div>", unsafe_allow_html=True)
        phys_rate = st.number_input("Physician ($/hr)", 50.0, 300.0, 135.79, 1.0,
            help="Physician hourly rate — used only when physician supervision hours > 0 below.")
        app_rate = 62.00  # not user-configurable; APC cost set via Provider Compensation above
        r3,r4 = st.columns(2)
        with r3: ma_rate   = st.number_input("MA ($/hr)",          8.0,  60.0,  24.14, 0.25)
        with r4: psr_rate  = st.number_input("PSR ($/hr)",         8.0,  60.0,  21.23, 0.25)
        r5,r6 = st.columns(2)
        with r5: rt_rate   = st.number_input("Rad Tech ($/hr)",    8.0,  80.0,  31.36, 0.25)
        with r6: sup_rate  = st.number_input("Supervisor ($/hr)",  8.0,  80.0,  28.25, 0.25)

        # ── 3. Staffing ratios ────────────────────────────────────────────────
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#7A8799;padding:0.5rem 0 0.25rem;'>"
                    "STAFFING RATIOS  (per APC on floor)</div>", unsafe_allow_html=True)
        ra1,ra2 = st.columns(2)
        with ra1: ma_ratio  = st.number_input("MA per APC", 0.0, 4.0, 1.0, 0.25,
            help="Medical assistants per APC on floor per shift. 1.0 = one MA for every APC. Scales with concurrent APC count each month.")
        with ra2: psr_ratio = st.number_input("PSR per APC", 0.0, 4.0, 1.0, 0.25,
            help="Patient service reps (front desk) per APC on floor. 1.0 = one PSR per APC. Scales with concurrent APC count.")
        rt_flat = st.number_input("Rad Tech FTE (flat per shift)", 0.0, 4.0, 1.0, 0.5,
            help="Rad tech FTE per shift — flat cost regardless of how many APCs are on floor. 1.0 = one RT always present when clinic is open.")

        # ── 4. Supervision ────────────────────────────────────────────────────
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#7A8799;padding:0.5rem 0 0.25rem;'>"
                    "SUPERVISION  (cost added only when hrs > 0)</div>", unsafe_allow_html=True)
        sv1,sv2 = st.columns(2)
        with sv1: phys_sup_hrs  = st.number_input("Physician sup (hrs/mo)", 0.0, 200.0, 0.0, 5.0,
            help="Hours/month a supervising physician is on-site or available. Cost = physician rate × hours × multiplier. Leave at 0 if APCs practice independently.")
        with sv2: sup_admin_hrs = st.number_input("Supervisor admin (hrs/mo)", 0.0, 200.0, 0.0, 5.0,
            help="Hours/month for an operations supervisor or clinical lead. Cost = supervisor rate × hours × multiplier. Leave at 0 if not applicable.")
        if phys_sup_hrs > 0 or sup_admin_hrs > 0:
            _pm = phys_sup_hrs  * phys_rate * _mult_preview if phys_sup_hrs  > 0 else 0
            _sm = sup_admin_hrs * sup_rate  * _mult_preview if sup_admin_hrs > 0 else 0
            st.caption(f"Supervision cost: "
                       + (f"Physician **${_pm:,.0f}/mo**" if phys_sup_hrs > 0 else "")
                       + (" · " if phys_sup_hrs > 0 and sup_admin_hrs > 0 else "")
                       + (f"Supervisor **${_sm:,.0f}/mo**" if sup_admin_hrs > 0 else ""))

    with st.expander("HIRING PHYSICS"):
        days_sign = st.number_input("Days to Sign", 7, 180, 90, 7,
            help="Days from posting a requisition to signed offer letter. Includes sourcing, interviewing, and offer negotiation.")
        days_cred = st.number_input("Days to Credential", 7, 180, 90, 7,
            help="Days from signed offer to credentialed and cleared to see patients. Includes hospital/payer credentialing and state licensing.")
        days_ind  = st.number_input("Days to Onboard/Train", 7, 180, 30, 7,
            help="Days from credentialed start date to working fully independently. Includes orientation, EMR training, and supervised shifts before solo practice.")
        annual_att = st.number_input("Annual Attrition Rate %", 1.0, 50.0, 18.0, 1.0,
            help="Expected annual turnover as % of total staff. 18% = roughly 1 in 6 APCs leaves per year. Divided by 12 for monthly simulation. Increases with overwork if Overload Attrition Factor > 0.")
        st.caption(f"Monthly rate: **{annual_att/12:.2f}%**")

    with st.expander("ATTRITION SENSITIVITY"):
        st.caption("Overwork amplifies attrition. 20% overload x factor=1.5 adds 30% to base rate.")
        overload_att_factor = st.slider("Overload Attrition Factor", 0.0, 5.0, 1.5, 0.1,
            help="How much overwork amplifies attrition. Formula: effective_rate = base_rate × (1 + factor × excess_load%). At 1.5: running 20% over budget multiplies attrition by 1.30×. Set to 0 to disable.")
        _ex_mult = 1 + overload_att_factor * 0.20
        st.caption(f"At 20% overload: base rate x **{_ex_mult:.2f}**  |  "
                   f"{annual_att:.1f}%/yr -> **{annual_att * _ex_mult:.1f}%/yr**")

    with st.expander("TURNOVER & PENALTY RATES"):
        # ── Replacement cost — model-derived default with override ────────────
        # All-in direct cost breakdown (matches Turnover Cost tab):
        #   Recruiting 20% + Paid pipeline 6.9mo + Flex premium + Admin = ~90%
        _lead_days_t  = days_sign + days_cred + days_ind
        _pipeline_mo  = _lead_days_t / 30.44
        _recruiting   = perm_cost_i * 0.20
        _pipeline_c   = (perm_cost_i / 12) * _pipeline_mo
        _flex_prem    = (flex_cost_i - perm_cost_i) / 365 * (_lead_days_t + 30) * 0.5
        _admin_c      = 5_000
        _derived_pct  = (_recruiting + _pipeline_c + _flex_prem + _admin_c) / perm_cost_i * 100
        _derived_pct_r = round(_derived_pct / 5) * 5   # snap to nearest 5%

        st.caption(f"Model-derived all-in replacement cost: **{_derived_pct_r:.0f}%** "
                   f"(${perm_cost_i*_derived_pct_r/100:,.0f}) · see **Turnover Cost** tab for breakdown")
        _use_derived = st.toggle("Use model-derived rate", value=True,
            help=f"ON = use the {_derived_pct_r:.0f}% derived from your pipeline inputs. "
                 f"OFF = enter a custom override.")
        if _use_derived:
            turnover_pct = float(_derived_pct_r)
            st.markdown(f"<div style='font-size:0.76rem;color:#0A6B4A;padding:0.2rem 0;'>"
                        f"✓ Using <b>{turnover_pct:.0f}%</b> = <b>${perm_cost_i*turnover_pct/100:,.0f}</b> / departure</div>",
                        unsafe_allow_html=True)
        else:
            turnover_pct = st.slider("Replacement Cost Override (% salary)", 10.0, 200.0,
                                     float(_derived_pct_r), 5.0,
                                     help="Override the model-derived rate. 100% = one full year's salary per departure.")
            st.caption(f"Override: **{turnover_pct:.0f}%** = **${perm_cost_i*turnover_pct/100:,.0f}** / departure")

        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

        # ── Burnout & optimizer penalties ─────────────────────────────────────
        tp2,tp3 = st.columns(2)
        with tp2: burnout_pct   = st.number_input("Burnout Penalty (% sal/red mo)", 5.0, 100.0, 25.0, 5.0,
            help="Economic penalty per Red zone month as % of annual APC salary. 25% = $43,750 per Red month on a $175k salary.")
        with tp3: overstaff_pen = st.number_input("Overstaff ($/FTE-mo)", 500, 20_000, 3_000, 500, format="%d",
            help="Penalty per FTE-month of overstaffing. Keeps optimizer from over-hiring.")
        swb_pen = st.number_input("SWB Violation ($)", 50_000, 2_000_000, 500_000, 50_000, format="%d",
            help="One-time penalty if annual SWB/visit exceeds target. Large value = near-hard constraint.")
        st.caption(f"Burnout/red mo: **${perm_cost_i*burnout_pct/100:,.0f}**  |  "
                   f"Overstaff: **${overstaff_pen:,}/FTE-mo**")

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    run_opt = st.button("RUN OPTIMIZER", type="primary", use_container_width=True)

# ── Config ────────────────────────────────────────────────────────────────────
support_cfg = SupportStaffConfig(
    physician_rate_hr=phys_rate, app_rate_hr=app_rate,
    psr_rate_hr=psr_rate, ma_rate_hr=ma_rate,
    rt_rate_hr=rt_rate, supervisor_rate_hr=sup_rate,
    ma_ratio=ma_ratio, psr_ratio=psr_ratio, rt_flat_fte=rt_flat,
    supervisor_hrs_mo=phys_sup_hrs, supervisor_admin_mo=sup_admin_hrs,
    benefits_load_pct=benefits_load/100, bonus_pct=bonus_pct_ss/100, ot_sick_pct=ot_sick_pct/100,
)
cfg = ClinicConfig(
    base_visits_per_day=base_visits, budgeted_patients_per_provider_per_day=budget_ppp,
    peak_factor=peak_factor, monthly_volume_impact=quarterly_impacts,
    annual_growth_pct=annual_growth,
    operating_days_per_week=int(op_days), shifts_per_day=int(shifts_day),
    shift_hours=shift_hrs, fte_shifts_per_week=fte_shifts, fte_fraction=fte_frac,
    load_band_lo=load_lo, load_band_hi=load_hi, load_winter_target=load_winter, use_load_band=use_band,
    min_coverage_fte=min_coverage,
    flu_anchor_month=flu_anchor, summer_shed_floor_pct=summer_shed_floor/100,
    annual_provider_cost_perm=perm_cost_i, annual_provider_cost_flex=flex_cost_i,
    net_revenue_per_visit=rev_visit, swb_target_per_visit=swb_target, support=support_cfg,
    days_to_sign=days_sign, days_to_credential=days_cred, days_to_independent=days_ind,
    annual_attrition_pct=annual_att, overload_attrition_factor=overload_att_factor,
    turnover_replacement_pct=turnover_pct, burnout_pct_per_red_month=burnout_pct,
    overstaff_penalty_per_fte_month=overstaff_pen, swb_violation_penalty=swb_pen,
    monthly_fixed_overhead=fixed_overhead,
)
# Store provider mix for acceleration lever
cfg._apc_pct     = _apc_pct
cfg._apc_salary  = _apc_salary
cfg._phys_salary = _phys_salary

if run_opt:
    with st.spinner("Running grid search..."):
        best, all_p = optimize(cfg)
    st.session_state.update(best_policy=best, all_policies=all_p, optimized=True,
                            manual_b=best.base_fte, manual_w=best.winter_fte, manual_policy=None)
    st.success(f"Optimizer complete — {len(all_p):,} policies evaluated")

# ══════════════════════════════════════════════════════════════════════════════
# PRE-OPTIMIZER LANDING
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.optimized:
    st.markdown("## PERMANENT STAFFING MODEL")
    st.title("Urgent Care\nStaffing Optimizer")
    st.markdown(f"<p style='font-size:0.9rem;color:{SLATE};margin-top:-0.4rem;margin-bottom:2rem;'>"
                f"36-month horizon | load-band optimization | attrition-as-burnout model</p>",
                unsafe_allow_html=True)
    st.info("Configure your clinic profile in the sidebar, then click **RUN OPTIMIZER**.")
    st.markdown("## DEMAND PREVIEW")
    si  = cfg.seasonality_index
    mv  = [base_visits * si[m] * peak_factor * (1 + annual_growth/100)**(m/12) for m in range(12)]
    mv_y3 = [base_visits * si[m] * peak_factor * (1 + annual_growth/100)**((24+m)/12) for m in range(12)]
    fr  = [v / budget_ppp * cfg.fte_per_shift_slot for v in mv]
    bft = (base_visits / budget_ppp) * cfg.fte_per_shift_slot
    fp  = make_subplots(specs=[[{"secondary_y": True}]])
    for mi in range(12):
        im = _mo_vals[mi]
        fp.add_annotation(x=mi, y=max(mv)*1.09,
                          text=f"{chr(43) if im>=0 else chr(45)}{im*100:.0f}%",
                          showarrow=False, font=dict(size=9, color=Q_COLORS[MONTH_TO_QUARTER[mi]]),
                          bgcolor="rgba(255,255,255,0.85)", borderpad=2)
    fp.add_bar(x=MONTH_NAMES,y=mv,name="Seasonal volume",marker_color=C_BARS)
    fp.add_scatter(x=MONTH_NAMES,y=fr,name="FTE @ Budget",
                   line=dict(color=C_DEMAND,width=3),mode="lines+markers",
                   marker=dict(size=9,color=C_DEMAND,symbol="diamond",line=dict(color="white",width=2)),
                   secondary_y=True)
    fp.add_hline(y=bft,line_dash="dash",line_color=SLATE,line_width=1.5,
                 annotation_text=f"Baseline FTE {bft:.1f}",
                 annotation_font=dict(size=10,color=SLATE),secondary_y=True)
    if annual_growth > 0:
        fr_y3 = [v / budget_ppp * cfg.fte_per_shift_slot for v in mv_y3]
        fp.add_bar(x=MONTH_NAMES, y=mv_y3, name="Y3 projected volume",
                   marker_color="rgba(200,75,17,0.18)", secondary_y=False)
        fp.add_scatter(x=MONTH_NAMES, y=fr_y3, name="FTE Required (Y3)",
                       line=dict(color=C_ACTUAL, width=2, dash="dash"), mode="lines",
                       opacity=0.6, secondary_y=True)
    fp.update_layout(**mk_layout(height=400,barmode="stack",title="Annual Volume & FTE Requirement"))
    fp.update_yaxes(title_text="Visits / Day",secondary_y=False)
    fp.update_yaxes(title_text="FTE Required",secondary_y=True,showgrid=False)
    st.plotly_chart(fp,use_container_width=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def active_policy():
    return st.session_state.get("manual_policy") or st.session_state.best_policy

def mlabel(mo):
    return f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}"

best   = st.session_state.best_policy
s      = best.summary
budget = cfg.budgeted_patients_per_provider_per_day

# ══════════════════════════════════════════════════════════════════════════════
# HERO CHART
# ══════════════════════════════════════════════════════════════════════════════
def render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp, peak_factor, title=None, monthly_impacts=None):
    yr1    = [mo for mo in pol.months if mo.year == 1]
    labels = [MONTH_NAMES[mo.calendar_month-1] for mo in yr1]
    visits_nf  = [base_visits * cfg.seasonality_index[mo.calendar_month-1] * peak_factor for mo in yr1]
    fte_req    = [mo.demand_fte_required for mo in yr1]
    paid_fte   = [mo.paid_fte for mo in yr1]
    eff_fte    = [mo.effective_fte for mo in yr1]
    dot_colors = [HIRE_COLORS.get(mo.hiring_mode, SLATE) for mo in yr1]
    summer_floor = pol.base_fte * cfg.summer_shed_floor_pct

    fig = make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=0.10,row_heights=[0.40,0.60])

    for qi,(mq,bg) in enumerate(zip(Q_MONTH_GROUPS,Q_BG)):
        fig.add_vrect(x0=mq[0]-0.5,x1=mq[-1]+0.5,fillcolor=bg,layer="below",line_width=0,row=1,col=1)
    fig.add_bar(x=labels,y=visits_nf,name="Seasonal volume",marker_color=C_BARS,marker_line_width=0,row=1,col=1)
    fig.add_hline(y=base_visits,line_dash="dash",line_color=SLATE,line_width=1,
                  annotation_text=f"Base {base_visits:.0f}/day",annotation_position="right",
                  annotation_font=dict(size=9,color=SLATE),row=1,col=1)
    _m_impacts = monthly_impacts if monthly_impacts is not None else quarterly_impacts
    for mi, im in enumerate(_m_impacts):
        fig.add_annotation(row=1,col=1,xref="x",yref="paper",x=mi,y=1.0,
                           text=f"{chr(43) if im>=0 else chr(45)}{abs(im*100):.0f}%",
                           showarrow=False,yanchor="bottom",
                           font=dict(size=9,color=Q_COLORS[MONTH_TO_QUARTER[mi]]),
                           bgcolor="rgba(255,255,255,0.88)",borderpad=2)

    for qi,(mq,bg) in enumerate(zip(Q_MONTH_GROUPS,Q_BG)):
        fig.add_vrect(x0=mq[0]-0.5,x1=mq[-1]+0.5,fillcolor=bg,layer="below",line_width=0,row=2,col=1)

    # Load band shading on FTE panel
    if cfg.use_load_band:
        band_hi_fte = [fte_for_band(v, cfg.load_band_hi, cfg) for v in visits_nf]
        band_lo_fte = [fte_for_band(v, cfg.load_band_lo, cfg) for v in visits_nf]
        fig.add_scatter(x=labels+labels[::-1], y=band_hi_fte+band_lo_fte[::-1],
                        fill="toself", fillcolor="rgba(10,117,84,0.08)",
                        line=dict(width=0), showlegend=True, name="Target load band", row=2, col=1)

    for i in range(len(labels)):
        gc = "rgba(10,117,84,0.08)" if paid_fte[i]>=fte_req[i] else "rgba(185,28,28,0.08)"
        fig.add_vrect(x0=i-0.48,x1=i+0.48,fillcolor=gc,layer="below",line_width=0,row=2,col=1)

    for yval,label,color in [
        (pol.winter_fte, f"Winter {pol.winter_fte:.1f}", NAVY),
        (pol.base_fte,   f"Base {pol.base_fte:.1f}",    SLATE),
        (summer_floor,   f"Summer floor {summer_floor:.1f}", C_GREEN),
    ]:
        fig.add_hline(y=yval,line_dash="dot",line_color=color,line_width=1.2,
                      annotation_text=label,annotation_position="right",
                      annotation_font=dict(size=9,color=color),row=2,col=1)

    fig.add_scatter(x=labels,y=eff_fte,name="Effective FTE (ramp-adj)",
                    mode="lines",line=dict(color=C_ACTUAL,width=2,dash="dash"),opacity=0.45,row=2,col=1)
    fig.add_scatter(x=labels,y=paid_fte,name="Paid FTE",
                    mode="lines+markers",line=dict(color=C_ACTUAL,width=3.5),
                    marker=dict(size=11,color=dot_colors,line=dict(color="white",width=2.5)),row=2,col=1)
    fig.add_scatter(x=labels,y=fte_req,name="FTE Required (demand)",
                    mode="lines+markers",line=dict(color=C_DEMAND,width=3.5),
                    marker=dict(size=9,symbol="diamond",color=C_DEMAND,line=dict(color="white",width=2)),row=2,col=1)

    fig.update_layout(
        height=580, template="plotly_white", paper_bgcolor="white", plot_bgcolor="white", barmode="stack",
        font=dict(family="'DM Sans', system-ui, sans-serif",size=11,color=SLATE),
        title=dict(text=title or "Annual Demand & Staffing Model - Year 1",
                   font=dict(family="'EB Garamond', Georgia, serif",size=15,color=INK),x=0,xanchor="left"),
        margin=dict(t=60,b=80,l=60,r=140),
        legend=dict(orientation="h",y=-0.16,x=0,font=dict(size=11,color=SLATE),
                    bgcolor="rgba(0,0,0,0)",borderwidth=0,itemsizing="constant"),
        xaxis=dict(showgrid=False,zeroline=False,linecolor=RULE,tickfont=dict(size=11)),
        xaxis2=dict(showgrid=False,zeroline=False,linecolor=RULE,tickfont=dict(size=11,color=SLATE)),
        yaxis=dict(title="Visits / Day",showgrid=True,gridcolor=RULE,zeroline=False,tickfont=dict(size=11)),
        yaxis2=dict(title="FTE",showgrid=True,gridcolor=RULE,zeroline=False,tickfont=dict(size=11)),
    )
    for row,text in [(1,"PATIENT VOLUME"),(2,"FTE - DEMAND vs ACTUAL STAFFING")]:
        fig.add_annotation(row=row,col=1,xref="paper",yref="paper",x=0,y=1.01,
                           xanchor="left",yanchor="bottom",
                           text=f"<span style='font-size:9px;font-weight:600;letter-spacing:0.12em;color:{SLATE};'>{text}</span>",
                           showarrow=False)
    return fig

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD HEADER + KPIs
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## PERMANENT STAFFING MODEL")
st.title("Staffing Model")
st.markdown(f"<p style='font-size:0.87rem;color:{SLATE};margin-top:-0.5rem;margin-bottom:1.5rem;'>"
            f"36-month horizon | load-band optimizer | attrition-as-burnout model</p>",unsafe_allow_html=True)
st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1rem;'>",unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SHARED CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════
_swb_actual     = s["annual_swb_per_visit"]
_swb_target     = cfg.swb_target_per_visit
_swb_delta_pv   = _swb_actual - _swb_target
_ann_visits_kpi = s["annual_visits"]
_swb_impact_ann = -_swb_delta_pv * _ann_visits_kpi
_total_cap_3yr  = sum(mo.visits_captured for mo in best.months)
_swb_impact_3yr = -_swb_delta_pv * _total_cap_3yr
_perm_3yr       = sum(mo.permanent_cost for mo in best.months)
_supp_3yr       = sum(mo.support_cost   for mo in best.months)
_var_clr        = "#0A6B4A" if _swb_delta_pv <= 0 else "#B91C1C"
_var_word       = "favorable" if _swb_delta_pv <= 0 else "unfavorable"
_var_arrow      = "▼" if _swb_delta_pv <= 0 else "▲"
_impact_sign    = "+" if _swb_impact_ann >= 0 else "−"
_impact_abs_ann = abs(_swb_impact_ann)
_impact_abs_3yr = abs(_swb_impact_3yr)

_es             = best.ebitda_summary
_ann_swb        = _es["swb"]      / 3
_ann_flex       = _es["flex"]     / 3
_ann_turnover   = _es["turnover"] / 3
_ann_burnout    = _es["burnout"]  / 3
_ann_visits_3yr = _total_cap_3yr  / 3
_ann_swb_goal   = _swb_target * _ann_visits_3yr

_oa = s.get("total_overload_attrition", 0)

# ─── VPD / provider stats ────────────────────────────────────────────────────
_all_vpd_prov = [mo.patients_per_provider_per_shift for mo in best.months]
_vpd_avg = sum(_all_vpd_prov) / len(_all_vpd_prov)
_vpd_min = min(_all_vpd_prov)
_vpd_max = max(_all_vpd_prov)

# ─── Turnover risk label ─────────────────────────────────────────────────────
# Scale thresholds by annualised attrition rate, not absolute dollars,
# so the label stays meaningful regardless of clinic size or salary level.
_tot_turn_events = s.get("total_turnover_events", 0)
_turn_cost_3yr   = _es["turnover"]
_ann_attrition   = cfg.annual_attrition_pct   # 0–50 %
if _ann_attrition == 0 or _tot_turn_events < 0.1:
    _turn_risk_lbl = "None"
    _turn_risk_clr = "#0A6B4A"
elif _ann_attrition < 10:
    _turn_risk_lbl = "Low risk"
    _turn_risk_clr = "#0A6B4A"
elif _ann_attrition < 20:
    _turn_risk_lbl = "Moderate"
    _turn_risk_clr = "#92600A"
else:
    _turn_risk_lbl = "High risk"
    _turn_risk_clr = "#B91C1C"

# ─── SWB tile border color ───────────────────────────────────────────────────
_swb_tile_clr = "#B91C1C" if _swb_delta_pv > 0 else "#0A6B4A"

# ─── Marginal row ────────────────────────────────────────────────────────────
_ma_row = ""
if best.marginal_analysis:
    ma    = best.marginal_analysis
    _net  = ma["net_annual"]
    _mc   = "#0A6B4A" if _net > 0 else "#92600A"
    _mpay = "never" if ma["payback_months"] == float("inf") else f"{ma['payback_months']:.0f} mo"
    _ma_row = (
        f"<span style='color:#7A6200;font-size:0.60rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.13em;'>+{ma['delta_fte']:.1f} FTE Marginal</span>"
        f"<span style='color:#4A5568;font-size:0.76rem'>Saves "
        f"<b style='color:#B91C1C'>{ma['red_months_saved']}R</b> + "
        f"<b style='color:#92600A'>{ma['yellow_months_saved']}Y</b> zone-months</span>"
        f"<span style='color:#4A5568;font-size:0.76rem'>Net annual: "
        f"<b style='color:{_mc}'>${_net:+,.0f}</b></span>"
        f"<span style='color:#4A5568;font-size:0.76rem'>Payback: <b>{_mpay}</b>"
        f"<span title='Months until the cost of adding 0.5 FTE is offset by savings from avoided Yellow/Red zone months. \'Never\' means the hire would be a net cost — current staffing is at or above the EBITDA-optimal point.' "
        f"style='cursor:help;margin-left:3px;color:#7A8799;font-size:0.70rem;border-bottom:1px dotted #7A8799;'>?</span></span>"
    )

# ─── Years-to-goal calculation ───────────────────────────────────────────────
# Project forward: fixed staff cost stays ~constant; visits grow with annual_growth_pct.
# SWB/visit = staff_cost / (vpd × op_days).  Find the year it crosses the target.
_staff_cost_ann = (_perm_3yr + _supp_3yr) / 3        # annualised perm+support
_base_vpd       = cfg.base_visits_per_day
_growth         = cfg.annual_growth_pct / 100.0
_op_days        = cfg.operating_days_per_week * 52
# ─── Per-year data for year cards ────────────────────────────────────────────
_yr_data = {}
for _yr in [1, 2, 3]:
    _yr_mos   = [mo for mo in best.months if mo.year == _yr]
    _yr_vis   = sum(mo.visits_captured   for mo in _yr_mos)
    _yr_perm  = sum(mo.permanent_cost    for mo in _yr_mos)
    _yr_supp  = sum(mo.support_cost      for mo in _yr_mos)
    _yr_flex  = sum(mo.flex_cost         for mo in _yr_mos)
    _yr_turn  = sum(mo.turnover_cost     for mo in _yr_mos)
    _yr_burn  = sum(mo.burnout_penalty   for mo in _yr_mos)
    _yr_swb_a = (_yr_perm + _yr_supp) / _yr_vis if _yr_vis > 0 else 0
    _yr_goal_v= _swb_target * _yr_vis
    _yr_act   = _yr_perm + _yr_supp
    _yr_net_v = (_yr_goal_v - _yr_act) - _yr_flex - _yr_turn - _yr_burn
    _yr_data[_yr] = {
        "vis": _yr_vis, "flex": _yr_flex, "turn": _yr_turn, "burn": _yr_burn,
        "swb_actual": _yr_swb_a, "goal": _yr_goal_v, "act": _yr_act, "net_var": _yr_net_v,
        "G": sum(1 for m in _yr_mos if m.zone=="Green"),
        "Y": sum(1 for m in _yr_mos if m.zone=="Yellow"),
        "R": sum(1 for m in _yr_mos if m.zone=="Red"),
        "peak": max(m.patients_per_provider_per_shift for m in _yr_mos),
    }

_yr_goal        = None
_yr_swb_strip   = []   # list of (year, swb_per_visit) for the strip
# Strip uses ACTUAL simulated SWB/visit for yrs 1-3 (already in _yr_data),
# then extrapolates yrs 4-7 using the yr2→yr3 trend.
# This is data-driven and captures real cost/volume dynamics from the simulation.
_swb_yr = {yr: _yr_data[yr]["swb_actual"] for yr in [1, 2, 3]}
_trend   = _swb_yr[3] - _swb_yr[2]   # $/visit per year (negative = improving)

for _yy in range(1, 11):
    if _yy <= 3:
        _swb_proj = _swb_yr[_yy]
    else:
        _swb_proj = max(0, _swb_yr[3] + _trend * (_yy - 3))
    _yr_swb_strip.append((_yy, _swb_proj))
    if _swb_proj <= _swb_target and _yr_goal is None:
        _yr_goal = _yy

# Acceleration scenarios: scale the yr2→yr3 trend by growth/cost multipliers
# faster growth = steeper negative trend; lower cost = immediate offset
def _yrs_to_goal(growth_override=None, cost_mult=1.0, load_mult=1.0):
    g_ratio   = ((growth_override or _growth) / max(_growth, 0.001))
    trend_adj = _trend * g_ratio * load_mult   # steeper improvement if faster growth
    for yy in range(1, 26):
        if yy <= 3:
            swb_p = _swb_yr[yy] * cost_mult
        else:
            swb_p = max(0, _swb_yr[3] + trend_adj * (yy - 3)) * cost_mult
        if swb_p <= _swb_target:
            return yy
    return None

_accel_30   = _yrs_to_goal(growth_override=0.30)
_accel_load = _yrs_to_goal(load_mult=1.20)   # tighter staffing = ~same cost fewer FTE
_accel_combo= _yrs_to_goal(growth_override=0.30, cost_mult=0.92)

# PSR cross-train scenario: reduce PSR ratio from current to 0.5
# PSR cost is part of support cost. Compute savings as fraction of total SWB cost.
_psr_current  = cfg.support.psr_ratio
_psr_target   = max(0.5, _psr_current * 0.5)   # halve PSR ratio (floor 0.5)
_psr_only_ann = (_supp_3yr / 3) * ((_psr_current - _psr_target) / max(_psr_current, 0.01))                 * (cfg.support.psr_rate_hr / (cfg.support.psr_rate_hr + cfg.support.ma_rate_hr + 0.01))
_psr_cost_mult= max(0.5, 1.0 - (_psr_only_ann / max(_staff_cost_ann, 1)))
_accel_psr    = _yrs_to_goal(cost_mult=_psr_cost_mult) if _psr_current > 0.5 else None
_psr_save_pct = round((1 - _psr_cost_mult) * 100)
_psr_label    = (f"↓ Cross-train staff / reduce PSR ratio {_psr_current:.1f}→{_psr_target:.1f}"
                 f"  <span style='font-size:0.63rem;color:#4A5568;font-weight:400;'>"
                 f"(−{_psr_save_pct}% support cost)</span>")

# ─── Strip + acceleration HTML (all deps now satisfied) ──────────────────────
def _save_str(yrs):
    if yrs is None or _yr_goal is None: return ""
    diff = _yr_goal - yrs
    if diff <= 0: return ""
    return f"−{diff} yr{'s' if diff > 1 else ''}"

def _strip_cell(yr, swb, target):
    if swb <= target:
        bg = "#ECFDF5"; clr = "#0A6B4A"; val = f"${swb:.0f} ✓"
    elif swb <= target * 1.10:
        bg = "#FFFBEB"; clr = "#92600A"; val = f"${swb:.0f}"
    else:
        bg = "#FEF2F2"; clr = "#B91C1C"; val = f"${swb:.0f}"
    return (
        f"<div style='flex:1;padding:0.3rem 0.4rem;background:{bg};"
        f"border-right:1px solid #E2E8F0;min-width:0;'>"
        f"<div style='font-size:0.55rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.09em;color:#7A8799;margin-bottom:1px;'>Yr {yr}</div>"
        f"<div style='font-size:0.70rem;font-weight:700;color:{clr};"
        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{val}</div>"
        f"</div>"
    )

_strip_cells = ""
for (_syy, _sswb) in _yr_swb_strip[:7]:
    _strip_cells += _strip_cell(_syy, _sswb, _swb_target)

_strip_html = (
    f"<div style='display:flex;border:1px solid #E2E8F0;border-radius:3px;"
    f"overflow:hidden;margin-top:0.5rem;'>{_strip_cells}</div>"
)

def _accel_row(label, yrs, bg, border_clr):
    save = _save_str(yrs)
    if not save: return ""
    return (
        f"<div style='display:flex;align-items:flex-start;gap:0.65rem;"
        f"padding:0.42rem 0.6rem;background:{bg};border-radius:3px;"
        f"border-left:3px solid {border_clr};margin-bottom:0.4rem;'>"
        f"<div style='flex:1;font-size:0.72rem;font-weight:600;color:{border_clr};'>{label}"
        f"<div style='font-size:0.67rem;font-weight:400;color:#4A5568;margin-top:0.1rem;'>"
        f"Reaches ${_swb_target:.0f} target by Year {yrs}</div></div>"
        f"<div style='font-size:0.70rem;font-weight:700;color:{border_clr};"
        f"white-space:nowrap;'>{save}</div>"
        f"</div>"
    )

# ── Provider mix shift lever ─────────────────────────────────────────────────
_mix_lever_html = ""
_phys_pct_cur = 100 - getattr(cfg, "_apc_pct", 100)
if _phys_pct_cur > 0:
    _apc_sal    = getattr(cfg, "_apc_salary",  perm_cost_i)
    _phys_sal   = getattr(cfg, "_phys_salary", perm_cost_i)
    _blend_apc  = _apc_sal
    _mix_mult   = _blend_apc / max(perm_cost_i, 1)
    _mix_save_pct = round((1 - _mix_mult) * 100)
    _accel_mix  = _yrs_to_goal(cost_mult=_mix_mult) if _mix_mult < 1.0 else None
    if _accel_mix:
        _mix_lever_html = _accel_row(
            f"↑ Shift provider mix to 100% APC coverage"
            f"  <span style='font-size:0.63rem;color:#4A5568;font-weight:400;'>"
            f"(−{_mix_save_pct}% blended provider cost)</span>",
            _accel_mix, "#FFFBEB", "#92600A"
        )

# ── Attrition reduction lever ─────────────────────────────────────────────────
_att_cur      = cfg.annual_attrition_pct
_att_target   = max(5.0, _att_cur * 0.5)
_att_reduction= (_att_cur - _att_target) / max(_att_cur, 0.001)
_turn_ann     = _turn_cost_3yr / 3
_att_save_ann = _turn_ann * _att_reduction
_att_cost_mult= max(0.5, 1.0 - (_att_save_ann / max(_staff_cost_ann, 1)))
_accel_att    = _yrs_to_goal(cost_mult=_att_cost_mult) if _att_cur > 5 and _att_save_ann > 0 else None
_att_label    = (f"↓ Reduce attrition {_att_cur:.0f}%→{_att_target:.0f}%"
                 f"  <span style='font-size:0.63rem;color:#4A5568;font-weight:400;'>"
                 f"(saves ~${_att_save_ann/1e3:.0f}K/yr in replacement cost)</span>")

# ── Replacement cost reduction lever ─────────────────────────────────────────
_repl_pct_cur    = cfg.turnover_replacement_pct
_repl_pct_target = max(30.0, _repl_pct_cur * 0.6)
_repl_reduction  = (_repl_pct_cur - _repl_pct_target) / max(_repl_pct_cur, 0.001)
_repl_save_ann   = _turn_ann * _repl_reduction
_repl_cost_mult  = max(0.5, 1.0 - (_repl_save_ann / max(_staff_cost_ann, 1)))
_accel_repl      = (_yrs_to_goal(cost_mult=_repl_cost_mult)
                    if _repl_pct_cur > 30 and _repl_save_ann > 0 else None)
_repl_label      = (f"↓ Improve retention / lower replacement cost {_repl_pct_cur:.0f}%→{_repl_pct_target:.0f}% of salary"
                    f"  <span style='font-size:0.63rem;color:#4A5568;font-weight:400;'>"
                    f"(saves ~${_repl_save_ann/1e3:.0f}K/yr)</span>")

_accel_html = ""
_goal_already_met = _swb_delta_pv <= 0
if not _goal_already_met:
    _accel_html += _accel_row("↑ Accelerate volume growth to 30%/yr", _accel_30, "#ECFDF5", "#0A6B4A")
    _accel_html += _accel_row("↑ Run tighter load band (defer next FTE hire)", _accel_load, "#FFFBEB", "#92600A")
    _accel_html += _mix_lever_html
    if _accel_psr:
        _accel_html += _accel_row(_psr_label, _accel_psr, "#FFFBEB", "#92600A")
    if _accel_att:
        _accel_html += _accel_row(_att_label, _accel_att, "#FFFBEB", "#92600A")
    if _accel_repl:
        _accel_html += _accel_row(_repl_label, _accel_repl, "#FFFBEB", "#92600A")
    _accel_html += _accel_row("⚡ Combine: 30% growth + tighter staffing", _accel_combo, "#ECFDF5", "#0A6B4A")

def _yr_card_html(d, yr_label, target):
    # Labor section: SWB Goal − SWB Actual − Flex = SWB Savings
    _swb_savings  = d["goal"] - d["act"] - d["flex"]   # true labor budget vs spend incl. flex
    # Non-labor section: turnover + burnout
    _nonlabor     = d["turn"] + d["burn"]
    _net_var      = _swb_savings - _nonlabor
    _swb_fav      = d["swb_actual"] <= target

    _sav_clr  = "#0A6B4A" if _swb_savings >= 0 else "#B91C1C"
    _sav_sign = "+" if _swb_savings >= 0 else "−"
    _net_clr  = "#0A6B4A" if _net_var >= 0 else "#B91C1C"
    _net_sign = "+" if _net_var >= 0 else "−"
    _sub_clr  = "#0A6B4A" if _swb_fav else "#B91C1C"
    _sub_word = "SWB on target" if _swb_fav else "SWB over budget"

    # Section label style
    _sec = "font-size:0.58rem;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:#7A8799;"

    zones = f"{d['G']}G / {d['Y']}Y / {d['R']}R &nbsp;&middot;&nbsp; Peak {d['peak']:.1f} pts/APC"
    return (
        f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:4px;"
        f"padding:0.85rem 1rem 0.8rem;box-shadow:0 1px 3px rgba(0,0,0,0.04);'>"
        f"<div style='font-size:0.57rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.16em;color:#7A8799;margin-bottom:0.4rem;'>{yr_label}</div>"
        f"<div style='font-size:0.75rem;color:#4A5568;margin-bottom:0.55rem;line-height:1.5;'>{zones}</div>"
        f"<div style='font-size:0.74rem;line-height:1.85;'>"

        # ── Labor section label ───────────────────────────────────────────────
        f"<div style='{_sec}padding:0.1rem 0;'>LABOR</div>"
        # SWB Goal
        f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #F1F5F9;'>"
        f"<span style='color:#4A5568;'>SWB Goal</span>"
        f"<span style='color:#003366;font-variant-numeric:tabular-nums;font-weight:500;'>${d['goal']/1e3:.0f}K</span></div>"
        # SWB Actual
        f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #F1F5F9;'>"
        f"<span style='color:#4A5568;'>SWB Actual</span>"
        f"<span style='color:#B91C1C;font-variant-numeric:tabular-nums;'>−${d['act']/1e3:.0f}K</span></div>"
        # Flex
        f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #E2E8F0;'>"
        f"<span style='color:#4A5568;'>Flex / Locum</span>"
        f"<span style='color:#B91C1C;font-variant-numeric:tabular-nums;'>−${d['flex']/1e3:.0f}K</span></div>"
        # SWB Savings subtotal
        f"<div style='display:flex;justify-content:space-between;border-bottom:2px solid #CBD5E1;"
        f"background:#F8FAFC;padding:0.05rem 0.1rem;margin-bottom:0.4rem;'>"
        f"<span style='color:#4A5568;font-style:italic;font-size:0.70rem;'>SWB Savings</span>"
        f"<span style='color:{_sav_clr};font-variant-numeric:tabular-nums;font-style:italic;font-size:0.70rem;'>"
        f"{_sav_sign}${abs(_swb_savings)/1e3:.0f}K</span></div>"

        # ── Non-labor section label ───────────────────────────────────────────
        f"<div style='{_sec}padding:0.1rem 0;'>HR / OPERATIONAL</div>"
        # Turnover
        f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #F1F5F9;'>"
        f"<span style='color:#4A5568;'>Turnover</span>"
        f"<span style='color:#B91C1C;font-variant-numeric:tabular-nums;'>−${d['turn']/1e3:.0f}K</span></div>"
        # Burnout
        f"<div style='display:flex;justify-content:space-between;border-bottom:2px solid #0F1923;'>"
        f"<span style='color:#4A5568;'>Burnout</span>"
        f"<span style='color:#B91C1C;font-variant-numeric:tabular-nums;'>−${d['burn']/1e3:.0f}K</span></div>"

        # Net Variance
        f"<div style='display:flex;justify-content:space-between;padding-top:0.15rem;'>"
        f"<span style='color:#0F1923;font-weight:700;'>Net Variance</span>"
        f"<span style='color:{_net_clr};font-weight:700;font-size:0.88rem;font-variant-numeric:tabular-nums;'>"
        f"{_net_sign}${abs(_net_var)/1e3:.0f}K</span></div>"
        f"</div>"
        f"<div style='margin-top:0.45rem;font-size:0.68rem;color:{_sub_clr};font-weight:600;'>"
        f"${d['swb_actual']:.2f} actual vs ${target:.2f} target &nbsp;·&nbsp; {_sub_word}</div>"
        f"</div>"
    )

_yc1 = _yr_card_html(_yr_data[1], "Year 1", _swb_target)
_yc2 = _yr_card_html(_yr_data[2], "Year 2", _swb_target)
_yc3 = _yr_card_html(_yr_data[3], "Year 3", _swb_target)

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER — 7 TILES
# ═══════════════════════════════════════════════════════════════════════════════
def _tile(col, val, label, sub=None, border="#003366", val_color="#0F1923", val_size="1.65rem"):
    col.markdown(
        f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-top:3px solid {border};"
        f"border-radius:3px;padding:0.75rem 0.9rem 0.65rem;"
        f"box-shadow:0 1px 3px rgba(0,0,0,0.04);'>"
        f"<div style='font-family:\"EB Garamond\",serif;font-size:{val_size};font-weight:500;"
        f"color:{val_color};line-height:1;margin-bottom:0.2rem;'>{val}</div>"
        f"<div style='font-size:0.57rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.10em;color:#7A8799;'>{label}</div>"
        + (f"<div style='font-size:0.62rem;color:{val_color};margin-top:0.15rem;'>{sub}</div>" if sub else "")
        + "</div>",
        unsafe_allow_html=True
    )

# ── 7-tile header row ────────────────────────────────────────────────────────
_swb_sub  = f"{'▲' if _swb_delta_pv > 0 else '▼'} ${abs(_swb_delta_pv):.2f} vs ${_swb_target:.0f} target"
_vpd_sub  = f"↓ {_vpd_min:.1f} min · ↑ {_vpd_max:.1f} max"
_turn_sub = f"{_turn_risk_lbl} · ${_turn_cost_3yr/1e3:.0f}K cost"
_h1,_h2,_h3,_h4,_h5,_h6,_h7 = st.columns(7)
_tile(_h1, f"{best.base_fte:.1f}",   "Base FTE")
_tile(_h2, f"{best.winter_fte:.1f}", "Winter FTE")
_tile(_h3, f"{best.base_fte*cfg.summer_shed_floor_pct:.1f}", "Summer Floor")
_tile(_h4, MONTH_NAMES[best.req_post_month-1], "Post Req By", border="#7A6200")
_tile(_h5, f"${_swb_actual:.2f}", "SWB / Visit",
      sub=_swb_sub, border=_swb_tile_clr, val_color=_swb_tile_clr, val_size="1.3rem")
_tile(_h6, f"{_vpd_avg:.1f}", "Visits / Provider",
      sub=_vpd_sub, border="#7A6200", val_color="#0F1923", val_size="1.3rem")
_tile(_h7, f"{_tot_turn_events:.1f}", "Turnover Events",
      sub=_turn_sub, border=_turn_risk_clr, val_color=_turn_risk_clr, val_size="1.3rem")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY CARD
# ═══════════════════════════════════════════════════════════════════════════════
_yr_goal_str = (
    f"<span style='font-family:\"EB Garamond\",serif;font-size:2.2rem;font-weight:500;"
    f"color:{'#B91C1C' if (_yr_goal is None or _yr_goal > 3) else '#92600A'};line-height:1;'>"
    f"{'Already met' if _goal_already_met else (str(_yr_goal) + ' yrs' if _yr_goal else 'Beyond horizon')}"
    f"</span>"
)

_no_accel_msg = (
    f"<div style='font-size:0.76rem;color:#0A6B4A;padding:0.5rem 0;'>"
    f"✓ SWB/visit is already at or below the ${_swb_target:.0f} target — goal is met.</div>"
)


# ── Year cards ──────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='margin:0.5rem 0 0.5rem;font-size:0.60rem;font-weight:700;"
    f"text-transform:uppercase;letter-spacing:0.16em;color:{MUTED};'>"
    f"WHAT YOUR CURRENT INPUTS ARE PRODUCING</div>",
    unsafe_allow_html=True
)
_c1, _c2, _c3 = st.columns(3)
_c1.markdown(_yc1, unsafe_allow_html=True)
_c2.markdown(_yc2, unsafe_allow_html=True)
_c3.markdown(_yc3, unsafe_allow_html=True)

st.markdown("<div style='height:0.75rem'></div>",unsafe_allow_html=True)

st.markdown(
    f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-left:3px solid {NAVY};"
    f"border-radius:4px;margin:0.75rem 0 0.4rem;overflow:hidden;font-size:0.82rem;'>"

    # ── Row 1: SWB variance waterfall ────────────────────────────────────────
    f"<div style='padding:0.65rem 1.2rem 0.55rem;'>"
    f"<div style='color:{MUTED};font-size:0.58rem;font-weight:700;text-transform:uppercase;"
    f"letter-spacing:0.16em;margin-bottom:0.4rem;'>SWB Variance Breakdown — Annualised (3-yr avg)</div>"
    f"<span style='color:{NAVY};font-weight:600;'>SWB Goal ${_ann_swb_goal/1e3:.0f}K</span>"
    f"  <span style='color:{MUTED};'>−</span>  "
    f"<span style='color:#B91C1C;'>Actual ${_ann_swb/1e3:.0f}K</span>"
    f"  <span style='color:{MUTED};'>−</span>  "
    f"<span style='color:#B91C1C;'>Flex ${_ann_flex/1e3:.0f}K</span>"
    f"  <span style='color:{MUTED};'>−</span>  "
    f"<span style='color:#B91C1C;'>Turnover ${_ann_turnover/1e3:.0f}K</span>"
    f"  <span style='color:{MUTED};'>−</span>  "
    f"<span style='color:#B91C1C;'>Burnout ${_ann_burnout/1e3:.0f}K</span>"
    f"  <span style='color:{MUTED};'>=</span>  "
    f"<span style='color:{_var_clr};font-size:1.0rem;font-weight:700;'>"
    f"{_impact_sign}${_impact_abs_ann/1e3:.0f}K/yr SWB variance</span>"
    f"  <span style='color:{MUTED};font-size:0.72rem;'>({_var_word})</span>"
    f"</div>"

    # ── Row 2: Two-column — years-to-goal LEFT, acceleration RIGHT ────────────
    f"<div style='border-top:1px solid #E2E8F0;display:grid;grid-template-columns:1fr 1fr;'>"

    # Left: years-to-goal + strip
    f"<div style='padding:0.9rem 1.2rem;border-right:1px solid #E2E8F0;'>"
    f"<div style='color:{MUTED};font-size:0.58rem;font-weight:700;text-transform:uppercase;"
    f"letter-spacing:0.16em;margin-bottom:0.6rem;'>Time to SWB Goal — At Current Growth Rate</div>"
    f"<div style='display:flex;align-items:baseline;gap:0.8rem;margin-bottom:0.4rem;'>"
    f"{_yr_goal_str}"
    f"<div style='font-size:0.78rem;color:#4A5568;line-height:1.5;'>"
    f"At <b>{cfg.annual_growth_pct:.0f}% annual growth</b>, SWB/visit crosses<br>"
    f"the ${_swb_target:.0f} target by Year {_yr_goal or '?'} at current trajectory"
    f"</div></div>"
    f"<div style='font-size:0.68rem;color:#7A8799;margin-bottom:0.3rem;'>"
    f"Current: ${_swb_actual:.2f}/visit &nbsp;·&nbsp; Goal: ${_swb_target:.2f} &nbsp;·&nbsp; Gap: ${abs(_swb_delta_pv):.2f}</div>"
    f"{_strip_html}"
    f"</div>"

    # Right: acceleration levers (or "already met" message)
    f"<div style='padding:0.9rem 1.2rem;'>"
    f"<div style='color:{MUTED};font-size:0.58rem;font-weight:700;text-transform:uppercase;"
    f"letter-spacing:0.16em;margin-bottom:0.65rem;'>How to Reach Goal Sooner</div>"
    + (_no_accel_msg if not _accel_html else _accel_html)
    + f"</div>"

    + f"</div>"

    f"</div>",
    unsafe_allow_html=True
)

st.plotly_chart(render_hero_chart(active_policy(),cfg,quarterly_impacts,base_visits,budget_ppp,peak_factor,monthly_impacts=_mo_vals),
                use_container_width=True)

# Hiring mode legend
hm_map = {
    "growth":("Growth hire",NAVY), "attrition_replace":("Attrition backfill",NAVY_MID),
    "winter_ramp":("Winter ramp",C_GREEN), "shed_pause":("Q3 shed pause",C_YELLOW),
    "shed_passive":("Passive shed",C_YELLOW), "freeze_flu":("Flu freeze",SLATE),
}
yr1_mos = [mo for mo in active_policy().months if mo.year==1]
counts  = {m:sum(1 for mo in yr1_mos if mo.hiring_mode==m) for m in hm_map}
parts   = [f"<span style='color:{col};font-weight:600;'>•</span> <span style='color:{SLATE};'>{lbl} ({counts[k]} mo)</span>"
           for k,(lbl,col) in hm_map.items() if counts.get(k,0)>0]
if parts:
    st.markdown(f"<p style='font-size:0.72rem;color:{SLATE};margin-top:-0.3rem;'>"
                f"Dot color = hiring action: &nbsp; "+"  &nbsp;·&nbsp;  ".join(parts)+"</p>",
                unsafe_allow_html=True)
st.markdown(f"<hr style='border-color:{RULE};margin:1.5rem 0;'>",unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# AI ADVISOR — shared helpers
# ══════════════════════════════════════════════════════════════════════════════
import requests as _requests
import json as _json

def _openai_key():
    """Return the OpenAI API key from Streamlit secrets, or None."""
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return None

def _build_simulation_context(pol, cfg, MA):
    """Serialize the full simulation state into a compact text block for the system prompt."""
    es  = pol.ebitda_summary
    s   = pol.summary
    mos = pol.months

    lines = [
        "=== PSM SIMULATION STATE ===",
        f"Base visits/day: {cfg.base_visits_per_day}",
        f"Annual growth: {cfg.annual_growth_pct}%",
        f"Budgeted pts/APC/day: {cfg.budgeted_patients_per_provider_per_day}",
        f"APC annual cost (perm): ${cfg.annual_provider_cost_perm:,}",
        f"APC annual cost (flex): ${cfg.annual_provider_cost_flex:,}",
        f"Revenue/visit: ${cfg.net_revenue_per_visit}",
        f"SWB target/visit: ${cfg.swb_target_per_visit}",
        f"Annual attrition: {cfg.annual_attrition_pct}%  monthly: {cfg.monthly_attrition_rate*100:.3f}%",
        f"Pipeline: {cfg.days_to_sign}d sign + {cfg.days_to_credential}d credential + {cfg.days_to_independent}d orient = {cfg.days_to_sign+cfg.days_to_credential+cfg.days_to_independent}d total",
        f"Shifts: {cfg.fte_shifts_per_week} shifts/wk per APC, {cfg.shift_hours}h shift, {cfg.operating_days_per_week} days/wk",
        f"Min coverage FTE: {cfg.min_coverage_fte}",
        "",
        "=== 3-YEAR OUTCOMES ===",
        f"EBITDA: ${es['ebitda']:,.0f}",
        f"Revenue: ${es['revenue']:,.0f}",
        f"SWB: ${es['swb']:,.0f}",
        f"Turnover cost: ${es['turnover']:,.0f}  ({s['total_turnover_events']:.1f} events)",
        f"Burnout penalty: ${es['burnout']:,.0f}",
        f"Visit capture: {es['capture_rate']*100:.1f}%",
        f"SWB/visit actual: ${s['annual_swb_per_visit']:.2f}  target: ${cfg.swb_target_per_visit:.2f}",
        f"Zone distribution: {s['green_months']}G / {s['yellow_months']}Y / {s['red_months']}R",
        "",
        "=== RECOMMENDED POLICY ===",
        f"Base FTE: {pol.base_fte}  Winter FTE: {pol.winter_fte}",
        "",
        "=== HIRE EVENTS ===",
    ]
    for h in pol.hire_events:
        lines.append(
            f"  Y{h.year}-{MA[h.calendar_month-1]}: +{h.fte_hired:.2f} FTE  mode={h.mode}"
            f"  post_by=Y{h.post_by_year}-{MA[h.post_by_month-1]}"
            f"  productive=Y{h.independent_year}-{MA[h.independent_month-1]}"
        )
    # ── Support staff context ─────────────────────────────────────────────────
    sup  = cfg.support
    mult = sup.total_multiplier
    avg_apc_on_floor = sum(mo.paid_fte * cfg.fte_fraction for mo in mos) / len(mos)
    hrs_mo = cfg.shift_hours * cfg.operating_days_per_week * (52 / 12)

    ma_ann      = avg_apc_on_floor * sup.ma_ratio  * sup.ma_rate_hr  * hrs_mo * mult * 12
    psr_ann     = avg_apc_on_floor * sup.psr_ratio * sup.psr_rate_hr * hrs_mo * mult * 12
    rt_ann      = sup.rt_flat_fte  * sup.rt_rate_hr * hrs_mo * mult * 12
    phys_ann    = sup.supervisor_hrs_mo   * sup.physician_rate_hr  * mult * 12 if sup.supervisor_hrs_mo   > 0 else 0
    supadm_ann  = sup.supervisor_admin_mo * sup.supervisor_rate_hr * mult * 12 if sup.supervisor_admin_mo > 0 else 0
    total_sup   = ma_ann + psr_ann + rt_ann + phys_ann + supadm_ann
    ma_per_025  = 0.25 * avg_apc_on_floor * sup.ma_rate_hr  * hrs_mo * mult * 12
    psr_per_025 = 0.25 * avg_apc_on_floor * sup.psr_rate_hr * hrs_mo * mult * 12

    lines += [
        "",
        "=== SUPPORT STAFF CONFIGURATION ===",
        f"Comp multiplier: {mult:.2f}x  (benefits {sup.benefits_load_pct*100:.0f}% + bonus {sup.bonus_pct*100:.0f}% + OT/sick {sup.ot_sick_pct*100:.0f}%)",
        f"Hourly rates (base): MA ${sup.ma_rate_hr:.2f}/hr  PSR ${sup.psr_rate_hr:.2f}/hr  RT ${sup.rt_rate_hr:.2f}/hr  Supervisor ${sup.supervisor_rate_hr:.2f}/hr",
        f"Staffing ratios: MA {sup.ma_ratio:.2f}/APC  PSR {sup.psr_ratio:.2f}/APC  RT {sup.rt_flat_fte:.2f} flat/shift",
        f"Physician supervision: {sup.supervisor_hrs_mo:.0f} hrs/mo  Supervisor admin: {sup.supervisor_admin_mo:.0f} hrs/mo",
        f"Avg concurrent APCs on floor: {avg_apc_on_floor:.2f}",
        "",
        "Annualised support staff costs (at current ratios):",
        f"  MA:            ${ma_ann:,.0f}/yr",
        f"  PSR:           ${psr_ann:,.0f}/yr",
        f"  Rad Tech:      ${rt_ann:,.0f}/yr",
        f"  Physician sup: ${phys_ann:,.0f}/yr",
        f"  Supervisor:    ${supadm_ann:,.0f}/yr",
        f"  TOTAL:         ${total_sup:,.0f}/yr",
        "",
        "Ratio sensitivity (annual cost impact per +-0.25 ratio change):",
        f"  +-0.25 MA ratio  = +-${ma_per_025:,.0f}/yr",
        f"  +-0.25 PSR ratio = +-${psr_per_025:,.0f}/yr",
        "(Approximate — based on avg APC floor count; varies month-to-month with FTE ramp)",
    ]

    lines.append("")
    lines.append("=== MONTHLY DETAIL (demand_fte | paid_fte | zone | pts/APC) ===")
    for mo in mos:
        lines.append(
            f"  Y{mo.year}-{MA[mo.calendar_month-1]}: "
            f"demand={mo.demand_fte_required:.2f} paid={mo.paid_fte:.2f} "
            f"zone={mo.zone} pts={mo.patients_per_provider_per_shift:.1f} "
            f"vpd={mo.demand_visits_per_day:.1f}"
        )
    return "\n".join(lines)

def _call_openai(messages, key, model="gpt-4o", temperature=0.4, max_tokens=900):
    """Call OpenAI chat completions via requests. Returns (text, error_str)."""
    try:
        resp = _requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=45,
        )
        if resp.status_code != 200:
            return None, f"OpenAI API error {resp.status_code}: {resp.text[:200]}"
        return resp.json()["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, str(e)

def _advisor_system_prompt(sim_context):
    return f"""You are a staffing strategy advisor embedded in a Predictive Staffing Model (PSM) tool for an urgent care clinic operator. You have full access to the clinic's 36-month simulation results.

Your role:
- Interpret simulation data and give specific, actionable guidance
- Answer "now what?" questions when reality diverges from the plan
- Flag risks, tradeoffs, and operational implications
- Speak plainly — your audience is an operator and their CFO, not a data scientist
- Always ground answers in the specific numbers from the simulation context below
- Never invent staffing benchmarks or cite external statistics unless explicitly asked
- When a situation falls outside the model (e.g. sudden departure, delayed start), reason through the impact using the monthly FTE and demand data
- Keep responses concise — 3-5 sentences for simple questions, up to 3 short paragraphs for complex ones
- Add a disclaimer on HR/legal questions: "This is operational planning guidance, not HR or legal advice"

{sim_context}"""

tabs = st.tabs([
    "Staffing Model", "Executive Summary",
    "36-Month Load", "Hire Calendar", "Shift Coverage", "Seasonality",
    "Cost Breakdown", "Marginal APC", "Stress Test",
    "Policy Heatmap", "Req Timing", "Data Table", "Math & Logic", "Turnover Cost",
    "Sensitivity", "Advisor",
])

# ── TAB 0: STAFFING MODEL ────────────────────────────────────────────────────
with tabs[0]:
    pol  = active_policy()
    sup  = cfg.support
    fts  = cfg.fte_per_shift_slot          # e.g. 2.33 for 7-day, 3-shift/wk
    budget_load = cfg.budgeted_patients_per_provider_per_day

    # ── Build quarterly rows ──────────────────────────────────────────────────
    rows = []
    for yr in [1, 2, 3]:
        for q in [1, 2, 3, 4]:
            qmos = [mo for mo in pol.months if mo.year == yr and mo.quarter == q]
            if not qmos:
                continue
            avg_vpd  = sum(mo.demand_visits_per_day for mo in qmos) / len(qmos)
            avg_pof  = sum(mo.providers_on_floor    for mo in qmos) / len(qmos)
            avg_pfte = sum(mo.paid_fte               for mo in qmos) / len(qmos)
            # zones for row shading
            zones    = [mo.zone for mo in qmos]
            dom_zone = max(set(zones), key=zones.count)

            # Snap concurrent staff to nearest 0.25 FIRST, then derive FTE from
            # the snapped value so Staff/Day and FTE columns are always consistent.
            # (Deriving FTE from raw avg_pof then snapping independently causes
            #  rows where Staff/Day looks identical but FTE differs.)
            apc_day_snapped  = round(avg_pof * 4) / 4
            ma_day_snapped   = round(avg_pof * sup.ma_ratio  * 4) / 4
            psr_day_snapped  = round(avg_pof * sup.psr_ratio * 4) / 4
            rt_day_snapped   = round(sup.rt_flat_fte          * 4) / 4

            apc_fte  = round(apc_day_snapped  * fts * 4) / 4
            ma_fte   = round(ma_day_snapped   * fts * 4) / 4
            psr_fte  = round(psr_day_snapped  * fts * 4) / 4
            rt_fte   = round(rt_day_snapped   * fts * 4) / 4
            total_fte= apc_fte + ma_fte + psr_fte + rt_fte

            rows.append({
                "year": yr, "quarter": q, "zone": dom_zone,
                "vpd": avg_vpd,
                # staff per day (pre-snapped)
                "apc_day":  apc_day_snapped,
                "ma_day":   ma_day_snapped,
                "psr_day":  psr_day_snapped,
                "rt_day":   rt_day_snapped,
                # FTE (derived from snapped concurrent, not raw avg_pfte)
                "apc_fte":  apc_fte,
                "ma_fte":   ma_fte,
                "psr_fte":  psr_fte,
                "rt_fte":   rt_fte,
                "total_fte":total_fte,
            })

    # ── Colour helpers ────────────────────────────────────────────────────────
    ZONE_BG   = {"Green": "#ECFDF5", "Yellow": "#FFFBEB", "Red": "#FEF2F2"}
    ZONE_PILL = {"Green": ("#0A6B4A","#ECFDF5"), "Yellow": ("#92600A","#FFFBEB"), "Red": ("#B91C1C","#FEF2F2")}

    # ── Clinic summary header values ──────────────────────────────────────────
    _total_fte_avg = sum(r["total_fte"] for r in rows) / len(rows) if rows else 0

    # ── Print-friendly HTML table ─────────────────────────────────────────────
    # Build complete HTML so browser print works cleanly
    _clinic_name  = "Urgent Care Clinic"   # could be a config field later
    _print_date   = __import__("datetime").date.today().strftime("%B %d, %Y")

    def _fmt(v, dec=2):
        """Format staffing numbers. dec=1 → 1dp (visits/day). dec=2 → snap to 0.25."""
        if dec == 1:
            return f"{v:.1f}"
        # Round to nearest 0.25 for clean schedule-friendly display
        snapped = round(v * 4) / 4
        return f"{snapped:.2f}"

    # Table rows HTML
    _rows_html = ""
    prev_yr = None
    for r in rows:
        yr_label = f"Year {r['year']}" if r['year'] != prev_yr else ""
        prev_yr  = r['year']
        q_labels = ["Q1 (Jan–Mar)", "Q2 (Apr–Jun)", "Q3 (Jul–Sep)", "Q4 (Oct–Dec)"]
        q_label  = q_labels[r['quarter'] - 1]
        pill_fg, pill_bg = ZONE_PILL[r["zone"]]
        zone_pill = (f"<span style='background:{pill_bg};color:{pill_fg};"
                     f"font-size:0.62rem;font-weight:700;padding:1px 6px;"
                     f"border-radius:3px;letter-spacing:0.06em'>{r['zone'].upper()}</span>")

        yr_cell  = (f"<td rowspan='4' style='border-right:1px solid #1E3A52;"
                    f"color:#003366;font-weight:700;font-size:0.9rem;"
                    f"text-align:center;vertical-align:middle;white-space:nowrap;"
                    f"padding:0 0.9rem'>{yr_label}</td>") if yr_label else ""

        _rows_html += f"""
        <tr style='border-bottom:1px solid #132333;'>
          {yr_cell}
          <td style='padding:0.55rem 0.7rem;color:#0F1923;font-size:0.8rem'>{q_label}</td>
          <td style='padding:0.55rem 0.5rem;text-align:center'>{zone_pill}</td>
          <td style='padding:0.55rem 0.5rem;text-align:right;color:#4A5568;font-size:0.78rem'>{_fmt(r['vpd'],1)}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['apc_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['ma_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['psr_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['rt_day'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['apc_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['ma_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['psr_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['rt_fte'])}</td>
          <td style='text-align:right;color:#003366;font-weight:700;font-size:0.82rem;padding:0.55rem 0.7rem'>{_fmt(r['total_fte'])}</td>
        </tr>"""

    _table_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600&family=DM+Sans:wght@400;500;600&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #FFFFFF;
    color: #0F1923;
    font-family: 'DM Sans', system-ui, sans-serif;
    padding: 1.5rem 2rem;
  }}

  /* ── Header ── */
  .doc-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 2px solid #003366;
    padding-bottom: 0.8rem;
    margin-bottom: 1.4rem;
  }}
  .doc-title {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 1.2rem;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: #0F1923;
  }}
  .doc-sub {{
    font-size: 0.68rem;
    color: #7A8799;
    letter-spacing: 0.06em;
    margin-top: 0.3rem;
  }}
  .doc-meta {{
    text-align: right;
    font-size: 0.68rem;
    color: #7A8799;
    line-height: 1.7;
  }}
  .doc-meta strong {{ color: #4A5568; }}

  /* ── Config strip ── */
  .config-strip {{
    display: flex;
    gap: 2rem;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #7A6200;
    border-radius: 3px;
    padding: 0.6rem 1.1rem;
    margin-bottom: 1.2rem;
    flex-wrap: wrap;
  }}
  .cfg-item {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .cfg-label {{
    font-size: 0.57rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #7A8799;
    font-weight: 700;
  }}
  .cfg-value {{
    font-size: 0.84rem;
    font-weight: 600;
    color: #0F1923;
    font-variant-numeric: tabular-nums;
  }}

  /* ── Table ── */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }}
  thead tr:first-child {{
    background: #FFFFFF;
    border-bottom: 2px solid #0F1923;
  }}
  thead tr:last-child {{
    background: #F8FAFC;
    border-bottom: 1px solid #E2E8F0;
  }}
  /* Section headers */
  .th-group {{
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #7A8799;
    padding: 0.3rem 0.5rem 0.1rem;
    text-align: center;
  }}
  .th-group-spd {{ color: #003366; border-bottom: 2px solid #003366; }}
  .th-group-fte {{ color: #7A6200; border-bottom: 2px solid #7A6200; }}
  th {{
    padding: 0.35rem 0.5rem;
    font-size: 0.64rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    white-space: nowrap;
    color: #7A8799;
    background: #F8FAFC;
  }}
  th.spd {{ color: #003366; }}
  th.fte {{ color: #7A6200; }}
  tbody tr {{ border-bottom: 1px solid #F1F5F9; }}
  tbody tr:hover td {{ background: #F8FAFC; }}
  td {{ padding: 0.42rem 0.5rem; color: #4A5568; }}
  td.spd {{ color: #003366; font-variant-numeric: tabular-nums; font-size: 0.78rem; font-weight: 500; }}
  td.fte {{ color: #7A6200; font-variant-numeric: tabular-nums; font-size: 0.78rem; font-weight: 500; }}

  /* Year separators */
  tr.yr-sep td {{ border-top: 2px solid #E2E8F0; }}

  /* ── Footnotes ── */
  .footnotes {{
    margin-top: 1rem;
    font-size: 0.64rem;
    color: #7A8799;
    border-top: 1px solid #E2E8F0;
    padding-top: 0.65rem;
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    line-height: 1.5;
  }}
  .fn-item {{ display: flex; gap: 0.3rem; }}
  .fn-key {{ color: #003366; font-weight: 700; }}

  /* ── Print styles ── */
  @media print {{
    body {{
      background: #fff !important;
      color: #111 !important;
      padding: 0.5in 0.6in;
      font-size: 9pt;
    }}
    .doc-header {{ border-color: #333; }}
    .doc-title {{ color: #111; }}
    .doc-sub, .doc-meta {{ color: #555; }}
    .config-strip {{ background: #f5f5f5; border-color: #ccc; }}
    .cfg-label {{ color: #777; }}
    .cfg-value {{ color: #111; }}
    table {{ font-size: 8.5pt; }}
    thead tr {{ background: #eee; border-color: #999; }}
    .th-group-spd {{ color: #1a56b0; border-color: #999; }}
    .th-group-fte {{ color: #5a1ab0; border-color: #999; }}
    th {{ color: #444; }}
    th.spd {{ color: #1a56b0; }}
    th.fte {{ color: #5a1ab0; }}
    td.spd {{ color: #1a56b0; }}
    td.fte {{ color: #5a1ab0; }}
    .footnotes {{ color: #555; border-color: #ccc; }}
    .fn-key {{ color: #1a56b0; }}
    tr.yr-sep td {{ border-color: #999; }}
  }}
  @page {{ size: landscape; margin: 0.5in; }}
</style>
</head>
<body>

<div class="doc-header">
  <div>
    <div class="doc-title">Complete Staffing Model</div>
    <div class="doc-sub">PERMANENT STAFFING MODEL · 36-MONTH QUARTERLY PROJECTION · LOAD-BAND OPTIMIZER</div>
  </div>
  <div class="doc-meta">
    Generated {_print_date}<br>
    Base {cfg.base_visits_per_day:.0f} vpd · {cfg.annual_growth_pct:.0f}% growth · Budget {budget_load:.0f} pts/APC
  </div>
</div>

<div class="config-strip">
  <div class="cfg-item"><span class="cfg-label">Operating Days/Wk</span><span class="cfg-value">{cfg.operating_days_per_week}</span></div>
  <div class="cfg-item"><span class="cfg-label">Shift Hours</span><span class="cfg-value">{cfg.shift_hours:.0f}h</span></div>
  <div class="cfg-item"><span class="cfg-label">Shifts/Wk per APC</span><span class="cfg-value">{cfg.fte_shifts_per_week:.1f}</span></div>
  <div class="cfg-item"><span class="cfg-label">FTE per Slot</span><span class="cfg-value">{fts:.2f}</span></div>
  <div class="cfg-item"><span class="cfg-label">MA Ratio (per APC)</span><span class="cfg-value">{sup.ma_ratio:.1f}</span></div>
  <div class="cfg-item"><span class="cfg-label">PSR Ratio (per APC)</span><span class="cfg-value">{sup.psr_ratio:.1f}</span></div>
  <div class="cfg-item"><span class="cfg-label">RT (flat/shift)</span><span class="cfg-value">{sup.rt_flat_fte:.1f}</span></div>
  <div class="cfg-item"><span class="cfg-label">WLT</span><span class="cfg-value">{cfg.load_winter_target:.0f} pts/APC</span></div>
  <div class="cfg-item"><span class="cfg-label">Base FTE</span><span class="cfg-value">{best.base_fte:.1f}</span></div>
  <div class="cfg-item"><span class="cfg-label">Winter FTE</span><span class="cfg-value">{best.winter_fte:.1f}</span></div>
</div>

<table>
  <thead>
    <tr>
      <th rowspan="2" style="text-align:left;padding-left:0.7rem">Year</th>
      <th rowspan="2" style="text-align:left">Quarter</th>
      <th rowspan="2">Zone</th>
      <th rowspan="2" style="text-align:right;color:#7A8799">Visits/Day</th>
      <th colspan="4" class="th-group th-group-spd">Staff per Day (Concurrent)</th>
      <th colspan="4" class="th-group th-group-fte">FTE Required</th>
      <th rowspan="2" style="text-align:right;padding-right:0.7rem;color:#7A6200;font-weight:700">Total FTE</th>
    </tr>
    <tr>
      <th class="spd" style="text-align:right">Provider</th>
      <th class="spd" style="text-align:right">MA</th>
      <th class="spd" style="text-align:right">PSR</th>
      <th class="spd" style="text-align:right">Rad Tech</th>
      <th class="fte" style="text-align:right">Provider</th>
      <th class="fte" style="text-align:right">MA</th>
      <th class="fte" style="text-align:right">PSR</th>
      <th class="fte" style="text-align:right">Rad Tech</th>
    </tr>
  </thead>
  <tbody>
    {_rows_html}
  </tbody>
</table>

<div class="footnotes">
  <div class="fn-item"><span class="fn-key">Staff/Day</span><span>Concurrent positions on the floor each operating day · rounded to nearest 0.25</span></div>
  <div class="fn-item"><span class="fn-key">FTE</span><span>Full-time equivalents · rounded to nearest 0.25 · {cfg.fte_shifts_per_week:.0f} shifts/wk per APC · {cfg.operating_days_per_week}-day schedule ({fts:.2f}× slot)</span></div>
  <div class="fn-item"><span class="fn-key">MA / PSR</span><span>Scale with providers on floor at {sup.ma_ratio:.1f}× and {sup.psr_ratio:.1f}× ratios respectively</span></div>
  <div class="fn-item"><span class="fn-key">Rad Tech</span><span>Flat {sup.rt_flat_fte:.1f} concurrent slot regardless of provider count</span></div>
  <div class="fn-item"><span class="fn-key">Zone</span><span>Dominant zone across the quarter — Green ≤{budget_load:.0f} · Yellow ≤{budget_load+cfg.red_threshold_above:.0f} · Red >{budget_load+cfg.red_threshold_above:.0f} pts/APC</span></div>
</div>

</body>
</html>"""

    # ── Render in Streamlit ───────────────────────────────────────────────────
    st.markdown("## COMPLETE STAFFING MODEL")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{SLATE};margin:-0.4rem 0 1rem;'>"
        f"Quarterly averages · recommended policy · all roles · "
        f"<strong style='color:#0F1923'>Staff/Day</strong> = concurrent positions on floor · "
        f"<strong style='color:#0F1923'>FTE</strong> = headcount to sustain that coverage</p>",
        unsafe_allow_html=True
    )

    # Print button
    _pb_col, _ = st.columns([1, 5])
    _pb_col.markdown(
        "<button onclick='window.print()' style='"
        "background:#F8FAFC;border:1px solid #E2E8F0;border-left:3px solid #7A6200;color:#0F1923;padding:0.7rem 1rem;"
        "font-size:0.75rem;padding:0.35rem 0.9rem;border-radius:3px;"
        "cursor:pointer;letter-spacing:0.06em;font-family:inherit;"
        "'>🖨 Print / Save PDF</button>",
        unsafe_allow_html=True
    )
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    _components.html(_table_html, height=820, scrolling=True)

    # ── Supporting metrics below table ────────────────────────────────────────
    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0.2rem 0 0.8rem;'>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='font-size:0.72rem;color:{SLATE};'>"
        f"Ratios: MA {sup.ma_ratio:.1f}× · PSR {sup.psr_ratio:.1f}× · RT flat {sup.rt_flat_fte:.1f} · "
        f"FTE/slot {fts:.2f} · Shift {cfg.shift_hours:.0f}h · "
        f"{cfg.operating_days_per_week} days/wk · {cfg.fte_shifts_per_week:.0f} shifts/wk per APC</p>",
        unsafe_allow_html=True
    )
# ── TAB 1: Executive Summary ────────────────────────────────────────────────
with tabs[1]:
    pol = active_policy()
    s   = pol.summary
    es  = pol.ebitda_summary
    ma  = pol.marginal_analysis
    MA  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    # ─────────────────────────────────────────────────────────────────────────
    # NARRATIVE GENERATOR — pure Python, no API needed
    # Reads live simulation data and writes conditional CFO-quality prose
    # ─────────────────────────────────────────────────────────────────────────
    def _generate_exec_summary(pol, s, es, ma, cfg, MA):
        """
        Build a structured executive summary memo from simulation results.
        Returns a dict of {section_title: prose_string}.
        """
        import datetime

        ebitda      = es["ebitda"]
        capture     = es["capture_rate"] * 100
        revenue     = es["revenue"]
        swb_cost    = es["swb"]
        burnout     = es["burnout"]
        turnover    = es["turnover"]
        flex        = es["flex"]
        green_m     = s["green_months"]
        yellow_m    = s["yellow_months"]
        red_m       = s["red_months"]
        swb_actual  = s["annual_swb_per_visit"]
        swb_target  = cfg.swb_target_per_visit
        swb_ok      = not s["swb_violation"]
        tot_turnover= s["total_turnover_events"]
        start_fte   = pol.months[0].paid_fte

        # Zone characterization
        zone_pct_green = green_m / 36 * 100
        if red_m == 0 and yellow_m <= 4:
            zone_health = "excellent"
            zone_prose  = f"all {green_m} months in Green"
        elif red_m == 0:
            zone_health = "good"
            zone_prose  = f"{green_m} Green and {yellow_m} Yellow months — no Red exposure"
        elif red_m <= 3:
            zone_health = "moderate"
            zone_prose  = f"{green_m} Green, {yellow_m} Yellow, and {red_m} Red months"
        else:
            zone_health = "stressed"
            zone_prose  = f"only {green_m} Green months against {red_m} Red — provider load is routinely excessive"

        # SWB variance — primary decision metric
        swb_delta       = swb_actual - swb_target          # positive = over budget
        total_visits_3yr= sum(mo.visits_captured for mo in pol.months)
        swb_impact_3yr  = -swb_delta * total_visits_3yr    # positive = saving money
        swb_impact_ann  = swb_impact_3yr / 3
        swb_impact_sign = "+" if swb_impact_ann >= 0 else "−"
        swb_fav         = swb_impact_ann >= 0

        # Compute avg actual SWB per year for the prose
        perm_3yr = sum(mo.permanent_cost for mo in pol.months)
        supp_3yr = sum(mo.support_cost   for mo in pol.months)
        avg_swb_actual = (perm_3yr + supp_3yr) / total_visits_3yr if total_visits_3yr > 0 else swb_actual

        _vc = "#0A6B4A" if swb_fav else "#B91C1C"
        if swb_fav and abs(swb_impact_3yr) > 500_000:
            swb_prose = (
                f"At <strong style='color:{_vc}'>${avg_swb_actual:.2f}/visit</strong> actual vs the "
                f"${swb_target:.0f} target, staffing costs are running "
                f"<strong style='color:{_vc}'>${abs(swb_delta):.2f}/visit below budget</strong> — "
                f"a <strong style='color:{_vc}'>{swb_impact_sign}${abs(swb_impact_3yr)/1e6:.2f}M "
                f"favorable variance</strong> "
                f"(<span style='color:{_vc}'>{swb_impact_sign}${abs(swb_impact_ann)/1e3:.0f}K/yr</span>) "
                f"over the 3-year horizon")
        elif swb_fav:
            swb_prose = (
                f"At <strong style='color:{_vc}'>${avg_swb_actual:.2f}/visit</strong> actual vs the "
                f"${swb_target:.0f} target, staffing costs are "
                f"<strong style='color:{_vc}'>${abs(swb_delta):.2f}/visit below budget</strong> — "
                f"a <span style='color:{_vc}'>{swb_impact_sign}${abs(swb_impact_ann)/1e3:.0f}K/yr "
                f"favorable variance</span>")
        elif abs(swb_impact_3yr) > 300_000:
            swb_prose = (
                f"At <strong style='color:{_vc}'>${avg_swb_actual:.2f}/visit</strong> actual vs the "
                f"${swb_target:.0f} target, staffing costs are running "
                f"<strong style='color:{_vc}'>${abs(swb_delta):.2f}/visit over budget</strong> — "
                f"a <strong style='color:{_vc}'>−${abs(swb_impact_3yr)/1e6:.2f}M "
                f"unfavorable variance</strong> "
                f"(<span style='color:{_vc}'>−${abs(swb_impact_ann)/1e3:.0f}K/yr</span>) "
                f"that warrants review")
        else:
            swb_prose = (
                f"At <strong style='color:{_vc}'>${avg_swb_actual:.2f}/visit</strong> actual vs the "
                f"${swb_target:.0f} target, staffing costs are "
                f"<strong style='color:{_vc}'>${abs(swb_delta):.2f}/visit over budget</strong> — "
                f"a <span style='color:{_vc}'>−${abs(swb_impact_ann)/1e3:.0f}K/yr "
                f"unfavorable variance</span>")

        # EBITDA (supporting context only)
        ebitda_annual = ebitda / 3
        if ebitda > 3_000_000:
            ebitda_prose = f"strong 3-year EBITDA contribution of ${ebitda/1e6:.2f}M (${ebitda_annual/1e3:.0f}K/year)"
        elif ebitda > 1_500_000:
            ebitda_prose = f"solid 3-year EBITDA contribution of ${ebitda/1e6:.2f}M (${ebitda_annual/1e3:.0f}K/year)"
        elif ebitda > 0:
            ebitda_prose = f"modest 3-year EBITDA contribution of ${ebitda/1e6:.2f}M — there is meaningful room for improvement"
        else:
            ebitda_prose = f"a 3-year EBITDA loss of ${abs(ebitda)/1e6:.2f}M — immediate staffing restructuring is required"

        # Burnout characterization
        burnout_pct_of_revenue = burnout / revenue * 100
        if burnout < 50_000:
            burnout_prose = f"Burnout-driven attrition cost of ${burnout/1e3:.0f}K is well-controlled, representing {burnout_pct_of_revenue:.1f}% of captured revenue"
        elif burnout < 150_000:
            burnout_prose = f"Burnout risk is accumulating at ${burnout/1e3:.0f}K — {burnout_pct_of_revenue:.1f}% of revenue is being eroded by overload-driven attrition"
        else:
            burnout_prose = f"Burnout cost of ${burnout/1e3:.0f}K is a significant financial leak — {burnout_pct_of_revenue:.1f}% of captured revenue lost to overload-driven turnover cycles"

        # Visit capture
        if capture >= 99.5:
            capture_prose = f"Visit capture is near-perfect at {capture:.1f}%"
        elif capture >= 98:
            capture_prose = f"Visit capture of {capture:.1f}% is strong but leaves ${(revenue/capture*100 - revenue)/1e3:.0f}K in uncaptured revenue across the 3-year horizon"
        else:
            lost_rev = revenue / capture * 100 - revenue
            capture_prose = f"Visit capture of {capture:.1f}% represents ${lost_rev/1e3:.0f}K in diverted or lost patients across 3 years — a direct consequence of provider overload"

        # Year-by-year breakdown
        yr_data = {}
        for yr in [1, 2, 3]:
            yr_mos = [mo for mo in pol.months if mo.year == yr]
            _yr_visits  = sum(m.visits_captured for m in yr_mos)
            _yr_perm    = sum(m.permanent_cost   for m in yr_mos)
            _yr_supp    = sum(m.support_cost     for m in yr_mos)
            _yr_swb_act = (_yr_perm + _yr_supp) / _yr_visits if _yr_visits > 0 else 0
            _yr_swb_var = cfg.swb_target_per_visit - _yr_swb_act  # positive = favorable
            yr_data[yr] = {
                "G": sum(1 for m in yr_mos if m.zone == "Green"),
                "Y": sum(1 for m in yr_mos if m.zone == "Yellow"),
                "R": sum(1 for m in yr_mos if m.zone == "Red"),
                "peak": max(m.patients_per_provider_per_shift for m in yr_mos),
                "avg_visits": sum(m.demand_visits_per_day for m in yr_mos) / 12,
                "ebitda": sum(m.ebitda_contribution for m in yr_mos),
                "visits": _yr_visits,
                "swb_actual": _yr_swb_act,
                "swb_variance": _yr_swb_var,
                "swb_impact": _yr_swb_var * _yr_visits,
            }

        # Marginal APC signal
        if ma:
            net_ann   = ma.get("net_annual_impact", 0)
            pb_months = ma.get("payback_months")
            r_saved   = ma.get("red_months_saved", 0)
            y_saved   = ma.get("yellow_months_saved", 0)
            if pb_months is not None and pb_months <= 0:
                marginal_prose = (f"The marginal APC signal is urgent: adding 0.5 FTE generates "
                                  f"${abs(net_ann)/1e3:.0f}K net annual benefit with immediate payback, "
                                  f"saving {r_saved}R + {y_saved}Y months. This clinic is currently understaffed "
                                  f"relative to demand — the next hire should be prioritized.")
            elif pb_months is not None and pb_months <= 18:
                marginal_prose = (f"Adding 0.5 FTE yields a ${net_ann/1e3:.0f}K net annual benefit "
                                  f"with a {pb_months:.0f}-month payback, saving {r_saved}R + {y_saved}Y months. "
                                  f"A hire is financially justified and should be planned for the next available window.")
            elif net_ann > 0:
                marginal_prose = (f"A marginal 0.5 FTE hire would generate ${net_ann/1e3:.0f}K annually "
                                  f"with a {pb_months:.0f}-month payback. Worthwhile but not urgent — "
                                  f"plan for the Year 2 growth window.")
            else:
                marginal_prose = (f"The marginal APC analysis shows a negative return of ${abs(net_ann)/1e3:.0f}K/year "
                                  f"for an additional 0.5 FTE — the current staffing level is at or above the EBITDA-optimal point. "
                                  f"Focus on retention over recruitment.")
        else:
            marginal_prose = "Run the marginal APC analysis for specific hire recommendations."

        # Hire calendar interpretation
        hire_events = pol.hire_events
        perm_hires  = [h for h in hire_events if h.mode != "per_diem"]
        pd_hires    = [h for h in hire_events if h.mode == "per_diem"]

        if len(perm_hires) == 0:
            hire_prose = "No permanent hires are required under the current policy — attrition is manageable within the existing headcount."
        elif len(perm_hires) == 1:
            h = perm_hires[0]
            hire_prose = (f"One permanent hire is required: {h.fte_hired:.2f} FTE in "
                          f"Y{h.year}-{MA[h.calendar_month-1]}, with the requisition posted by "
                          f"Y{h.post_by_year}-{MA[h.post_by_month-1]} to achieve independence by "
                          f"Y{h.independent_year}-{MA[h.independent_month-1]}.")
        else:
            first_h = perm_hires[0]
            total_perm_fte = sum(h.fte_hired for h in perm_hires)
            winter_hires = [h for h in perm_hires if h.mode == "winter_ramp"]
            growth_hires = [h for h in perm_hires if h.mode == "growth"]
            hire_prose = (f"The hire calendar requires {len(perm_hires)} permanent hire events totaling "
                          f"{total_perm_fte:.2f} FTE over 3 years")
            if winter_hires and growth_hires:
                hire_prose += (f" — {len(winter_hires)} seasonal winter ramps and {len(growth_hires)} "
                               f"growth-driven hires")
            elif winter_hires:
                hire_prose += f" — all seasonal winter ramps to maintain flu-season coverage"
            hire_prose += (f". The first requisition must be posted by "
                           f"Y{first_h.post_by_year}-{MA[first_h.post_by_month-1]}.")
            if pd_hires:
                hire_prose += (f" {len(pd_hires)} small peak-season gaps ({sum(h.fte_hired for h in pd_hires):.2f} FTE-eq) "
                               f"are flagged as per-diem or extra-shift coverage rather than full requisitions.")

        # Growth trajectory
        y1_vis = yr_data[1]["avg_visits"]
        y3_vis = yr_data[3]["avg_visits"]
        growth_pct = (y3_vis / y1_vis - 1) * 100
        y3_zone_concern = yr_data[3]["Y"] + yr_data[3]["R"]

        if y3_zone_concern >= 4:
            growth_prose = (f"Volume growth of {cfg.annual_growth_pct:.0f}% annually pushes average daily visits "
                            f"from {y1_vis:.1f} in Year 1 to {y3_vis:.1f} by Year 3 — a {growth_pct:.0f}% increase. "
                            f"Year 3 already shows {yr_data[3]['Y']}Y + {yr_data[3]['R']}R months, meaning current staffing "
                            f"strategy will be inadequate by Year 3. A proactive hire in the Year 2 window is required "
                            f"to stay ahead of this demand curve.")
        else:
            growth_prose = (f"Volume growth of {cfg.annual_growth_pct:.0f}% annually takes daily visits "
                            f"from {y1_vis:.1f} to {y3_vis:.1f} — {growth_pct:.0f}% higher by Year 3. "
                            f"The current hiring policy absorbs this growth cleanly, with Year 3 showing "
                            f"{yr_data[3]['G']}G / {yr_data[3]['Y']}Y / {yr_data[3]['R']}R. "
                            f"Continue monitoring load targets as Year 3 demand approaches — "
                            f"a load target adjustment may be needed in the Year 3 planning cycle.")

        # ── Recommended actions ───────────────────────────────────────────────
        actions = []

        # Action: fix winter load target if burnout is high
        if burnout > 100_000:
            actions.append(
                f"Tighten the Winter Load Target — current burnout cost of ${burnout/1e3:.0f}K suggests "
                f"providers are being pushed too hard during flu season. Reducing the winter load target "
                f"by 2 pts/APC typically reduces burnout cost by 60–80% with a net EBITDA improvement "
                f"once the turnover savings are counted."
            )

        # Action: post first req
        if perm_hires:
            fh = perm_hires[0]
            actions.append(
                f"Post the first requisition by Y{fh.post_by_year}-{MA[fh.post_by_month-1]} — "
                f"this {fh.fte_hired:.2f} FTE [{fh.mode.replace('_',' ')}] hire must be independent by "
                f"Y{fh.independent_year}-{MA[fh.independent_month-1]} to maintain zone performance. "
                f"Delays here cascade into Yellow/Red months with direct revenue impact."
            )

        # Action: marginal hire if justified
        if ma and ma.get("net_annual_impact", 0) > 0 and ma.get("payback_months", 999) <= 18:
            pb = ma.get("payback_months", 0)
            actions.append(
                f"Evaluate an opportunistic 0.5 FTE hire — marginal analysis shows ${ma['net_annual_impact']/1e3:.0f}K "
                f"annual net benefit with a {pb:.0f}-month payback. If a strong candidate is available, "
                f"hiring ahead of schedule is financially justified."
            )

        # Action: SWB discipline
        if not swb_ok:
            actions.append(
                f"Address SWB overage — at ${swb_actual:.2f}/visit against a ${swb_target:.0f} target, "
                f"annual SWB cost is running ${(swb_actual - swb_target) * s['annual_visits']/1e3:.0f}K above plan. "
                f"Review support staff ratios and shift coverage overlap for reduction opportunities."
            )

        # Action: retention focus if turnover is high
        replace_cost = cfg.annual_provider_cost_perm * cfg.turnover_replacement_pct / 100
        if tot_turnover > 4:
            actions.append(
                f"Prioritize APC retention — {tot_turnover:.1f} projected turnover events over 3 years "
                f"at ${replace_cost:,.0f} replacement cost each represents ${tot_turnover * replace_cost/1e3:.0f}K "
                f"in avoidable spend. Retention bonuses or schedule flexibility investments below this threshold "
                f"are immediately EBITDA-accretive."
            )

        # Action: growth readiness
        if y3_zone_concern >= 4:
            actions.append(
                f"Plan for Year 3 demand — with {yr_data[3]['Y']}Y + {yr_data[3]['R']}R months projected, "
                f"a growth hire in the Year 2 window is required. Begin the recruiting pipeline in Year 2 "
                f"to ensure independence before Year 3 volume peaks."
            )

        if not actions:
            actions.append(
                f"Maintain current staffing trajectory — the model is performing well across all key metrics. "
                f"Focus on executing the hire calendar on time and monitoring load targets quarterly as "
                f"volume growth compounds in Year 3."
            )

        return {
            "date": datetime.date.today().strftime("%B %d, %Y"),
            "ebitda_prose":   ebitda_prose,
            "capture_prose":  capture_prose,
            "zone_prose":     zone_prose,
            "zone_health":    zone_health,
            "swb_prose":      swb_prose,
            "burnout_prose":  burnout_prose,
            "yr_data":        yr_data,
            "hire_prose":     hire_prose,
            "marginal_prose": marginal_prose,
            "growth_prose":   growth_prose,
            "actions":        actions,
        }

    memo = _generate_exec_summary(pol, s, es, ma, cfg, MA)

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER
    # ─────────────────────────────────────────────────────────────────────────
    import datetime

    # Pre-build all dynamic HTML fragments — must be done BEFORE the f-string
    # so Python doesn't try to evaluate nested quotes/braces as f-string syntax
    ebitda_color  = "#0A6B4A" if es["ebitda"] > 0 else "#F87171"
    zone_badge    = {"excellent":"#22C55E","good":"#0A6B4A","moderate":"#FBBF24","stressed":"#EF4444"}
    badge_col     = zone_badge.get(memo["zone_health"], "#94A3B8")
    actions_html  = "".join(f"<li>{a}</li>" for a in memo["actions"])
    yr1 = memo["yr_data"][1]; yr2 = memo["yr_data"][2]; yr3 = memo["yr_data"][3]
    # Top-right KPI: cumulative SWB variance impact vs budget across all 3 years
    _total_swb_impact = yr1["swb_impact"] + yr2["swb_impact"] + yr3["swb_impact"]
    _swb_impact_color = "#0A6B4A" if _total_swb_impact >= 0 else "#B91C1C"
    _swb_impact_sign  = "+" if _total_swb_impact >= 0 else "−"
    _swb_impact_word  = "favorable" if _total_swb_impact >= 0 else "unfavorable"
    _avg_actual_swb   = (yr1["swb_actual"] + yr2["swb_actual"] + yr3["swb_actual"]) / 3
    ebitda_3yr_fmt    = f"{_swb_impact_sign}${abs(_total_swb_impact)/1e6:.2f}M"
    ebitda_color      = _swb_impact_color
    ebitda_lbl        = f"3-Year SWB Variance vs ${cfg.swb_target_per_visit:.0f} Target"
    zones_fmt         = f"${_avg_actual_swb:.2f} avg actual &nbsp;·&nbsp; {_swb_impact_word}"
    gen_date      = memo['date']
    base_vis      = f"{cfg.base_visits_per_day:.0f}"
    growth_pct    = f"{cfg.annual_growth_pct:.0f}"
    headline_ebitda   = memo['ebitda_prose']
    headline_capture  = memo['capture_prose']
    headline_zone     = memo['zone_prose']
    headline_swb      = memo['swb_prose']
    yr1_zones     = f"{yr1['G']}G / {yr1['Y']}Y / {yr1['R']}R &nbsp;&middot;&nbsp; Peak {yr1['peak']:.1f} pts/APC"
    yr2_zones     = f"{yr2['G']}G / {yr2['Y']}Y / {yr2['R']}R &nbsp;&middot;&nbsp; Peak {yr2['peak']:.1f} pts/APC"
    yr3_zones     = f"{yr3['G']}G / {yr3['Y']}Y / {yr3['R']}R &nbsp;&middot;&nbsp; Peak {yr3['peak']:.1f} pts/APC"
    def _swb_impact_label(yr_d, target):
        imp  = yr_d["swb_impact"]
        var  = yr_d["swb_variance"]
        sign = "+" if imp >= 0 else "−"
        clr  = "#0A6B4A" if imp >= 0 else "#B91C1C"
        word = "favorable" if imp >= 0 else "unfavorable"
        return (f"<span style='color:{clr};font-weight:700'>"
                f"{sign}${abs(imp)/1e3:.0f}K vs budget</span>"
                f"<span style='font-size:0.78em;color:#7A8799;'>"
                f" &nbsp;(${yr_d['swb_actual']:.2f} actual vs ${target:.2f} target · {word})</span>")
    yr1_ebitda = _swb_impact_label(yr1, cfg.swb_target_per_visit)
    yr2_ebitda = _swb_impact_label(yr2, cfg.swb_target_per_visit)
    yr3_ebitda = _swb_impact_label(yr3, cfg.swb_target_per_visit)
    hire_txt      = memo['hire_prose']
    burnout_txt   = memo['burnout_prose']
    marginal_txt  = memo['marginal_prose']
    growth_txt    = memo['growth_prose']

    _memo_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:12px 0;background:#FFFFFF;">
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600&family=DM+Sans:wght@400;500;600&display=swap');
.memo-wrap {{
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    overflow: hidden;
    max-width: 900px;
    margin: 0 auto;
    font-family: 'DM Sans', system-ui, sans-serif;
}}
.memo-masthead {{
    background:#F8FAFC;
    border-bottom: 1px solid #E2E8F0;
    padding: 2rem 2.5rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}}
.memo-eyebrow {{
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #7A8799;
    margin-bottom: 0.5rem;
}}
.memo-title-main {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #0F1923;
    line-height: 1.2;
    margin-bottom: 0.3rem;
}}
.memo-subtitle {{
    font-size: 0.75rem;
    color: #7A8799;
}}
.memo-kpi-block {{
    text-align: right;
}}
.memo-ebitda-num {{
    font-family: 'DM Sans', system-ui, sans-serif;
    font-size: 2.2rem;
    font-weight: 700;
    color: {ebitda_color};
    line-height: 1;
}}
.memo-ebitda-label {{
    font-size: 0.58rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #7A8799;
    margin-top: 0.2rem;
}}
.memo-body {{
    padding: 0 2.5rem 2rem;
}}
.memo-section-label {{
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #7A8799;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 0.35rem;
    margin: 1.8rem 0 0.8rem;
}}
.memo-prose {{
    font-size: 0.88rem;
    line-height: 1.8;
    color: #4A5568;
}}
.memo-prose strong {{ color: #0F1923; }}
.memo-actions {{
    counter-reset: action-counter;
    list-style: none;
    padding: 0;
    margin: 0;
}}
.memo-actions li {{
    counter-increment: action-counter;
    display: flex;
    gap: 1rem;
    margin-bottom: 0.9rem;
    font-size: 0.88rem;
    line-height: 1.7;
    color: #4A5568;
}}
.memo-actions li::before {{
    content: counter(action-counter);
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 1.6rem;
    height: 1.6rem;
    background: #F1F5F9;
    color: #003366;
    border-radius: 50%;
    font-size: 0.72rem;
    font-weight: 700;
    margin-top: 0.1rem;
    flex-shrink: 0;
}}
.memo-yr-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin: 0.8rem 0;
}}
.memo-yr-card {{
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    padding: 0.75rem 1rem;
}}
.memo-yr-title {{
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #7A8799;
    margin-bottom: 0.4rem;
}}
.memo-yr-zones {{
    font-size: 0.82rem;
    color: #4A5568;
}}
.memo-yr-ebitda {{
    font-size: 0.86rem;
    font-weight: 600;
    color: #003366;
    margin-top: 0.4rem;
    line-height: 1.45;
}}
</style>

<div class="memo-wrap">
  <div class="memo-masthead">
    <div>
      <div class="memo-eyebrow">Predictive Staffing Model &nbsp;·&nbsp; Executive Summary</div>
      <div class="memo-title-main">Staffing & EBITDA Outlook</div>
      <div class="memo-subtitle">
        Generated {gen_date} &nbsp;·&nbsp;
        {base_vis} visits/day &nbsp;·&nbsp;
        {growth_pct}% YoY growth &nbsp;·&nbsp;
        36-month horizon
      </div>
    </div>
    <div class="memo-kpi-block">
      <div class="memo-ebitda-num">{ebitda_3yr_fmt}</div>
      <div class="memo-ebitda-label">{ebitda_lbl}</div>
      <div style="margin-top:0.5rem;font-size:0.72rem;color:{_swb_impact_color};font-weight:500;text-align:right;letter-spacing:0.02em;">
        {zones_fmt}
      </div>
    </div>
  </div>

  <div class="memo-body">

    <div class="memo-section-label">Headline Verdict</div>
    <div class="memo-prose">
      {headline_swb}.
      Zone performance is <strong>{headline_zone}</strong>
      with {headline_capture}.
    </div>

    <div class="memo-section-label">What Your Current Inputs Are Producing</div>
    <div class="memo-yr-grid">
      <div class="memo-yr-card">
        <div class="memo-yr-title">Year 1</div>
        <div class="memo-yr-zones">{yr1_zones}</div>
        <div class="memo-yr-ebitda">{yr1_ebitda}</div>
      </div>
      <div class="memo-yr-card">
        <div class="memo-yr-title">Year 2</div>
        <div class="memo-yr-zones">{yr2_zones}</div>
        <div class="memo-yr-ebitda">{yr2_ebitda}</div>
      </div>
      <div class="memo-yr-card">
        <div class="memo-yr-title">Year 3</div>
        <div class="memo-yr-zones">{yr3_zones}</div>
        <div class="memo-yr-ebitda">{yr3_ebitda}</div>
      </div>
    </div>
    <div class="memo-prose">
      {hire_txt}
    </div>

    <div class="memo-section-label">Where Money Is Being Left On The Table</div>
    <div class="memo-prose">
      {burnout_txt}.
      {marginal_txt}
    </div>

    <div class="memo-section-label">Recommended Actions</div>
    <ol class="memo-actions">
      {actions_html}
    </ol>

    <div class="memo-section-label">3-Year Outlook</div>
    <div class="memo-prose">
      {growth_txt}
    </div>

  </div>
</div>
</body></html>"""
    _memo_height = 900 + len(memo["actions"]) * 80
    _components.html(_memo_html, height=_memo_height, scrolling=False)

    # KPI strip
    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    ek1,ek2,ek3,ek4,ek5 = st.columns(5)
    ek1.metric("3-Yr EBITDA",        f"${es['ebitda']/1e6:.2f}M")
    ek2.metric("Visit Capture",       f"{es['capture_rate']*100:.1f}%")
    ek3.metric("3-Yr Burnout Cost",   f"${s['total_burnout_penalty']/1e3:.0f}K")
    ek4.metric("Turnover Events",     f"{s['total_turnover_events']:.1f}")
    ek5.metric("SWB/Visit",           f"${s['annual_swb_per_visit']:.2f}",
               delta=f"Target ${cfg.swb_target_per_visit:.0f}",
               delta_color="inverse" if s['swb_violation'] else "normal")


    # ── PDF EXPORT ────────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    def _build_exec_pdf(pol, memo, cfg, s, es, MA, yr_data_ext):
        """Build executive summary PDF from simulation data."""
        import io as _io
        import re as _re
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors as rc
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                         Table, TableStyle, HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT

        def _strip(html):
            return _re.sub(r'<[^>]+>', '', str(html))                .replace('&nbsp;',' ').replace('&middot;','·')                .replace('&ndash;','–').replace('&mdash;','—').strip()

        RN=rc.HexColor("#003366"); RG=rc.HexColor("#C9A227")
        RS=rc.HexColor("#4A5568"); RM=rc.HexColor("#7A8799")
        RI=rc.HexColor("#0F1923"); RL=rc.HexColor("#F1F5F9")
        RGR=rc.HexColor("#0A6B4A"); RRD=rc.HexColor("#B91C1C")
        RAM=rc.HexColor("#92600A"); RW=rc.white

        def sty(name, **kw):
            d = dict(fontName="Helvetica", fontSize=9, textColor=RI,
                     leading=13, spaceAfter=3, spaceBefore=0)
            d.update(kw); return ParagraphStyle(name, **d)

        def rule(color="#E2E8F0", thick=0.5, before=3, after=5):
            return HRFlowable(width="100%", thickness=thick,
                              color=rc.HexColor(color),
                              spaceBefore=before, spaceAfter=after)

        GRID = [("VALIGN",(0,0),(-1,-1),"TOP"),
                ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
                ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0"))]

        buf = _io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter,
            leftMargin=0.75*inch, rightMargin=0.75*inch,
            topMargin=0.65*inch, bottomMargin=0.65*inch)
        story = []

        # Computed values
        _ebitda     = es["ebitda"]
        _ebitda_clr = RGR if _ebitda >= 0 else RRD
        _ebitda_sign= "+" if _ebitda >= 0 else ""
        _swb_a      = s["annual_swb_per_visit"]
        _swb_t      = cfg.swb_target_per_visit
        _swb_var    = _swb_a - _swb_t
        _swb_clr    = RGR if _swb_var <= 0 else RRD
        _swb_fav    = _swb_var <= 0
        _cap_pct    = es["capture_rate"] * 100
        _cap_clr    = RGR if _cap_pct >= 99.0 else RAM
        _turn_clr   = RRD if es["turnover"] > 150_000 else (RAM if es["turnover"] > 50_000 else RGR)
        _burn_clr   = RRD if s["red_months"] > 0 else RGR

        # ── MASTHEAD ────────────────────────────────────────────────────────────
        story.append(Paragraph(
            "PREDICTIVE STAFFING MODEL  ·  EXECUTIVE SUMMARY",
            sty("eye", fontSize=6.5, textColor=RM, spaceAfter=2, leading=9)))
        mast = Table([[
            [Paragraph("Staffing & EBITDA Outlook",
                       sty("mh", fontName="Helvetica-Bold", fontSize=17,
                           textColor=RN, leading=21, spaceAfter=2)),
             Paragraph(f"Generated {memo['date']}  ·  {cfg.base_visits_per_day:.0f} vpd  ·  "
                       f"{cfg.annual_growth_pct:.0f}% YoY growth  ·  "
                       f"Base {pol.base_fte:.1f} FTE / Winter {pol.winter_fte:.1f} FTE",
                       sty("ms", fontSize=8, textColor=RS))],
            [Paragraph(f"{_ebitda_sign}${_ebitda/1e6:.2f}M",
                       sty("ev", fontName="Helvetica-Bold", fontSize=20,
                           textColor=_ebitda_clr, alignment=TA_RIGHT, leading=22, spaceAfter=1)),
             Paragraph("3-YEAR EBITDA",
                       sty("el", fontSize=6.5, textColor=RM,
                           alignment=TA_RIGHT, leading=8, spaceAfter=2)),
             Paragraph(f"${_swb_a:.2f} avg SWB/visit  ·  "
                       f"{'favorable' if _swb_fav else 'over budget'}",
                       sty("es", fontSize=7.5, textColor=_swb_clr,
                           alignment=TA_RIGHT, leading=10))]
        ]], colWidths=[4.1*inch, 2.65*inch])
        mast.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"BOTTOM"),
            ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),0),
            ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
        ]))
        story.append(mast)
        story.append(rule("#C9A227", thick=1.5, before=6, after=8))

        # ── KPI BAR (6 tiles) ───────────────────────────────────────────────────
        def _kpi(lbl, val, sub, vc):
            return [
                Paragraph(lbl, sty(f"kl{lbl}", fontSize=6, textColor=RM,
                                   fontName="Helvetica-Bold", leading=8, spaceAfter=1)),
                Paragraph(val, sty(f"kv{lbl}", fontSize=12, fontName="Helvetica-Bold",
                                   textColor=vc, leading=14, spaceAfter=1)),
                Paragraph(sub, sty(f"ks{lbl}", fontSize=7, textColor=RS,
                                   leading=9, spaceAfter=0)),
            ]
        kpi_cols = [
            _kpi("BASE FTE",    f"{pol.base_fte:.1f}",
                 f"Winter {pol.winter_fte:.1f} FTE", RN),
            _kpi("SWB / VISIT", f"${_swb_a:.2f}",
                 f"{'▼' if _swb_fav else '▲'} ${abs(_swb_var):.2f} vs ${_swb_t:.0f} target",
                 _swb_clr),
            _kpi("VISIT CAPTURE", f"{_cap_pct:.1f}%",
                 f"{s['green_months']}G / {s['yellow_months']}Y / {s['red_months']}R",
                 _cap_clr),
            _kpi("TURNOVER (3YR)", f"${es['turnover']/1e3:.0f}K",
                 f"{s['total_turnover_events']:.1f} events", _turn_clr),
            _kpi("BURNOUT COST",  f"${es['burnout']/1e3:.0f}K",
                 f"{s['red_months']} Red months", _burn_clr),
            _kpi("3-YR EBITDA",  f"${_ebitda/1e6:.2f}M",
                 f"Rev ${es['revenue']/1e6:.2f}M", _ebitda_clr),
        ]
        krows = list(zip(*kpi_cols))
        ktbl  = Table(list(krows), colWidths=[1.13*inch]*6)
        ktbl.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),6), ("BACKGROUND",(0,0),(-1,-1),RL),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
        ]))
        story.append(ktbl)
        story.append(Spacer(1, 6))

        # ── HEADLINE VERDICT ────────────────────────────────────────────────────
        story.append(Paragraph("HEADLINE VERDICT",
                                sty("hl", fontName="Helvetica-Bold", fontSize=7,
                                    textColor=RM, spaceBefore=6, spaceAfter=4)))
        story.append(Paragraph(_strip(memo["ebitda_prose"]),
                                sty("hb1", fontSize=8.5, textColor=RS, leading=13, spaceAfter=3)))
        story.append(Paragraph(_strip(memo["zone_prose"]),
                                sty("hb2", fontSize=8.5, textColor=RS, leading=13, spaceAfter=3)))
        story.append(rule())

        # ── YEAR CARDS ──────────────────────────────────────────────────────────
        story.append(Paragraph("WHAT YOUR CURRENT INPUTS ARE PRODUCING",
                                sty("wcl", fontName="Helvetica-Bold", fontSize=7,
                                    textColor=RM, spaceAfter=4)))

        def _yr_card(n, yd):
            _swb_savings = yd["goal"] - yd["act"] - yd.get("flex", 0)  # labor budget vs spend incl. flex
            _nonlabor    = yd.get("turn", 0) + yd.get("burn", 0)
            _net_var     = _swb_savings - _nonlabor

            _sav_clr  = RGR if _swb_savings >= 0 else RRD
            _sav_sign = "+" if _swb_savings >= 0 else "−"
            _net_clr  = RGR if _net_var >= 0 else RRD
            _net_sign = "+" if _net_var >= 0 else ""

            _swb_fav  = yd["swb_actual"] <= cfg.swb_target_per_visit
            _swb_clr  = RGR if _swb_fav else RRD
            _swb_word = "SWB on target" if _swb_fav else "SWB over budget"

            return [
                Paragraph(f"YEAR {n}", sty(f"yh{n}", fontSize=6.5, textColor=RM,
                           fontName="Helvetica-Bold", leading=9, spaceAfter=2)),
                Paragraph(f"{yd['G']}G / {yd['Y']}Y / {yd['R']}R  ·  Peak {yd['peak']:.1f} pts/APC",
                           sty(f"yz{n}", fontSize=7.5, textColor=RS, leading=10, spaceAfter=4)),
                # Labor section
                Paragraph("LABOR", sty(f"yls{n}", fontSize=6, textColor=RM,
                           fontName="Helvetica-Bold", leading=9, spaceAfter=1)),
                Paragraph(f"SWB Goal      ${yd['goal']/1e3:.0f}K",
                           sty(f"y1{n}", fontSize=8, textColor=RI, leading=11, spaceAfter=1)),
                Paragraph(f"SWB Actual    −${yd['act']/1e3:.0f}K",
                           sty(f"y2{n}", fontSize=8, textColor=RRD, leading=11, spaceAfter=1)),
                Paragraph(f"Flex / Locum  −${yd.get('flex',0)/1e3:.0f}K",
                           sty(f"y3{n}", fontSize=8, textColor=RRD, leading=11, spaceAfter=1)),
                Paragraph(f"SWB Savings   {_sav_sign}${abs(_swb_savings)/1e3:.0f}K",
                           sty(f"y2s{n}", fontSize=7.5, textColor=_sav_clr,
                               fontName="Helvetica-BoldOblique", leading=10, spaceAfter=4)),
                # HR / Operational section
                Paragraph("HR / OPERATIONAL", sty(f"yhs{n}", fontSize=6, textColor=RM,
                           fontName="Helvetica-Bold", leading=9, spaceAfter=1)),
                Paragraph(f"Turnover      −${yd.get('turn',0)/1e3:.0f}K",
                           sty(f"y4{n}", fontSize=8, textColor=RRD, leading=11, spaceAfter=1)),
                Paragraph(f"Burnout       −${yd.get('burn',0)/1e3:.0f}K",
                           sty(f"y5{n}", fontSize=8, textColor=RRD, leading=11, spaceAfter=3)),
                Paragraph(f"Net Variance  {_net_sign}${abs(_net_var)/1e3:.0f}K",
                           sty(f"yv{n}", fontName="Helvetica-Bold", fontSize=9,
                               textColor=_net_clr, leading=11, spaceAfter=2)),
                Paragraph(f"${yd['swb_actual']:.2f} actual vs ${cfg.swb_target_per_visit:.2f} target  ·  {_swb_word}",
                           sty(f"ys{n}", fontSize=7, textColor=_swb_clr, leading=9)),
            ]

        yr1d = yr_data_ext[1]; yr2d = yr_data_ext[2]; yr3d = yr_data_ext[3]
        ytbl = Table([[_yr_card(1,yr1d), _yr_card(2,yr2d), _yr_card(3,yr3d)]],
                     colWidths=[2.25*inch]*3)
        ytbl.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),7), ("BOTTOMPADDING",(0,0),(-1,-1),7),
            ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
            ("BACKGROUND",(0,0),(-1,-1),rc.HexColor("#FAFBFC")),
        ]))
        story.append(ytbl)
        story.append(Spacer(1, 4))
        story.append(rule())

        # ── SWB VARIANCE BREAKDOWN ──────────────────────────────────────────────
        _ann_vis  = sum(mo.visits_captured for mo in pol.months) / 3
        _ann_goal = cfg.swb_target_per_visit * _ann_vis
        _ann_act  = sum(mo.permanent_cost + mo.support_cost for mo in pol.months) / 3
        _ann_flex = sum(mo.flex_cost        for mo in pol.months) / 3
        _ann_turn = sum(mo.turnover_cost    for mo in pol.months) / 3
        _ann_burn = sum(mo.burnout_penalty  for mo in pol.months) / 3
        _ann_var  = _ann_goal - _ann_act - _ann_flex - _ann_turn - _ann_burn
        _av_clr   = RGR if _ann_var >= 0 else RRD
        _av_sign  = "+" if _ann_var >= 0 else ""
        _av_word  = "favorable" if _ann_var >= 0 else "unfavorable"
        _ann_savings     = _ann_goal - _ann_act
        _ann_sav_sign    = "+" if _ann_savings >= 0 else "−"
        _ann_sav_clr     = RGR if _ann_savings >= 0 else RRD
        _ann_other       = _ann_flex + _ann_turn + _ann_burn

        story.append(Paragraph("SWB VARIANCE BREAKDOWN — ANNUALISED (3-YR AVG)",
                                sty("svl", fontName="Helvetica-Bold", fontSize=7,
                                    textColor=RM, spaceAfter=4)))

        # Two-row breakdown table: SWB savings line + other costs line = net
        svb_data = [
            [
                Paragraph("SWB Goal", sty("sg", fontSize=8, textColor=RM)),
                Paragraph(f"${_ann_goal/1e3:.0f}K", sty("sgv", fontSize=8, textColor=RI)),
                Paragraph("−  SWB Actual", sty("sa", fontSize=8, textColor=RM)),
                Paragraph(f"${_ann_act/1e3:.0f}K", sty("sav", fontSize=8, textColor=RRD)),
                Paragraph("=  SWB Savings", sty("ss", fontSize=8, textColor=RM,
                           fontName="Helvetica-Oblique")),
                Paragraph(f"{_ann_sav_sign}${abs(_ann_savings)/1e3:.0f}K",
                          sty("ssv", fontSize=8, textColor=_ann_sav_clr,
                              fontName="Helvetica-BoldOblique")),
            ],
            [
                Paragraph("Flex", sty("fl", fontSize=8, textColor=RM)),
                Paragraph(f"−${_ann_flex/1e3:.0f}K", sty("flv", fontSize=8, textColor=RRD)),
                Paragraph("Turnover", sty("tu", fontSize=8, textColor=RM)),
                Paragraph(f"−${_ann_turn/1e3:.0f}K", sty("tuv", fontSize=8, textColor=RRD)),
                Paragraph("Burnout", sty("bu2", fontSize=8, textColor=RM)),
                Paragraph(f"−${_ann_burn/1e3:.0f}K", sty("buv", fontSize=8, textColor=RRD)),
            ],
        ]
        svb_total = Table([
            [
                Paragraph("Net Variance / yr",
                          sty("nt", fontSize=9, fontName="Helvetica-Bold", textColor=RI)),
                Paragraph(f"{_av_sign}${abs(_ann_var)/1e3:.0f}K  ({_av_word})",
                          sty("ntv", fontSize=9, fontName="Helvetica-Bold", textColor=_av_clr)),
            ]
        ], colWidths=[1.6*inch, 5.1*inch])
        svb_total.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),6),
            ("BACKGROUND",(0,0),(-1,-1),rc.HexColor("#F8FAFC")),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
        ]))

        svb_rows = Table(svb_data,
                         colWidths=[0.75*inch,0.65*inch,1.05*inch,0.65*inch,1.05*inch,0.65*inch])
        svb_rows.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),5),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[rc.white, rc.HexColor("#F8FAFC")]),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
            ("LINEBELOW",(0,0),(-1,0),0.5,rc.HexColor("#E2E8F0")),
        ]))
        story.append(svb_rows)
        story.append(Spacer(1,3))
        story.append(svb_total)
        story.append(rule())

        # ── HIRE CALENDAR ────────────────────────────────────────────────────────
        story.append(Paragraph("HIRE CALENDAR",
                                sty("hcl", fontName="Helvetica-Bold", fontSize=7,
                                    textColor=RM, spaceAfter=4)))
        _lead = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
        S_hh  = sty("hh", fontName="Helvetica-Bold", fontSize=7.5, textColor=RW)
        S_hv  = sty("hv", fontSize=8, textColor=RI)
        h_data = [[Paragraph(c, S_hh) for c in ["Post By","Productive","FTE","Mode","Driver"]]]
        for h in pol.hire_events:
            h_data.append([
                Paragraph(f"Y{h.post_by_year}-{MA[h.post_by_month-1]}", S_hv),
                Paragraph(f"Y{h.independent_year}-{MA[h.independent_month-1]}", S_hv),
                Paragraph(f"+{h.fte_hired:.2f}", S_hv),
                Paragraph(h.mode.replace("_"," ").title(), S_hv),
                Paragraph("Flu anchor" if h.mode=="winter_ramp" else "Growth demand", S_hv),
            ])
        h_tbl = Table(h_data,
                      colWidths=[0.85*inch, 0.85*inch, 0.6*inch, 1.3*inch, 3.15*inch])
        h_tbl.setStyle(TableStyle(GRID + [
            ("BACKGROUND",(0,0),(-1,0),RN),
            ("TEXTCOLOR",(0,0),(-1,0),RW),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,0),7.5),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[rc.white,RL]),
        ]))
        story.append(h_tbl)
        story.append(Paragraph(
            f"Pipeline: {cfg.days_to_sign}d sign + {cfg.days_to_credential}d credential + "
            f"{cfg.days_to_independent}d onboard = {_lead}d.  "
            f"APCs are 0% productive until credentialing completes.",
            sty("hn", fontSize=7.5, textColor=RM, leading=10, spaceAfter=3)))

        # Narrative prose sections removed — data is represented in structured tables above

        # ── RECOMMENDED ACTIONS ─────────────────────────────────────────────────
        story.append(rule())
        story.append(Paragraph("RECOMMENDED ACTIONS",
                                sty("al", fontName="Helvetica-Bold", fontSize=7,
                                    textColor=RM, spaceAfter=4)))
        for i, action in enumerate(memo["actions"], 1):
            story.append(Paragraph(f"{i}.  {_strip(action)}",
                sty(f"ac{i}", fontSize=8.5, textColor=RS,
                    leading=13, leftIndent=16, spaceAfter=4)))

        # ── 3-YEAR OUTLOOK ───────────────────────────────────────────────────────
        if memo.get("growth_prose"):
            story.append(rule())
            story.append(Paragraph("3-YEAR OUTLOOK",
                sty("gl", fontName="Helvetica-Bold", fontSize=7,
                    textColor=RM, spaceAfter=4)))
            story.append(Paragraph(_strip(memo["growth_prose"]),
                sty("gb", fontSize=8.5, textColor=RS, leading=13, spaceAfter=4)))

        # ── AI BRIEFING ──────────────────────────────────────────────────────────
        if st.session_state.get("psm_briefing"):
            story.append(rule())
            story.append(Paragraph("AI ADVISOR BRIEFING",
                sty("abl", fontName="Helvetica-Bold", fontSize=7,
                    textColor=RM, spaceAfter=4)))
            for para in st.session_state["psm_briefing"].split("\n\n"):
                if para.strip():
                    story.append(Paragraph(para.strip(),
                        sty("abp", fontSize=8.5, textColor=RS, leading=13, spaceAfter=4)))

        # ── ZONE + MARGINAL FOOTER ───────────────────────────────────────────────
        story.append(rule())
        _ma      = pol.marginal_analysis or {}
        _net_ann = _ma.get("net_annual_impact", 0)
        _pay_mo  = _ma.get("payback_months", float("inf"))
        _pay_str = "never" if _pay_mo == float("inf") else f"{_pay_mo:.0f} mo"
        _rs      = _ma.get("red_months_saved", 0)
        _ys      = _ma.get("yellow_months_saved", 0)
        _mn_clr  = RGR if _net_ann >= 0 else RRD
        _mn_sign = "+" if _net_ann >= 0 else ""
        _gm = s["green_months"]; _ym = s["yellow_months"]; _rm = s["red_months"]
        _oa = s.get("total_overload_attrition", 0)

        zone_tbl = Table([[
            Paragraph("36-MONTH ZONES", sty("zl", fontSize=6.5, textColor=RM,
                       fontName="Helvetica-Bold", leading=9)),
            Paragraph(f"{_gm}G", sty("zg", fontSize=12, fontName="Helvetica-Bold",
                       textColor=RGR, leading=14, alignment=TA_CENTER)),
            Paragraph("/", sty("zd1", fontSize=10, textColor=RM,
                       alignment=TA_CENTER, leading=14)),
            Paragraph(f"{_ym}Y", sty("zy2", fontSize=12, fontName="Helvetica-Bold",
                       textColor=RAM, leading=14, alignment=TA_CENTER)),
            Paragraph("/", sty("zd2", fontSize=10, textColor=RM,
                       alignment=TA_CENTER, leading=14)),
            Paragraph(f"{_rm}R", sty("zr3", fontSize=12, fontName="Helvetica-Bold",
                       textColor=RRD, leading=14, alignment=TA_CENTER)),
            Paragraph(f"·  {es['capture_rate']*100:.1f}% visit capture  ·  "
                      f"{_oa:.1f} FTE overload attrition",
                      sty("zn", fontSize=7.5, textColor=RS, leading=10)),
        ]], colWidths=[1.3*inch,0.35*inch,0.2*inch,0.35*inch,0.2*inch,0.35*inch,4.0*inch])
        zone_tbl.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),6),
            ("BACKGROUND",(0,0),(-1,-1),RL),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
        ]))

        marg_tbl = Table([[
            Paragraph("+0.5 FTE MARGINAL", sty("ml", fontSize=6.5, textColor=RM,
                       fontName="Helvetica-Bold", leading=9)),
            Paragraph(f"Saves {_rs}R + {_ys}Y zone-months",
                      sty("ms", fontSize=7.5, textColor=RS, leading=10)),
            Paragraph(f"Net annual: {_mn_sign}${abs(_net_ann)/1e3:.0f}K",
                      sty("mn", fontSize=7.5, textColor=_mn_clr,
                          fontName="Helvetica-Bold", leading=10)),
            Paragraph(f"Payback: {_pay_str}",
                      sty("mp", fontSize=7.5, textColor=RS, leading=10)),
        ]], colWidths=[1.3*inch, 2.0*inch, 1.8*inch, 1.65*inch])
        marg_tbl.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),6),
            ("BACKGROUND",(0,0),(-1,-1),rc.HexColor("#F8FAFC")),
            ("GRID",(0,0),(-1,-1),0.3,rc.HexColor("#E2E8F0")),
        ]))

        story.append(zone_tbl)
        story.append(Spacer(1, 3))
        story.append(marg_tbl)

        # ── FOOTER ──────────────────────────────────────────────────────────────
        story.append(rule("#C9A227", thick=1.5, before=8, after=4))
        story.append(Paragraph(
            f"Predictive Staffing Model  ·  Urgent Care  ·  36-Month Horizon  ·  "
            f"Generated {memo['date']}",
            sty("ftr", fontSize=7, textColor=RM, alignment=TA_CENTER)))

        doc.build(story)
        return buf.getvalue()
    # ── Export button ──────────────────────────────────────────────────────────
    _pc1, _pc2, _pc3 = st.columns([1, 1, 4])
    with _pc1:
        if st.button("⬇ Export PDF", key="export_pdf", use_container_width=True):
            with st.spinner("Building PDF..."):
                _pdf_bytes = _build_exec_pdf(pol, memo, cfg, s, es, MA, _yr_data)
            st.session_state["psm_exec_pdf"] = _pdf_bytes
            st.success("PDF ready — click Download below.", icon="✅")
    with _pc2:
        if "psm_exec_pdf" in st.session_state:
            import datetime as _dt
            _fname = f"PSM_ExecSummary_{_dt.date.today().strftime('%Y%m%d')}.pdf"
            st.download_button(
                "⬇ Download PDF",
                data=st.session_state["psm_exec_pdf"],
                file_name=_fname,
                mime="application/pdf",
                use_container_width=True,
                key="dl_pdf",
            )


    # ── AI BRIEFING ───────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1rem;'>", unsafe_allow_html=True)
    st.markdown("## AI ADVISOR BRIEFING")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{SLATE};margin:-0.4rem 0 1rem;'>"
        f"One-click CFO-quality memo interpreting this staffing model — "
        f"risks, tradeoffs, and what to watch. Powered by GPT-4o.</p>",
        unsafe_allow_html=True)

    _oai_key_brief = _openai_key()
    if not _oai_key_brief:
        st.warning("Add `OPENAI_API_KEY` to your Streamlit secrets to enable AI features.", icon="🔑")
    else:
        if st.button("✦ Generate Briefing", type="primary", key="gen_briefing"):
            _sim_ctx = _build_simulation_context(pol, cfg, MA)
            _brief_messages = [
                {"role": "system", "content": _advisor_system_prompt(_sim_ctx)},
                {"role": "user", "content": (
                    "Write a concise CFO-quality briefing memo for this staffing model. "
                    "Structure it as: (1) Policy overview and what it achieves, "
                    "(2) Key risks or watch items, "
                    "(3) The single most important operational decision in the next 90 days. "
                    "Be specific — reference actual months, FTE counts, and dollar amounts from the simulation. "
                    "Plain prose, no bullet points, no headers. 3-4 paragraphs."
                )},
            ]
            with st.spinner("Drafting briefing..."):
                _brief_text, _brief_err = _call_openai(_brief_messages, _oai_key_brief, max_tokens=600)
            if _brief_err:
                st.error(f"Error: {_brief_err}")
            else:
                st.session_state["psm_briefing"] = _brief_text

        if "psm_briefing" in st.session_state:
            st.markdown(
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;"
                f"border-left:4px solid {NAVY};border-radius:4px;"
                f"padding:1.1rem 1.3rem;font-size:0.87rem;line-height:1.7;"
                f"color:{INK};margin-top:0.6rem;'>"
                f"{st.session_state['psm_briefing'].replace(chr(10), '<br>')}"
                f"</div>",
                unsafe_allow_html=True)
            st.markdown(
                f"<div style='font-size:0.68rem;color:{MUTED};margin-top:0.35rem;'>"
                f"Generated by GPT-4o · grounded in your simulation data · "
                f"not HR or legal advice</div>",
                unsafe_allow_html=True)
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # ── SENSITIVITY SNAPSHOT ─────────────────────────────────────────────────
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1.2rem;'>", unsafe_allow_html=True)
    st.markdown("## KEY SENSITIVITIES")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{SLATE};margin:-0.4rem 0 1.2rem;'>"
        f"Top inputs ranked by their impact on 3-year EBITDA. "
        f"Each shows the swing from low to high scenario. "
        f"See the <b>Sensitivity</b> tab for the full tornado chart.</p>",
        unsafe_allow_html=True)

    with st.spinner("Computing sensitivities..."):
        _es_base   = pol.ebitda_summary["ebitda"]
        _sens_scenarios = [
            ("Revenue / Visit",        "net_revenue_per_visit",
             max(60.0, cfg.net_revenue_per_visit * 0.80),
             cfg.net_revenue_per_visit * 1.20,
             f"${cfg.net_revenue_per_visit*0.80:.0f}", f"${cfg.net_revenue_per_visit*1.20:.0f}"),
            ("Base Visits / Day",      "base_visits_per_day",
             max(10.0, cfg.base_visits_per_day * 0.75),
             cfg.base_visits_per_day * 1.35,
             f"{cfg.base_visits_per_day*0.75:.0f} vpd", f"{cfg.base_visits_per_day*1.35:.0f} vpd"),
            ("Pts / APC / Day Budget", "budgeted_patients_per_provider_per_day",
             max(18.0, cfg.budgeted_patients_per_provider_per_day - 8),
             cfg.budgeted_patients_per_provider_per_day + 8,
             f"{cfg.budgeted_patients_per_provider_per_day-8:.0f} pts",
             f"{cfg.budgeted_patients_per_provider_per_day+8:.0f} pts"),
            ("APC Annual Cost",        "annual_provider_cost_perm",
             cfg.annual_provider_cost_perm * 0.80,
             cfg.annual_provider_cost_perm * 1.25,
             f"${cfg.annual_provider_cost_perm*0.80/1e3:.0f}K",
             f"${cfg.annual_provider_cost_perm*1.25/1e3:.0f}K"),
            ("Annual Growth %",        "annual_growth_pct",
             max(0.0, cfg.annual_growth_pct - 5),
             cfg.annual_growth_pct + 10,
             f"{max(0,cfg.annual_growth_pct-5):.0f}%", f"{cfg.annual_growth_pct+10:.0f}%"),
        ]

        def _run_sens(kwarg, val):
            _f = {f: getattr(cfg, f) for f in cfg.__dataclass_fields__}
            _f[kwarg] = val
            try:
                _p, _ = optimize(ClinicConfig(**_f))
                return _p.ebitda_summary["ebitda"]
            except Exception:
                return _es_base

        _sens_results = []
        for _sl, _sk, _slo, _shi, _sll, _shl in _sens_scenarios:
            _lo_e = _run_sens(_sk, _slo)
            _hi_e = _run_sens(_sk, _shi)
            _sens_results.append((_sl, _sll, _shl, _lo_e, _hi_e, abs(_hi_e - _lo_e)))
        _sens_results.sort(key=lambda x: x[5], reverse=True)
        _max_swing = _sens_results[0][5] if _sens_results else 1

    # Render cards — 3 per row
    _C_NEG_S = "#C0392B"
    _C_POS_S = "#0A6B4A"
    _card_cols = st.columns(3)
    for _ci, (_sl, _sll, _shl, _lo_e, _hi_e, _swing) in enumerate(_sens_results):
        _lo_d = _lo_e - _es_base
        _hi_d = _hi_e - _es_base
        _bar_pct = int(_swing / _max_swing * 100)
        _unfav_w = int(abs(min(_lo_d, _hi_d)) / _max_swing * 50)
        _fav_w   = int(abs(max(_lo_d, _hi_d)) / _max_swing * 50)
        _rank    = _ci + 1
        _rank_color = {1: "#7A6200", 2: NAVY, 3: NAVY}.get(_rank, MUTED)

        with _card_cols[_ci % 3]:
            st.markdown(
                f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;"
                f"border-top:3px solid {_rank_color};"
                f"border-radius:4px;padding:0.85rem 1rem 0.8rem;"
                f"box-shadow:0 1px 3px rgba(0,0,0,0.04);margin-bottom:0.75rem;'>"

                # Rank + label
                f"<div style='display:flex;align-items:baseline;gap:0.5rem;margin-bottom:0.55rem;'>"
                f"<span style='font-size:0.62rem;font-weight:700;color:{_rank_color};"
                f"font-family:Courier New,monospace;'>#{_rank}</span>"
                f"<span style='font-size:0.82rem;font-weight:700;color:{INK};'>{_sl}</span>"
                f"</div>"

                # Swing headline
                f"<div style='font-size:1.10rem;font-weight:700;color:{NAVY};"
                f"margin-bottom:0.4rem;'>"
                f"${_swing/1e3:.0f}K swing</div>"

                # Mini bar — red left, green right, meeting at center
                f"<div style='display:flex;height:6px;border-radius:3px;"
                f"overflow:hidden;margin-bottom:0.45rem;background:#F1F5F9;'>"
                f"<div style='flex:1;display:flex;justify-content:flex-end;'>"
                f"<div style='width:{_unfav_w}%;background:{_C_NEG_S};border-radius:3px 0 0 3px;'></div>"
                f"</div>"
                f"<div style='width:2px;background:#CBD5E0;flex-shrink:0;'></div>"
                f"<div style='flex:1;'>"
                f"<div style='width:{_fav_w}%;background:{_C_POS_S};border-radius:0 3px 3px 0;'></div>"
                f"</div>"
                f"</div>"

                # Low / High labels
                f"<div style='display:flex;justify-content:space-between;"
                f"font-size:0.70rem;margin-bottom:0.3rem;'>"
                f"<span style='color:{_C_NEG_S};'>"
                f"▼ {_sll} → ${_lo_e/1e6:.2f}M</span>"
                f"<span style='color:{_C_POS_S};'>"
                f"▲ {_shl} → ${_hi_e/1e6:.2f}M</span>"
                f"</div>"

                f"</div>",
                unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size:0.72rem;color:{MUTED};margin:-0.2rem 0 0.4rem;'>"
        f"Each card varies one input independently. All others held at current values. "
        f"Full 8-input tornado in the <b>Sensitivity</b> tab.</div>",
        unsafe_allow_html=True)
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1.2rem;'>", unsafe_allow_html=True)

    # ── MONTE CARLO SENSITIVITY ───────────────────────────────────────────────
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1.2rem;'>", unsafe_allow_html=True)
    st.markdown("## MONTE CARLO SENSITIVITY")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{SLATE};margin:-0.4rem 0 1.2rem;'>"
        "500 trials — holds the recommended staffing model fixed and randomizes the four "
        "inputs you cannot control: volume growth, attrition rate, net revenue per visit, "
        "and overload sensitivity. Shows the range of outcomes if key assumptions prove wrong.</p>",
        unsafe_allow_html=True
    )

    with st.expander("Uncertainty ranges used in each trial", expanded=False):
        _ua1, _ua2, _ua3, _ua4 = st.columns(4)
        _ua1.metric("Growth Rate",       f"{cfg.annual_growth_pct:.0f}%",
                    delta=f"±{cfg.annual_growth_pct*0.15:.1f}% (1σ)")
        _ua2.metric("Attrition Rate",    f"{cfg.annual_attrition_pct:.0f}%",
                    delta=f"±{cfg.annual_attrition_pct*0.15:.1f}% (1σ)")
        _ua3.metric("Revenue / Visit",   f"${cfg.net_revenue_per_visit:.0f}",
                    delta=f"±${cfg.net_revenue_per_visit*0.05:.0f} (1σ)")
        _ua4.metric("Overload Factor",   f"{cfg.overload_attrition_factor:.1f}×",
                    delta=f"±{cfg.overload_attrition_factor*0.125:.2f} (1σ)")
        st.caption(
            "Each trial draws these four inputs independently from normal distributions. "
            "Base FTE, Winter FTE, and WLT are held constant — this tests policy robustness "
            "to assumption error, not a comparison of different policies. Seed is fixed (42) "
            "so results are reproducible."
        )

    # Run 500 trials -----------------------------------------------------------
    with st.spinner("Running 500 Monte Carlo trials…"):
        _rng = np.random.default_rng(42)
        _N   = 500
        _mc_ebitda  = np.empty(_N)
        _mc_swb     = np.empty(_N)
        _mc_capture = np.empty(_N)
        _mc_green   = np.empty(_N)
        _mc_burnout = np.empty(_N)

        for _i in range(_N):
            _kw = {f: getattr(cfg, f) for f in cfg.__dataclass_fields__}
            _kw["annual_growth_pct"]         = float(np.clip(
                _rng.normal(cfg.annual_growth_pct,         cfg.annual_growth_pct*0.15),         1,  50))
            _kw["net_revenue_per_visit"]      = float(np.clip(
                _rng.normal(cfg.net_revenue_per_visit,     cfg.net_revenue_per_visit*0.05),      60, 300))
            _kw["annual_attrition_pct"]       = float(np.clip(
                _rng.normal(cfg.annual_attrition_pct,      cfg.annual_attrition_pct*0.15),       3,  60))
            _kw["overload_attrition_factor"]  = float(np.clip(
                _rng.normal(cfg.overload_attrition_factor, cfg.overload_attrition_factor*0.125), 0.2, 5))
            _p = simulate_policy(best.base_fte, best.winter_fte,
                                 ClinicConfig(**_kw))
            _mc_ebitda[_i]  = _p.ebitda_summary["ebitda"]
            _mc_swb[_i]     = _p.summary["annual_swb_per_visit"]
            _mc_capture[_i] = _p.ebitda_summary["capture_rate"] * 100
            _mc_green[_i]   = _p.summary["green_months"]
            _mc_burnout[_i] = _p.ebitda_summary["burnout"]

    # Probability KPI strip ----------------------------------------------------
    _p_pos  = (_mc_ebitda > 0).mean() * 100
    _p_swb  = (_mc_swb <= cfg.swb_target_per_visit).mean() * 100
    _p_cap  = (_mc_capture >= 99.0).mean() * 100
    _p_grn  = (_mc_green >= 30).mean() * 100

    _mk1, _mk2, _mk3, _mk4 = st.columns(4)
    _mk1.metric("P(EBITDA > 0)",       f"{_p_pos:.0f}%",
                delta="all scenarios positive" if _p_pos == 100 else f"{100-_p_pos:.0f}% loss risk",
                delta_color="normal" if _p_pos >= 80 else "inverse")
    _mk2.metric("P(SWB on target)",    f"{_p_swb:.0f}%",
                delta=f"≤ ${cfg.swb_target_per_visit:.0f}/visit",
                delta_color="normal" if _p_swb >= 70 else "inverse")
    _mk3.metric("P(Capture ≥ 99%)",    f"{_p_cap:.0f}%",
                delta="near-perfect throughput",
                delta_color="normal" if _p_cap >= 70 else "inverse")
    _mk4.metric("P(≥ 30 Green months)", f"{_p_grn:.0f}%",
                delta="low provider stress",
                delta_color="normal" if _p_grn >= 70 else "inverse")

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    # Fan chart — EBITDA distribution -----------------------------------------
    _pct_vals = [5, 10, 25, 50, 75, 90, 95]
    _ep       = {p: float(np.percentile(_mc_ebitda, p)) / 1e6 for p in _pct_vals}
    _base_e   = es["ebitda"] / 1e6

    _fig_mc = go.Figure()

    # Shaded confidence bands (narrow → wide)
    _bands_mc = [
        (5,  95, "rgba(56,140,220,0.10)", "p5–p95 (90% CI)"),
        (10, 90, "rgba(56,140,220,0.15)", "p10–p90 (80% CI)"),
        (25, 75, "rgba(56,140,220,0.22)", "p25–p75 (50% CI)"),
    ]
    _sc = ["Pessimistic", "Expected", "Optimistic"]
    for _lo, _hi, _col, _nm in _bands_mc:
        _yhi = [_ep[_lo], _ep[_hi], _ep[_hi]]  # fan shape: narrows pessimistic side
        _ylo = [_ep[_lo], _ep[_lo], _ep[_hi]]
        _fig_mc.add_trace(go.Scatter(
            x=_sc + _sc[::-1],
            y=[_ep[_hi], (_ep[_hi]+_ep[50])/2, _ep[_hi]] + [_ep[_lo], (_ep[_lo]+_ep[50])/2, _ep[_lo]],
            fill="toself", fillcolor=_col,
            line=dict(width=0), showlegend=True, name=_nm, hoverinfo="skip",
        ))

    # Median spine
    _fig_mc.add_trace(go.Scatter(
        x=_sc,
        y=[(_ep[25]+_ep[10])/2, _ep[50], (_ep[75]+_ep[90])/2],
        mode="lines+markers",
        line=dict(color=C_GREEN, width=2.5, dash="solid"),
        marker=dict(size=8, color=C_GREEN),
        name=f"Median  ${_ep[50]:.2f}M",
    ))

    # p5 / p95 boundary markers
    _fig_mc.add_trace(go.Scatter(
        x=["Pessimistic", "Optimistic"],
        y=[_ep[5], _ep[95]],
        mode="markers+text",
        marker=dict(size=9, color="#FCD34D", symbol="diamond"),
        text=[f"p5  ${_ep[5]:.2f}M", f"p95  ${_ep[95]:.2f}M"],
        textposition=["bottom center", "top center"],
        textfont=dict(size=10, color="#FCD34D"),
        name="p5 / p95 bounds",
        showlegend=True,
    ))

    # Base case horizontal reference
    _fig_mc.add_hline(
        y=_base_e,
        line_dash="dot", line_color="#FBBF24", line_width=1.5,
        annotation_text=f"  Base case  ${_base_e:.2f}M",
        annotation_font=dict(color="#FBBF24", size=11),
        annotation_position="right",
    )

    _fig_mc.update_layout(**mk_layout(
        height=360,
        title="3-Year EBITDA Range  —  Monte Carlo Fan  (500 trials, seed=42)",
        yaxis=dict(title="3-Year EBITDA ($M)", tickprefix="$", ticksuffix="M",
                   gridcolor="rgba(30,58,92,0.5)"),
        xaxis=dict(title="Scenario bracket"),
        legend=dict(orientation="h", y=-0.22, x=0),
    ))
    st.plotly_chart(_fig_mc, use_container_width=True)

    # Percentile table ---------------------------------------------------------
    _tbl_pcts = [5, 25, 50, 75, 95]
    _tbl_labels = {5:"Tail risk", 25:"Pessimistic", 50:"Median", 75:"Optimistic", 95:"Upside"}
    _tbl_rows = []
    for _p in _tbl_pcts:
        _tbl_rows.append({
            "":              f"p{_p}  —  {_tbl_labels[_p]}",
            "3-Yr EBITDA":   f"${np.percentile(_mc_ebitda,  _p)/1e6:.2f}M",
            "EBITDA / Yr":   f"${np.percentile(_mc_ebitda,  _p)/3/1e3:.0f}K",
            "SWB / Visit":   f"${np.percentile(_mc_swb,     _p):.2f}",
            "Visit Capture": f"{np.percentile(_mc_capture,  _p):.1f}%",
            "Green Months":  f"{np.percentile(_mc_green,    _p):.0f} / 36",
            "Burnout Cost":  f"${np.percentile(_mc_burnout, _p)/1e3:.0f}K",
        })

    def _mc_row_style(row):
        if "Median" in str(row[""]):
            return ["background-color:#ECFDF5; font-weight:600; color:#0A6B4A"] * len(row)
        return [""] * len(row)

    st.dataframe(
        pd.DataFrame(_tbl_rows).style.apply(_mc_row_style, axis=1),
        use_container_width=True, hide_index=True, height=215,
    )
    st.caption(
        f"Policy held fixed at Base {best.base_fte:.1f} FTE · Winter {best.winter_fte:.1f} FTE · "
        f"WLT {cfg.load_winter_target:.0f} pts/APC.  "
        f"Deterministic base case: EBITDA ${_base_e:.2f}M · "
        f"SWB ${s['annual_swb_per_visit']:.2f}/visit · "
        f"Capture {es['capture_rate']*100:.1f}%."
    )




# ── TAB 2: 36-Month Load ──────────────────────────────────────────────────────
with tabs[2]:
    pol=active_policy(); mos=pol.months; lbls=[mlabel(mo) for mo in mos]
    st.markdown("## 36-MONTH APC LOAD & FTE TRAJECTORY")

    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=0.08,row_heights=[0.55,0.45])

    for i,mo in enumerate(mos):
        zc={"Green":"rgba(10,117,84,0.07)","Yellow":"rgba(154,100,0,0.10)","Red":"rgba(185,28,28,0.12)"}[mo.zone]
        fig.add_vrect(x0=i-0.5,x1=i+0.5,fillcolor=zc,layer="below",line_width=0,row=1,col=1)

    if cfg.use_load_band:
        fig.add_hrect(y0=cfg.load_band_lo,y1=cfg.load_band_hi,
                      fillcolor="rgba(10,117,84,0.05)",line_width=0,row=1,col=1)
        fig.add_hline(y=cfg.load_band_lo,line_dash="dot",line_color=C_GREEN,line_width=1,
                      annotation_text=f"Band floor {cfg.load_band_lo:.0f}",annotation_position="right",
                      annotation_font=dict(size=8,color=C_GREEN),row=1,col=1)
        fig.add_hline(y=cfg.load_band_hi,line_dash="dot",line_color=C_GREEN,line_width=1,
                      annotation_text=f"Band ceiling {cfg.load_band_hi:.0f}",annotation_position="right",
                      annotation_font=dict(size=8,color=C_GREEN),row=1,col=1)

    fig.add_scatter(x=lbls,y=[mo.patients_per_provider_per_shift for mo in mos],
                    mode="lines+markers",name="Pts/APC/Shift",
                    line=dict(color=NAVY,width=2.5),
                    marker=dict(color=[ZONE_COLORS[mo.zone] for mo in mos],size=7,line=dict(color="white",width=1.5)),
                    row=1,col=1)
    for yv,lbl,col in [(budget,"Green ceiling",C_GREEN),(budget+cfg.yellow_threshold_above if cfg.yellow_threshold_above>0 else budget+0.01,"Yellow",C_YELLOW),(budget+cfg.red_threshold_above,"Red",C_RED)]:
        fig.add_hline(y=yv,line_dash="dot",line_color=col,line_width=1.5,
                      annotation_text=lbl,annotation_position="right",annotation_font=dict(size=9,color=col),row=1,col=1)

    fig.add_scatter(x=lbls,y=[mo.paid_fte for mo in mos],name="Paid FTE",
                    mode="lines",line=dict(color=C_ACTUAL,width=2.5),row=2,col=1)
    fig.add_scatter(x=lbls,y=[mo.effective_fte for mo in mos],name="Effective FTE",
                    mode="lines",line=dict(color=C_ACTUAL,width=1.5,dash="dash"),opacity=0.5,row=2,col=1)
    fig.add_scatter(x=lbls,y=[mo.demand_fte_required for mo in mos],name="FTE Required",
                    mode="lines",line=dict(color=NAVY,width=2.5,dash="dot"),row=2,col=1)
    fig.add_bar(x=lbls,y=[mo.flex_fte for mo in mos],name="Flex FTE",
                marker_color="rgba(185,28,28,0.30)",row=2,col=1)

    for mode,col,lbl in [("shed_pause",C_YELLOW,"Q3 shed pause"),("shed_passive","#D97706","Passive shed")]:
        sx=[lbls[i] for i,mo in enumerate(mos) if mo.hiring_mode==mode]
        sy=[mos[i].paid_fte for i,mo in enumerate(mos) if mo.hiring_mode==mode]
        if sx:
            fig.add_scatter(x=sx,y=sy,mode="markers",name=lbl,
                            marker=dict(symbol="triangle-down",size=9,color=col,line=dict(color="white",width=1.5)),row=2,col=1)

    has_overload = any(mo.overload_attrition_delta > 0.001 for mo in mos)
    if has_overload:
        fig.add_scatter(x=lbls,y=[mo.paid_fte*mo.effective_attrition_rate for mo in mos],
                        name="Monthly attrition (overload-adj)",
                        mode="lines",line=dict(color=C_RED,width=1.5,dash="dot"),opacity=0.7,row=2,col=1)

    fig.update_layout(**mk_layout(height=640,xaxis2=dict(tickangle=-45),title="36-Month APC Load & FTE Trajectory"))
    fig.update_yaxes(title_text="Pts/APC/Shift",showgrid=True,gridcolor=RULE,row=1,col=1)
    fig.update_yaxes(title_text="FTE",showgrid=True,gridcolor=RULE,row=2,col=1)
    st.plotly_chart(fig,use_container_width=True)

    fz=go.Figure(go.Bar(x=lbls,y=[1]*len(mos),marker_color=[ZONE_COLORS[mo.zone] for mo in mos],showlegend=False,
                         hovertext=[f"{mlabel(mo)}: {mo.zone} {mo.patients_per_provider_per_shift:.1f}" for mo in mos]))
    fz.update_layout(height=44,margin=dict(t=0,b=0,l=0,r=0),paper_bgcolor="white",plot_bgcolor="white",
                     yaxis=dict(visible=False),xaxis=dict(visible=False))
    st.plotly_chart(fz,use_container_width=True)

    hmc={m:sum(1 for mo in mos if mo.hiring_mode==m) for m in ["growth","attrition_replace","winter_ramp","floor_protect","shed_pause","shed_passive","freeze_flu","none"]}
    hml={"growth":"Growth","attrition_replace":"Att.backfill","winter_ramp":"Winter ramp","floor_protect":"Floor protect","shed_pause":"Q3 shed","shed_passive":"Passive shed","freeze_flu":"Flu freeze","none":"No action"}
    st.caption("  |  ".join(f"{hml[k]}: {v} mo" for k,v in hmc.items() if v>0))


# ── TAB 3: Hire Calendar ──────────────────────────────────────────────────────
with tabs[3]:
    pol=active_policy()
    st.markdown("## HIRING DECISION CALENDAR")
    st.caption("Every hire event from the simulation with back-calculated posting deadline and independence date.")
    hevs=pol.hire_events
    if not hevs:
        st.info("No hire events in this policy.")
    else:
        _perm_hevs   = [h for h in hevs if h.mode != "per_diem"]
        _pd_hevs     = [h for h in hevs if h.mode == "per_diem"]
        total_hires   = sum(h.fte_hired for h in _perm_hevs)
        growth_hires  = sum(h.fte_hired for h in hevs if h.mode=="growth")
        winter_hires  = sum(h.fte_hired for h in hevs if h.mode=="winter_ramp")
        perdiem_hires = sum(h.fte_hired for h in _pd_hevs)
        hc1,hc2,hc3,hc4=st.columns(4)
        hc1.metric("Perm FTE Hired (36mo)",  f"{total_hires:.1f}")
        hc2.metric("Growth Hires",           f"{growth_hires:.1f}")
        hc3.metric("Winter Ramp Hires",      f"{winter_hires:.1f}")
        hc4.metric("Per-Diem / Extra Shifts",f"{perdiem_hires:.1f} FTE-eq")

        mode_c={"growth":NAVY,"attrition_replace":NAVY_MID,"winter_ramp":C_GREEN,"floor_protect":C_YELLOW,"per_diem":"#9CA3AF"}
        fhc=go.Figure()
        for h in hevs:
            lbl=f"Y{h.year}-{MONTH_NAMES[h.calendar_month-1]}"
            post_l=f"Y{h.post_by_year}-{MONTH_NAMES[h.post_by_month-1]}"
            indep_l=f"Y{h.independent_year}-{MONTH_NAMES[h.independent_month-1]}"
            col=mode_c.get(h.mode,SLATE)
            _mode_label = ("Per-Diem / Extra Shifts" if h.mode=="per_diem"
                          else h.mode.replace("_"," ").title())
            _bar_text   = (f" {h.fte_hired:.2f} FTE-eq  [Per-Diem]  {lbl}"
                          if h.mode=="per_diem"
                          else f" {h.fte_hired:.2f} FTE [{h.mode}]  post by {post_l} -> indep {indep_l}")
            _bar_pattern = "x" if h.mode=="per_diem" else ""
            fhc.add_bar(x=[h.fte_hired],y=[lbl],orientation="h",base=[0],name=_mode_label,
                        marker_color=col,marker_pattern_shape=_bar_pattern,
                        showlegend=False,
                        text=_bar_text,
                        textposition="inside",textfont=dict(color="white",size=10),
                        hovertemplate=(f"<b>{lbl}</b><br>{_mode_label}<br>FTE-equiv: {h.fte_hired:.2f}<br>Cover with extra shifts / per-diem agreements<extra></extra>"
                                      if h.mode=="per_diem" else
                                      f"<b>{lbl}</b><br>FTE: {h.fte_hired:.2f}<br>Mode: {h.mode}<br>Post by: {post_l}<br>Independent: {indep_l}<extra></extra>"))
        fhc.update_layout(**mk_layout(height=max(280,len(hevs)*28+60),barmode="stack",title="Hire Events",
                           xaxis=dict(title="FTE Hired"),yaxis=dict(autorange="reversed",tickfont=dict(size=10)),
                           margin=dict(t=52,b=60,l=110,r=48)))
        st.plotly_chart(fhc,use_container_width=True)

        df_hc=pd.DataFrame([{
            "Hire Month": f"Y{h.year}-{MONTH_NAMES[h.calendar_month-1]}",
            "FTE": round(h.fte_hired,2),
            "Type": ("Per-Diem / Extra Shifts" if h.mode=="per_diem"
                     else h.mode.replace("_"," ").title()),
            "Post Req By": f"Y{h.post_by_year}-{MONTH_NAMES[h.post_by_month-1]}",
            "Independent By": f"Y{h.independent_year}-{MONTH_NAMES[h.independent_month-1]}",
        } for h in hevs])
        st.dataframe(df_hc,use_container_width=True,hide_index=True,height=380)
        st.download_button("Download Hire Calendar CSV",df_hc.to_csv(index=False),"psm_hire_calendar.csv","text/csv")


# ── TAB 4: Shift Coverage ─────────────────────────────────────────────────────
with tabs[4]:
    pol=active_policy(); mos=pol.months; lbls=[mlabel(mo) for mo in mos]
    st.markdown("## SHIFT COVERAGE MODEL")
    e1,e2,e3=st.columns(3)
    e1.metric("Shifts/Week per APC", f"{cfg.fte_shifts_per_week:.1f}",
              help="APC contract shifts — coverage denominator (FTE fraction affects cost only)")
    e2.metric("FTE per Concurrent Slot", f"{cfg.fte_per_shift_slot:.2f}",
              help=f"{cfg.operating_days_per_week} days ÷ {cfg.fte_shifts_per_week} shifts/APC = {cfg.fte_per_shift_slot:.2f} FTE to keep one slot filled every day")
    e3.metric("Baseline FTE Needed",f"{(base_visits/budget)*cfg.fte_per_shift_slot:.2f}",
              help="visits/day ÷ pts-per-APC × FTE-per-slot — minimum to staff the floor at base volume")

    # Shift scheduling interpreter — translates fractional APC need into practical shift language
    _shift_h = cfg.shift_hours
    _peak_apcs = max((mo.demand_providers_per_shift for mo in mos), default=0)
    _full_shifts = int(_peak_apcs)
    _partial_hrs = round((_peak_apcs - _full_shifts) * _shift_h)
    if _partial_hrs > 0:
        _shift_desc = f"{_full_shifts} full {_shift_h:.0f}h shift{'s' if _full_shifts != 1 else ''} + one {_partial_hrs}h shift"
    else:
        _shift_desc = f"{_full_shifts} full {_shift_h:.0f}h shift{'s' if _full_shifts != 1 else ''}"
    st.info(
        f"**Peak concurrent need: {_peak_apcs:.2f} APCs on floor** — "
        f"operationally this is **{_shift_desc}** per day at peak volume "
        f"({_shift_h:.0f}h shift length).",
        icon="🕐"
    )

    prov_needed=[mo.demand_providers_per_shift for mo in mos]
    prov_on_floor=[mo.providers_on_floor for mo in mos]
    flex_prov=[mo.flex_fte/cfg.fte_per_shift_slot if cfg.fte_per_shift_slot else 0 for mo in mos]
    gap=[mo.shift_coverage_gap for mo in mos]

    fc=go.Figure()
    fc.add_scatter(x=lbls,y=prov_needed,name="APCs Needed",mode="lines",line=dict(color=NAVY,width=2.5,dash="dot"))
    fc.add_scatter(x=lbls,y=prov_on_floor,name="APCs on Floor",mode="lines+markers",
                   line=dict(color=C_ACTUAL,width=2.5),marker=dict(size=7,color=C_ACTUAL,line=dict(color="white",width=1.5)))
    fc.add_bar(x=lbls,y=flex_prov,name="Flex APCs",marker_color="rgba(185,28,28,0.28)")
    fc.update_layout(**mk_layout(height=340,barmode="overlay",xaxis=dict(tickangle=-45),title="Concurrent APCs: Required vs On Floor"))
    fc.update_yaxes(title_text="Concurrent APCs")
    st.plotly_chart(fc,use_container_width=True)

    gap_colors=[C_RED if g>0.05 else(C_YELLOW if g>-0.05 else C_GREEN) for g in gap]
    fg=go.Figure(go.Bar(x=lbls,y=gap,marker_color=gap_colors,hovertext=[f"{mlabel(mo)}: {g:+.2f}" for mo,g in zip(mos,gap)]))
    fg.add_hline(y=0,line_color=SLATE,line_width=1)
    fg.update_layout(**mk_layout(height=220,xaxis=dict(tickangle=-45),title="Coverage Gap ( + = understaffed  |  - = overstaffed )"))
    fg.update_yaxes(title_text="APCs")
    st.plotly_chart(fg,use_container_width=True)

    df_sh=pd.DataFrame([{"Month":mlabel(mo),"Q":f"Q{mo.quarter}","Visits/Day":round(mo.demand_visits_per_day,1),
        "APCs Needed":round(mo.demand_providers_per_shift,2),"FTE Required":round(mo.demand_fte_required,2),
        "Paid FTE":round(mo.paid_fte,2),"APCs on Floor":round(mo.providers_on_floor,2),
        "Coverage Gap":round(mo.shift_coverage_gap,2),"Hiring Mode":mo.hiring_mode,"Zone":mo.zone} for mo in mos])
    def _sz(v): return {"Green":"background-color:#ECFDF5","Yellow":"background-color:#FFFBEB","Red":"background-color:#FEF2F2"}.get(v,"")
    def _sg(v):
        try:
            f=float(v)
            if f>0.1:  return f"color:{C_RED};font-weight:600"
            if f<-0.1: return f"color:{C_GREEN}"
        except: pass
        return ""
    st.dataframe(df_sh.style.applymap(_sz,subset=["Zone"]).applymap(_sg,subset=["Coverage Gap"]),use_container_width=True,height=440)
    st.download_button("Download CSV",df_sh.to_csv(index=False),"psm_shift.csv","text/csv")


# ── TAB 5: Seasonality ────────────────────────────────────────────────────────
with tabs[5]:
    pol=active_policy(); mos=pol.months
    st.markdown("## MONTHLY VOLUME DISTRIBUTION")
    mcols = st.columns(6)
    for mi, (mn, im) in enumerate(zip(MONTH_NAMES, _mo_vals)):
        with mcols[mi % 6]:
            vm = base_visits * (1 + im) * peak_factor
            fm = (vm / budget) * cfg.fte_per_shift_slot
            st.metric(mn, f"{chr(43) if im>=0 else chr(45)}{im*100:.0f}%",
                      delta=f"{vm:.0f} vpd · {fm:.1f} FTE")

    st.plotly_chart(render_hero_chart(pol,cfg,quarterly_impacts,base_visits,budget,peak_factor,
                                      title="Annual Demand Curve - Year 1",monthly_impacts=_mo_vals),
                    use_container_width=True)

    st.markdown("## MONTHLY SUMMARY  (36-Month Avg)")
    mr=[]
    for mi, mn in enumerate(MONTH_NAMES):
        mm=[mo for mo in mos if mo.calendar_month == mi+1]
        if mm:
            mr.append({"Month": mn,
                       "Adjustment": f"{chr(43) if _mo_vals[mi]>=0 else chr(45)}{_mo_vals[mi]*100:.0f}%",
                       "Avg Visits/Day": f"{np.mean([mo.demand_visits_per_day for mo in mm]):.1f}",
                       "Avg Paid FTE":   f"{np.mean([mo.paid_fte for mo in mm]):.2f}",
                       "Avg Pts/APC":    f"{np.mean([mo.patients_per_provider_per_shift for mo in mm]):.1f}",
                       "Red Months":     sum(1 for mo in mm if mo.zone=="Red"),
                       "In-Band %":      f"{sum(1 for mo in mm if mo.within_band)/len(mm)*100:.0f}%"})
    st.dataframe(pd.DataFrame(mr), use_container_width=True, hide_index=True)

    st.markdown("## ATTRITION TRAJECTORY  (overload-amplified)")
    fa=go.Figure()
    fa.add_scatter(x=[mlabel(mo) for mo in mos],y=[mo.effective_attrition_rate*100 for mo in mos],
                   name="Effective attrition %/mo",mode="lines+markers",line=dict(color=C_RED,width=2.5),
                   marker=dict(color=[ZONE_COLORS[mo.zone] for mo in mos],size=8,line=dict(color="white",width=1.5)))
    fa.add_hline(y=cfg.monthly_attrition_rate*100,line_dash="dash",line_color=SLATE,line_width=1.5,
                 annotation_text=f"Base {cfg.monthly_attrition_rate*100:.2f}%/mo",
                 annotation_position="right",annotation_font=dict(size=9,color=SLATE))
    fa.update_layout(**mk_layout(height=280,xaxis=dict(tickangle=-45),title="Monthly Attrition Rate (rises with overwork)"))
    fa.update_yaxes(title_text="Attrition Rate (%/mo)")
    st.plotly_chart(fa,use_container_width=True)

    fs=go.Figure()
    for i,mo in enumerate(mos):
        if mo.quarter==3: fs.add_vrect(x0=i-0.5,x1=i+0.5,fillcolor="rgba(154,100,0,0.06)",layer="below",line_width=0)
    fs.add_scatter(x=[mlabel(mo) for mo in mos],y=[mo.paid_fte for mo in mos],
                   mode="lines+markers",name="Paid FTE",line=dict(color=C_ACTUAL,width=3),
                   marker=dict(color=[HIRE_COLORS.get(mo.hiring_mode,SLATE) for mo in mos],size=9,line=dict(color="white",width=2)))
    for yv,lbl,col in [(best.winter_fte,f"Winter {best.winter_fte:.1f}",NAVY),
                       (best.base_fte,f"Base {best.base_fte:.1f}",SLATE),
                       (best.base_fte*cfg.summer_shed_floor_pct,f"Summer floor {best.base_fte*cfg.summer_shed_floor_pct:.1f}",C_GREEN)]:
        fs.add_hline(y=yv,line_dash="dot",line_color=col,line_width=1.5,
                     annotation_text=lbl,annotation_position="right",annotation_font=dict(size=9,color=col))
    fs.update_layout(**mk_layout(height=300,xaxis=dict(tickangle=-45),title="Paid FTE Trajectory (shaded = summer shed)"))
    fs.update_yaxes(title_text="Paid FTE")
    st.plotly_chart(fs,use_container_width=True)


# ── TAB 6: Cost Breakdown ─────────────────────────────────────────────────────
with tabs[6]:
    pol=active_policy(); s2=pol.summary; mos=pol.months
    st.markdown("## 3-YEAR COST BREAKDOWN")

    # ── EBITDA waterfall ────────────────────────────────────────────────
    _es2 = pol.ebitda_summary
    _elabel2 = "EBITDA Contribution" if cfg.monthly_fixed_overhead == 0 else "EBITDA"
    wf_labels = ["Revenue Captured","SWB Cost","Flex Premium","Turnover Cost","Burnout Risk"]
    wf_raw    = [_es2["revenue"], _es2["swb"], _es2["flex"], _es2["turnover"], _es2["burnout"]]
    if cfg.monthly_fixed_overhead > 0:
        wf_labels.append("Fixed Overhead"); wf_raw.append(_es2["fixed"])
    wf_labels.append(_elabel2); wf_raw.append(_es2["ebitda"])
    wf_vals   = [v if i==0 or i==len(wf_raw)-1 else -v for i,v in enumerate(wf_raw)]
    wf_colors = ["#22C55E" if i==0 else ("#1A6FD4" if i==len(wf_vals)-1 else "#EF4444") for i in range(len(wf_vals))]
    fw = go.Figure(go.Bar(x=[v/1e6 for v in wf_vals], y=wf_labels, orientation="h",
                         marker_color=wf_colors,
                         text=[f"${abs(v)/1e6:.2f}M" for v in wf_vals], textposition="outside"))
    fw.update_layout(**mk_layout(height=320, title=f"3-Year {_elabel2} Waterfall"))
    fw.update_xaxes(title_text="$ Millions")
    st.plotly_chart(fw, use_container_width=True)

    # ── Monthly EBITDA trajectory ────────────────────────────────────────
    _me_x   = [f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1][:3]}" for mo in pol.months]
    _me_bar = [mo.ebitda_contribution/1e3 for mo in pol.months]
    _me_cum = [mo.cumulative_ebitda/1e3   for mo in pol.months]
    _vc_pct = [mo.throughput_factor*100   for mo in pol.months]
    fig_me  = go.Figure()
    fig_me.add_bar(x=_me_x, y=_me_bar,
                   marker_color=[C_GREEN if v>=0 else C_RED for v in _me_bar],
                   name="Monthly EBITDA ($K)", opacity=0.75)
    fig_me.add_scatter(x=_me_x, y=_me_cum, mode="lines",
                       line=dict(color=C_ACTUAL, width=2.5), name="Cumulative ($K)")
    fig_me.update_layout(**mk_layout(height=280, title="Monthly EBITDA & Cumulative Trajectory"))
    fig_me.update_yaxes(title_text="$K")
    st.plotly_chart(fig_me, use_container_width=True)

    # ── Visit capture rate ───────────────────────────────────────────────
    fig_vc = go.Figure(go.Bar(x=_me_x, y=_vc_pct,
        marker_color=[C_GREEN if v==100 else (C_YELLOW if v==95 else C_RED) for v in _vc_pct],
        name="Visit Capture %"))
    fig_vc.add_hline(y=100, line_dash="dash", line_color=SLATE, line_width=1)
    fig_vc.update_layout(**mk_layout(height=200,
        title="Monthly Visit Capture Rate — 100% Green | 95% Yellow | 85% Red"))
    fig_vc.update_yaxes(range=[80, 102])
    st.plotly_chart(fig_vc, use_container_width=True)

    st.divider()
    lc=["Permanent","Flex","Support Staff","Turnover","Lost Revenue","Burnout","Overstaff"]
    vc=[s2["total_permanent_cost"],s2["total_flex_cost"],s2["total_support_cost"],
        s2["total_turnover_cost"],s2["total_lost_revenue"],s2["total_burnout_penalty"],s2["total_overstaff_penalty"]]
    pal=[NAVY,NAVY_MID,"#4B8BBE",C_YELLOW,C_RED,"#7F1D1D",C_GREEN]
    _av=s2["annual_visits"]
    _sp=(s2["total_permanent_cost"]+s2["total_flex_cost"])/3
    _ss=s2["total_support_cost"]/3
    _spv=_sp/_av if _av else 0; _ssv=_ss/_av if _av else 0
    st.markdown(f"<div style='background:#FDFAED;border-left:3px solid #7A6200;padding:0.7rem 1rem;"
                f"border-radius:0 3px 3px 0;margin-bottom:1rem;font-size:0.82rem;'>"
                f"<b>SWB/Visit:</b> APC ${_spv:.2f} + Support ${_ssv:.2f} = <b>${s2['annual_swb_per_visit']:.2f}</b>  |  Target ${cfg.swb_target_per_visit:.2f}</div>",
                unsafe_allow_html=True)

    cl,cr=st.columns([1.1,0.9])
    with cl:
        fp2=go.Figure(go.Pie(labels=lc,values=vc,marker_colors=pal,hole=0.54,textinfo="label+percent",
                             textfont=dict(size=11)))
        fp2.add_annotation(text=f"<b>${sum(vc)/1e6:.1f}M</b><br><span style='font-size:11px'>3-year</span>",
                           x=0.5,y=0.5,showarrow=False,font=dict(family="'EB Garamond', Georgia, serif",size=17,color=INK))
        fp2.update_layout(**mk_layout(height=380,title="3-Year Cost Mix",margin=dict(t=40,b=40,l=16,r=16),
                           legend=dict(orientation="v",x=1.02,y=0.5)))
        st.plotly_chart(fp2,use_container_width=True)
    with cr:
        dfc=pd.DataFrame({"Component":lc,"3-Year ($)":[f"${v:,.0f}" for v in vc],
                           "Annual Avg":[f"${v/3:,.0f}" for v in vc],"$/Visit":[f"${v/3/(_av or 1):.2f}" for v in vc]})
        st.dataframe(dfc,use_container_width=True,hide_index=True)
        r1,r2,r3=st.columns(3)
        r1.metric("Total 3-Year",f"${sum(vc)/1e6:.2f}M"); r2.metric("Annual Avg",f"${sum(vc)/3/1e6:.2f}M"); r3.metric("SWB/Visit",f"${s2['annual_swb_per_visit']:.2f}")

    dfms=pd.DataFrame([{"Month":mlabel(mo),"Permanent":mo.permanent_cost,"Flex":mo.flex_cost,
                         "Support":mo.support_cost,"Turnover":mo.turnover_cost,"Lost Revenue":mo.lost_revenue,"Burnout":mo.burnout_penalty} for mo in mos])
    fst=go.Figure()
    for col_,color in zip(["Permanent","Flex","Support","Turnover","Lost Revenue","Burnout"],[NAVY,NAVY_MID,"#4B8BBE",C_YELLOW,C_RED,"#7F1D1D"]):
        fst.add_bar(x=dfms["Month"],y=dfms[col_],name=col_,marker_color=color)
    fst.update_layout(**mk_layout(height=340,barmode="stack",xaxis=dict(tickangle=-45),title="Monthly Cost Stack"))
    fst.update_yaxes(title_text="Cost ($)")
    st.plotly_chart(fst,use_container_width=True)


# ── TAB 7: Marginal APC Analysis ─────────────────────────────────────────────
with tabs[7]:
    st.markdown("## MARGINAL APC ANALYSIS")
    st.caption("Slide left to model reducing FTE, right to model adding FTE — see the cost, savings, and load impact.")
    pol = active_policy()

    # Bidirectional slider: −1.0 to +1.0 in 0.25 increments, default 0.50
    ma_delta = st.select_slider(
        "FTE change to analyze",
        options=[-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0],
        value=0.5,
        key="ma_delta_slider",
        format_func=lambda x: f"{x:+.2f} FTE"
    )

    with st.spinner("Computing marginal impact..."):
        ma = compare_marginal_fte(pol, cfg, delta_fte=ma_delta)

    # Direction-aware labels
    _adding     = ma_delta > 0
    _delta_lbl  = f"{ma_delta:+.2f} FTE"
    _new_fte    = pol.base_fte + ma_delta
    _nc         = ma["net_annual"]
    _cost_lbl   = "Added Cost" if _adding else "Cost Saved"
    _sav_lbl    = "Savings Unlocked" if _adding else "Savings Lost"
    _net_lbl    = "Net Annual Benefit" if _nc > 0 else "Net Annual Cost"
    _pay_lbl    = "Never" if ma["payback_months"] == float("inf") else f"{ma['payback_months']:.0f} mo"
    _zones_lbl  = (f"{ma['red_months_saved']}R + {ma['yellow_months_saved']}Y saved"
                   if _adding else
                   f"{-ma['red_months_saved']}R + {-ma['yellow_months_saved']}Y added")

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric(f"{_delta_lbl} {_cost_lbl}", f"${abs(ma['annual_cost_delta']):,.0f}")
    mc2.metric(_sav_lbl,                    f"${abs(ma['annual_savings']):,.0f}")
    mc3.metric(_net_lbl,                    f"${abs(_nc):,.0f}",
               delta=("positive" if _nc > 0 else "negative"),
               delta_color="normal" if _nc > 0 else "inverse")
    mc4.metric("Payback" if _adding else "—", _pay_lbl if _adding else "—")
    mc5.metric("Zone Months",               _zones_lbl)

    # Verdict banner
    if _adding:
        if _nc > 0:
            st.success(f"✓ Adding {ma_delta:+.2f} FTE is **net positive** — ${_nc:,.0f}/yr benefit. "
                       f"Saves {ma['red_months_saved']}R + {ma['yellow_months_saved']}Y zone-months. "
                       f"Payback {_pay_lbl}.")
        elif ma["red_months_saved"] > 0:
            st.warning(f"Costs ${-_nc:,.0f}/yr net but eliminates {ma['red_months_saved']} Red months of burnout risk.")
        else:
            st.info(f"Adding {ma_delta:+.2f} FTE costs ${ma['annual_cost_delta']:,.0f}/yr with no material zone improvement.")
    else:
        if _nc < 0:
            st.error(f"⚠ Removing {abs(ma_delta):.2f} FTE saves ${ma['annual_cost_delta']:,.0f}/yr in wages "
                     f"but adds {-ma['red_months_saved']}R + {-ma['yellow_months_saved']}Y risk months "
                     f"— net **${abs(_nc):,.0f}/yr worse**.")
        else:
            st.success(f"✓ Reducing {abs(ma_delta):.2f} FTE saves ${abs(ma['annual_cost_delta']):,.0f}/yr "
                       f"with minimal zone impact — net **${_nc:,.0f}/yr benefit**.")

    m_labels_12 = [MONTH_NAMES[i] for i in range(12)]
    _line_clr   = C_GREEN if _adding else C_RED
    _line_lbl   = f"{_delta_lbl} → {_new_fte:.2f} FTE"
    fma = go.Figure()
    if cfg.use_load_band:
        fma.add_hrect(y0=cfg.load_band_lo, y1=cfg.load_band_hi,
                      fillcolor="rgba(10,117,84,0.06)", line_width=0)
    fma.add_scatter(x=m_labels_12, y=ma["yr1_load_base"],
                    name=f"Current ({pol.base_fte:.2f} FTE)",
                    mode="lines+markers", line=dict(color=NAVY, width=2.5),
                    marker=dict(size=8, line=dict(color="white", width=1.5)))
    fma.add_scatter(x=m_labels_12, y=ma["yr1_load_plus"],
                    name=_line_lbl,
                    mode="lines+markers",
                    line=dict(color=_line_clr, width=2.5, dash="dash"),
                    marker=dict(size=8, line=dict(color="white", width=1.5)))
    for yv, lbl, col in [
        (budget, "Green ceiling", C_GREEN),
        (budget + (cfg.yellow_threshold_above if cfg.yellow_threshold_above > 0 else 0.01), "Yellow", C_YELLOW),
        (budget + cfg.red_threshold_above, "Red", C_RED)
    ]:
        fma.add_hline(y=yv, line_dash="dot", line_color=col, line_width=1.5,
                      annotation_text=lbl, annotation_position="right",
                      annotation_font=dict(size=9, color=col))
    fma.update_layout(**mk_layout(height=340,
                                   title=f"Year 1 Load: Current vs {_delta_lbl}"))
    fma.update_yaxes(title_text="Pts/APC/Shift")
    st.plotly_chart(fma, use_container_width=True)

    st.markdown("## FULL RANGE TABLE")
    rows = []
    for d in [-1.0, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 1.0]:
        m2 = compare_marginal_fte(pol, cfg, delta_fte=d)
        rows.append({
            "FTE Change":    f"{d:+.2f}",
            "Cost Impact":   f"${m2['annual_cost_delta']:+,.0f}",
            "Savings":       f"${m2['annual_savings']:,.0f}",
            "Net Annual":    f"${m2['net_annual']:+,.0f}",
            "Payback":       "Never" if m2["payback_months"] == float("inf") else f"{m2['payback_months']:.0f} mo",
            "Red Δ":         f"{-m2['red_months_saved']:+d}",
            "Yellow Δ":      f"{-m2['yellow_months_saved']:+d}",
            "SWB/Visit Δ":   f"${m2['swb_delta']:+.2f}",
        })
    def _cn(v):
        try:
            val = float(str(v).replace("$","").replace(",","").replace("+","").replace(" mo",""))
            return f"color:{C_GREEN};font-weight:600" if val > 0 else (f"color:{C_RED}" if val < 0 else "")
        except: return ""
    st.dataframe(
        pd.DataFrame(rows).style.applymap(_cn, subset=["Net Annual"]),
        use_container_width=True, hide_index=True
    )


# ── TAB 8: Stress Test ────────────────────────────────────────────────────────
with tabs[8]:
    st.markdown("## STRESS TEST — VOLUME SHOCK SCENARIOS")
    st.caption("Apply a volume surge and see how the current policy holds.")
    pol=active_policy()
    sc1,sc2,sc3=st.columns(3)
    with sc1: shock_start=st.number_input("Shock start (simulation month)",1,34,13)
    with sc2: shock_dur=st.number_input("Duration (months)",1,12,3)
    with sc3: shock_mag=st.slider("Surge magnitude",0.05,0.50,0.15,0.05)

    shock_end=min(36,int(shock_start)+int(shock_dur)-1)
    _slabels=[]
    for sm in range(int(shock_start),shock_end+1):
        cm=((sm-1)%12)+1; yr=((sm-1)//12)+1
        _slabels.append(f"Y{yr}-{MONTH_NAMES[cm-1]}")
    st.info(f"Shock window: **{_slabels[0]}** to **{_slabels[-1]}**  (+{shock_mag*100:.0f}% volume for {shock_dur} months)")

    with st.spinner("Running stress simulation..."):
        pol_stress=simulate_stress(pol,cfg,int(shock_start),int(shock_dur),shock_mag)

    ss=pol_stress.summary; ss0=pol.summary
    st1,st2,st3,st4,st5=st.columns(5)
    st1.metric("Red Months (base)",   f"{ss0['red_months']}",delta=f"+{ss['red_months']-ss0['red_months']} shock",delta_color="inverse")
    st2.metric("Yellow Months",       f"{ss0['yellow_months']}",delta=f"+{ss['yellow_months']-ss0['yellow_months']} shock",delta_color="inverse")
    st3.metric("SWB/Visit",           f"${ss0['annual_swb_per_visit']:.2f}",delta=f"+${ss['annual_swb_per_visit']-ss0['annual_swb_per_visit']:.2f}",delta_color="inverse")
    st4.metric("3-Yr EBITDA",         f"${ss0.get('total_ebitda_3yr',0)/1e6:.2f}M",delta=f"${(ss.get('total_ebitda_3yr',0)-ss0.get('total_ebitda_3yr',0))/1e6:+.2f}M")
    st5.metric("Extra Turnover",      f"{ss['total_turnover_events']-ss0['total_turnover_events']:.1f} FTE")

    if ss["red_months"]>ss0["red_months"]:
        st.error(f"Policy breaks — {ss['red_months']-ss0['red_months']} new Red months under this shock.")
    elif ss["yellow_months"]>ss0["yellow_months"]:
        st.warning(f"Policy shows strain — {ss['yellow_months']-ss0['yellow_months']} new Yellow months. Flex staffing would help.")
    else:
        st.success("Policy holds under this shock — all months remain in current zones.")

    lbls_36=[mlabel(mo) for mo in pol.months]
    fs2=go.Figure()
    fs2.add_vrect(x0=shock_start-1.5,x1=shock_end-0.5,fillcolor="rgba(124,58,237,0.08)",layer="below",line_width=0)
    fs2.add_scatter(x=lbls_36,y=[mo.patients_per_provider_per_shift for mo in pol.months],
                    name="Base scenario",line=dict(color=NAVY,width=2.5))
    fs2.add_scatter(x=lbls_36,y=[mo.patients_per_provider_per_shift for mo in pol_stress.months],
                    name=f"Stress (+{shock_mag*100:.0f}%)",line=dict(color=C_STRESS,width=2.5,dash="dash"))
    for yv,lbl,col in [(budget,"Green ceiling",C_GREEN),(budget+cfg.yellow_threshold_above if cfg.yellow_threshold_above>0 else budget+0.01,"Yellow",C_YELLOW),(budget+cfg.red_threshold_above,"Red",C_RED)]:
        fs2.add_hline(y=yv,line_dash="dot",line_color=col,line_width=1.5,annotation_text=lbl,annotation_position="right",annotation_font=dict(size=9,color=col))
    fs2.update_layout(**mk_layout(height=360,xaxis=dict(tickangle=-45),title=f"Load: Base vs Stress (+{shock_mag*100:.0f}% volume)"))
    fs2.update_yaxes(title_text="Pts/APC/Shift")
    st.plotly_chart(fs2,use_container_width=True)

    fs3=go.Figure()
    fs3.add_vrect(x0=shock_start-1.5,x1=shock_end-0.5,fillcolor="rgba(124,58,237,0.08)",layer="below",line_width=0)
    fs3.add_scatter(x=lbls_36,y=[mo.paid_fte for mo in pol.months],name="Base Paid FTE",line=dict(color=NAVY,width=2.5))
    fs3.add_scatter(x=lbls_36,y=[mo.paid_fte for mo in pol_stress.months],name="Stress Paid FTE",line=dict(color=C_STRESS,width=2.5,dash="dash"))
    fs3.add_scatter(x=lbls_36,y=[mo.demand_fte_required for mo in pol_stress.months],name="FTE Required (stress)",line=dict(color=C_RED,width=1.5,dash="dot"),opacity=0.7)
    fs3.update_layout(**mk_layout(height=260,xaxis=dict(tickangle=-45),title="FTE Trajectory Under Stress"))
    fs3.update_yaxes(title_text="FTE")
    st.plotly_chart(fs3,use_container_width=True)

    df_stress=pd.DataFrame([{
        "Month":mlabel(mo),
        "Base Load":round(pol.months[i].patients_per_provider_per_shift,1),
        "Stress Load":round(mo.patients_per_provider_per_shift,1),
        "Delta":round(mo.patients_per_provider_per_shift-pol.months[i].patients_per_provider_per_shift,1),
        "Base Zone":pol.months[i].zone,"Stress Zone":mo.zone,
        "Zone Changed":"YES" if mo.zone!=pol.months[i].zone else "",
    } for i,mo in enumerate(pol_stress.months)])
    def _zc(v): return f"color:{C_RED};font-weight:600" if "YES" in str(v) else ""
    st.dataframe(df_stress.style.applymap(_sz,subset=["Stress Zone"]).applymap(_zc,subset=["Zone Changed"]),
                 use_container_width=True,height=380)


# ── TAB 9: Policy Heatmap ─────────────────────────────────────────────────────
with tabs[9]:
    st.markdown("## POLICY SCORE HEATMAP")
    if st.session_state.all_policies:
        all_p=st.session_state.all_policies
        bv=sorted(set(round(p.base_fte,1) for p in all_p)); wv=sorted(set(round(p.winter_fte,1) for p in all_p))
        bi={v:i for i,v in enumerate(bv)}; wi={v:i for i,v in enumerate(wv)}
        mat=np.full((len(wv),len(bv)),np.nan)
        for p in all_p:
            b2=bi.get(round(p.base_fte,1)); w2=wi.get(round(p.winter_fte,1))
            if b2 is not None and w2 is not None: mat[w2][b2]=p.summary.get('total_ebitda_3yr', -p.total_score)
        vmin,vmax=np.nanmin(mat),np.nanpercentile(mat,95)
        fh=go.Figure(go.Heatmap(z=mat,x=[str(v) for v in bv],y=[str(v) for v in wv],
                                 colorscale=[[0,C_GREEN],[0.5,"#FFFBEB"],[1,C_RED]],zmin=vmin,zmax=vmax,
                                 colorbar=dict(title="Score ($)",tickfont=dict(size=10,color=SLATE))))
        fh.add_scatter(x=[str(round(best.base_fte,1))],y=[str(round(best.winter_fte,1))],mode="markers",
                       marker=dict(symbol="star",size=22,color="white",line=dict(color=INK,width=2)),name="Optimal")
        fh.update_layout(**mk_layout(height=500,title="Policy Score Landscape (lower = better) * = Optimal",
                          xaxis=dict(title="Base FTE"),yaxis=dict(title="Winter FTE",showgrid=False)))
        st.plotly_chart(fh,use_container_width=True)
    else:
        st.info("Run the optimizer to see the heatmap.")


# ── TAB 10: Req Timing ─────────────────────────────────────────────────────────
with tabs[10]:
    st.markdown("## REQUISITION TIMING")
    ld=cfg.days_to_sign+cfg.days_to_credential+cfg.days_to_independent; lm=int(np.ceil(ld/30))
    t1,t2,t3=st.columns(3)
    t1.metric("Flu Anchor",MONTH_NAMES[cfg.flu_anchor_month-1])
    t2.metric("Post Req By",MONTH_NAMES[best.req_post_month-1])
    t3.metric("Lead Time",f"{ld} days / {lm} months")
    st.markdown(f"| Phase | Days | Cumulative |\n|:--|--:|--:|\n| Sign offer | {cfg.days_to_sign} | {cfg.days_to_sign} |\n| Credential | {cfg.days_to_credential} | {cfg.days_to_sign+cfg.days_to_credential} |\n| Ramp to independence | {cfg.days_to_independent} | {ld} |")
    phases_tl=[("Post -> Sign",cfg.days_to_sign,NAVY),("Sign -> Credentialed",cfg.days_to_credential,NAVY_MID),("Credentialed -> Indep.",cfg.days_to_independent,C_GREEN)]
    ftl=go.Figure(); start=0
    for lbl_tl,dur,col in phases_tl:
        ftl.add_bar(x=[dur],y=[""],orientation="h",base=[start],name=lbl_tl,marker_color=col,
                    text=f"  {lbl_tl}  ({dur}d)",textposition="inside",textfont=dict(color="white",size=11)); start+=dur
    ftl.add_vline(x=ld,line_dash="dash",line_color=C_RED,line_width=2,
                  annotation_text=f"Independent: {MONTH_NAMES[cfg.flu_anchor_month-1]}",
                  annotation_font=dict(color=C_RED,size=11))
    ftl.update_layout(**mk_layout(height=150,barmode="stack",margin=dict(t=16,b=48,l=8,r=8),
        title=f"Hiring Timeline: Post {MONTH_NAMES[best.req_post_month-1]} -> Independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}",
        xaxis=dict(title="Days from Requisition"),yaxis=dict(visible=False),legend=dict(orientation="h",y=-0.65)))
    st.plotly_chart(ftl,use_container_width=True)
    st.info(f"Post req by **{MONTH_NAMES[best.req_post_month-1]}** to have {best.winter_fte:.1f} Winter FTE independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}.")


# ── TAB 11: Data Table ────────────────────────────────────────────────────────
with tabs[11]:
    pol=active_policy()
    st.markdown("## FULL 36-MONTH DATA")
    dff=pd.DataFrame([{
        "Month":mlabel(mo),"Q":f"Q{mo.quarter}","Zone":mo.zone,
        "Hiring Mode":mo.hiring_mode,"In Band":"Y" if mo.within_band else "N",
        "Visits/Day":round(mo.demand_visits_per_day,1),
        "FTE Required":round(mo.demand_fte_required,2),"Paid FTE":round(mo.paid_fte,2),
        "APCs on Floor":round(mo.providers_on_floor,2),
        "Pts/APC/Shift":round(mo.patients_per_provider_per_shift,1),
        "Attrition %/mo":f"{mo.effective_attrition_rate*100:.2f}%",
        "Overload Att":round(mo.overload_attrition_delta,3),
        "Perm Cost":f"${mo.permanent_cost:,.0f}","Support":f"${mo.support_cost:,.0f}",
        "Turnover":round(mo.turnover_events,2),"Burnout":f"${mo.burnout_penalty:,.0f}",
        "Lost Rev":f"${mo.lost_revenue:,.0f}",
    } for mo in pol.months])
    def _szz(v): return {"Green":"background-color:#ECFDF5","Yellow":"background-color:#FFFBEB","Red":"background-color:#FEF2F2"}.get(v,"")
    st.dataframe(dff.style.applymap(_szz,subset=["Zone"]),use_container_width=True,height=520)
    st.download_button("Download CSV",dff.to_csv(index=False),"psm_36month.csv","text/csv")





with tabs[12]:
    pol  = active_policy()
    mos  = pol.months
    es   = pol.ebitda_summary
    MA   = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    # ── Shared helpers ────────────────────────────────────────────────────────
    def _h2(txt):
        st.markdown(
            f"<div style='font-size:0.60rem;font-weight:700;text-transform:uppercase;"
            f"letter-spacing:0.16em;color:{MUTED};margin:1.6rem 0 0.5rem;border-bottom:"
            f"1px solid #E2E8F0;padding-bottom:0.35rem;'>{txt}</div>",
            unsafe_allow_html=True)

    def _eq(label, formula, result, note=""):
        note_html = f"<span style='color:{MUTED};font-size:0.72rem;margin-left:0.6rem;'>{note}</span>" if note else ""
        st.markdown(
            f"<div style='background:#F8FAFC;border-left:3px solid {NAVY};border-radius:3px;"
            f"padding:0.55rem 1rem;margin:0.3rem 0;font-size:0.82rem;'>"
            f"<span style='color:{MUTED};'>{label}</span>&nbsp;&nbsp;"
            f"<code style='background:#EEF2F7;padding:0.1rem 0.4rem;border-radius:2px;"
            f"font-size:0.79rem;'>{formula}</code>"
            f"&nbsp;&nbsp;=&nbsp;&nbsp;"
            f"<strong style='color:{NAVY};font-size:0.92rem;'>{result}</strong>"
            f"{note_html}</div>",
            unsafe_allow_html=True)

    def _check(label, expected, actual, fmt="$.0f", tol=0.02):
        match = abs(actual - expected) / max(abs(expected), 1) < tol
        icon  = "✅" if match else "⚠️"
        e_str = f"${expected:,.0f}" if "f" in fmt else f"{expected:.2f}"
        a_str = f"${actual:,.0f}"   if "f" in fmt else f"{actual:.2f}"
        color = "#0A6B4A" if match else "#B91C1C"
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:0.8rem;font-size:0.80rem;"
            f"padding:0.3rem 0;border-bottom:1px solid #F1F5F9;'>"
            f"<span style='width:1.2rem;'>{icon}</span>"
            f"<span style='flex:1;color:#4A5568;'>{label}</span>"
            f"<span style='color:{MUTED};'>expected <b>{e_str}</b></span>"
            f"<span style='color:{color};font-weight:600;'>actual {a_str}</span>"
            f"</div>",
            unsafe_allow_html=True)

    st.markdown("## MATH & LOGIC — MODEL AUDIT")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{MUTED};margin:-0.4rem 0 1.2rem;'>"
        f"Step-by-step derivation of every number in the staffing model recommendation. "
        f"All figures use the same inputs and formulas as the simulation — this tab "
        f"is a transparent re-computation, not a summary.</p>",
        unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — DEMAND DERIVATION
    # ══════════════════════════════════════════════════════════════════════════
    _h2("① Demand Derivation — Visits → APCs → FTE")

    _y1_jan  = next(mo for mo in mos if mo.year==1 and mo.calendar_month==1)
    _y1_apr  = next(mo for mo in mos if mo.year==1 and mo.calendar_month==4)
    _y1_jul  = next(mo for mo in mos if mo.year==1 and mo.calendar_month==7)

    st.markdown(
        f"<p style='font-size:0.80rem;color:#4A5568;margin-bottom:0.6rem;'>"
        f"Three representative months are traced in full: <b>Y1-Jan</b> (flu peak), "
        f"<b>Y1-Apr</b> (spring base), <b>Y1-Jul</b> (summer trough). "
        f"All other months follow the same arithmetic.</p>",
        unsafe_allow_html=True)

    for lbl, mo in [("Y1-Jan (flu peak)", _y1_jan), ("Y1-Apr (spring base)", _y1_apr), ("Y1-Jul (summer trough)", _y1_jul)]:
        st.markdown(f"**{lbl}**")
        _eq("Base visits/day", f"{base_visits:.0f} base × {mo.seasonal_multiplier:.2f} seasonal × {peak_factor:.2f} peak",
            f"{mo.demand_visits_per_day:.1f} visits/day")
        _eq("APCs needed (concurrent)", f"{mo.demand_visits_per_day:.1f} visits ÷ {budget_ppp:.0f} pts/APC",
            f"{mo.demand_providers_per_shift:.3f} APCs on floor")
        _eq("FTE to sustain that slot", f"{mo.demand_providers_per_shift:.3f} APCs × {cfg.fte_per_shift_slot:.3f} FTE/slot",
            f"{mo.demand_fte_required:.3f} FTE required",
            note=f"({cfg.operating_days_per_week}d ÷ {cfg.fte_shifts_per_week} shifts/APC = {cfg.fte_per_shift_slot:.3f})")
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # Annual growth effect
    _h2_sub = (f"<div style='font-size:0.76rem;color:#4A5568;background:#FFFBEB;"
               f"border-left:3px solid #F59E0B;padding:0.45rem 0.85rem;border-radius:3px;margin:0.3rem 0 0.8rem;'>"
               f"<b>Annual growth compounding:</b> each month's visits = prior month × "
               f"(1 + {cfg.annual_growth_pct:.0f}% ÷ 12)<sup>m</sup> — FTE requirement "
               f"grows proportionally. By Y3-Dec, daily visits reach "
               f"<b>{next(mo for mo in mos if mo.year==3 and mo.calendar_month==12).demand_visits_per_day:.1f}/day</b> "
               f"vs Y1-Jan's <b>{_y1_jan.demand_visits_per_day:.1f}/day</b>.</div>")
    st.markdown(_h2_sub, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — REVENUE MATH
    # ══════════════════════════════════════════════════════════════════════════
    _h2("② Revenue Math — Visits × Capture × Rate")

    _total_visits_raw   = sum(mo.demand_visits_per_day * cfg.operating_days_per_week / 7 * 30.44 for mo in mos)
    _total_visits_cap   = sum(mo.visits_captured for mo in mos)
    _avg_capture        = _total_visits_cap / _total_visits_raw if _total_visits_raw else 0
    _total_rev_check    = _total_visits_cap * cfg.net_revenue_per_visit

    _eq("Monthly visits (e.g. Y1-Jan)", f"{_y1_jan.demand_visits_per_day:.1f} visits/day × {cfg.operating_days_per_week} days/wk ÷ 7 × 30.44 days/mo",
        f"{_y1_jan.visits_captured:,.0f} visits/mo")
    _eq("Revenue per month (Y1-Jan)", f"{_y1_jan.visits_captured:,.0f} visits × ${cfg.net_revenue_per_visit:.0f}/visit",
        f"${_y1_jan.revenue_captured:,.0f}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    _eq("Total 36-month revenue", f"{_total_visits_cap:,.0f} captured visits × ${cfg.net_revenue_per_visit:.0f}/visit",
        f"${_total_rev_check:,.0f}", note="cross-check ↓")
    _check("Revenue cross-check vs simulation", es["revenue"], _total_rev_check)

    st.markdown(
        f"<div style='font-size:0.76rem;color:#4A5568;margin:0.6rem 0;'>"
        f"<b>Visit capture rate: {_avg_capture*100:.1f}%</b> — visits are lost only when paid FTE "
        f"falls below demand FTE (understaffed months). "
        f"Lost revenue = missed visits × ${cfg.net_revenue_per_visit:.0f}/visit.</div>",
        unsafe_allow_html=True)

    _lost_rev = sum(mo.lost_revenue for mo in mos)
    _eq("Total lost revenue (understaffing)", "sum of monthly lost_revenue across 36 months",
        f"${_lost_rev:,.0f}", note=f"{_lost_rev/es['revenue']*100:.1f}% of gross")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — SWB EXPENSE BUILDUP
    # ══════════════════════════════════════════════════════════════════════════
    _h2("③ SWB Expense Buildup — FTE × Cost × Months")

    _monthly_perm_rate  = cfg.annual_provider_cost_perm / 12
    _monthly_flex_rate  = cfg.annual_provider_cost_flex / 12
    _total_perm_check   = sum(mo.permanent_cost for mo in mos)
    _total_flex_check   = sum(mo.flex_cost for mo in mos)
    _total_swb_check    = _total_perm_check + _total_flex_check

    _eq("Monthly cost per perm FTE", f"${cfg.annual_provider_cost_perm:,.0f}/yr ÷ 12 months",
        f"${_monthly_perm_rate:,.0f}/mo/FTE")
    _eq("Y1-Jan permanent SWB", f"{_y1_jan.paid_fte:.3f} paid FTE × ${_monthly_perm_rate:,.0f}",
        f"${_y1_jan.permanent_cost:,.0f}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    # SWB per visit derivation
    _total_visits_36    = sum(mo.visits_captured for mo in mos)
    _swb_per_visit_calc = _total_swb_check / _total_visits_36 if _total_visits_36 else 0
    _eq("SWB/visit (provider only)", f"${_total_swb_check:,.0f} provider SWB ÷ {_total_visits_36:,.0f} captured visits",
        f"${_swb_per_visit_calc:.2f}/visit", note=f"target ${cfg.swb_target_per_visit:.2f}")

    target_color = "#0A6B4A" if _swb_per_visit_calc <= cfg.swb_target_per_visit else "#B91C1C"
    delta = _swb_per_visit_calc - cfg.swb_target_per_visit
    st.markdown(
        f"<div style='background:{'#ECFDF5' if delta<=0 else '#FEF2F2'};"
        f"border-left:3px solid {target_color};padding:0.45rem 0.85rem;"
        f"border-radius:3px;font-size:0.80rem;margin:0.4rem 0 0.6rem;'>"
        f"SWB/visit is <b style='color:{target_color};'>"
        f"{'$'+f'{abs(delta):.2f}'+' favorable' if delta<=0 else '$'+f'{abs(delta):.2f}'+' over target'}</b> "
        f"vs the ${cfg.swb_target_per_visit:.2f} budget target.</div>",
        unsafe_allow_html=True)

    _total_support_check = sum(mo.support_cost for mo in mos)
    _total_swb_full_check = _total_perm_check + _total_support_check
    _eq("Monthly support staff cost (Y1-Jan)", f"MA, PSR, Rad Tech per APC on floor",
        f"${_y1_jan.support_cost:,.0f}/mo", note="scales with providers_on_floor")
    _eq("Total SWB (provider + support)", f"${_total_perm_check:,.0f} perm + ${_total_support_check:,.0f} support",
        f"${_total_swb_full_check:,.0f}")
    _check("Total SWB vs simulation",             es["swb"],  _total_swb_full_check)
    _check("Total flex SWB vs simulation",        es["flex"], _total_flex_check)

    # Per-year SWB breakdown table
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    _yr_rows = []
    for yr in [1,2,3]:
        ymos = [mo for mo in mos if mo.year==yr]
        y_visits = sum(mo.visits_captured for mo in ymos)
        y_swb    = sum(mo.permanent_cost + mo.support_cost + mo.flex_cost for mo in ymos)
        y_rev    = sum(mo.revenue_captured for mo in ymos)
        y_goal   = y_visits * cfg.swb_target_per_visit
        y_var    = y_goal - y_swb
        _yr_rows.append({
            "Year": f"Year {yr}",
            "Captured Visits": f"{y_visits:,.0f}",
            "SWB Actual": f"${y_swb:,.0f}",
            "SWB Goal (target/visit)": f"${y_goal:,.0f}",
            "SWB Variance": f"{'+'if y_var>=0 else ''}{y_var/1e3:.0f}K",
            "SWB/Visit": f"${y_swb/y_visits:.2f}" if y_visits else "—",
            "Revenue": f"${y_rev:,.0f}",
        })
    import pandas as pd
    df_yr = pd.DataFrame(_yr_rows)
    st.dataframe(df_yr, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — TURNOVER & BURNOUT
    # ══════════════════════════════════════════════════════════════════════════
    _h2("④ Turnover & Burnout Cost Logic")

    _base_att_rate_mo   = cfg.monthly_attrition_rate
    _replace_cost       = cfg.turnover_replacement_cost_per_provider
    _total_turnover_ev  = sum(mo.turnover_events for mo in mos)
    _total_turnover_c   = sum(mo.turnover_cost   for mo in mos)
    _total_burnout_c    = sum(mo.burnout_penalty  for mo in mos)
    _red_months         = [mo for mo in mos if mo.zone=="Red"]
    _overload_months    = [mo for mo in mos if mo.overload_attrition_delta > 0]

    _eq("Base monthly attrition rate", f"{cfg.annual_attrition_pct:.0f}% annual ÷ 12 months",
        f"{_base_att_rate_mo*100:.3f}%/month per FTE")
    _eq("Replacement cost per turnover", f"${cfg.annual_provider_cost_perm:,.0f} annual cost × {cfg.turnover_replacement_pct:.0f}%",
        f"${_replace_cost:,.0f}/event",
        note="recruiting, onboarding, lost productivity")
    _eq("Y1-Jan turnover events", f"{_y1_jan.paid_fte:.3f} FTE × {_base_att_rate_mo*100:.3f}%",
        f"{_y1_jan.turnover_events:.4f} events → ${_y1_jan.turnover_cost:,.0f}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size:0.80rem;color:#4A5568;background:#F8FAFC;"
        f"border-left:3px solid #7A8799;padding:0.5rem 0.85rem;border-radius:3px;margin:0.4rem 0;'>"
        f"<b>Overload attrition:</b> when pts/APC exceeds the load-band ceiling ({cfg.load_band_hi:.0f}), "
        f"the effective rate scales up: <code>rate × (1 + {cfg.overload_attrition_factor:.1f} × excess%)</code>. "
        f"This model has <b>{len(_overload_months)} months</b> with above-baseline attrition.</div>",
        unsafe_allow_html=True)

    _eq("Total turnover events (36 mo)", "Σ (paid_fte × effective_rate) each month",
        f"{_total_turnover_ev:.2f} events → ${_total_turnover_c:,.0f}")
    _check("Turnover cost vs simulation", es["turnover"], _total_turnover_c)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if _red_months:
        _burnout_per_red = cfg.burnout_penalty_per_red_month
        _eq("Burnout penalty per Red month", f"${cfg.annual_provider_cost_perm:,.0f} × {cfg.burnout_pct_per_red_month:.0f}%",
            f"${_burnout_per_red:,.0f}/Red month")
        _eq("Total burnout penalty", f"{len(_red_months)} Red months × ${_burnout_per_red:,.0f}",
            f"${_total_burnout_c:,.0f}")
    else:
        st.markdown(
            f"<div style='font-size:0.80rem;color:#0A6B4A;background:#ECFDF5;"
            f"border-left:3px solid #0A6B4A;padding:0.45rem 0.85rem;border-radius:3px;margin:0.4rem 0;'>"
            f"✅ <b>Zero Red months</b> — no burnout penalty applied. "
            f"Burnout fires at ${cfg.burnout_penalty_per_red_month:.0f}% of annual APC cost "
            f"per Red month (pts/APC > {cfg.load_band_hi:.0f}).</div>",
            unsafe_allow_html=True)
    _check("Burnout cost vs simulation", es["burnout"], _total_burnout_c)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5 — HIRING CALENDAR LOGIC
    # ══════════════════════════════════════════════════════════════════════════
    _h2("⑤ Hiring Calendar — Lead Time & Post Dates")

    _lead_days  = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    _lead_months = round(_lead_days / 30.44)

    st.markdown(
        f"<div style='font-size:0.80rem;color:#4A5568;margin-bottom:0.8rem;'>"
        f"Total pipeline: <b>{cfg.days_to_sign}d to offer acceptance</b> + "
        f"<b>{cfg.days_to_credential}d credentialing</b> + "
        f"<b>{cfg.days_to_independent}d orientation</b> = "
        f"<b>{_lead_days} days ({_lead_months} months)</b> before first productive shift. "
        f"APCs are <b>binary</b>: 0% productive until credentialing is complete, "
        f"then 100% from day one — no ramp curve.</div>",
        unsafe_allow_html=True)

    _h_rows = []
    for h in pol.hire_events:
        _h_rows.append({
            "Decision / Post By":    f"Y{h.post_by_year}-{MA[h.post_by_month-1]}",
            "Start (Productive)":    f"Y{h.independent_year}-{MA[h.independent_month-1]}",
            "FTE Added":             f"{h.fte_hired:.2f}",
            "Mode":                  h.mode.replace("_"," ").title(),
            "Lead (days)":           f"{_lead_days}d",
            "Why hired":             (
                "Flu-season anchor hire — Dec credentialing deadline" if h.mode=="winter_ramp"
                else "Demand growth — load-band floor breached"
            ),
        })
    df_hire = pd.DataFrame(_h_rows)
    st.dataframe(df_hire, use_container_width=True, hide_index=True)

    st.markdown(
        f"<div style='font-size:0.76rem;color:{MUTED};margin-top:0.4rem;'>"
        f"<b>Post by</b> = start month minus {_lead_months} months lead time. "
        f"Winter ramp hires are always scheduled to begin in December (flu anchor month) — "
        f"the decision is made in Sep/Oct/Nov when the model detects the coming flu-season gap.</div>",
        unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 6 — EBITDA ROLL-UP & CROSS-CHECKS
    # ══════════════════════════════════════════════════════════════════════════
    _h2("⑥ EBITDA Roll-Up & Cross-Checks")

    _ebitda_check = es["revenue"] - es["swb"] - es["flex"] - es["turnover"] - es["burnout"] - es["fixed"]

    _eq("EBITDA", "Revenue − SWB − Flex − Turnover − Burnout − Fixed",
        f"${_ebitda_check:,.0f}")
    _eq("Breakdown",
        f"${es['revenue']:,.0f} − ${es['swb']:,.0f} − ${es['flex']:,.0f} − ${es['turnover']:,.0f} − ${es['burnout']:,.0f}",
        f"${_ebitda_check:,.0f}")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    _check("EBITDA cross-check vs simulation",   es["ebitda"],   _ebitda_check)
    _check("Revenue cross-check",                es["revenue"],  sum(mo.revenue_captured for mo in mos))
    _check("SWB cross-check",                    es["swb"],      sum(mo.permanent_cost + mo.support_cost for mo in mos))
    _check("Turnover cross-check",               es["turnover"], sum(mo.turnover_cost     for mo in mos))
    _check("Burnout cross-check",                es["burnout"],  sum(mo.burnout_penalty   for mo in mos))

    st.markdown(
        f"<div style='margin-top:1rem;font-size:0.76rem;color:{MUTED};'>"
        f"All ✅ checks confirm the displayed numbers are a direct re-derivation of the "
        f"simulation's month-by-month outputs — no separate calculation path, no rounding "
        f"introduced. ⚠️ appears only if a value diverges by more than 2%.</div>",
        unsafe_allow_html=True)



with tabs[13]:
    pol  = active_policy()
    mos  = pol.months
    MA   = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    st.markdown("## TURNOVER COST — FULL BREAKDOWN")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{MUTED};margin:-0.4rem 0 1.4rem;'>"
        f"All-in replacement cost derived from your pipeline inputs. "
        f"Toggle between the model-derived rate and a custom override in the "
        f"<b>Turnover & Penalty Rates</b> sidebar expander.</p>",
        unsafe_allow_html=True)

    # ── Recompute components (mirrors sidebar logic) ──────────────────────────
    _lead_days_tc   = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    _pipeline_mo_tc = _lead_days_tc / 30.44
    _vacancy_days   = 30   # typical days from departure to signed replacement offer
    _total_dark     = _vacancy_days + _lead_days_tc

    _recruiting_tc  = cfg.annual_provider_cost_perm * 0.20
    _pipeline_tc    = (cfg.annual_provider_cost_perm / 12) * _pipeline_mo_tc
    _flex_prem_tc   = (cfg.annual_provider_cost_flex - cfg.annual_provider_cost_perm) / 365 * _total_dark * 0.5
    _admin_tc       = 5_000
    _direct_total   = _recruiting_tc + _pipeline_tc + _flex_prem_tc + _admin_tc
    _derived_pct_tc = _direct_total / cfg.annual_provider_cost_perm * 100
    _model_pct      = cfg.turnover_replacement_pct   # what's actually in the model
    _model_cost     = cfg.annual_provider_cost_perm * (_model_pct / 100)

    # ── Component breakdown table ─────────────────────────────────────────────
    def _cost_row(icon, label, formula, amount, note=""):
        pct = amount / cfg.annual_provider_cost_perm * 100
        note_html = f"<span style='color:{MUTED};font-size:0.72rem;'>{note}</span>" if note else ""
        return (
            f"<tr style='border-bottom:1px solid #F1F5F9;'>"
            f"<td style='padding:0.55rem 0.8rem;font-size:0.85rem;'>{icon}</td>"
            f"<td style='padding:0.55rem 0.5rem;font-size:0.82rem;color:{INK};font-weight:500;'>{label}</td>"
            f"<td style='padding:0.55rem 0.5rem;font-size:0.78rem;color:{MUTED};font-family:monospace;'>{formula}</td>"
            f"<td style='padding:0.55rem 0.8rem;font-size:0.85rem;font-weight:600;color:{NAVY};text-align:right;'>${amount:,.0f}</td>"
            f"<td style='padding:0.55rem 0.8rem;font-size:0.78rem;color:{MUTED};text-align:right;'>{pct:.0f}%</td>"
            f"<td style='padding:0.55rem 0.8rem;font-size:0.76rem;color:#4A5568;'>{note_html}</td>"
            f"</tr>"
        )

    rows_html = ""
    rows_html += _cost_row("🔍", "Recruiting",
        f"${cfg.annual_provider_cost_perm:,} × 20%",
        _recruiting_tc,
        "Agency fee / job boards / interview time / HR burden")
    rows_html += _cost_row("📋", "Paid pipeline — no revenue",
        f"${cfg.annual_provider_cost_perm/12:,.0f}/mo × {_pipeline_mo_tc:.1f} mo",
        _pipeline_tc,
        f"{cfg.days_to_sign}d sign + {cfg.days_to_credential}d credential + {cfg.days_to_independent}d orient — APC on payroll, zero visits")
    rows_html += _cost_row("🔄", "Flex/locum premium",
        f"${cfg.annual_provider_cost_flex - cfg.annual_provider_cost_perm:,}/yr premium × {_total_dark}d × 50%",
        _flex_prem_tc,
        f"Incremental cost above perm rate to backfill during {_vacancy_days}d vacancy + {_lead_days_tc}d pipeline")
    rows_html += _cost_row("🗂️", "Onboarding & admin burden",
        "flat estimate",
        _admin_tc,
        "Credentialing admin, IT setup, orientation staff time, EMR access")

    # Totals row
    rows_html += (
        f"<tr style='border-top:2px solid {NAVY};background:#F8FAFC;'>"
        f"<td colspan='2' style='padding:0.65rem 0.8rem;font-size:0.88rem;font-weight:700;color:{NAVY};'>TOTAL — Direct Costs</td>"
        f"<td style='padding:0.65rem 0.5rem;font-size:0.78rem;color:{MUTED};font-family:monospace;'>sum of above</td>"
        f"<td style='padding:0.65rem 0.8rem;font-size:1.0rem;font-weight:700;color:{NAVY};text-align:right;'>${_direct_total:,.0f}</td>"
        f"<td style='padding:0.65rem 0.8rem;font-size:0.88rem;font-weight:700;color:{NAVY};text-align:right;'>{_derived_pct_tc:.0f}%</td>"
        f"<td style='padding:0.65rem 0.8rem;font-size:0.78rem;color:{MUTED};'>of ${cfg.annual_provider_cost_perm:,} annual salary</td>"
        f"</tr>"
    )

    st.markdown(
        f"<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
        f"<thead><tr style='border-bottom:2px solid {NAVY};'>"
        f"<th style='width:2rem;'></th>"
        f"<th style='padding:0.5rem;text-align:left;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.12em;color:{MUTED};'>Component</th>"
        f"<th style='padding:0.5rem;text-align:left;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.12em;color:{MUTED};'>Formula</th>"
        f"<th style='padding:0.5rem;text-align:right;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.12em;color:{MUTED};'>Amount</th>"
        f"<th style='padding:0.5rem;text-align:right;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.12em;color:{MUTED};'>% Salary</th>"
        f"<th style='padding:0.5rem;text-align:left;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.12em;color:{MUTED};'>Notes</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>",
        unsafe_allow_html=True)

    # ── Revenue loss callout ───────────────────────────────────────────────────
    _apc_daily_rev  = cfg.budgeted_patients_per_provider_per_day * cfg.net_revenue_per_visit
    _gross_rev_loss = _apc_daily_rev * _total_dark
    st.markdown(
        f"<div style='background:#FFFBEB;border-left:3px solid #F59E0B;border-radius:3px;"
        f"padding:0.7rem 1rem;margin:1rem 0;font-size:0.82rem;'>"
        f"<b style='color:#92600A;'>⚠️ Revenue loss excluded from above total</b> — "
        f"if the vacant slot goes completely unfilled for {_total_dark} days, gross revenue impact is "
        f"<b>${_gross_rev_loss:,.0f}</b> "
        f"({cfg.budgeted_patients_per_provider_per_day:.0f} pts/day × ${cfg.net_revenue_per_visit:.0f}/visit × {_total_dark}d). "
        f"In practice, flex coverage and load redistribution recover a portion of this — "
        f"your model tracks actual lost revenue separately in the monthly simulation rather than "
        f"double-counting it here.</div>",
        unsafe_allow_html=True)

    # ── Current model rate vs derived ─────────────────────────────────────────
    st.markdown(f"### Model Rate in Use")
    _delta      = _model_cost - _direct_total
    _delta_pct  = _model_pct - _derived_pct_tc
    _color      = "#0A6B4A" if abs(_delta_pct) < 10 else ("#B91C1C" if _delta < 0 else "#92600A")
    _status     = "within 10% of derived — well calibrated" if abs(_delta_pct) < 10 else (
                  "below derived cost — may understate turnover penalty" if _delta < 0
                  else "above derived cost — conservative assumption")

    c1, c2, c3 = st.columns(3)
    c1.metric("Model rate (active)", f"{_model_pct:.0f}%", f"${_model_cost:,.0f}/event")
    c2.metric("Derived all-in rate", f"{_derived_pct_tc:.0f}%", f"${_direct_total:,.0f}/event")
    c3.metric("Gap", f"{_delta_pct:+.0f}pp", f"${abs(_delta):,.0f} {'under' if _delta<0 else 'over'}")

    st.markdown(
        f"<div style='background:{'#ECFDF5' if abs(_delta_pct)<10 else '#FEF2F2'};"
        f"border-left:3px solid {_color};border-radius:3px;padding:0.55rem 1rem;"
        f"font-size:0.80rem;margin-top:0.4rem;'>"
        f"<b style='color:{_color};'>{_status.capitalize()}.</b> "
        f"Adjust in <b>Turnover & Penalty Rates</b> sidebar expander — "
        f"toggle off the model-derived rate to enter a custom override.</div>",
        unsafe_allow_html=True)

    # ── 36-month turnover event summary ──────────────────────────────────────
    st.markdown("### 36-Month Turnover Activity")
    _total_events = sum(mo.turnover_events for mo in mos)
    _total_cost   = sum(mo.turnover_cost   for mo in mos)
    _overload_mos = [(mo.year, mo.calendar_month, mo.overload_attrition_delta)
                     for mo in mos if mo.overload_attrition_delta > 0.001]

    co1, co2, co3, co4 = st.columns(4)
    co1.metric("Total turnover events",    f"{_total_events:.1f}")
    co2.metric("Total turnover cost",      f"${_total_cost:,.0f}")
    co3.metric("Cost per event (model)",   f"${_model_cost:,.0f}")
    co4.metric("Overload-amplified months",f"{len(_overload_mos)}")

    if _overload_mos:
        st.markdown(
            f"<div style='font-size:0.78rem;color:#92600A;background:#FFFBEB;"
            f"border-left:3px solid #F59E0B;padding:0.5rem 0.85rem;border-radius:3px;margin-top:0.4rem;'>"
            f"<b>Overload attrition active in {len(_overload_mos)} months</b> — "
            f"pts/APC exceeded load ceiling, amplifying base attrition rate by "
            f"up to {cfg.overload_attrition_factor:.1f}×. Months: "
            + ", ".join(f"Y{y}-{MA[m-1]}" for y,m,_ in _overload_mos[:8])
            + ("…" if len(_overload_mos) > 8 else "")
            + "</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='font-size:0.78rem;color:#0A6B4A;background:#ECFDF5;"
            f"border-left:3px solid #0A6B4A;padding:0.5rem 0.85rem;border-radius:3px;margin-top:0.4rem;'>"
            f"✅ No overload-amplified attrition — all months within load band.</div>",
            unsafe_allow_html=True)



with tabs[14]:
    pol  = active_policy()
    es0  = pol.ebitda_summary
    base_ebitda = es0["ebitda"]

    st.markdown("## SENSITIVITY — EBITDA TORNADO")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{MUTED};margin:-0.4rem 0 1.2rem;'>"
        f"Each bar shows how 3-year EBITDA changes when one input is varied from low to high, "
        f"holding all others at your current values. Bars are sorted by total swing — "
        f"the inputs at the top move the needle most.</p>",
        unsafe_allow_html=True)

    _tornado_scenarios = [
        ("Revenue / Visit",        "net_revenue_per_visit",
         max(60.0, cfg.net_revenue_per_visit * 0.80),
         cfg.net_revenue_per_visit * 1.20,
         f"${cfg.net_revenue_per_visit*0.80:.0f}", f"${cfg.net_revenue_per_visit*1.20:.0f}",
         "Net revenue per patient visit (±20%)"),
        ("Base Visits / Day",      "base_visits_per_day",
         max(10.0, cfg.base_visits_per_day * 0.75),
         cfg.base_visits_per_day * 1.35,
         f"{cfg.base_visits_per_day*0.75:.0f} vpd", f"{cfg.base_visits_per_day*1.35:.0f} vpd",
         "Daily baseline visit volume (−25% / +35%)"),
        ("Pts / APC / Day Budget", "budgeted_patients_per_provider_per_day",
         max(18.0, cfg.budgeted_patients_per_provider_per_day - 8),
         cfg.budgeted_patients_per_provider_per_day + 8,
         f"{cfg.budgeted_patients_per_provider_per_day-8:.0f} pts",
         f"{cfg.budgeted_patients_per_provider_per_day+8:.0f} pts",
         "Budgeted patient throughput per APC per shift (±8 pts)"),
        ("APC Annual Cost",        "annual_provider_cost_perm",
         cfg.annual_provider_cost_perm * 0.80,
         cfg.annual_provider_cost_perm * 1.25,
         f"${cfg.annual_provider_cost_perm*0.80/1e3:.0f}K",
         f"${cfg.annual_provider_cost_perm*1.25/1e3:.0f}K",
         "Total annual compensation per permanent APC (±20–25%)"),
        ("Annual Growth %",        "annual_growth_pct",
         max(0.0, cfg.annual_growth_pct - 5),
         cfg.annual_growth_pct + 10,
         f"{max(0,cfg.annual_growth_pct-5):.0f}%", f"{cfg.annual_growth_pct+10:.0f}%",
         "Compounding annual volume growth rate"),
        ("Annual Attrition %",     "annual_attrition_pct",
         max(0.0, cfg.annual_attrition_pct - 10),
         min(50.0, cfg.annual_attrition_pct + 15),
         f"{max(0,cfg.annual_attrition_pct-10):.0f}%",
         f"{min(50,cfg.annual_attrition_pct+15):.0f}%",
         "Annual APC turnover rate"),
        ("Credentialing Days",     "days_to_credential",
         max(30, cfg.days_to_credential - 45),
         min(270, cfg.days_to_credential + 60),
         f"{max(30,cfg.days_to_credential-45)}d",
         f"{min(270,cfg.days_to_credential+60)}d",
         "Days from signed offer to credentialed and seeing patients"),
        ("SWB Target / Visit",     "swb_target_per_visit",
         max(40.0, cfg.swb_target_per_visit - 20),
         cfg.swb_target_per_visit + 20,
         f"${cfg.swb_target_per_visit-20:.0f}", f"${cfg.swb_target_per_visit+20:.0f}",
         "SWB budget target per visit (shifts optimizer pressure)"),
    ]

    with st.spinner("Running sensitivity analysis — computing 16 scenarios..."):
        def _run_tornado(kwarg, val):
            _fields = {f: getattr(cfg, f) for f in cfg.__dataclass_fields__}
            _fields[kwarg] = val
            try:
                _p, _ = optimize(ClinicConfig(**_fields))
                return _p.ebitda_summary["ebitda"]
            except Exception:
                return base_ebitda

        _results = []
        for _lbl, _kw, _lo_v, _hi_v, _lo_lbl, _hi_lbl, _desc in _tornado_scenarios:
            _lo_e = _run_tornado(_kw, _lo_v)
            _hi_e = _run_tornado(_kw, _hi_v)
            _swing = abs(_hi_e - _lo_e)
            _results.append((_lbl, _kw, _lo_v, _hi_v, _lo_lbl, _hi_lbl, _desc, _lo_e, _hi_e, _swing))
        _results.sort(key=lambda x: x[9], reverse=True)

    _c_base, _c_note = st.columns([1, 2])
    with _c_base:
        st.metric("Base Case EBITDA (3yr)", f"${base_ebitda/1e6:.3f}M")
    with _c_note:
        st.markdown(
            f"<div style='font-size:0.78rem;color:{MUTED};padding-top:0.6rem;'>"
            f"Inputs ranked by total swing. Change any sidebar value and revisit this tab to refresh.</div>",
            unsafe_allow_html=True)

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    _C_NEG = "#C0392B"
    _C_POS = "#0A6B4A"
    _labels, _lo_ds, _hi_ds, _lo_lbls, _hi_lbls, _swings, _lo_abs, _hi_abs = [], [], [], [], [], [], [], []
    for _lbl, _kw, _lo_v, _hi_v, _lo_lbl, _hi_lbl, _desc, _lo_e, _hi_e, _swing in _results:
        _labels.append(_lbl); _lo_ds.append(_lo_e - base_ebitda); _hi_ds.append(_hi_e - base_ebitda)
        _lo_lbls.append(_lo_lbl); _hi_lbls.append(_hi_lbl); _swings.append(_swing)
        _lo_abs.append(_lo_e); _hi_abs.append(_hi_e)

    _fig_t = go.Figure()
    _n = len(_labels)
    _max_delta = max((max(abs(_lo_ds[i]), abs(_hi_ds[i])) for i in range(_n)), default=1)

    for _i in range(_n):
        _ld, _hd = _lo_ds[_i], _hi_ds[_i]
        _left_d  = min(_ld, _hd);  _right_d = max(_ld, _hd)
        _left_is_lo = _ld <= _hd
        _left_lbl  = _lo_lbls[_i] if _left_is_lo else _hi_lbls[_i]
        _right_lbl = _hi_lbls[_i] if _left_is_lo else _lo_lbls[_i]
        _left_abs  = _lo_abs[_i]  if _left_is_lo else _hi_abs[_i]
        _right_abs = _hi_abs[_i]  if _left_is_lo else _lo_abs[_i]

        _fig_t.add_trace(go.Bar(
            name="Unfavorable" if _i == 0 else "", y=[_labels[_i]], x=[_left_d],
            orientation="h", base=0, marker_color=_C_NEG, marker_opacity=0.85,
            showlegend=(_i == 0), legendgroup="low",
            text=_left_lbl, textposition="inside",
            textfont=dict(size=10, color="white"),
            insidetextanchor="end",
            hovertemplate=f"<b>{_labels[_i]}</b><br>Scenario: {_left_lbl}<br>EBITDA: ${_left_abs/1e6:.3f}M<br>Delta: {_left_d/1e3:+.0f}K<extra></extra>",
        ))
        _fig_t.add_trace(go.Bar(
            name="Favorable" if _i == 0 else "", y=[_labels[_i]], x=[_right_d],
            orientation="h", base=0, marker_color=_C_POS, marker_opacity=0.85,
            showlegend=(_i == 0), legendgroup="high",
            text=_right_lbl, textposition="inside",
            textfont=dict(size=10, color="white"),
            insidetextanchor="start",
            hovertemplate=f"<b>{_labels[_i]}</b><br>Scenario: {_right_lbl}<br>EBITDA: ${_right_abs/1e6:.3f}M<br>Delta: {_right_d/1e3:+.0f}K<extra></extra>",
        ))

    _swing_annotations = [
        dict(x=_max_delta * 1.08, y=_labels[_i], xref="x", yref="y",
             text=f"<b>${_swings[_i]/1e3:.0f}K</b>",
             showarrow=False, font=dict(size=10, color=NAVY, family="Courier New"),
             xanchor="left")
        for _i in range(_n)
    ] + [
        dict(x=-_max_delta * 0.02, y=_n - 0.9, xref="x", yref="y",
             text="◀ Unfavorable", showarrow=False,
             font=dict(size=9, color=_C_NEG, family="Courier New"), xanchor="right"),
        dict(x=_max_delta * 0.02, y=_n - 0.9, xref="x", yref="y",
             text="Favorable ▶", showarrow=False,
             font=dict(size=9, color=_C_POS, family="Courier New"), xanchor="left"),
        dict(x=_max_delta * 1.08, y=_n - 0.9, xref="x", yref="y",
             text="Swing", showarrow=False,
             font=dict(size=9, color=MUTED, family="Courier New"), xanchor="left"),
    ]

    _fig_t.update_layout(
        barmode="overlay",
        height=max(380, _n * 60 + 120),
        margin=dict(l=0, r=100, t=40, b=52),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="inherit", size=11, color=INK),
        xaxis=dict(
            title="3-Year EBITDA delta vs base case",
            tickformat="$,.0f",
            gridcolor="#E2E8F0", zeroline=True,
            zerolinecolor=NAVY, zerolinewidth=2,
            range=[-_max_delta * 1.05, _max_delta * 1.18],
        ),
        yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)",
                   tickfont=dict(size=11, color=INK)),
        legend=dict(orientation="h", y=1.06, x=0, font=dict(size=10)),
        annotations=_swing_annotations,
    )

    st.plotly_chart(_fig_t, use_container_width=True)

    # Detail table
    st.markdown(
        f"<div style='font-size:0.60rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:0.16em;color:{MUTED};border-bottom:1px solid #E2E8F0;"
        f"padding-bottom:0.3rem;margin-bottom:0.6rem;'>Full Detail</div>",
        unsafe_allow_html=True)
    _tbl = []
    for _lbl, _kw, _lo_v, _hi_v, _lo_lbl, _hi_lbl, _desc, _lo_e, _hi_e, _swing in _results:
        _tbl.append({
            "Input": _lbl, "Description": _desc,
            "Low scenario": _lo_lbl,
            "Low EBITDA":   f"${_lo_e/1e6:.3f}M",
            "Low Δ":        f"${(_lo_e-base_ebitda)/1e3:+.0f}K",
            "High scenario": _hi_lbl,
            "High EBITDA":  f"${_hi_e/1e6:.3f}M",
            "High Δ":       f"${(_hi_e-base_ebitda)/1e3:+.0f}K",
            "Total Swing":  f"${_swing/1e3:.0f}K",
        })
    st.dataframe(pd.DataFrame(_tbl), use_container_width=True, hide_index=True)

    st.markdown(
        f"<div style='font-size:0.72rem;color:{MUTED};margin-top:0.6rem;'>"
        f"Each row varies one input independently. All other inputs held at current sidebar values.</div>",
        unsafe_allow_html=True)


@st.fragment
def _advisor_tab():
    pol_adv = active_policy()
    MA_ADV  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    st.markdown("## SITUATION ADVISOR")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{MUTED};margin:-0.4rem 0 0.8rem;'>"
        f"Ask what to do when reality diverges from the plan — a provider leaves without notice, "
        f"a new hire pushes their start date, a flu season arrives earlier than expected. "
        f"The advisor has full context of your staffing model and answers are specific to your situation.</p>",
        unsafe_allow_html=True)

    _oai_key_adv = _openai_key()
    if not _oai_key_adv:
        st.warning("Add `OPENAI_API_KEY` to your Streamlit secrets (.streamlit/secrets.toml) to enable the advisor.", icon="🔑")
        st.code("[secrets]\nOPENAI_API_KEY = \"sk-...your-key-here...\"", language="toml")
    else:
        # Build sim context once per session (reset when optimizer reruns)
        _ctx_key = f"psm_adv_ctx_{id(pol_adv)}"
        if _ctx_key not in st.session_state:
            st.session_state[_ctx_key] = _build_simulation_context(pol_adv, cfg, MA_ADV)
        _adv_ctx = st.session_state[_ctx_key]

        # Init chat history
        if "psm_adv_history" not in st.session_state:
            st.session_state["psm_adv_history"] = []

        # ── Suggested prompts ─────────────────────────────────────────────────
        if not st.session_state["psm_adv_history"]:
            st.markdown(
                f"<div style='font-size:0.75rem;font-weight:600;color:{MUTED};"
                f"text-transform:uppercase;letter-spacing:0.12em;margin-bottom:0.5rem;'>"
                f"Suggested questions</div>",
                unsafe_allow_html=True)
            _suggestions = [
                "A provider just resigned with 2 weeks notice instead of 90 days — what do I do?",
                "My December hire pushed their start to February — which months are at risk?",
                "Flu season is hitting 3 weeks early this year — am I covered?",
                "I need to cut costs by $50K — where does this model have the most slack?",
                "A new hire failed credentialing — how do I assess the gap?",
            ]
            _sug_cols = st.columns(2)
            for _si, _sug in enumerate(_suggestions):
                with _sug_cols[_si % 2]:
                    if st.button(_sug, key=f"sug_{_si}", use_container_width=True):
                        st.session_state["psm_adv_prefill"] = _sug

        # ── Chat display ──────────────────────────────────────────────────────
        if st.session_state["psm_adv_history"]:
            _chat_html = ""
            for _msg in st.session_state["psm_adv_history"]:
                if _msg["role"] == "user":
                    _chat_html += (
                        f"<div style='display:flex;justify-content:flex-end;margin-bottom:0.7rem;'>"
                        f"<div style='background:{NAVY};color:#E8F0F8;padding:0.6rem 0.9rem;"
                        f"border-radius:12px 12px 3px 12px;max-width:78%;font-size:0.83rem;"
                        f"line-height:1.5;'>{_msg['content']}</div></div>"
                    )
                else:
                    _chat_html += (
                        f"<div style='display:flex;justify-content:flex-start;margin-bottom:0.7rem;'>"
                        f"<div style='background:#F0F4F8;color:{INK};padding:0.6rem 0.9rem;"
                        f"border-radius:12px 12px 12px 3px;max-width:82%;font-size:0.83rem;"
                        f"line-height:1.65;'>{_msg['content'].replace(chr(10), '<br>')}</div></div>"
                    )
            st.markdown(
                f"<div style='background:#FAFBFC;border:1px solid #E2E8F0;border-radius:6px;"
                f"padding:1rem 1rem 0.4rem;margin-bottom:0.75rem;max-height:480px;"
                f"overflow-y:auto;'>{_chat_html}</div>",
                unsafe_allow_html=True)

        # ── Input area ────────────────────────────────────────────────────────
        _prefill = st.session_state.pop("psm_adv_prefill", "")
        _user_input = st.chat_input(
            "Describe your situation or ask a question...",
            key="psm_adv_input",
        )
        # Handle suggested prompt clicks
        if _prefill and not _user_input:
            _user_input = _prefill

        if _user_input:
            st.session_state["psm_adv_history"].append(
                {"role": "user", "content": _user_input})

            # Build full messages list: system + history
            _adv_messages = [
                {"role": "system", "content": _advisor_system_prompt(_adv_ctx)}
            ] + st.session_state["psm_adv_history"]

            with st.spinner("Thinking..."):
                _adv_reply, _adv_err = _call_openai(
                    _adv_messages, _oai_key_adv, max_tokens=500)

            if _adv_err:
                st.error(f"Error: {_adv_err}")
                st.session_state["psm_adv_history"].pop()
            else:
                st.session_state["psm_adv_history"].append(
                    {"role": "assistant", "content": _adv_reply})
                st.rerun()

        # ── Controls ──────────────────────────────────────────────────────────
        if st.session_state["psm_adv_history"]:
            _ctrl1, _ctrl2, _ = st.columns([1, 1, 4])
            with _ctrl1:
                if st.button("🗑 Clear conversation", key="adv_clear"):
                    st.session_state["psm_adv_history"] = []
                    st.rerun()
            with _ctrl2:
                if st.button("↺ Refresh context", key="adv_refresh",
                             help="Re-reads the simulation after running the optimizer"):
                    for _k in list(st.session_state.keys()):
                        if _k.startswith("psm_adv_ctx_"):
                            del st.session_state[_k]
                    st.rerun()

        st.markdown(
            f"<div style='font-size:0.68rem;color:{MUTED};margin-top:0.5rem;'>"
            f"Powered by GPT-4o · Grounded in your simulation data · "
            f"Operational planning guidance only — not HR or legal advice</div>",
            unsafe_allow_html=True)

with tabs[15]:
    _advisor_tab()

# ──────────────────────────────────────────────────────────────────────────────
st.markdown(f"<hr style='border-color:{RULE};margin:2rem 0 1rem;'>",unsafe_allow_html=True)
st.markdown(f"<p style='font-size:0.68rem;color:#8FA8BF;text-align:center;letter-spacing:0.12em;'>"
            f"PSM | PERMANENT STAFFING MODEL | URGENT CARE | 36-MONTH HORIZON | LOAD-BAND OPTIMIZER | ATTRITION-AS-BURNOUT MODEL"
            f"</p>",unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 12: MATH & LOGIC — CFO Validation Audit
# ══════════════════════════════════════════════════════════════════════════════
