"""
PSM — Permanent Staffing Model  v6
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
INK      = "#0D1B2A"
NAVY     = "#1A3A5C"
NAVY_LT  = "#2E5F8A"
SLATE    = "#5B6E82"
RULE     = "#DDE3EA"
CANVAS   = "#F8F9FB"
C_DEMAND = "#1A3A5C"
C_ACTUAL = "#C84B11"
C_BARS   = "#B8C9D9"
C_GREEN  = "#0A7554"
C_YELLOW = "#9A6400"
C_RED    = "#B91C1C"
C_STRESS = "#7C3AED"

Q_COLORS       = [NAVY, C_GREEN, C_YELLOW, NAVY_LT]
Q_BG           = ["rgba(26,58,92,0.05)","rgba(10,117,84,0.04)",
                   "rgba(154,100,0,0.04)","rgba(46,95,138,0.05)"]
Q_MONTH_GROUPS = [[0,1,2],[3,4,5],[6,7,8],[9,10,11]]

HIRE_COLORS = {
    "growth":            NAVY,
    "attrition_replace": NAVY_LT,
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
        font=dict(family="'IBM Plex Sans', sans-serif", size=11, color=SLATE),
        title_font=dict(family="'Playfair Display', serif", size=14, color=INK),
        margin=dict(t=52, b=60, l=56, r=48),
        legend=dict(orientation="h", y=-0.22, x=0,
                    font=dict(size=11, color=SLATE),
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
        xaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=11, color=SLATE),
                   linecolor=RULE, linewidth=1, ticks="outside", ticklen=4),
        yaxis=dict(showgrid=True, gridcolor=RULE, gridwidth=1,
                   zeroline=False, tickfont=dict(size=11, color=SLATE),
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
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');
html, body, [class*="css"] {{ font-family: 'IBM Plex Sans', sans-serif; background-color: {CANVAS}; color: {SLATE}; }}
[data-testid="stSidebar"] {{ background: {INK} !important; border-right: none; }}
[data-testid="stSidebar"] > div {{ padding-top: 0 !important; }}
[data-testid="stSidebar"] * {{ color: #C8D8E8 !important; }}
[data-testid="stSidebar"] button[data-testid="tooltipHoverTarget"],
[data-testid="stSidebar"] button[data-testid="tooltipHoverTarget"] svg,
[data-testid="stSidebar"] button[data-testid="tooltipHoverTarget"] path,
[data-testid="stSidebar"] .stTooltipIcon,
[data-testid="stSidebar"] .stTooltipIcon svg {{
    color: #7AAFD4 !important;
    fill: #7AAFD4 !important;
    opacity: 1 !important; }}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] select {{
    background: #E8F0F8 !important;
    border: 1px solid #4A7A9B !important;
    color: #0D1B2A !important;
    -webkit-text-fill-color: #0D1B2A !important;
    border-radius: 3px;
    font-size: 0.95rem !important;
    font-weight: 600 !important; }}
[data-testid="stSidebar"] input::placeholder {{
    color: #7A9AB8 !important;
    -webkit-text-fill-color: #7A9AB8 !important; }}
[data-testid="stSidebar"] input:focus, [data-testid="stSidebar"] select:focus {{
    background: #F0F6FF !important;
    border-color: #1A3A5C !important;
    color: #0D1B2A !important;
    -webkit-text-fill-color: #0D1B2A !important;
    outline: none !important; }}
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"],
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-baseweb="base-input"] > div {{
    background: #E8F0F8 !important; }}
[data-testid="stSidebar"] [data-baseweb="input"] input,
[data-testid="stSidebar"] [data-baseweb="base-input"] input,
[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
[data-testid="stSidebar"] div[class*="InputContainer"] input,
[data-testid="stSidebar"] div[class*="stNumberInput"] input {{
    background: #E8F0F8 !important;
    color: #0D1B2A !important;
    -webkit-text-fill-color: #0D1B2A !important;
    font-weight: 600 !important; }}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] .stExpander summary p {{
    font-size: 0.68rem !important; font-weight: 600 !important; text-transform: uppercase !important;
    letter-spacing: 0.10em !important; color: #8FAABB !important; }}
[data-testid="stSidebar"] .stButton > button {{
    background: {C_ACTUAL} !important; color: white !important; border: none; border-radius: 3px;
    font-size: 0.78rem !important; font-weight: 600 !important; letter-spacing: 0.12em !important;
    text-transform: uppercase; padding: 0.65rem 1rem !important; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background: #A53C0D !important; }}
.main .block-container {{ background: {CANVAS}; padding: 2rem 2.5rem 3rem; max-width: 1440px; }}
h1 {{ font-family: 'Playfair Display', serif !important; font-size: 2.0rem !important;
      font-weight: 700 !important; color: {INK} !important; letter-spacing: -0.02em; line-height: 1.15; margin-bottom: 0 !important; }}
h2 {{ font-family: 'IBM Plex Sans', sans-serif !important; font-size: 0.65rem !important;
      font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.16em !important;
      color: {SLATE} !important; border: none !important; margin-top: 1.8rem !important; margin-bottom: 0.75rem !important; }}
[data-testid="stMetric"] {{ background: white; border: 1px solid {RULE}; border-top: 3px solid {NAVY};
    border-radius: 3px; padding: 1rem 1.25rem 0.85rem !important; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
[data-testid="stMetricLabel"] p {{ font-size: 0.65rem !important; font-weight: 600 !important;
    text-transform: uppercase !important; letter-spacing: 0.12em !important; color: {SLATE} !important; }}
[data-testid="stMetricValue"] {{ font-family: 'Playfair Display', serif !important; font-size: 1.75rem !important;
    font-weight: 700 !important; color: {INK} !important; line-height: 1.1 !important; }}
.stTabs [data-baseweb="tab-list"] {{ border-bottom: 1px solid {RULE}; gap: 0; background: transparent; }}
.stTabs [data-baseweb="tab"] {{ font-size: 0.72rem !important; font-weight: 500 !important;
    text-transform: uppercase !important; letter-spacing: 0.10em !important;
    color: {SLATE} !important; padding: 0.7rem 1.2rem !important; border: none !important;
    border-bottom: 2px solid transparent !important; margin-bottom: -1px; background: transparent !important; }}
.stTabs [aria-selected="true"] {{ color: {INK} !important; border-bottom: 2px solid {NAVY} !important; font-weight: 600 !important; }}
[data-testid="stSuccess"] {{ background: #F0FDF6; border-left: 3px solid {C_GREEN}; font-size: 0.84rem; color: #064E3B; }}
[data-testid="stError"]   {{ background: #FFF5F5; border-left: 3px solid {C_RED};   font-size: 0.84rem; }}
[data-testid="stInfo"]    {{ background: #EFF6FF; border-left: 3px solid {NAVY};    font-size: 0.84rem; }}
[data-testid="stWarning"] {{ background: #FFFBEB; border-left: 3px solid {C_YELLOW};font-size: 0.84rem; }}
hr {{ border-color: {RULE} !important; }}
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
    <div style='padding:1.6rem 1.2rem 1.2rem;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:0.8rem;'>
      <div style='font-size:0.6rem;font-weight:600;text-transform:uppercase;letter-spacing:0.18em;color:#4A6178;margin-bottom:0.35rem;'>Permanent Staffing Model</div>
      <div style='font-family:"Playfair Display",serif;font-size:1.3rem;font-weight:700;color:#E2EBF3;line-height:1.2;'>Staffing Optimizer</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("BASE DEMAND", expanded=True):
        base_visits = st.number_input("Visits / Day", 20.0, 300.0, 32.0, 5.0,
            help="Average patient visits per day across all shifts. Starting point for all demand calculations.")
        budget_ppp  = st.number_input("Pts / APC / Shift", 10.0, 60.0, 36.0, 1.0,
            help="Budgeted patient throughput per APC per shift. 36 = Green ceiling; above this enters Yellow zone.")
        annual_growth = st.slider("Annual Volume Growth %", 0.0, 30.0, 10.0, 0.5,
            help="Expected year-over-year visit growth, compounded monthly. Drives rising FTE demand in years 2-3, and increases the cost of understaffing since more visits are at risk in later years.")
        peak_factor = 1.0  # removed from UI — use quarterly seasonality for volume adjustments
        _y3_visits = base_visits * (1 + annual_growth/100) ** 2
        st.caption(f"Y1 baseline: **{base_visits:.0f}**/day  →  Y3 projected: **{_y3_visits:.0f}**/day")

    with st.expander("QUARTERLY SEASONALITY", expanded=True):
        c1, c2 = st.columns(2); c3, c4 = st.columns(2)
        with c1: q1 = st.number_input("Q1 Jan-Mar %", -50, 100, 20, 5, key="q1",
                help="Volume adjustment vs base for Jan–Mar. +20 = flu season drives 20% more visits.")
        with c2: q2 = st.number_input("Q2 Apr-Jun %", -50, 100,  0, 5, key="q2",
                help="Volume adjustment vs base for Apr–Jun. 0 = baseline volume.")
        with c3: q3 = st.number_input("Q3 Jul-Sep %", -50, 100,-10, 5, key="q3",
                help="Volume adjustment vs base for Jul–Sep. -10 = summer slowdown, natural shed opportunity.")
        with c4: q4 = st.number_input("Q4 Oct-Dec %", -50, 100,  5, 5, key="q4",
                help="Volume adjustment vs base for Oct–Dec. +5 = early flu ramp before peak.")
        quarterly_impacts = [q1/100, q2/100, q3/100, q4/100]
        s_idx = [1.0 + quarterly_impacts[MONTH_TO_QUARTER[m]] for m in range(12)]
        pv = [base_visits * s_idx[m] * peak_factor for m in range(12)]
        st.caption(f"Range: **{min(pv):.0f}** - **{max(pv):.0f}** visits/day")

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

    with st.expander("STAFFING POLICY"):
        flu_anchor        = st.selectbox("Flu Anchor Month", list(range(1,13)), index=11,
                                         format_func=lambda x: MONTH_NAMES[x-1],
                                         help="The month by which you need fully independent APCs on floor. Drives requisition posting deadline calculation.")
        summer_shed_floor = 85  # removed from UI — load-band optimizer handles shed floor implicitly

    with st.expander("PROVIDER COMPENSATION"):
        perm_cost_i = st.number_input("APC Annual Salary — Fully Loaded ($)", 100_000, 500_000, 175_000, 10_000, format="%d",
            help="Fully loaded annual cost per permanent APC — base salary, benefits, malpractice. Drives turnover replacement cost, burnout penalty, and optimizer score. Support staff rates are entered separately below.")
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
                    "letter-spacing:0.12em;color:#6A8FAA;padding:0.5rem 0 0.25rem;'>"
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
                    "letter-spacing:0.12em;color:#6A8FAA;padding:0.5rem 0 0.25rem;'>"
                    "HOURLY RATES  (base, before multiplier)</div>", unsafe_allow_html=True)
        r1,r2 = st.columns(2)
        with r1: phys_rate = st.number_input("Physician ($/hr)",  50.0, 300.0, 135.79, 1.0)
        with r2: app_rate  = st.number_input("APC ($/hr)",        30.0, 200.0,  62.00, 1.0)
        r3,r4 = st.columns(2)
        with r3: ma_rate   = st.number_input("MA ($/hr)",          8.0,  60.0,  24.14, 0.25)
        with r4: psr_rate  = st.number_input("PSR ($/hr)",         8.0,  60.0,  21.23, 0.25)
        r5,r6 = st.columns(2)
        with r5: rt_rate   = st.number_input("Rad Tech ($/hr)",    8.0,  80.0,  31.36, 0.25)
        with r6: sup_rate  = st.number_input("Supervisor ($/hr)",  8.0,  80.0,  28.25, 0.25)

        # ── 3. Staffing ratios ────────────────────────────────────────────────
        st.markdown("<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;"
                    "letter-spacing:0.12em;color:#6A8FAA;padding:0.5rem 0 0.25rem;'>"
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
                    "letter-spacing:0.12em;color:#6A8FAA;padding:0.5rem 0 0.25rem;'>"
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
        st.caption("Costs as % of annual APC salary.")
        tp1,tp2=st.columns(2); tp3,tp4=st.columns(2)
        with tp1: turnover_pct  = st.number_input("Replacement Cost (% salary)", 10.0, 150.0, 40.0, 5.0,
            help="Cost to replace one departing APC as % of annual salary. Includes recruiting, onboarding, and lost productivity during ramp. 40% of $200k = $80k per departure.")
        with tp2: burnout_pct   = st.number_input("Burnout Penalty (% sal/red mo)", 5.0, 100.0, 25.0, 5.0,
            help="Economic penalty per Red zone month as % of annual APC salary. Represents risk of accelerated attrition, reduced quality, and provider wellbeing costs. 25% of $200k = $50k per Red month.")
        with tp3: overstaff_pen = st.number_input("Overstaff ($/FTE-mo)", 500, 20_000, 3_000, 500, format="%d",
            help="Penalty per FTE-month of overstaffing. Represents idle cost, scheduling friction, and opportunity cost of excess headcount. Keeps optimizer from over-hiring.")
        with tp4: swb_pen       = st.number_input("SWB Violation ($)", 50_000, 2_000_000, 500_000, 50_000, format="%d",
            help="One-time penalty added to the optimizer score if annual SWB/visit exceeds your target. Large value forces optimizer to treat SWB compliance as a near-hard constraint.")
        st.caption(f"Replacement: **${perm_cost_i*turnover_pct/100:,.0f}**  |  Burnout/red mo: **${perm_cost_i*burnout_pct/100:,.0f}**")

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
    peak_factor=peak_factor, quarterly_volume_impact=quarterly_impacts,
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
    for qi,(mq,bg) in enumerate(zip(Q_MONTH_GROUPS,Q_BG)):
        fp.add_vrect(x0=mq[0]-0.5,x1=mq[-1]+0.5,fillcolor=bg,layer="below",line_width=0)
        im=quarterly_impacts[qi]
        fp.add_annotation(x=mq[1],y=max(mv)*1.09,
                          text=f"<b>{QUARTER_LABELS[qi]}</b>  {chr(43) if im>=0 else chr(45)}{im*100:.0f}%",
                          showarrow=False,font=dict(size=11,color=Q_COLORS[qi]),
                          bgcolor="rgba(255,255,255,0.9)",borderpad=3)
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
def render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp, peak_factor, title=None):
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
    for qi,(mq,_) in enumerate(zip(Q_MONTH_GROUPS,Q_BG)):
        im=quarterly_impacts[qi]
        fig.add_annotation(row=1,col=1,xref="x",yref="paper",x=mq[1],y=1.0,
                           text=f"<b>{QUARTER_LABELS[qi]}</b>  {chr(43) if im>=0 else chr(45)}{im*100:.0f}%",
                           showarrow=False,yanchor="bottom",
                           font=dict(size=10,color=Q_COLORS[qi]),bgcolor="rgba(255,255,255,0.92)",borderpad=3)

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
        font=dict(family="'IBM Plex Sans', sans-serif",size=11,color=SLATE),
        title=dict(text=title or "Annual Demand & Staffing Model - Year 1",
                   font=dict(family="'Playfair Display', serif",size=15,color=INK),x=0,xanchor="left"),
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
st.title("Staffing Policy Recommendation")
st.markdown(f"<p style='font-size:0.87rem;color:{SLATE};margin-top:-0.5rem;margin-bottom:1.5rem;'>"
            f"36-month horizon | load-band optimizer | attrition-as-burnout model</p>",unsafe_allow_html=True)
st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1.5rem;'>",unsafe_allow_html=True)

st.markdown("## RECOMMENDED POLICY")

# EBITDA Impact = SWB/visit variance × annual visits (annualized)
# Negative delta = under budget = favourable (green); positive = over budget (red)
_swb_actual     = s["annual_swb_per_visit"]
_swb_target     = cfg.swb_target_per_visit
_swb_delta_pv   = _swb_actual - _swb_target          # neg = favourable
_ann_visits_kpi = s["annual_visits"]
_ebitda_impact  = -_swb_delta_pv * _ann_visits_kpi   # flip sign: fav = positive $
_impact_str     = f"${abs(_ebitda_impact)/1e3:.0f}K/yr {'▲ contribution' if _ebitda_impact >= 0 else '▼ detraction'}"
_impact_delta   = f"{'▼' if _swb_delta_pv <= 0 else '▲'} ${abs(_swb_delta_pv):.2f}/visit vs ${_swb_target:.2f} target"

k1,k2,k3,k4,k5,k6,k7 = st.columns(7)
k1.metric("Base FTE",         f"{best.base_fte:.1f}")
k2.metric("Winter FTE",       f"{best.winter_fte:.1f}")
k3.metric("Summer Floor",     f"{best.base_fte*cfg.summer_shed_floor_pct:.1f}")
k4.metric("Post Req By",      MONTH_NAMES[best.req_post_month-1])
k5.metric("SWB / Visit",      f"${_swb_actual:.2f}",
          delta=f"Target ${_swb_target:.2f}",
          delta_color="inverse" if s["swb_violation"] else "normal")
k6.metric("In-Band Months",   f"{s['pct_months_in_band']:.0f}%")
k7.metric("EBITDA Impact",    _impact_str,
          delta=_impact_delta,
          delta_color="normal" if _ebitda_impact >= 0 else "inverse")

st.markdown("<div style='height:0.6rem'></div>",unsafe_allow_html=True)
if s["swb_violation"]:
    st.error(f"SWB/Visit target exceeded — ${s['annual_swb_per_visit']:.2f} vs ${cfg.swb_target_per_visit:.2f}")
else:
    st.success(f"SWB/Visit on target — **${s['annual_swb_per_visit']:.2f}** vs "
               f"${cfg.swb_target_per_visit:.2f}  |  ~{s['annual_visits']:,.0f} annual visits")

z1,z2,z3,z4,_ = st.columns([1,1,1,1,2])
z1.metric("Green",  s["green_months"])
z2.metric("Yellow", s["yellow_months"])

# ── EBITDA waterfall banner + SWB/visit variance row ─────────────────────────
_es = best.ebitda_summary
_elabel_b = "EBITDA CONTRIBUTION FROM STAFFING" if cfg.monthly_fixed_overhead == 0 else "EBITDA"
_fhtml = (f"  −  <span style='color:#F87171'>Fixed ${_es['fixed']/1e3:.0f}K</span>"
          if cfg.monthly_fixed_overhead > 0 else "")

# SWB/visit variance values (reuses _swb_* from KPI strip above)
_total_cap_3yr  = sum(mo.visits_captured for mo in best.months)
_swb_impact_3yr = -_swb_delta_pv * _total_cap_3yr   # positive = $ saved vs budget
_swb_impact_ann = -_swb_delta_pv * _ann_visits_kpi
_perm_3yr       = sum(mo.permanent_cost for mo in best.months)
_supp_3yr       = sum(mo.support_cost   for mo in best.months)
_apc_pv         = (_perm_3yr / 3) / _ann_visits_kpi if _ann_visits_kpi > 0 else 0
_sup_pv         = (_supp_3yr / 3) / _ann_visits_kpi if _ann_visits_kpi > 0 else 0
_var_clr        = "#4ADE80" if _swb_delta_pv <= 0 else "#F87171"
_var_word       = "favorable" if _swb_delta_pv <= 0 else "unfavorable"
_var_arrow      = "▼" if _swb_delta_pv <= 0 else "▲"
_impact_sign    = "+" if _swb_impact_ann >= 0 else "−"
_impact_abs_ann = abs(_swb_impact_ann)
_impact_abs_3yr = abs(_swb_impact_3yr)

st.markdown(
    f"<div style='background:#0D1B2A;border:1px solid #1A3A5C;border-radius:4px 4px 0 0;"
    f"padding:0.7rem 1.2rem 0.55rem;margin:0.5rem 0 0;font-size:0.82rem;'>"
    f"<span style='color:#6A8FAA;font-size:0.65rem;font-weight:700;text-transform:uppercase;"
    f"letter-spacing:0.12em;'>3-YEAR {_elabel_b}</span><br>"
    f"<span style='color:#4ADE80;font-weight:700'>Revenue ${_es['revenue']/1e6:.2f}M</span>"
    f"  −  <span style='color:#F87171'>SWB ${_es['swb']/1e6:.2f}M</span>"
    f"  −  <span style='color:#F87171'>Flex ${_es['flex']/1e3:.0f}K</span>"
    f"  −  <span style='color:#F87171'>Turnover ${_es['turnover']/1e3:.0f}K</span>"
    f"  −  <span style='color:#F87171'>Burnout ${_es['burnout']/1e3:.0f}K</span>"
    f"{_fhtml}"
    f"  =  <span style='color:#4ADE80;font-size:1.1rem;font-weight:700'>"
    f"${_es['ebitda']/1e6:.2f}M</span>"
    f"  <span style='color:#6A8FAA;font-size:0.75rem'>({_es['capture_rate']*100:.1f}% visit capture)</span>"
    f"</div>"
    f"<div style='background:#091623;border:1px solid #1A3A5C;border-top:1px solid #0F2A40;"
    f"border-radius:0 0 4px 4px;padding:0.42rem 1.2rem 0.45rem;margin:0 0 0.5rem;"
    f"display:flex;align-items:baseline;gap:1.4rem;flex-wrap:wrap;'>"
    f"<span style='color:#6A8FAA;font-size:0.62rem;font-weight:700;text-transform:uppercase;"
    f"letter-spacing:0.12em;white-space:nowrap;'>SWB / VISIT VARIANCE</span>"
    f"<span style='color:{_var_clr};font-weight:700;font-size:0.88rem'>"
    f"{_var_arrow} ${abs(_swb_delta_pv):.2f}/visit</span>"
    f"<span style='color:#6A8FAA;font-size:0.76rem'>"
    f"APC ${_apc_pv:.2f} + Support ${_sup_pv:.2f} = "
    f"<strong style='color:#CBD5E1'>${_swb_actual:.2f}</strong>"
    f" vs target ${_swb_target:.2f}</span>"
    f"<span style='color:#6A8FAA;font-size:0.76rem'>→</span>"
    f"<span style='color:{_var_clr};font-weight:700;font-size:0.88rem'>"
    f"{_impact_sign}${_impact_abs_ann/1e3:.0f}K/yr</span>"
    f"<span style='color:#6A8FAA;font-size:0.74rem'>"
    f"({_var_word}, {_impact_sign}${_impact_abs_3yr/1e3:.0f}K over 3 yrs)</span>"
    f"</div>",
    unsafe_allow_html=True
)
z3.metric("Red",    s["red_months"])
_oa = s.get("total_overload_attrition", 0)
z4.metric("Overload Attrition", f"{_oa:.1f} FTE")

# Marginal APC callout banner
if best.marginal_analysis:
    ma = best.marginal_analysis
    _net = ma["net_annual"]
    _clr = C_GREEN if _net > 0 else C_YELLOW
    st.markdown(
        f"<div style='background:#F0FDF4;border-left:3px solid {_clr};"
        f"padding:0.7rem 1rem;border-radius:0 3px 3px 0;margin-bottom:1rem;font-size:0.82rem;'>"
        f"<b>+{ma['delta_fte']:.1f} FTE marginal:</b> &nbsp;"
        f"Saves <b>{ma['red_months_saved']}R + {ma['yellow_months_saved']}Y</b> months  |  "
        f"Net annual: <b style='color:{_clr}'>${_net:+,.0f}</b>  |  "
        f"Payback: <b>{'never' if ma['payback_months']==float('inf') else f"{ma['payback_months']:.0f} mo"}</b>"
        f"</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.75rem'></div>",unsafe_allow_html=True)
st.plotly_chart(render_hero_chart(active_policy(),cfg,quarterly_impacts,base_visits,budget_ppp,peak_factor),
                use_container_width=True)

# Hiring mode legend
hm_map = {
    "growth":("Growth hire",NAVY), "attrition_replace":("Attrition backfill",NAVY_LT),
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
tabs = st.tabs([
    "Staffing Model", "Executive Summary",
    "36-Month Load", "Hire Calendar", "Shift Coverage", "Seasonality",
    "Cost Breakdown", "Marginal APC", "Stress Test",
    "Policy Heatmap", "Req Timing", "Data Table",
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

            ma_day   = avg_pof * sup.ma_ratio
            psr_day  = avg_pof * sup.psr_ratio
            rt_day   = sup.rt_flat_fte

            ma_fte   = ma_day  * fts
            psr_fte  = psr_day * fts
            rt_fte   = rt_day  * fts
            total_fte= avg_pfte + ma_fte + psr_fte + rt_fte

            rows.append({
                "year": yr, "quarter": q, "zone": dom_zone,
                "vpd": avg_vpd,
                # staff per day
                "apc_day":  avg_pof,
                "ma_day":   ma_day,
                "psr_day":  psr_day,
                "rt_day":   rt_day,
                # FTE
                "apc_fte":  avg_pfte,
                "ma_fte":   ma_fte,
                "psr_fte":  psr_fte,
                "rt_fte":   rt_fte,
                "total_fte":total_fte,
            })

    # ── Colour helpers ────────────────────────────────────────────────────────
    ZONE_BG   = {"Green": "#0A2818", "Yellow": "#1F1A00", "Red": "#2A0A0A"}
    ZONE_PILL = {"Green": ("#4ADE80","#0A2818"), "Yellow": ("#FCD34D","#1A1600"), "Red": ("#F87171","#2A0A0A")}

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
                    f"color:#4ADE80;font-weight:700;font-size:0.9rem;"
                    f"text-align:center;vertical-align:middle;white-space:nowrap;"
                    f"padding:0 0.9rem'>{yr_label}</td>") if yr_label else ""

        _rows_html += f"""
        <tr style='border-bottom:1px solid #132333;'>
          {yr_cell}
          <td style='padding:0.55rem 0.7rem;color:#CBD5E1;font-size:0.8rem'>{q_label}</td>
          <td style='padding:0.55rem 0.5rem;text-align:center'>{zone_pill}</td>
          <td style='padding:0.55rem 0.5rem;text-align:right;color:#94A3B8;font-size:0.78rem'>{_fmt(r['vpd'],1)}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['apc_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['ma_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['psr_day'])}</td>
          <td class='spd' style='text-align:right'>{_fmt(r['rt_day'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['apc_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['ma_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['psr_fte'])}</td>
          <td class='fte' style='text-align:right'>{_fmt(r['rt_fte'])}</td>
          <td style='text-align:right;color:#4ADE80;font-weight:700;font-size:0.82rem;padding:0.55rem 0.7rem'>{_fmt(r['total_fte'])}</td>
        </tr>"""

    _table_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #060F18;
    color: #CBD5E1;
    font-family: 'IBM Plex Sans', sans-serif;
    padding: 1.5rem 2rem;
  }}

  /* ── Header ── */
  .doc-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 2px solid #1A3A5C;
    padding-bottom: 0.8rem;
    margin-bottom: 1.4rem;
  }}
  .doc-title {{
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #E2EAF0;
  }}
  .doc-sub {{
    font-size: 0.7rem;
    color: #6A8FAA;
    letter-spacing: 0.1em;
    margin-top: 0.25rem;
  }}
  .doc-meta {{
    text-align: right;
    font-size: 0.68rem;
    color: #4A6A82;
    font-family: 'IBM Plex Mono', monospace;
  }}

  /* ── Config strip ── */
  .config-strip {{
    display: flex;
    gap: 2rem;
    background: #0A1A28;
    border: 1px solid #1A3A5C;
    border-radius: 4px;
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
    font-size: 0.58rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #4A6A82;
    font-weight: 600;
  }}
  .cfg-value {{
    font-size: 0.82rem;
    font-weight: 600;
    color: #CBD5E1;
    font-family: 'IBM Plex Mono', monospace;
  }}

  /* ── Table ── */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }}
  thead tr {{
    background: #091623;
    border-bottom: 2px solid #1A3A5C;
  }}
  /* Section headers */
  .th-group {{
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #4A6A82;
    padding: 0.3rem 0.5rem 0.1rem;
    text-align: center;
  }}
  .th-group-spd {{ color: #60A5FA; border-bottom: 1px solid #1A3A5C; }}
  .th-group-fte {{ color: #A78BFA; border-bottom: 1px solid #2A1A5C; }}
  th {{
    padding: 0.35rem 0.5rem;
    font-size: 0.66rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
    color: #6A8FAA;
  }}
  th.spd {{ color: #93C5FD; }}
  th.fte {{ color: #C4B5FD; }}
  tr:nth-child(4n+1) td, tr:nth-child(4n+2) td,
  tr:nth-child(4n+3) td, tr:nth-child(4n+4) td {{
    background: transparent;
  }}
  tbody tr:hover td {{ background: rgba(74,110,138,0.07); }}
  td.spd {{ color: #93C5FD; font-family: 'IBM Plex Mono', monospace; font-size: 0.77rem; }}
  td.fte {{ color: #C4B5FD; font-family: 'IBM Plex Mono', monospace; font-size: 0.77rem; }}

  /* Year separators */
  tr.yr-sep td {{ border-top: 2px solid #1A3A5C; }}

  /* ── Footnotes ── */
  .footnotes {{
    margin-top: 1rem;
    font-size: 0.65rem;
    color: #4A6A82;
    border-top: 1px solid #1A3A5C;
    padding-top: 0.6rem;
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
  }}
  .fn-item {{ display: flex; gap: 0.3rem; }}
  .fn-key {{ color: #60A5FA; font-weight: 600; }}

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
      <th rowspan="2" style="text-align:right;color:#6A8FAA">Visits/Day</th>
      <th colspan="4" class="th-group th-group-spd">Staff per Day (Concurrent)</th>
      <th colspan="4" class="th-group th-group-fte">FTE Required</th>
      <th rowspan="2" style="text-align:right;padding-right:0.7rem;color:#4ADE80">Total FTE</th>
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
        f"<strong style='color:#CBD5E1'>Staff/Day</strong> = concurrent positions on floor · "
        f"<strong style='color:#CBD5E1'>FTE</strong> = headcount to sustain that coverage</p>",
        unsafe_allow_html=True
    )

    # Print button
    _pb_col, _ = st.columns([1, 5])
    _pb_col.markdown(
        "<button onclick='window.print()' style='"
        "background:#0D1B2A;border:1px solid #1A3A5C;color:#CBD5E1;"
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

        # EBITDA characterization
        ebitda_annual = ebitda / 3
        if ebitda > 3_000_000:
            ebitda_prose = f"strong 3-year EBITDA contribution of ${ebitda/1e6:.2f}M (${ebitda_annual/1e3:.0f}K/year)"
        elif ebitda > 1_500_000:
            ebitda_prose = f"solid 3-year EBITDA contribution of ${ebitda/1e6:.2f}M (${ebitda_annual/1e3:.0f}K/year)"
        elif ebitda > 0:
            ebitda_prose = f"modest 3-year EBITDA contribution of ${ebitda/1e6:.2f}M — there is meaningful room for improvement"
        else:
            ebitda_prose = f"a 3-year EBITDA loss of ${abs(ebitda)/1e6:.2f}M — immediate staffing restructuring is required"

        # SWB characterization
        swb_delta = swb_actual - swb_target
        if swb_ok:
            swb_prose = f"SWB/visit of ${swb_actual:.2f} sits ${abs(swb_delta):.2f} below the ${swb_target:.0f} target — cost efficiency is on track"
        else:
            swb_prose = f"SWB/visit of ${swb_actual:.2f} exceeds the ${swb_target:.0f} target by ${swb_delta:.2f} — a staffing cost discipline issue that warrants review"

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
            yr_data[yr] = {
                "G": sum(1 for m in yr_mos if m.zone == "Green"),
                "Y": sum(1 for m in yr_mos if m.zone == "Yellow"),
                "R": sum(1 for m in yr_mos if m.zone == "Red"),
                "peak": max(m.patients_per_provider_per_shift for m in yr_mos),
                "avg_visits": sum(m.demand_visits_per_day for m in yr_mos) / 12,
                "ebitda": sum(m.ebitda_contribution for m in yr_mos),
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
    ebitda_color  = "#4ADE80" if es["ebitda"] > 0 else "#F87171"
    zone_badge    = {"excellent":"#22C55E","good":"#4ADE80","moderate":"#FBBF24","stressed":"#EF4444"}
    badge_col     = zone_badge.get(memo["zone_health"], "#94A3B8")
    actions_html  = "".join(f"<li>{a}</li>" for a in memo["actions"])
    yr1 = memo["yr_data"][1]; yr2 = memo["yr_data"][2]; yr3 = memo["yr_data"][3]
    ebitda_3yr_fmt= f"${es['ebitda']/1e6:.2f}M"
    ebitda_lbl    = "3-Year EBITDA Contribution"
    zones_fmt     = f"{s['green_months']}G &nbsp;/&nbsp; {s['yellow_months']}Y &nbsp;/&nbsp; {s['red_months']}R"
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
    yr1_ebitda    = f"${yr1['ebitda']/1e3:.0f}K EBITDA"
    yr2_ebitda    = f"${yr2['ebitda']/1e3:.0f}K EBITDA"
    yr3_ebitda    = f"${yr3['ebitda']/1e3:.0f}K EBITDA"
    hire_txt      = memo['hire_prose']
    burnout_txt   = memo['burnout_prose']
    marginal_txt  = memo['marginal_prose']
    growth_txt    = memo['growth_prose']

    _memo_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:12px 0;background:#0A0F1A;">
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
.memo-wrap {{
    background: #080F1A;
    border: 1px solid #1E3A5F;
    border-radius: 8px;
    overflow: hidden;
    max-width: 900px;
    margin: 0 auto;
    font-family: 'IBM Plex Sans', sans-serif;
}}
.memo-masthead {{
    background: linear-gradient(135deg, #0D1B2A 0%, #0A1628 100%);
    border-bottom: 1px solid #1E3A5F;
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
    color: #4A7FA5;
    margin-bottom: 0.5rem;
}}
.memo-title-main {{
    font-family: 'Playfair Display', serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #E2E8F0;
    line-height: 1.2;
    margin-bottom: 0.3rem;
}}
.memo-subtitle {{
    font-size: 0.75rem;
    color: #6A8FAA;
}}
.memo-kpi-block {{
    text-align: right;
}}
.memo-ebitda-num {{
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 2.2rem;
    font-weight: 700;
    color: {ebitda_color};
    line-height: 1;
}}
.memo-ebitda-label {{
    font-size: 0.58rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #6A8FAA;
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
    color: #4A7FA5;
    border-bottom: 1px solid #1E3A5F;
    padding-bottom: 0.35rem;
    margin: 1.8rem 0 0.8rem;
}}
.memo-prose {{
    font-size: 0.88rem;
    line-height: 1.8;
    color: #B8C9D9;
}}
.memo-prose strong {{ color: #E2E8F0; }}
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
    color: #B8C9D9;
}}
.memo-actions li::before {{
    content: counter(action-counter);
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 1.6rem;
    height: 1.6rem;
    background: #1A3A5C;
    color: #4ADE80;
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
    background: #0D1B2A;
    border: 1px solid #1E3A5F;
    border-radius: 4px;
    padding: 0.75rem 1rem;
}}
.memo-yr-title {{
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #4A7FA5;
    margin-bottom: 0.4rem;
}}
.memo-yr-zones {{
    font-size: 0.82rem;
    color: #94A3B8;
}}
.memo-yr-ebitda {{
    font-size: 0.88rem;
    font-weight: 600;
    color: #4ADE80;
    margin-top: 0.3rem;
}}
</style>

<div class="memo-wrap">
  <div class="memo-masthead">
    <div>
      <div class="memo-eyebrow">Permanent Staffing Model &nbsp;·&nbsp; Executive Summary</div>
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
      <div style="margin-top:0.5rem;font-size:0.72rem;color:{badge_col};font-weight:600;text-align:right;">
        {zones_fmt}
      </div>
    </div>
  </div>

  <div class="memo-body">

    <div class="memo-section-label">Headline Verdict</div>
    <div class="memo-prose">
      This clinic is projecting a <strong>{headline_ebitda}</strong>.
      {headline_capture}.
      Zone performance is <strong>{headline_zone}</strong>,
      with {headline_swb}.
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

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    st.info("📋 PDF export — coming next build.", icon="📄")

    # ── MONTE CARLO SENSITIVITY ───────────────────────────────────────────────
    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    st.markdown(f"<hr style='border-color:{RULE};margin:0 0 1.2rem;'>", unsafe_allow_html=True)
    st.markdown("## MONTE CARLO SENSITIVITY")
    st.markdown(
        f"<p style='font-size:0.84rem;color:{SLATE};margin:-0.4rem 0 1.2rem;'>"
        "500 trials — holds the recommended staffing policy fixed and randomizes the four "
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
            return ["background-color:#0A2818; font-weight:600"] * len(row)
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

        mode_c={"growth":NAVY,"attrition_replace":NAVY_LT,"winter_ramp":C_GREEN,"floor_protect":C_YELLOW,"per_diem":"#9CA3AF"}
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
    st.markdown("## QUARTERLY VOLUME SETTINGS")
    qcols=st.columns(4)
    for qi,(qn,im,col) in enumerate(zip(QUARTER_NAMES,quarterly_impacts,Q_COLORS)):
        with qcols[qi]:
            vq=base_visits*(1+im)*peak_factor
            fq=(vq/budget)*cfg.fte_per_shift_slot
            st.metric(qn,f"{chr(43) if im>=0 else chr(45)}{im*100:.0f}%",delta=f"{vq:.0f} visits -> {fq:.1f} FTE")

    st.plotly_chart(render_hero_chart(pol,cfg,quarterly_impacts,base_visits,budget,peak_factor,title="Annual Demand Curve - Year 1"),use_container_width=True)

    st.markdown("## QUARTERLY SUMMARY  (36-Month Avg)")
    qr=[]
    for qi in range(1,5):
        qm=[mo for mo in mos if mo.quarter==qi]
        qr.append({"Quarter":QUARTER_NAMES[qi-1],
                   "Impact":f"{chr(43) if quarterly_impacts[qi-1]>=0 else chr(45)}{quarterly_impacts[qi-1]*100:.0f}%",
                   "Avg Visits/Day":f"{np.mean([mo.demand_visits_per_day for mo in qm]):.1f}",
                   "Avg Paid FTE":f"{np.mean([mo.paid_fte for mo in qm]):.2f}",
                   "Avg Pts/APC":f"{np.mean([mo.patients_per_provider_per_shift for mo in qm]):.1f}",
                   "Red Months":sum(1 for mo in qm if mo.zone=="Red"),
                   "In-Band %":f"{sum(1 for mo in qm if mo.within_band)/len(qm)*100:.0f}%"})
    st.dataframe(pd.DataFrame(qr),use_container_width=True,hide_index=True)

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
    pal=[NAVY,NAVY_LT,"#4B8BBE",C_YELLOW,C_RED,"#7F1D1D",C_GREEN]
    _av=s2["annual_visits"]
    _sp=(s2["total_permanent_cost"]+s2["total_flex_cost"])/3
    _ss=s2["total_support_cost"]/3
    _spv=_sp/_av if _av else 0; _ssv=_ss/_av if _av else 0
    st.markdown(f"<div style='background:#F0F6FF;border-left:3px solid {NAVY};padding:0.7rem 1rem;"
                f"border-radius:0 3px 3px 0;margin-bottom:1rem;font-size:0.82rem;'>"
                f"<b>SWB/Visit:</b> APC ${_spv:.2f} + Support ${_ssv:.2f} = <b>${s2['annual_swb_per_visit']:.2f}</b>  |  Target ${cfg.swb_target_per_visit:.2f}</div>",
                unsafe_allow_html=True)

    cl,cr=st.columns([1.1,0.9])
    with cl:
        fp2=go.Figure(go.Pie(labels=lc,values=vc,marker_colors=pal,hole=0.54,textinfo="label+percent",
                             textfont=dict(size=11)))
        fp2.add_annotation(text=f"<b>${sum(vc)/1e6:.1f}M</b><br><span style='font-size:11px'>3-year</span>",
                           x=0.5,y=0.5,showarrow=False,font=dict(family="'Playfair Display', serif",size=17,color=INK))
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
    for col_,color in zip(["Permanent","Flex","Support","Turnover","Lost Revenue","Burnout"],[NAVY,NAVY_LT,"#4B8BBE",C_YELLOW,C_RED,"#7F1D1D"]):
        fst.add_bar(x=dfms["Month"],y=dfms[col_],name=col_,marker_color=color)
    fst.update_layout(**mk_layout(height=340,barmode="stack",xaxis=dict(tickangle=-45),title="Monthly Cost Stack"))
    fst.update_yaxes(title_text="Cost ($)")
    st.plotly_chart(fst,use_container_width=True)


# ── TAB 7: Marginal APC Analysis ─────────────────────────────────────────────
with tabs[7]:
    st.markdown("## MARGINAL APC ANALYSIS")
    st.caption("What does one more APC actually cost — and what does it buy you?")
    pol=active_policy()
    ma_delta=st.slider("FTE increment to analyze",0.5,3.0,0.5,0.5,key="ma_delta_slider")
    with st.spinner("Computing marginal impact..."):
        ma=compare_marginal_fte(pol,cfg,delta_fte=ma_delta)

    mc1,mc2,mc3,mc4,mc5=st.columns(5)
    mc1.metric(f"+{ma_delta} FTE Annual Cost",   f"${ma['annual_cost_delta']:+,.0f}")
    mc2.metric("Annual Savings",                  f"${ma['annual_savings']:,.0f}")
    _nc=ma["net_annual"]
    mc3.metric("Net Annual",                      f"${_nc:+,.0f}",delta_color="normal" if _nc>0 else "inverse")
    mc4.metric("Payback",                         "Never" if ma["payback_months"]==float("inf") else f"{ma['payback_months']:.0f} mo")
    mc5.metric("Red+Yellow Months Saved",         f"{ma['red_months_saved']}R + {ma['yellow_months_saved']}Y")

    if ma["net_annual"]>0:
        st.success(f"**Add {ma_delta} FTE** — net ${ma['net_annual']:,.0f}/yr positive. Saves {ma['red_months_saved']}R + {ma['yellow_months_saved']}Y months. Payback {ma['payback_months']:.0f} mo.")
    elif ma["red_months_saved"]>0:
        st.warning(f"Costs ${-ma['net_annual']:,.0f}/yr net but eliminates {ma['red_months_saved']} Red months of burnout risk.")
    else:
        st.info(f"Adding {ma_delta} FTE costs ${ma['annual_cost_delta']:,.0f}/yr with no material zone improvement.")

    m_labels_12=[MONTH_NAMES[i] for i in range(12)]
    fma=go.Figure()
    if cfg.use_load_band:
        fma.add_hrect(y0=cfg.load_band_lo,y1=cfg.load_band_hi,fillcolor="rgba(10,117,84,0.06)",line_width=0)
    fma.add_scatter(x=m_labels_12,y=ma["yr1_load_base"],name=f"Current ({pol.base_fte:.1f} FTE)",
                    mode="lines+markers",line=dict(color=NAVY,width=2.5),marker=dict(size=8,line=dict(color="white",width=1.5)))
    fma.add_scatter(x=m_labels_12,y=ma["yr1_load_plus"],name=f"+{ma_delta} FTE ({pol.base_fte+ma_delta:.1f} FTE)",
                    mode="lines+markers",line=dict(color=C_GREEN,width=2.5,dash="dash"),marker=dict(size=8,line=dict(color="white",width=1.5)))
    for yv,lbl,col in [(budget,"Green ceiling",C_GREEN),(budget+cfg.yellow_threshold_above if cfg.yellow_threshold_above>0 else budget+0.01,"Yellow",C_YELLOW),(budget+cfg.red_threshold_above,"Red",C_RED)]:
        fma.add_hline(y=yv,line_dash="dot",line_color=col,line_width=1.5,
                      annotation_text=lbl,annotation_position="right",annotation_font=dict(size=9,color=col))
    fma.update_layout(**mk_layout(height=340,title=f"Year 1 Load: Current vs +{ma_delta} FTE"))
    fma.update_yaxes(title_text="Pts/APC/Shift")
    st.plotly_chart(fma,use_container_width=True)

    st.markdown("## BREAKEVEN TABLE")
    rows=[]
    for d in [0.5,1.0,1.5,2.0,2.5,3.0]:
        m2=compare_marginal_fte(pol,cfg,delta_fte=d)
        rows.append({"Delta FTE":f"+{d:.1f}","Annual Cost":f"${m2['annual_cost_delta']:+,.0f}",
                     "Annual Savings":f"${m2['annual_savings']:,.0f}","Net Annual":f"${m2['net_annual']:+,.0f}",
                     "Payback (mo)":"Never" if m2["payback_months"]==float("inf") else f"{m2['payback_months']:.0f}",
                     "Red Mo Saved":m2["red_months_saved"],"Yel Mo Saved":m2["yellow_months_saved"],
                     "SWB Delta":f"${m2['swb_delta']:+.2f}"})
    def _cn(v):
        try:
            val=float(str(v).replace("$","").replace(",","").replace("+",""))
            return f"color:{C_GREEN};font-weight:600" if val>0 else (f"color:{C_RED}" if val<0 else "")
        except: return ""
    st.dataframe(pd.DataFrame(rows).style.applymap(_cn,subset=["Net Annual"]),use_container_width=True,hide_index=True)


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
    phases_tl=[("Post -> Sign",cfg.days_to_sign,NAVY),("Sign -> Credentialed",cfg.days_to_credential,NAVY_LT),("Credentialed -> Indep.",cfg.days_to_independent,C_GREEN)]
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




# ──────────────────────────────────────────────────────────────────────────────
st.markdown(f"<hr style='border-color:{RULE};margin:2rem 0 1rem;'>",unsafe_allow_html=True)
st.markdown(f"<p style='font-size:0.68rem;color:#8FA8BF;text-align:center;letter-spacing:0.12em;'>"
            f"PSM | PERMANENT STAFFING MODEL | URGENT CARE | 36-MONTH HORIZON | LOAD-BAND OPTIMIZER | ATTRITION-AS-BURNOUT MODEL"
            f"</p>",unsafe_allow_html=True)
