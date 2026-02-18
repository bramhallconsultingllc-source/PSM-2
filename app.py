"""
PSM — Permanent Staffing Model  v4
McKinsey-grade: editorial authority, ink-on-white precision.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from simulation import (ClinicConfig, SupportStaffConfig, simulate_policy, optimize,
                        MONTH_TO_QUARTER, QUARTER_NAMES, QUARTER_LABELS)

# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
INK       = "#0D1B2A"    # near-black headlines
NAVY      = "#1A3A5C"    # primary brand
NAVY_LT   = "#2E5F8A"    # hover / secondary brand
SLATE     = "#5B6E82"    # body / secondary text
RULE      = "#DDE3EA"    # dividers / grid lines
CANVAS    = "#F8F9FB"    # page background

# Chart roles — maximum contrast, each role instantly legible
C_DEMAND  = "#1A3A5C"    # FTE Required (demand) — deep navy
C_ACTUAL  = "#C84B11"    # Paid FTE (actual) — burnt orange: stands against navy
C_RAMP    = "#C84B11"    # Effective FTE — same family, dashed
C_BARS    = "#B8C9D9"    # Volume bars — cool silver-blue (background data)
C_FLU     = "#8FA8BF"    # Flu uplift bars — slightly darker
C_GREEN   = "#0A7554"
C_YELLOW  = "#9A6400"
C_RED     = "#B91C1C"

Q_COLORS = [NAVY, C_GREEN, C_YELLOW, NAVY_LT]
Q_BG     = ["rgba(26,58,92,0.05)", "rgba(10,117,84,0.04)",
            "rgba(154,100,0,0.04)", "rgba(46,95,138,0.05)"]
Q_MONTH_GROUPS = [[0,1,2],[3,4,5],[6,7,8],[9,10,11]]

HIRE_COLORS = {
    "growth":      NAVY,
    "replacement": NAVY_LT,
    "shed_pause":  C_YELLOW,
    "freeze_flu":  SLATE,
    "none":        RULE,
}
ZONE_COLORS = {"Green": C_GREEN, "Yellow": C_YELLOW, "Red": C_RED}
MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]


def mk_layout(**kw):
    """Base McKinsey chart layout — apply to every figure."""
    base = dict(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="'IBM Plex Sans', sans-serif", size=11, color=SLATE),
        title_font=dict(family="'Playfair Display', serif", size=14, color=INK),
        margin=dict(t=52, b=60, l=56, r=48),
        legend=dict(
            orientation="h", y=-0.22, x=0,
            font=dict(size=11, color=SLATE),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
        ),
        xaxis=dict(
            showgrid=False, zeroline=False,
            tickfont=dict(size=11, color=SLATE),
            linecolor=RULE, linewidth=1, ticks="outside", ticklen=4,
        ),
        yaxis=dict(
            showgrid=True, gridcolor=RULE, gridwidth=1,
            zeroline=False, tickfont=dict(size=11, color=SLATE),
            linecolor=RULE, linewidth=1,
        ),
    )
    base.update(kw)
    return base


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG & CSS
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="PSM — Staffing Optimizer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

/* ── Reset ── */
html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: {CANVAS};
    color: {SLATE};
}}

/* ── Sidebar: deep navy ── */
[data-testid="stSidebar"] {{
    background: {INK} !important;
    border-right: none;
}}
[data-testid="stSidebar"] > div {{ padding-top: 0 !important; }}
[data-testid="stSidebar"] * {{ color: #C8D8E8 !important; }}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] select {{
    background: rgba(255,255,255,0.11) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    color: #F0F6FB !important;
    border-radius: 3px;
    font-size: 0.92rem !important;
    font-weight: 500 !important;
}}
[data-testid="stSidebar"] .stSlider [data-testid="stThumb"] {{
    background: {C_ACTUAL} !important;
}}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stExpander summary p {{
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
    color: #8FAABB !important;
}}
[data-testid="stSidebar"] .stButton > button {{
    background: {C_ACTUAL} !important;
    color: white !important;
    border: none;
    border-radius: 3px;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase;
    padding: 0.65rem 1rem !important;
    transition: background 0.15s;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: #A53C0D !important;
}}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.08) !important; }}

/* ── Main canvas ── */
.main .block-container {{
    background: {CANVAS};
    padding: 2rem 2.5rem 3rem;
    max-width: 1440px;
}}

/* ── Typography ── */
h1 {{
    font-family: 'Playfair Display', serif !important;
    font-size: 2.0rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    letter-spacing: -0.02em;
    line-height: 1.15;
    margin-bottom: 0 !important;
}}
h2 {{
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.16em !important;
    color: {SLATE} !important;
    border: none !important;
    margin-top: 1.8rem !important;
    margin-bottom: 0.75rem !important;
}}
h3 {{
    font-family: 'Playfair Display', serif !important;
    font-size: 1.2rem !important;
    color: {INK} !important;
}}

/* ── KPI Metric cards ── */
[data-testid="stMetric"] {{
    background: white;
    border: 1px solid {RULE};
    border-top: 3px solid {NAVY};
    border-radius: 3px;
    padding: 1rem 1.25rem 0.85rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}
[data-testid="stMetricLabel"] p {{
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: {SLATE} !important;
}}
[data-testid="stMetricValue"] {{
    font-family: 'Playfair Display', serif !important;
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    line-height: 1.1 !important;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.7rem !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {{
    border-bottom: 1px solid {RULE};
    gap: 0;
    background: transparent;
}}
.stTabs [data-baseweb="tab"] {{
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
    color: {SLATE} !important;
    padding: 0.7rem 1.5rem !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -1px;
    background: transparent !important;
    transition: color 0.15s;
}}
.stTabs [aria-selected="true"] {{
    color: {INK} !important;
    border-bottom: 2px solid {NAVY} !important;
    font-weight: 600 !important;
}}

/* ── Alerts ── */
[data-testid="stSuccess"] {{
    background: #F0FDF6; border-left: 3px solid {C_GREEN};
    border-radius: 0 3px 3px 0; font-size: 0.84rem; color: #064E3B;
}}
[data-testid="stError"] {{
    background: #FFF5F5; border-left: 3px solid {C_RED};
    border-radius: 0 3px 3px 0; font-size: 0.84rem;
}}
[data-testid="stInfo"] {{
    background: #EFF6FF; border-left: 3px solid {NAVY};
    border-radius: 0 3px 3px 0; font-size: 0.84rem;
}}
[data-testid="stWarning"] {{
    background: #FFFBEB; border-left: 3px solid {C_YELLOW};
    border-radius: 0 3px 3px 0; font-size: 0.84rem;
}}

/* ── Dividers ── */
hr {{ border-color: {RULE} !important; margin: 1.5rem 0 !important; }}

/* ── Caption ── */
[data-testid="stCaptionContainer"] p {{
    font-size: 0.73rem; color: #8FA8BF; letter-spacing: 0.02em;
}}

/* ── Dataframes ── */
[data-testid="stDataFrame"] {{
    border: 1px solid {RULE}; border-radius: 3px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
for k, v in dict(optimized=False, best_policy=None,
                 manual_policy=None, all_policies=[]).items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"""
    <div style='padding:1.6rem 1.2rem 1.2rem; border-bottom:1px solid rgba(255,255,255,0.08);
                margin-bottom:0.8rem;'>
      <div style='font-family:"IBM Plex Sans",sans-serif; font-size:0.6rem; font-weight:600;
                  text-transform:uppercase; letter-spacing:0.18em; color:#4A6178;
                  margin-bottom:0.35rem;'>Permanent Staffing Model</div>
      <div style='font-family:"Playfair Display",serif; font-size:1.3rem; font-weight:700;
                  color:#E2EBF3; line-height:1.2;'>Staffing Optimizer</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("BASE DEMAND", expanded=True):
        base_visits = st.number_input("Visits / Day", 20.0, 300.0, 80.0, 5.0)
        budget_ppp  = st.number_input("Pts / APC / Shift", 10.0, 60.0, 36.0, 1.0)
        peak_factor = st.slider("Peak Factor", 1.00, 1.30, 1.10, 0.01)

    with st.expander("QUARTERLY SEASONALITY", expanded=True):
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)
        with c1: q1 = st.number_input("Q1 Jan–Mar %", -50, 100, 20, 5, key="q1")
        with c2: q2 = st.number_input("Q2 Apr–Jun %", -50, 100,  0, 5, key="q2")
        with c3: q3 = st.number_input("Q3 Jul–Sep %", -50, 100,-10, 5, key="q3")
        with c4: q4 = st.number_input("Q4 Oct–Dec %", -50, 100,  5, 5, key="q4")
        quarterly_impacts = [q1/100, q2/100, q3/100, q4/100]
        s_idx = [1.0 + quarterly_impacts[MONTH_TO_QUARTER[m]] for m in range(12)]
        pv = [base_visits * s_idx[m] * peak_factor for m in range(12)]
        st.caption(f"Range: **{min(pv):.0f}** – **{max(pv):.0f}** visits/day")

    with st.expander("SHIFT STRUCTURE"):
        op_days   = st.number_input("Operating Days/Week", 1, 7, 7)
        shift_hrs = st.number_input("Hours/Shift", 4.0, 24.0, 12.0, 0.5)
        # Compute the smart default: assume 12-hr operating window, ceil(12 / shift_hrs), cap 1-3
        import math as _math
        _auto_shifts = max(1, min(3, _math.ceil(12.0 / shift_hrs)))
        # Persist user overrides across rerenders; reset when shift_hrs changes
        _shift_key = f"shifts_day_override_{shift_hrs}"
        if _shift_key not in st.session_state:
            st.session_state[_shift_key] = _auto_shifts
        shifts_day = st.number_input(
            "Shifts/Day",
            min_value=1, max_value=3,
            value=st.session_state[_shift_key],
            step=1,
            help=f"Auto-computed as ⌈12 hr day ÷ {shift_hrs:.0f} hr shift⌉ = {_auto_shifts}. Edit to override.",
            key=_shift_key,
        )
        fte_shifts = st.number_input("Shifts/Week per APC", 1.0, 7.0, 3.0, 0.5)
        fte_frac   = st.number_input("FTE Fraction of Contract", 0.1, 1.0, 0.9, 0.05)

    with st.expander("STAFFING POLICY"):
        flu_anchor = st.selectbox("Flu Anchor Month", list(range(1,13)), index=10,
                                  format_func=lambda x: MONTH_NAMES[x-1])
        summer_shed_floor = st.slider("Summer Shed Floor (% of Base)", 60, 100, 85, 5)

    with st.expander("PROVIDER COMPENSATION"):
        perm_cost_i = st.number_input("Perm APC Cost/Year ($)", 100_000, 500_000, 200_000, 10_000, format="%d")
        flex_cost_i = st.number_input("Flex APC Cost/Year ($)", 100_000, 600_000, 280_000, 10_000, format="%d")
        rev_visit   = st.number_input("Net Revenue/Visit ($)", 50.0, 300.0, 110.0, 5.0)
        swb_target  = st.number_input("SWB Target ($/Visit)", 5.0, 100.0, 32.0, 1.0)

    with st.expander("SUPPORT STAFF  (SWB only)"):
        st.caption("Scales with APCs on floor each month. RT is flat per shift. Feeds SWB/visit only — not graphed.")

        # Comp multipliers
        sm1, sm2, sm3 = st.columns(3)
        with sm1: benefits_load = st.number_input("Benefits Load %", 0.0, 60.0, 30.0, 1.0)
        with sm2: bonus_pct_ss  = st.number_input("Bonus %",         0.0, 30.0, 10.0, 1.0)
        with sm3: ot_sick_pct   = st.number_input("OT+Sick %",       0.0, 20.0,  4.0, 0.5)

        # Hourly rates
        st.markdown("<div style='font-size:0.65rem; text-transform:uppercase; "
                    "letter-spacing:0.1em; color:#8FAABB; padding-top:0.4rem;'>Hourly Rates</div>",
                    unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        r3, r4 = st.columns(2)
        r5, r6 = st.columns(2)
        with r1: phys_rate = st.number_input("Physician ($/hr)",  50.0, 300.0, 135.79, 1.0)
        with r2: psr_rate  = st.number_input("PSR ($/hr)",         8.0, 60.0,  21.23, 0.25)
        with r3: app_rate  = st.number_input("APC ($/hr)",        30.0, 200.0,  62.00, 1.0)
        with r4: rt_rate   = st.number_input("RT ($/hr)",          8.0, 80.0,   31.36, 0.25)
        with r5: ma_rate   = st.number_input("MA ($/hr)",          8.0, 60.0,   24.14, 0.25)
        with r6: sup_rate  = st.number_input("Supervisor ($/hr)",  8.0, 80.0,   28.25, 0.25)

        # Ratios
        st.markdown("<div style='font-size:0.65rem; text-transform:uppercase; "
                    "letter-spacing:0.1em; color:#8FAABB; padding-top:0.4rem;'>Staff Ratios (per APC on floor)</div>",
                    unsafe_allow_html=True)
        ra1, ra2 = st.columns(2)
        with ra1: ma_ratio  = st.number_input("MA : APC",  0.0, 4.0, 1.0, 0.25)
        with ra2: psr_ratio = st.number_input("PSR : APC", 0.0, 4.0, 1.0, 0.25)
        rt_flat  = st.number_input("RT FTE (flat per shift)", 0.0, 4.0, 1.0, 0.5)

        # Physician supervision — cost added only when hours > 0
        st.markdown("<div style='font-size:0.65rem; text-transform:uppercase; "
                    "letter-spacing:0.1em; color:#8FAABB; padding-top:0.4rem;'>"
                    "Physician Supervision  (cost added only when hrs &gt; 0)</div>",
                    unsafe_allow_html=True)
        sv1, sv2 = st.columns(2)
        with sv1: phys_sup_hrs  = st.number_input("Physician Supervision (hrs/mo)", 0.0, 200.0, 0.0, 5.0,
                                                   help="Physician supervisor billed at Physician $/hr × hrs/mo × multiplier")
        with sv2: sup_admin_hrs = st.number_input("Supervisor Admin (hrs/mo)",       0.0, 200.0, 0.0, 5.0,
                                                   help="Operations supervisor billed at Supervisor $/hr × hrs/mo × multiplier")
        if phys_sup_hrs > 0 or sup_admin_hrs > 0:
            _mult = 1 + benefits_load/100 + bonus_pct_ss/100 + ot_sick_pct/100
            _phys_mo  = phys_sup_hrs  * phys_rate * _mult if phys_sup_hrs  > 0 else 0
            _sup_mo   = sup_admin_hrs * sup_rate   * _mult if sup_admin_hrs > 0 else 0
            st.caption(
                f"Supervision cost: "
                + (f"Physician **${_phys_mo:,.0f}/mo**" if phys_sup_hrs > 0 else "")
                + (" · " if phys_sup_hrs > 0 and sup_admin_hrs > 0 else "")
                + (f"Supervisor **${_sup_mo:,.0f}/mo**" if sup_admin_hrs > 0 else "")
            )

    with st.expander("HIRING PHYSICS"):
        days_sign  = st.number_input("Days to Sign",           7, 120, 30, 7)
        days_cred  = st.number_input("Days to Credential",     7, 180, 60, 7)
        days_ind   = st.number_input("Days to Independence",  14, 180, 90, 7)
        annual_att = st.number_input("Annual Attrition Rate %", 1.0, 50.0, 18.0, 1.0,
                                     help="Converted to monthly rate internally (÷ 12)")
        st.caption(f"Monthly rate: **{annual_att/12:.2f}%**")

    with st.expander("TURNOVER & PENALTY RATES"):
        st.caption("Costs derived as % of annual APC salary — no manual dollar entry needed.")
        tp1, tp2 = st.columns(2)
        tp3, tp4 = st.columns(2)
        with tp1:
            turnover_pct = st.number_input("Replacement Cost\n(% of salary)", 10.0, 150.0, 40.0, 5.0,
                                           help="Recruiting + temp coverage + onboarding. Default 40% ≈ $80k on $200k salary.")
        with tp2:
            burnout_pct  = st.number_input("Burnout Penalty\n(% salary/red mo)", 5.0, 100.0, 25.0, 5.0,
                                           help="Risk cost per Red month. Default 25% ≈ $50k on $200k salary.")
        with tp3:
            overstaff_pen= st.number_input("Overstaff Penalty\n($/FTE-month)", 500, 20_000, 3_000, 500, format="%d")
        with tp4:
            swb_pen      = st.number_input("SWB Violation\nPenalty ($)", 50_000, 2_000_000, 500_000, 50_000, format="%d")

        # Show derived dollar amounts for transparency
        _rep_cost = perm_cost_i * turnover_pct / 100
        _burn_cost = perm_cost_i * burnout_pct / 100
        st.caption(f"Replacement cost: **${_rep_cost:,.0f}** · Burnout/red month: **${_burn_cost:,.0f}**")

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    run_opt = st.button("RUN OPTIMIZER", type="primary", use_container_width=True)

# ── Config ────────────────────────────────────────────────────────────────────
support_cfg = SupportStaffConfig(
    physician_rate_hr=phys_rate,
    app_rate_hr=app_rate,
    psr_rate_hr=psr_rate,
    ma_rate_hr=ma_rate,
    rt_rate_hr=rt_rate,
    supervisor_rate_hr=sup_rate,
    ma_ratio=ma_ratio,
    psr_ratio=psr_ratio,
    rt_flat_fte=rt_flat,
    supervisor_hrs_mo=phys_sup_hrs,
    supervisor_admin_mo=sup_admin_hrs,
    benefits_load_pct=benefits_load/100,
    bonus_pct=bonus_pct_ss/100,
    ot_sick_pct=ot_sick_pct/100,
)

# flu_uplift removed — seasonality % is the sole demand modifier
_zero_flu = [0.0] * 12

cfg = ClinicConfig(
    base_visits_per_day=base_visits,
    budgeted_patients_per_provider_per_day=budget_ppp,
    peak_factor=peak_factor,
    quarterly_volume_impact=quarterly_impacts,
    operating_days_per_week=int(op_days),
    shifts_per_day=int(shifts_day),
    shift_hours=shift_hrs,
    fte_shifts_per_week=fte_shifts,
    fte_fraction=fte_frac,
    flu_anchor_month=flu_anchor,
    summer_shed_floor_pct=summer_shed_floor / 100,
    annual_provider_cost_perm=perm_cost_i,
    annual_provider_cost_flex=flex_cost_i,
    net_revenue_per_visit=rev_visit,
    swb_target_per_visit=swb_target,
    support=support_cfg,
    days_to_sign=days_sign,
    days_to_credential=days_cred,
    days_to_independent=days_ind,
    annual_attrition_pct=annual_att,
    turnover_replacement_pct=turnover_pct,
    burnout_pct_per_red_month=burnout_pct,
    overstaff_penalty_per_fte_month=overstaff_pen,
    swb_violation_penalty=swb_pen,
)

if run_opt:
    with st.spinner("Running grid search across 36-month horizon…"):
        best, all_p = optimize(cfg)
    st.session_state.update(
        best_policy=best, all_policies=all_p, optimized=True,
        manual_b=best.base_fte, manual_w=best.winter_fte, manual_policy=None
    )
    st.success(f"Optimizer complete — {len(all_p):,} policies evaluated")


# ══════════════════════════════════════════════════════════════════════════════
# PRE-OPTIMIZER LANDING
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.optimized:
    st.markdown("## PERMANENT STAFFING MODEL")
    st.title("Urgent Care\nStaffing Optimizer")
    st.markdown(f"<p style='font-family:\"IBM Plex Sans\",sans-serif; color:{SLATE}; "
                f"font-size:0.9rem; margin-top:-0.4rem; margin-bottom:2rem;'>"
                f"36-month horizon &nbsp;·&nbsp; quarterly seasonality &nbsp;·&nbsp; "
                f"natural attrition shed</p>", unsafe_allow_html=True)
    st.info("Configure your clinic profile in the sidebar, then click **RUN OPTIMIZER**.")
    st.markdown("## DEMAND PREVIEW")

    si = cfg.seasonality_index
    mv = [base_visits*si[m]*peak_factor for m in range(12)]
    mv_nf = mv  # no flu uplift — seasonality IS the demand signal
    fr = [v/budget_ppp*cfg.fte_per_shift_slot for v in mv]
    bft = (base_visits/budget_ppp)*cfg.fte_per_shift_slot

    fp = make_subplots(specs=[[{"secondary_y": True}]])
    for qi, (mq, bg) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        fp.add_vrect(x0=mq[0]-0.5, x1=mq[-1]+0.5, fillcolor=bg, layer="below", line_width=0)
        im = quarterly_impacts[qi]
        fp.add_annotation(x=mq[1], y=max(mv)*1.09,
                          text=f"<b>{QUARTER_LABELS[qi]}</b>  {'+' if im>=0 else ''}{im*100:.0f}%",
                          showarrow=False, font=dict(size=11, color=Q_COLORS[qi]),
                          bgcolor="rgba(255,255,255,0.9)", borderpad=3)
    fp.add_bar(x=MONTH_NAMES, y=mv_nf, name="Seasonal volume", marker_color=C_BARS)
    fp.add_scatter(x=MONTH_NAMES, y=fr, name="FTE Required", mode="lines+markers",
                   line=dict(color=C_DEMAND, width=3),
                   marker=dict(size=9, color=C_DEMAND, symbol="diamond",
                               line=dict(color="white", width=2)),
                   secondary_y=True)
    fp.add_hline(y=bft, line_dash="dash", line_color=SLATE, line_width=1.5,
                 annotation_text=f"Baseline FTE {bft:.1f}",
                 annotation_font=dict(size=10, color=SLATE), secondary_y=True)
    fp.update_layout(**mk_layout(height=400, barmode="stack",
                                 title="Annual Volume & FTE Requirement by Month"))
    fp.update_yaxes(title_text="Visits / Day", secondary_y=False)
    fp.update_yaxes(title_text="FTE Required", secondary_y=True, showgrid=False)
    st.plotly_chart(fp, use_container_width=True)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def active_policy():
    return st.session_state.get("manual_policy") or st.session_state.best_policy

def mlabel(mo):
    return f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}"

best = st.session_state.best_policy
s    = best.summary
lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent


# ══════════════════════════════════════════════════════════════════════════════
# HERO CHART
# Two-panel architecture: bars on top, lines on bottom.
# Lines live in their own clean white space — they can never be lost.
# ══════════════════════════════════════════════════════════════════════════════
def render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp,
                      peak_factor, title=None):
    yr1      = [mo for mo in pol.months if mo.year == 1]
    labels   = [MONTH_NAMES[mo.calendar_month - 1] for mo in yr1]

    visits_nf = [base_visits * cfg.seasonality_index[mo.calendar_month-1] * peak_factor
                 for mo in yr1]
    visits_fl = visits_nf  # no separate flu uplift — seasonality IS the demand curve

    fte_req   = [mo.demand_fte_required for mo in yr1]
    paid_fte  = [mo.paid_fte            for mo in yr1]
    eff_fte   = [mo.effective_fte       for mo in yr1]

    summer_floor = pol.base_fte * cfg.summer_shed_floor_pct
    dot_colors   = [HIRE_COLORS.get(mo.hiring_mode, SLATE) for mo in yr1]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.40, 0.60],
    )

    # ── Panel 1: Volume (bars only — clean background signal) ─────────────────
    for qi, (mq, bg) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        fig.add_vrect(x0=mq[0]-0.5, x1=mq[-1]+0.5,
                      fillcolor=bg, layer="below", line_width=0, row=1, col=1)

    fig.add_bar(x=labels, y=visits_nf, name="Seasonal volume",
                marker_color=C_BARS, marker_line_width=0, row=1, col=1)
    fig.add_hline(y=base_visits, line_dash="dash", line_color=SLATE, line_width=1,
                  annotation_text=f"Base {base_visits:.0f}/day",
                  annotation_position="right",
                  annotation_font=dict(size=9, color=SLATE), row=1, col=1)

    # Quarter labels above bars
    for qi, (mq, _) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        im = quarterly_impacts[qi]
        fig.add_annotation(
            row=1, col=1, xref="x", yref="paper",
            x=mq[1], y=1.0,
            text=f"<b>{QUARTER_LABELS[qi]}</b>  {'+' if im>=0 else ''}{im*100:.0f}%",
            showarrow=False, yanchor="bottom",
            font=dict(size=10, color=Q_COLORS[qi], family="IBM Plex Sans, sans-serif"),
            bgcolor="rgba(255,255,255,0.92)", borderpad=3,
        )

    # ── Panel 2: FTE lines (clean white, maximum legibility) ─────────────────
    for qi, (mq, bg) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        fig.add_vrect(x0=mq[0]-0.5, x1=mq[-1]+0.5,
                      fillcolor=bg, layer="below", line_width=0, row=2, col=1)

    # Subtle gap fill: green when overstaffed, red when understaffed
    for i in range(len(labels)):
        gap_color = ("rgba(10,117,84,0.08)" if paid_fte[i] >= fte_req[i]
                     else "rgba(185,28,28,0.08)")
        fig.add_vrect(x0=i-0.48, x1=i+0.48, fillcolor=gap_color,
                      layer="below", line_width=0, row=2, col=1)

    # Policy reference lines — thin, labeled on right
    for yval, label, color in [
        (pol.winter_fte,  f"Winter target  {pol.winter_fte:.1f}", NAVY),
        (pol.base_fte,    f"Base  {pol.base_fte:.1f}",           SLATE),
        (summer_floor,    f"Summer floor  {summer_floor:.1f}",   C_GREEN),
    ]:
        fig.add_hline(y=yval, line_dash="dot", line_color=color, line_width=1.2,
                      annotation_text=label, annotation_position="right",
                      annotation_font=dict(size=9, color=color,
                                           family="IBM Plex Sans, sans-serif"),
                      row=2, col=1)

    # Effective FTE — dashed, semi-transparent (ramp drag layer)
    fig.add_scatter(
        x=labels, y=eff_fte,
        name="Effective FTE (ramp-adjusted)",
        mode="lines",
        line=dict(color=C_ACTUAL, width=2, dash="dash"),
        opacity=0.45,
        row=2, col=1,
    )

    # Paid FTE — bold burnt orange, hiring-mode dots
    fig.add_scatter(
        x=labels, y=paid_fte,
        name="Paid FTE (actual headcount)",
        mode="lines+markers",
        line=dict(color=C_ACTUAL, width=3.5),
        marker=dict(
            size=11, color=dot_colors,
            line=dict(color="white", width=2.5),
        ),
        row=2, col=1,
    )

    # FTE Required — deep navy, diamond markers (demand is the anchor)
    fig.add_scatter(
        x=labels, y=fte_req,
        name="FTE Required (demand)",
        mode="lines+markers",
        line=dict(color=C_DEMAND, width=3.5),
        marker=dict(
            size=9, symbol="diamond",
            color=C_DEMAND, line=dict(color="white", width=2),
        ),
        row=2, col=1,
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        height=580,
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        barmode="stack",
        font=dict(family="'IBM Plex Sans', sans-serif", size=11, color=SLATE),
        title=dict(
            text=title or "Annual Demand & Staffing Model — Year 1",
            font=dict(family="'Playfair Display', serif", size=15, color=INK),
            x=0, xanchor="left",
        ),
        margin=dict(t=60, b=80, l=60, r=140),
        legend=dict(
            orientation="h", y=-0.16, x=0,
            font=dict(size=11, color=SLATE, family="IBM Plex Sans, sans-serif"),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            itemsizing="constant",
        ),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=RULE,
                   tickfont=dict(size=11)),
        xaxis2=dict(showgrid=False, zeroline=False, linecolor=RULE,
                    tickfont=dict(size=11, color=SLATE)),
        yaxis=dict(title="Visits / Day", showgrid=True, gridcolor=RULE,
                   zeroline=False, tickfont=dict(size=11)),
        yaxis2=dict(title="FTE", showgrid=True, gridcolor=RULE,
                    zeroline=False, tickfont=dict(size=11)),
    )

    # Panel divider line
    fig.add_hline(y=0, line_color=RULE, line_width=1, row=2, col=1)

    # Panel labels (top-left of each panel)
    for row, text in [(1, "PATIENT VOLUME"), (2, "FTE — DEMAND vs ACTUAL STAFFING")]:
        fig.add_annotation(
            row=row, col=1, xref="paper", yref="paper",
            x=0, y=1.01, xanchor="left", yanchor="bottom",
            text=f"<span style='font-size:9px; font-weight:600; letter-spacing:0.12em; "
                 f"color:{SLATE}; font-family:IBM Plex Sans,sans-serif;'>{text}</span>",
            showarrow=False, bgcolor="rgba(0,0,0,0)",
        )

    return fig


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD HEADER + KPIs
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## PERMANENT STAFFING MODEL")
st.title("Staffing Policy Recommendation")
st.markdown(
    f"<p style='font-family:\"IBM Plex Sans\",sans-serif; color:{SLATE}; "
    f"font-size:0.87rem; margin-top:-0.5rem; margin-bottom:1.5rem;'>"
    f"36-month horizon &nbsp;·&nbsp; quarterly seasonality &nbsp;·&nbsp; "
    f"natural attrition shed</p>",
    unsafe_allow_html=True,
)
st.markdown(f"<hr style='border-color:{RULE}; margin:0 0 1.5rem;'>",
            unsafe_allow_html=True)

st.markdown("## RECOMMENDED POLICY")
k1,k2,k3,k4,k5,k6 = st.columns(6)
k1.metric("Base FTE",          f"{best.base_fte:.1f}")
k2.metric("Winter FTE",        f"{best.winter_fte:.1f}")
k3.metric("Summer Floor FTE",  f"{best.base_fte * cfg.summer_shed_floor_pct:.1f}")
k4.metric("Post Req By",       MONTH_NAMES[best.req_post_month-1])
k5.metric("SWB / Visit",       f"${s['annual_swb_per_visit']:.2f}",
          delta=f"Target ${cfg.swb_target_per_visit:.2f}",
          delta_color="inverse" if s["swb_violation"] else "normal")
k6.metric("3-Year Score",      f"${s['total_score']/1e6:.2f}M")

st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

if s["swb_violation"]:
    st.error(f"SWB/Visit target exceeded — ${s['annual_swb_per_visit']:.2f} vs "
             f"${cfg.swb_target_per_visit:.2f} target")
else:
    st.success(
        f"SWB/Visit on target — **${s['annual_swb_per_visit']:.2f}** vs "
        f"${cfg.swb_target_per_visit:.2f} target  ·  ~{s['annual_visits']:,.0f} annual visits"
    )

z1,z2,z3,_ = st.columns([1,1,1,3])
z1.metric("🟢 Green",  s["green_months"])
z2.metric("🟡 Yellow", s["yellow_months"])
z3.metric("🔴 Red",    s["red_months"])

st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

# ── HERO CHART ────────────────────────────────────────────────────────────────
st.plotly_chart(
    render_hero_chart(active_policy(), cfg, quarterly_impacts,
                      base_visits, budget_ppp, peak_factor),
    use_container_width=True,
)

# Hiring mode key
hm_labels = {
    "growth":      ("●", "Growth hire",   NAVY),
    "replacement": ("●", "Replacement",   NAVY_LT),
    "shed_pause":  ("●", "Natural shed",  C_YELLOW),
    "freeze_flu":  ("●", "Flu freeze",    SLATE),
}
yr1_mos = [mo for mo in active_policy().months if mo.year == 1]
counts = {m: sum(1 for mo in yr1_mos if mo.hiring_mode == m) for m in hm_labels}
parts = [
    f"<span style='color:{col}; font-weight:600;'>{sym}</span> "
    f"<span style='color:{SLATE}'>{lbl} ({counts[k]} mo)</span>"
    for k, (sym, lbl, col) in hm_labels.items() if counts[k] > 0
]
st.markdown(
    f"<p style='font-size:0.72rem; color:{SLATE}; margin-top:-0.3rem; "
    f"font-family:\"IBM Plex Sans\",sans-serif; letter-spacing:0.01em;'>"
    f"Dot color indicates hiring action: &nbsp; " + "  &nbsp;·&nbsp;  ".join(parts) +
    "</p>",
    unsafe_allow_html=True,
)

st.markdown(f"<hr style='border-color:{RULE}; margin:1.5rem 0;'>",
            unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "36-Month Load", "Shift Coverage", "Seasonality",
    "Cost Breakdown", "Manual Override", "Policy Heatmap",
    "Req Timing", "Data Table",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 36-Month Load
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    pol  = active_policy()
    mos  = pol.months
    lbls = [mlabel(mo) for mo in mos]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.55, 0.45])

    for i, mo in enumerate(mos):
        zc = {"Green":"rgba(10,117,84,0.07)","Yellow":"rgba(154,100,0,0.10)",
               "Red":"rgba(185,28,28,0.12)"}[mo.zone]
        fig.add_vrect(x0=i-0.5, x1=i+0.5, fillcolor=zc, layer="below",
                      line_width=0, row=1, col=1)

    fig.add_scatter(
        x=lbls, y=[mo.patients_per_provider_per_shift for mo in mos],
        mode="lines+markers", name="Pts / APC / Shift",
        line=dict(color=NAVY, width=2.5),
        marker=dict(color=[ZONE_COLORS[mo.zone] for mo in mos], size=7,
                    line=dict(color="white", width=1.5)),
        row=1, col=1,
    )
    budget = cfg.budgeted_patients_per_provider_per_day
    for yv, lbl, col in [
        (budget,                            "Budget",  C_GREEN),
        (budget+cfg.yellow_threshold_above, "Yellow",  C_YELLOW),
        (budget+cfg.red_threshold_above,    "Red",     C_RED),
    ]:
        fig.add_hline(y=yv, line_dash="dot", line_color=col, line_width=1.5,
                      annotation_text=lbl, annotation_position="right",
                      annotation_font=dict(size=9, color=col), row=1, col=1)

    fig.add_scatter(x=lbls, y=[mo.paid_fte for mo in mos], name="Paid FTE",
                    mode="lines", line=dict(color=C_ACTUAL, width=2.5), row=2, col=1)
    fig.add_scatter(x=lbls, y=[mo.effective_fte for mo in mos], name="Effective FTE",
                    mode="lines", line=dict(color=C_ACTUAL, width=1.5, dash="dash"),
                    opacity=0.5, row=2, col=1)
    fig.add_scatter(x=lbls, y=[mo.demand_fte_required for mo in mos], name="FTE Required",
                    mode="lines", line=dict(color=NAVY, width=2.5, dash="dot"), row=2, col=1)
    fig.add_bar(x=lbls, y=[mo.flex_fte for mo in mos], name="Flex FTE",
                marker_color="rgba(185,28,28,0.30)", row=2, col=1)

    shed_x = [lbls[i] for i,mo in enumerate(mos) if mo.hiring_mode=="shed_pause"]
    shed_y = [mos[i].paid_fte for i,mo in enumerate(mos) if mo.hiring_mode=="shed_pause"]
    if shed_x:
        fig.add_scatter(x=shed_x, y=shed_y, mode="markers", name="Natural shed",
                        marker=dict(symbol="triangle-down", size=9, color=C_YELLOW,
                                    line=dict(color="white", width=1.5)), row=2, col=1)

    fig.update_layout(**mk_layout(height=620, xaxis2=dict(tickangle=-45),
                                  title="36-Month APC Load & FTE Trajectory"))
    fig.update_yaxes(title_text="Pts / APC / Shift", showgrid=True,
                     gridcolor=RULE, row=1, col=1)
    fig.update_yaxes(title_text="FTE", showgrid=True, gridcolor=RULE, row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # Zone strip
    fz = go.Figure(go.Bar(x=lbls, y=[1]*36,
                           marker_color=[ZONE_COLORS[mo.zone] for mo in mos],
                           showlegend=False,
                           hovertext=[f"{mlabel(mo)}: {mo.zone}  {mo.patients_per_provider_per_shift:.1f} pts/prov" for mo in mos]))
    fz.update_layout(height=44, margin=dict(t=0,b=0,l=0,r=0),
                     paper_bgcolor="white", plot_bgcolor="white",
                     yaxis=dict(visible=False), xaxis=dict(visible=False))
    st.plotly_chart(fz, use_container_width=True)

    hmc = {m: sum(1 for mo in mos if mo.hiring_mode==m)
           for m in ["growth","replacement","shed_pause","freeze_flu","none"]}
    hml = {"growth":"Growth hire","replacement":"Replacement",
           "shed_pause":"Natural shed","freeze_flu":"Flu freeze","none":"No action"}
    st.caption("  ·  ".join(f"{hml[k]}: {v} months" for k,v in hmc.items() if v>0))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Shift Coverage
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    pol  = active_policy()
    mos  = pol.months
    lbls = [mlabel(mo) for mo in mos]

    st.markdown("## SHIFT COVERAGE MODEL")
    e1,e2,e3,e4 = st.columns(4)
    e1.metric("Shift Slots / Week",  f"{cfg.shift_slots_per_week:.0f}")
    e2.metric("Shifts/Week per FTE", f"{cfg.shifts_per_week_per_fte:.2f}")
    e3.metric("FTE per Shift Slot",  f"{cfg.fte_per_shift_slot:.2f}")
    e4.metric("Baseline FTE Needed", f"{(base_visits/budget_ppp)*cfg.fte_per_shift_slot:.2f}")

    prov_needed   = [mo.demand_providers_per_shift for mo in mos]
    prov_on_floor = [mo.providers_on_floor for mo in mos]
    flex_prov     = [mo.flex_fte/cfg.fte_per_shift_slot if cfg.fte_per_shift_slot else 0 for mo in mos]
    gap           = [mo.shift_coverage_gap for mo in mos]

    fc = go.Figure()
    fc.add_scatter(x=lbls, y=prov_needed, name="Providers Needed",
                   mode="lines", line=dict(color=NAVY, width=2.5, dash="dot"))
    fc.add_scatter(x=lbls, y=prov_on_floor, name="Providers on Floor",
                   mode="lines+markers", line=dict(color=C_ACTUAL, width=2.5),
                   marker=dict(size=7, color=C_ACTUAL, line=dict(color="white", width=1.5)))
    fc.add_bar(x=lbls, y=flex_prov, name="Flex Providers",
               marker_color="rgba(185,28,28,0.28)")
    fc.update_layout(**mk_layout(height=340, barmode="overlay",
                                 xaxis=dict(tickangle=-45),
                                 title="Concurrent APCs: Required vs On Floor"))
    fc.update_yaxes(title_text="Concurrent APCs")
    st.plotly_chart(fc, use_container_width=True)

    gap_colors = [C_RED if g>0.05 else (C_YELLOW if g>-0.05 else C_GREEN) for g in gap]
    fg = go.Figure(go.Bar(x=lbls, y=gap, marker_color=gap_colors,
                           hovertext=[f"{mlabel(mo)}: {g:+.2f}" for mo,g in zip(mos,gap)]))
    fg.add_hline(y=0, line_color=SLATE, line_width=1)
    fg.update_layout(**mk_layout(height=220, xaxis=dict(tickangle=-45),
                                 title="Coverage Gap  ( + = understaffed  ·  − = overstaffed )"))
    fg.update_yaxes(title_text="APCs")
    st.plotly_chart(fg, use_container_width=True)

    df_sh = pd.DataFrame([{
        "Month": mlabel(mo), "Q": f"Q{mo.quarter}",
        "Visits/Day": round(mo.demand_visits_per_day,1),
        "Seasonal Mult": f"{mo.seasonal_multiplier:.2f}×",
        "Providers Needed": round(mo.demand_providers_per_shift,2),
        "FTE Required": round(mo.demand_fte_required,2),
        "Paid FTE": round(mo.paid_fte,2), "Effective FTE": round(mo.effective_fte,2),
        "Providers on Floor": round(mo.providers_on_floor,2),
        "Coverage Gap": round(mo.shift_coverage_gap,2),
        "Hiring Mode": mo.hiring_mode, "Zone": mo.zone,
    } for mo in mos])

    def _sz(v): return {"Green":"background-color:#ECFDF5","Yellow":"background-color:#FFFBEB",
                        "Red":"background-color:#FEF2F2"}.get(v,"")
    def _sg(v):
        try:
            f=float(v)
            if f>0.1: return f"color:{C_RED};font-weight:600"
            if f<-0.1: return f"color:{C_GREEN}"
        except: pass
        return ""

    st.dataframe(df_sh.style.applymap(_sz, subset=["Zone"])
                             .applymap(_sg, subset=["Coverage Gap"]),
                 use_container_width=True, height=440)
    st.download_button("Download CSV", df_sh.to_csv(index=False),
                       "psm_shift.csv", "text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Seasonality
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    pol = active_policy()
    mos = pol.months

    st.markdown("## QUARTERLY VOLUME SETTINGS")
    qcols = st.columns(4)
    for qi, (qn, im, col) in enumerate(zip(QUARTER_NAMES, quarterly_impacts, Q_COLORS)):
        with qcols[qi]:
            vq = base_visits*(1+im)*peak_factor
            fq = (vq/budget_ppp)*cfg.fte_per_shift_slot
            st.metric(qn, f"{'+' if im>=0 else ''}{im*100:.0f}%",
                      delta=f"{vq:.0f} visits/day → {fq:.1f} FTE")

    st.plotly_chart(
        render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp,
                          peak_factor, title="Annual Demand Curve — Year 1"),
        use_container_width=True,
    )

    st.markdown("## QUARTERLY SUMMARY  (36-Month Average)")
    qr = []
    for qi in range(1,5):
        qm=[mo for mo in mos if mo.quarter==qi]
        qr.append({
            "Quarter": QUARTER_NAMES[qi-1],
            "Impact": f"{'+' if quarterly_impacts[qi-1]>=0 else ''}{quarterly_impacts[qi-1]*100:.0f}%",
            "Avg Visits/Day": f"{np.mean([mo.demand_visits_per_day for mo in qm]):.1f}",
            "Avg FTE Required": f"{np.mean([mo.demand_fte_required for mo in qm]):.2f}",
            "Avg Paid FTE": f"{np.mean([mo.paid_fte for mo in qm]):.2f}",
            "Avg Pts/Prov": f"{np.mean([mo.patients_per_provider_per_shift for mo in qm]):.1f}",
            "Red Months": sum(1 for mo in qm if mo.zone=="Red"),
            "Shed Months": sum(1 for mo in qm if mo.hiring_mode=="shed_pause"),
        })
    st.dataframe(pd.DataFrame(qr), use_container_width=True, hide_index=True)

    st.markdown("## NATURAL ATTRITION SHED TRAJECTORY")
    fs = go.Figure()
    for i,mo in enumerate(mos):
        if mo.quarter==3:
            fs.add_vrect(x0=i-0.5, x1=i+0.5,
                         fillcolor="rgba(154,100,0,0.06)", layer="below", line_width=0)
    fs.add_scatter(
        x=[mlabel(mo) for mo in mos], y=[mo.paid_fte for mo in mos],
        mode="lines+markers", name="Paid FTE",
        line=dict(color=C_ACTUAL, width=3),
        marker=dict(color=[HIRE_COLORS.get(mo.hiring_mode, SLATE) for mo in mos],
                    size=9, line=dict(color="white", width=2)),
    )
    for yv, lbl, col in [
        (best.winter_fte, f"Winter {best.winter_fte:.1f}", NAVY),
        (best.base_fte,   f"Base {best.base_fte:.1f}",    SLATE),
        (best.base_fte*cfg.summer_shed_floor_pct,
         f"Summer floor {best.base_fte*cfg.summer_shed_floor_pct:.1f}", C_GREEN),
    ]:
        fs.add_hline(y=yv, line_dash="dot", line_color=col, line_width=1.5,
                     annotation_text=lbl, annotation_position="right",
                     annotation_font=dict(size=9, color=col))
    fs.update_layout(**mk_layout(height=320, xaxis=dict(tickangle=-45),
                                 title="Paid FTE Over 36 Months  (shaded = summer shed window)"))
    fs.update_yaxes(title_text="Paid FTE")
    st.plotly_chart(fs, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Cost Breakdown
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    pol = active_policy(); s2 = pol.summary; mos = pol.months

    st.markdown("## 3-YEAR COST BREAKDOWN")
    lc  = ["Permanent","Flex","Support Staff","Turnover","Lost Revenue","Burnout","Overstaff"]
    vc  = [s2["total_permanent_cost"], s2["total_flex_cost"], s2["total_support_cost"],
           s2["total_turnover_cost"],  s2["total_lost_revenue"],
           s2["total_burnout_penalty"], s2["total_overstaff_penalty"]]
    pal = [NAVY, NAVY_LT, "#4B8BBE", C_YELLOW, C_RED, "#7F1D1D", C_GREEN]

    # SWB breakdown annotation
    _swb_prov    = (s2["total_permanent_cost"] + s2["total_flex_cost"]) / 3
    _swb_support = s2["total_support_cost"] / 3
    _ann_visits  = s2["annual_visits"]
    _swb_prov_v  = _swb_prov   / _ann_visits if _ann_visits else 0
    _swb_supp_v  = _swb_support / _ann_visits if _ann_visits else 0
    st.markdown(
        f"<div style='background:#F0F6FF; border-left:3px solid {NAVY}; "
        f"padding:0.7rem 1rem; border-radius:0 3px 3px 0; margin-bottom:1rem; "
        f"font-size:0.82rem;'>"
        f"<b>SWB/Visit breakdown:</b> &nbsp; "
        f"APC ${_swb_prov_v:.2f} &nbsp;+&nbsp; "
        f"Support staff ${_swb_supp_v:.2f} &nbsp;=&nbsp; "
        f"<b>${s2['annual_swb_per_visit']:.2f}</b> total &nbsp;·&nbsp; "
        f"Target ${cfg.swb_target_per_visit:.2f}"
        f"</div>",
        unsafe_allow_html=True
    )

    cl, cr = st.columns([1.1, 0.9])
    with cl:
        fp2 = go.Figure(go.Pie(
            labels=lc, values=vc, marker_colors=pal, hole=0.54,
            textinfo="label+percent",
            textfont=dict(family="IBM Plex Sans, sans-serif", size=11),
        ))
        fp2.add_annotation(
            text=f"<b>${sum(vc)/1e6:.1f}M</b><br><span style='font-size:11px'>3-year total</span>",
            x=0.5, y=0.5, showarrow=False,
            font=dict(family="Playfair Display, serif", size=17, color=INK),
        )
        fp2.update_layout(**mk_layout(height=380, title="3-Year Cost Mix",
                           margin=dict(t=40,b=40,l=16,r=16),
                           legend=dict(orientation="v", x=1.02, y=0.5)))
        st.plotly_chart(fp2, use_container_width=True)
    with cr:
        dfc = pd.DataFrame({"Component": lc,
                             "3-Year ($)": [f"${v:,.0f}" for v in vc],
                             "Annual Avg": [f"${v/3:,.0f}" for v in vc],
                             "$/Visit":    [f"${v/3/(_ann_visits or 1):.2f}" for v in vc]})
        st.dataframe(dfc, use_container_width=True, hide_index=True)
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        r1,r2,r3 = st.columns(3)
        r1.metric("Total 3-Year", f"${sum(vc)/1e6:.2f}M")
        r2.metric("Annual Avg",   f"${sum(vc)/3/1e6:.2f}M")
        r3.metric("SWB/Visit",    f"${s2['annual_swb_per_visit']:.2f}")

    dfms = pd.DataFrame([{
        "Month":mlabel(mo), "Permanent":mo.permanent_cost, "Flex":mo.flex_cost,
        "Support":mo.support_cost, "Turnover":mo.turnover_cost,
        "Lost Revenue":mo.lost_revenue, "Burnout":mo.burnout_penalty,
    } for mo in mos])
    fst = go.Figure()
    for col_, color in zip(["Permanent","Flex","Support","Turnover","Lost Revenue","Burnout"],
                            [NAVY, NAVY_LT, "#4B8BBE", C_YELLOW, C_RED, "#7F1D1D"]):
        fst.add_bar(x=dfms["Month"], y=dfms[col_], name=col_, marker_color=color)
    fst.update_layout(**mk_layout(height=340, barmode="stack",
                                  xaxis=dict(tickangle=-45), title="Monthly Cost Stack"))
    fst.update_yaxes(title_text="Cost ($)")
    st.plotly_chart(fst, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Manual Override
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("## MANUAL OVERRIDE")
    st.caption("Adjust Base and Winter FTE to explore staffing scenarios against the optimizer recommendation.")

    ca, cb = st.columns(2)
    with ca:
        manual_b = st.slider("Base FTE", 1.0, 25.0,
                             float(st.session_state.get("manual_b", best.base_fte)), 0.5)
    with cb:
        manual_w = st.slider("Winter FTE", manual_b, 35.0,
                             float(max(st.session_state.get("manual_w", best.winter_fte), manual_b)), 0.5)

    man_pol = simulate_policy(manual_b, manual_w, cfg)
    st.session_state.manual_policy = man_pol
    ms = man_pol.summary

    st.markdown("## IMPACT vs OPTIMAL")
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Policy Score", f"${man_pol.total_score/1e6:.2f}M",
              delta=f"${(man_pol.total_score-s['total_score'])/1e6:+.2f}M", delta_color="inverse")
    m2.metric("Red Months", ms["red_months"],
              delta=f"{ms['red_months']-s['red_months']:+d}", delta_color="inverse")
    m3.metric("SWB/Visit", f"${ms['annual_swb_per_visit']:.2f}",
              delta="⚠️ Exceeds target" if ms["swb_violation"] else "✅ On target")
    m4.metric("Summer Floor", f"{manual_b*cfg.summer_shed_floor_pct:.1f} FTE")
    m5.metric("Annual Visits", f"{ms['annual_visits']:,.0f}")

    lb2 = [mlabel(mo) for mo in best.months]
    fcm = go.Figure()
    fcm.add_scatter(x=lb2, y=[mo.patients_per_provider_per_shift for mo in best.months],
                    name=f"Optimal  B={best.base_fte:.1f}  W={best.winter_fte:.1f}",
                    line=dict(color=NAVY, width=2.5))
    fcm.add_scatter(x=lb2, y=[mo.patients_per_provider_per_shift for mo in man_pol.months],
                    name=f"Manual  B={manual_b:.1f}  W={manual_w:.1f}",
                    line=dict(color=C_ACTUAL, width=2.5, dash="dash"))
    fcm.add_hline(y=budget, line_dash="dash", line_color=SLATE, line_width=1,
                  annotation_text="Budget", annotation_position="right")
    fcm.add_hline(y=budget+cfg.red_threshold_above, line_dash="dot",
                  line_color=C_RED, line_width=1.5,
                  annotation_text="Red", annotation_position="right")
    fcm.update_layout(**mk_layout(height=340, xaxis=dict(tickangle=-45),
                                  title="APC Load: Optimal vs Manual Override"))
    fcm.update_yaxes(title_text="Pts / APC / Shift")
    st.plotly_chart(fcm, use_container_width=True)

    ff2 = go.Figure()
    for i,mo in enumerate(best.months):
        if mo.quarter==3:
            ff2.add_vrect(x0=i-0.5, x1=i+0.5,
                          fillcolor="rgba(154,100,0,0.06)", layer="below", line_width=0)
    ff2.add_scatter(x=lb2, y=[mo.paid_fte for mo in best.months],
                    name="Optimal Paid FTE", line=dict(color=NAVY, width=2.5))
    ff2.add_scatter(x=lb2, y=[mo.paid_fte for mo in man_pol.months],
                    name="Manual Paid FTE", line=dict(color=C_ACTUAL, width=2.5, dash="dash"))
    ff2.add_scatter(x=lb2, y=[mo.demand_fte_required for mo in best.months],
                    name="FTE Required", line=dict(color=SLATE, width=1.5, dash="dot"))
    ff2.update_layout(**mk_layout(height=280, xaxis=dict(tickangle=-45),
                                  title="FTE Trajectory  (shaded = summer shed window)"))
    ff2.update_yaxes(title_text="FTE")
    st.plotly_chart(ff2, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Policy Heatmap
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("## POLICY SCORE HEATMAP")
    if st.session_state.all_policies:
        all_p  = st.session_state.all_policies
        bv     = sorted(set(round(p.base_fte,1) for p in all_p))
        wv     = sorted(set(round(p.winter_fte,1) for p in all_p))
        bi     = {v:i for i,v in enumerate(bv)}
        wi     = {v:i for i,v in enumerate(wv)}
        mat    = np.full((len(wv),len(bv)), np.nan)
        for p in all_p:
            b2=bi.get(round(p.base_fte,1)); w2=wi.get(round(p.winter_fte,1))
            if b2 is not None and w2 is not None:
                mat[w2][b2] = p.total_score
        vmin, vmax = np.nanmin(mat), np.nanpercentile(mat, 95)

        fh = go.Figure(go.Heatmap(
            z=mat, x=[str(v) for v in bv], y=[str(v) for v in wv],
            colorscale=[[0, C_GREEN],[0.5,"#FFFBEB"],[1, C_RED]],
            zmin=vmin, zmax=vmax,
            colorbar=dict(title="Score ($)", tickfont=dict(size=10, color=SLATE)),
        ))
        fh.add_scatter(
            x=[str(round(best.base_fte,1))], y=[str(round(best.winter_fte,1))],
            mode="markers",
            marker=dict(symbol="star", size=22, color="white",
                        line=dict(color=INK, width=2)),
            name="Optimal",
        )
        fh.update_layout(**mk_layout(height=500,
                          title="Policy Score Landscape  (lower = better)  ★ = Optimal",
                          xaxis=dict(title="Base FTE"),
                          yaxis=dict(title="Winter FTE", showgrid=False)))
        st.plotly_chart(fh, use_container_width=True)
    else:
        st.info("Run the optimizer to see the heatmap.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — Req Timing
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown("## REQUISITION TIMING")
    ld  = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lm  = int(np.ceil(ld / 30))
    t1,t2,t3 = st.columns(3)
    t1.metric("Flu Anchor",  MONTH_NAMES[cfg.flu_anchor_month-1])
    t2.metric("Post Req By", MONTH_NAMES[best.req_post_month-1])
    t3.metric("Lead Time",   f"{ld} days  /  {lm} months")

    st.markdown(f"""
    | Phase | Days | Cumulative |
    |:--|--:|--:|
    | Sign offer | {cfg.days_to_sign} | {cfg.days_to_sign} |
    | Credential | {cfg.days_to_credential} | {cfg.days_to_sign+cfg.days_to_credential} |
    | Ramp to independence | {cfg.days_to_independent} | {ld} |
    """)

    phases_tl = [
        ("Post → Sign",           cfg.days_to_sign,          NAVY),
        ("Sign → Credentialed",    cfg.days_to_credential,    NAVY_LT),
        ("Credentialed → Indep.",  cfg.days_to_independent,   C_GREEN),
    ]
    ftl = go.Figure()
    start = 0
    for lbl_tl, dur, col in phases_tl:
        ftl.add_bar(x=[dur], y=[""], orientation="h", base=[start],
                    name=lbl_tl, marker_color=col,
                    text=f"  {lbl_tl}  ({dur}d)", textposition="inside",
                    textfont=dict(color="white", size=11,
                                  family="IBM Plex Sans, sans-serif"))
        start += dur
    ftl.add_vline(x=ld, line_dash="dash", line_color=C_RED, line_width=2,
                  annotation_text=f"Independent: {MONTH_NAMES[cfg.flu_anchor_month-1]}",
                  annotation_font=dict(color=C_RED, size=11))
    ftl.update_layout(**mk_layout(
        height=150, barmode="stack",
        margin=dict(t=16,b=48,l=8,r=8),
        title=f"Hiring Timeline: Post {MONTH_NAMES[best.req_post_month-1]} → "
              f"Independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}",
        xaxis=dict(title="Days from Requisition Post"),
        yaxis=dict(visible=False),
        legend=dict(orientation="h", y=-0.65),
    ))
    st.plotly_chart(ftl, use_container_width=True)
    st.info(f"Post the requisition by **{MONTH_NAMES[best.req_post_month-1]}** "
            f"to have {best.winter_fte:.1f} Winter FTE independent by "
            f"{MONTH_NAMES[cfg.flu_anchor_month-1]}.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — Data Table
# ══════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    pol = active_policy()
    st.markdown("## FULL 36-MONTH DATA")
    dff = pd.DataFrame([{
        "Month": mlabel(mo), "Q": f"Q{mo.quarter}",
        "Seasonal Mult": f"{mo.seasonal_multiplier:.2f}×",
        "Zone": mo.zone, "Hiring Mode": mo.hiring_mode,
        "Visits/Day": round(mo.demand_visits_per_day,1),
        "Providers/Shift": round(mo.demand_providers_per_shift,2),
        "FTE Required": round(mo.demand_fte_required,2),
        "Paid FTE": round(mo.paid_fte,2),
        "Effective FTE": round(mo.effective_fte,2),
        "Providers on Floor": round(mo.providers_on_floor,2),
        "Coverage Gap": round(mo.shift_coverage_gap,2),
        "Pts/Prov/Shift": round(mo.patients_per_provider_per_shift,1),
        "Perm Cost": f"${mo.permanent_cost:,.0f}",
        "Flex Cost": f"${mo.flex_cost:,.0f}",
        "Turnover": round(mo.turnover_events,2),
        "Burnout": f"${mo.burnout_penalty:,.0f}",
        "Lost Revenue": f"${mo.lost_revenue:,.0f}",
    } for mo in pol.months])

    def _szz(v):
        return {"Green":"background-color:#ECFDF5","Yellow":"background-color:#FFFBEB",
                "Red":"background-color:#FEF2F2"}.get(v,"")

    st.dataframe(dff.style.applymap(_szz, subset=["Zone"]),
                 use_container_width=True, height=520)
    st.download_button("Download CSV", dff.to_csv(index=False),
                       "psm_36month.csv", "text/csv")


# ──────────────────────────────────────────────────────────────────────────────
st.markdown(f"<hr style='border-color:{RULE}; margin:2rem 0 1rem;'>",
            unsafe_allow_html=True)
st.markdown(
    f"<p style='font-size:0.68rem; color:#8FA8BF; text-align:center; "
    f"font-family:\"IBM Plex Sans\",sans-serif; letter-spacing:0.12em;'>"
    f"PSM &nbsp;·&nbsp; PERMANENT STAFFING MODEL &nbsp;·&nbsp; URGENT CARE &nbsp;·&nbsp; "
    f"36-MONTH HORIZON &nbsp;·&nbsp; QUARTERLY SEASONALITY &nbsp;·&nbsp; NATURAL ATTRITION SHED"
    f"</p>",
    unsafe_allow_html=True,
)
