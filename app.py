"""
PSM — Permanent Staffing Model  v3
Urgent Care Staffing Optimizer
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from simulation import (ClinicConfig, simulate_policy, optimize,
                         MONTH_TO_QUARTER, QUARTER_NAMES, QUARTER_LABELS)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PSM — Urgent Care Staffing",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
h1 { color: #1e3a5f; }
h2 { color: #1e3a5f; border-bottom: 2px solid #3b82f6; padding-bottom:4px; }
h3 { color: #1e3a5f; }
.stTabs [data-baseweb="tab"] { font-size: 0.92rem; font-weight: 600; }
div[data-testid="stExpander"] > div { background: #f8fafc; }
</style>
""", unsafe_allow_html=True)

MONTH_NAMES  = ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"]
ZONE_COLORS  = {"Green":"#10b981","Yellow":"#f59e0b","Red":"#ef4444"}
HIRE_COLORS  = {"growth":"#3b82f6","replacement":"#6366f1",
                "shed_pause":"#f59e0b","freeze_flu":"#94a3b8","none":"#e2e8f0"}
Q_COLORS        = ["#6366f1","#10b981","#f59e0b","#3b82f6"]   # Q1–Q4
Q_MONTH_GROUPS  = [[0,1,2],[3,4,5],[6,7,8],[9,10,11]]         # month indices per quarter
Q_BG            = ["rgba(99,102,241,0.07)","rgba(16,185,129,0.07)",
                   "rgba(245,158,11,0.07)","rgba(59,130,246,0.07)"]

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in dict(optimized=False, best_policy=None, manual_policy=None, all_policies=[]).items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🏥 Clinic Profile")

    # ── Demand ────────────────────────────────────────────────────────────────
    with st.expander("📊 Base Demand", expanded=True):
        base_visits = st.number_input("Base Visits/Day", 20.0, 300.0, 80.0, 5.0,
                                       help="Average daily visits before seasonality")
        budget_ppp  = st.number_input("Budgeted Pts/Provider/Shift", 10.0, 60.0, 36.0, 1.0)
        peak_factor = st.slider("Intraday Peak Factor", 1.00, 1.30, 1.10, 0.01,
                                 help="Accounts for peak-hour concentration within a shift")

    # ── Seasonality — Quarterly ────────────────────────────────────────────────
    with st.expander("📅 Quarterly Seasonality", expanded=True):
        st.caption("Volume impact **relative to base** for each quarter. "
                   "Positive = more visits, negative = fewer.")

        col_q1, col_q2 = st.columns(2)
        col_q3, col_q4 = st.columns(2)

        with col_q1:
            q1_impact = st.number_input(
                "Q1 Jan–Mar (%)", -50, 100, 20, 5,
                help="Winter/flu season — default +20%",
                key="q1"
            )
        with col_q2:
            q2_impact = st.number_input(
                "Q2 Apr–Jun (%)", -50, 100, 0, 5,
                help="Spring — default neutral",
                key="q2"
            )
        with col_q3:
            q3_impact = st.number_input(
                "Q3 Jul–Sep (%)", -50, 100, -10, 5,
                help="Summer valley — default -10%",
                key="q3"
            )
        with col_q4:
            q4_impact = st.number_input(
                "Q4 Oct–Dec (%)", -50, 100, 5, 5,
                help="Fall ramp-up — default +5%",
                key="q4"
            )

        quarterly_impacts = [q1_impact/100, q2_impact/100, q3_impact/100, q4_impact/100]

        # Live mini preview
        season_idx = [1.0 + quarterly_impacts[MONTH_TO_QUARTER[m]] for m in range(12)]
        preview_visits = [base_visits * season_idx[m] * peak_factor for m in range(12)]
        min_v, max_v = min(preview_visits), max(preview_visits)
        st.caption(f"Range: **{min_v:.0f}** – **{max_v:.0f}** visits/day "
                   f"(swing: {(max_v-min_v)/base_visits*100:.0f}% of base)")

    # ── Flu Uplift ────────────────────────────────────────────────────────────
    with st.expander("🤧 Flu Uplift (additive visits/day)"):
        st.caption("Additional illness-driven visits on top of the seasonal curve. "
                   "Applied per calendar month.")
        flu_cols = st.columns(4)
        flu_defaults = [10, 8, 3, 0, 0, 0, 0, 0, 0, 0, 5, 8]
        flu_uplift_vals = []
        for i, (col, default) in enumerate(zip(flu_cols * 3, flu_defaults)):
            with col:
                flu_uplift_vals.append(
                    st.number_input(MONTH_NAMES[i], 0, 50, default, 1,
                                     key=f"flu_{i}", label_visibility="visible")
                )

    # ── Shift Structure ───────────────────────────────────────────────────────
    with st.expander("🕐 Shift Structure"):
        op_days    = st.number_input("Operating Days/Week", 1, 7, 7)
        shifts_day = st.number_input("Shifts/Day", 1, 3, 1)
        shift_hrs  = st.number_input("Hours/Shift", 4.0, 24.0, 12.0, 0.5)
        fte_shifts = st.number_input("Shifts/Week per Provider", 1.0, 7.0, 3.0, 0.5)
        fte_frac   = st.number_input("FTE Fraction of that Contract", 0.1, 1.0, 0.9, 0.05)

    # ── Staffing Policy ───────────────────────────────────────────────────────
    with st.expander("👥 Staffing Policy"):
        flu_anchor = st.selectbox("Flu Anchor Month", list(range(1,13)), index=10,
                                   format_func=lambda x: MONTH_NAMES[x-1],
                                   help="Month by which winter FTE must be fully independent")
        summer_shed_floor = st.slider(
            "Summer Shed Floor (% of Base)", 60, 100, 85, 5,
            help="Replacement hiring pauses in summer until FTE drops below this % of Base FTE. "
                 "Allows natural attrition to right-size post-winter without forced exits."
        )

    # ── Economics ─────────────────────────────────────────────────────────────
    with st.expander("💰 Economics"):
        perm_cost_i  = st.number_input("Annual Perm Provider Cost ($)", 100_000, 500_000, 200_000, 10_000, format="%d")
        flex_cost_i  = st.number_input("Annual Flex Provider Cost ($)", 100_000, 600_000, 280_000, 10_000, format="%d")
        rev_visit    = st.number_input("Net Revenue/Visit ($)", 50.0, 300.0, 110.0, 5.0)
        swb_target   = st.number_input("SWB Target ($/Visit)", 5.0, 100.0, 32.0, 1.0)

    # ── Hiring Physics ────────────────────────────────────────────────────────
    with st.expander("⏱️ Hiring Physics"):
        days_sign  = st.number_input("Days to Sign", 7, 120, 30, 7)
        days_cred  = st.number_input("Days to Credential", 7, 180, 60, 7)
        days_ind   = st.number_input("Days to Independence", 14, 180, 90, 7)
        attrition  = st.slider("Monthly Attrition Rate", 0.005, 0.05, 0.015, 0.005, format="%.3f",
                                help="Natural monthly turnover (~18%/yr at 1.5%/mo). This is the shed mechanism.")
        turnover_rc= st.number_input("Turnover Replace Cost/Provider ($)", 20_000, 300_000, 80_000, 5_000, format="%d")

    # ── Penalty Weights ───────────────────────────────────────────────────────
    with st.expander("⚠️ Penalty Weights"):
        burnout_pen   = st.number_input("Burnout Penalty/Red Month ($)", 10_000, 500_000, 50_000, 10_000, format="%d")
        overstaff_pen = st.number_input("Overstaff Penalty/FTE-Month ($)", 500, 20_000, 3_000, 500, format="%d")
        swb_pen       = st.number_input("SWB Violation Penalty ($)", 50_000, 2_000_000, 500_000, 50_000, format="%d")

    run_optimizer = st.button("🚀 Run Optimizer", type="primary", use_container_width=True)

# ── Build config ──────────────────────────────────────────────────────────────
cfg = ClinicConfig(
    base_visits_per_day=base_visits,
    budgeted_patients_per_provider_per_day=budget_ppp,
    peak_factor=peak_factor,
    quarterly_volume_impact=quarterly_impacts,
    flu_uplift=flu_uplift_vals,
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
    days_to_sign=days_sign,
    days_to_credential=days_cred,
    days_to_independent=days_ind,
    monthly_attrition_rate=attrition,
    turnover_replacement_cost_per_provider=turnover_rc,
    burnout_penalty_per_red_month=burnout_pen,
    overstaff_penalty_per_fte_month=overstaff_pen,
    swb_violation_penalty=swb_pen,
)

# Sidebar derived hint
with st.sidebar:
    st.divider()
    st.caption("**Baseline Shift Math**")
    pps_base = base_visits / budget_ppp
    total_fte_base = pps_base * cfg.fte_per_shift_slot
    st.caption(f"Providers/shift: **{pps_base:.2f}**")
    st.caption(f"FTE/slot: **{cfg.fte_per_shift_slot:.2f}**")
    st.caption(f"Baseline FTE: **{total_fte_base:.2f}**")
    # Show quarterly demand
    for qi, (name, impact) in enumerate(zip(QUARTER_LABELS, quarterly_impacts)):
        v = base_visits * (1 + impact) * peak_factor
        st.caption(f"{name}: **{v:.0f}** visits/day ({'+' if impact>=0 else ''}{impact*100:.0f}%)")

# ══════════════════════════════════════════════════════════════════════════════
# RUN OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
if run_optimizer:
    with st.spinner("Running 36-month simulation grid search…"):
        best, all_policies = optimize(cfg)
    st.session_state.best_policy   = best
    st.session_state.all_policies  = all_policies
    st.session_state.optimized     = True
    st.session_state.manual_b      = best.base_fte
    st.session_state.manual_w      = best.winter_fte
    st.session_state.manual_policy = None
    st.success(f"✅ Optimizer complete — {len(all_policies):,} policies evaluated")

# ══════════════════════════════════════════════════════════════════════════════
# PRE-OPTIMIZER LANDING
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.optimized:
    st.title("🏥 PSM — Permanent Staffing Model")
    st.info("👈 Configure your clinic profile and click **Run Optimizer** to begin.")

    st.subheader("📅 Seasonal Demand Curve Preview")

    season_idx_list = cfg.seasonality_index
    month_visits = [base_visits * season_idx_list[m] * peak_factor + flu_uplift_vals[m]
                    for m in range(12)]
    month_visits_no_flu = [base_visits * season_idx_list[m] * peak_factor for m in range(12)]
    fte_req = [v / budget_ppp * cfg.fte_per_shift_slot for v in month_visits]

    fig_prev = make_subplots(specs=[[{"secondary_y": True}]])

    # Quarter shading
    for qi, (months_in_q, bg) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        fig_prev.add_vrect(x0=months_in_q[0]-0.5, x1=months_in_q[-1]+0.5,
                           fillcolor=bg, layer="below", line_width=0)
        impact = quarterly_impacts[qi]
        fig_prev.add_annotation(
            x=months_in_q[1], y=max(month_visits)*1.08,
            text=f"{QUARTER_LABELS[qi]}<br>{'+' if impact>=0 else ''}{impact*100:.0f}%",
            showarrow=False, font=dict(size=11, color=Q_COLORS[qi]), bgcolor="white"
        )

    fig_prev.add_bar(x=MONTH_NAMES, y=month_visits_no_flu,
                     name="Seasonal visits/day", marker_color="#3b82f6", opacity=0.7)
    fig_prev.add_bar(x=MONTH_NAMES,
                     y=[v - nf for v, nf in zip(month_visits, month_visits_no_flu)],
                     name="+ Flu uplift", marker_color="#ef4444", opacity=0.8,
                     base=month_visits_no_flu)
    fig_prev.add_scatter(x=MONTH_NAMES, y=fte_req, name="FTE Required",
                         mode="lines+markers", line=dict(color="#f59e0b", width=3),
                         marker=dict(size=8), secondary_y=True)
    fig_prev.add_hline(y=total_fte_base, line_dash="dash", line_color="#6366f1",
                       annotation_text=f"Baseline FTE ({total_fte_base:.1f})",
                       secondary_y=True)

    fig_prev.update_layout(
        height=420, template="plotly_white", barmode="stack",
        title="Annual Volume & FTE Requirement by Month",
        legend=dict(orientation="h", y=-0.2),
    )
    fig_prev.update_yaxes(title_text="Visits/Day", secondary_y=False)
    fig_prev.update_yaxes(title_text="FTE Required", secondary_y=True)
    st.plotly_chart(fig_prev, use_container_width=True)

    # Quarterly summary table
    q_rows = []
    for qi in range(4):
        months_in_q = [m for m in range(12) if MONTH_TO_QUARTER[m] == qi]
        avg_v = np.mean([month_visits[m] for m in months_in_q])
        avg_fte = np.mean([fte_req[m] for m in months_in_q])
        q_rows.append({
            "Quarter": QUARTER_NAMES[qi],
            "Vol Impact": f"{'+' if quarterly_impacts[qi]>=0 else ''}{quarterly_impacts[qi]*100:.0f}%",
            "Avg Visits/Day": f"{avg_v:.1f}",
            "Avg FTE Required": f"{avg_fte:.2f}",
            "vs Baseline FTE": f"{avg_fte - total_fte_base:+.2f}",
        })
    st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏥 PSM — Permanent Staffing Model")
st.caption("Urgent Care Staffing Optimizer · 36-Month Horizon · Quarterly Seasonality")

best = st.session_state.best_policy
s    = best.summary
lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent

# ── Recommendation bar ────────────────────────────────────────────────────────
st.subheader("📋 Recommended Staffing Policy")
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Base FTE",    f"{best.base_fte:.1f}")
c2.metric("Winter FTE",  f"{best.winter_fte:.1f}")
c3.metric("Summer Floor FTE", f"{best.base_fte * cfg.summer_shed_floor_pct:.1f}",
          help=f"Attrition sheds to this during Q3 (shed floor = {summer_shed_floor}% of base)")
c4.metric("Post Req By", MONTH_NAMES[best.req_post_month-1],
          help=f"{lead_days}d lead time")
c5.metric("SWB/Visit",   f"${s['annual_swb_per_visit']:.2f}",
          delta=f"Target ${cfg.swb_target_per_visit:.2f}",
          delta_color="inverse" if s["swb_violation"] else "normal")
c6.metric("3-Year Score", f"${s['total_score']:,.0f}")

if s["swb_violation"]:
    st.error("⚠️ SWB/Visit target exceeded.")
else:
    st.success(f"✅ SWB satisfied — ${s['annual_swb_per_visit']:.2f}/visit "
               f"(target ${cfg.swb_target_per_visit:.2f}, "
               f"~{s['annual_visits']:,.0f} visits/yr)")

z1,z2,z3 = st.columns(3)
z1.metric("🟢 Green Months", s["green_months"])
z2.metric("🟡 Yellow Months", s["yellow_months"])
z3.metric("🔴 Red Months",    s["red_months"])

# ── Helpers (defined here so they're available to hero chart + all tabs) ──────
def active_policy():
    return st.session_state.get("manual_policy") or best

def mlabel(mo):
    return f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}"


# Always visible above the tabs; updates when Manual Override changes policy
# ══════════════════════════════════════════════════════════════════════════════
def render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp, peak_factor, title=None):
    """
    Stacked bar (seasonal + flu uplift visits/day) with:
      - FTE Required line (demand)
      - Paid FTE line (actual headcount on payroll)
      - Effective FTE line (ramp-adjusted productive capacity)
      - Three policy reference lines: Winter FTE, Base FTE, Summer Floor FTE
    Uses Year 1 data from the simulation.
    """
    yr1 = [mo for mo in pol.months if mo.year == 1]
    yr1_lbls = [MONTH_NAMES[mo.calendar_month - 1] for mo in yr1]

    visits_base_only = [base_visits * cfg.seasonality_index[mo.calendar_month-1] * peak_factor
                        for mo in yr1]
    visits_with_flu  = [mo.demand_visits_per_day for mo in yr1]
    fte_req_yr1      = [mo.demand_fte_required for mo in yr1]
    paid_fte_yr1     = [mo.paid_fte for mo in yr1]
    eff_fte_yr1      = [mo.effective_fte for mo in yr1]
    flu_adder        = [vf - vb for vf, vb in zip(visits_with_flu, visits_base_only)]

    summer_floor_val = pol.base_fte * cfg.summer_shed_floor_pct

    # Hiring mode for marker coloring on Paid FTE line
    hire_marker_colors = [HIRE_COLORS.get(mo.hiring_mode, "#94a3b8") for mo in yr1]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Quarter shading + labels
    for qi, (months_in_q, bg) in enumerate(zip(Q_MONTH_GROUPS, Q_BG)):
        fig.add_vrect(x0=months_in_q[0]-0.5, x1=months_in_q[-1]+0.5,
                      fillcolor=bg, layer="below", line_width=0)
        impact = quarterly_impacts[qi]
        fig.add_annotation(
            x=months_in_q[1], y=max(visits_with_flu) * 1.10,
            text=f"<b>{QUARTER_LABELS[qi]}</b><br>{'+' if impact >= 0 else ''}{impact*100:.0f}%",
            showarrow=False, font=dict(size=12, color=Q_COLORS[qi]),
            bgcolor="rgba(255,255,255,0.85)", borderpad=3,
        )

    # Stacked bars: seasonal baseline + flu uplift
    fig.add_bar(x=yr1_lbls, y=visits_base_only,
                name="Seasonal visits/day", marker_color="#3b82f6", opacity=0.75)
    fig.add_bar(x=yr1_lbls, y=flu_adder,
                name="+ Flu uplift", marker_color="#ef4444", opacity=0.85,
                base=visits_base_only)

    # Base visits reference line
    fig.add_hline(y=base_visits, line_dash="dash", line_color="#9ca3af",
                  annotation_text=f"Base ({base_visits:.0f}/day)",
                  annotation_font=dict(color="#6b7280"))

    # ── Actual staffing lines (secondary axis) ────────────────────────────────
    # Effective FTE — ramp-adjusted productive capacity (dashed, inside Paid)
    fig.add_scatter(x=yr1_lbls, y=eff_fte_yr1,
                    name="Effective FTE (productive)",
                    mode="lines",
                    line=dict(color="#10b981", width=2, dash="dash"),
                    secondary_y=True)

    # Paid FTE — actual headcount on payroll (solid, colored dots by hiring mode)
    fig.add_scatter(x=yr1_lbls, y=paid_fte_yr1,
                    name="Paid FTE (actual)",
                    mode="lines+markers",
                    line=dict(color="#10b981", width=2.5),
                    marker=dict(size=10, color=hire_marker_colors,
                                line=dict(color="white", width=1.5)),
                    secondary_y=True)

    # ── Demand line (secondary axis) ──────────────────────────────────────────
    fig.add_scatter(x=yr1_lbls, y=fte_req_yr1,
                    name="FTE Required (demand)",
                    mode="lines+markers",
                    line=dict(color="#f59e0b", width=3),
                    marker=dict(size=9, color="#f59e0b",
                                line=dict(color="white", width=1.5)),
                    secondary_y=True)

    # ── Policy reference lines (secondary axis) ───────────────────────────────
    fig.add_hline(y=pol.winter_fte, line_dash="dot", line_color="#3b82f6", line_width=2,
                  annotation_text=f"Winter FTE ({pol.winter_fte:.1f})",
                  annotation_font=dict(color="#3b82f6", size=11),
                  secondary_y=True)
    fig.add_hline(y=pol.base_fte, line_dash="dot", line_color="#6366f1", line_width=2,
                  annotation_text=f"Base FTE ({pol.base_fte:.1f})",
                  annotation_font=dict(color="#6366f1", size=11),
                  secondary_y=True)
    fig.add_hline(y=summer_floor_val, line_dash="dot", line_color="#10b981", line_width=1.5,
                  annotation_text=f"Summer Floor ({summer_floor_val:.1f})",
                  annotation_font=dict(color="#10b981", size=11),
                  secondary_y=True)

    fig.update_layout(
        height=480,
        template="plotly_white",
        barmode="stack",
        title=dict(text=title or "Annual Volume & FTE Requirement by Month",
                   font=dict(size=15, color="#1e3a5f")),
        legend=dict(orientation="h", y=-0.18, x=0),
        margin=dict(t=60, b=90),
    )
    fig.update_yaxes(title_text="Visits/Day", secondary_y=False,
                     showgrid=True, gridcolor="#f1f5f9")
    fig.update_yaxes(title_text="FTE", secondary_y=True, showgrid=False)
    fig.update_xaxes(showgrid=False)

    return fig

st.divider()
st.plotly_chart(
    render_hero_chart(active_policy(), cfg, quarterly_impacts, base_visits, budget_ppp, peak_factor),
    use_container_width=True
)
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📈 36-Month Load",
    "🏥 Shift Coverage",
    "📅 Seasonality & Demand",
    "💵 Cost Breakdown",
    "🎛️ Manual Override",
    "🗺️ Policy Heatmap",
    "⏱️ Req Timing",
    "📊 Data Table",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 36-Month Load
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    pol  = active_policy()
    mos  = pol.months
    lbls = [mlabel(mo) for mo in mos]

    # Quarter background bands for all 36 months
    def get_q_bg(mo):
        return Q_BG[mo.quarter - 1]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Load (Pts/Provider/Shift)", "Staffing (FTE)"),
                        row_heights=[0.55, 0.45])

    for i, mo in enumerate(mos):
        zone_bg = {"Green":"rgba(16,185,129,0.08)","Yellow":"rgba(245,158,11,0.12)",
                   "Red":"rgba(239,68,68,0.15)"}[mo.zone]
        fig.add_vrect(x0=i-0.5, x1=i+0.5, fillcolor=zone_bg, layer="below",
                      line_width=0, row=1, col=1)

    fig.add_scatter(x=lbls, y=[mo.patients_per_provider_per_shift for mo in mos],
                    mode="lines+markers", name="Pts/Prov/Shift",
                    line=dict(color="#3b82f6", width=2.5),
                    marker=dict(color=[ZONE_COLORS[mo.zone] for mo in mos], size=8),
                    row=1, col=1)
    budget = cfg.budgeted_patients_per_provider_per_day
    fig.add_hline(y=budget, line_dash="dash", line_color="#10b981",
                  annotation_text="Budget", row=1, col=1)
    fig.add_hline(y=budget + cfg.yellow_threshold_above, line_dash="dot",
                  line_color="#f59e0b", annotation_text="Yellow", row=1, col=1)
    fig.add_hline(y=budget + cfg.red_threshold_above, line_dash="dot",
                  line_color="#ef4444", annotation_text="Red", row=1, col=1)

    fig.add_scatter(x=lbls, y=[mo.paid_fte for mo in mos], name="Paid FTE",
                    mode="lines", line=dict(color="#6366f1", width=2), row=2, col=1)
    fig.add_scatter(x=lbls, y=[mo.effective_fte for mo in mos], name="Effective FTE",
                    mode="lines", line=dict(color="#3b82f6", width=2, dash="dash"), row=2, col=1)
    fig.add_scatter(x=lbls, y=[mo.demand_fte_required for mo in mos], name="FTE Required",
                    mode="lines", line=dict(color="#f59e0b", width=2, dash="dot"), row=2, col=1)
    fig.add_bar(x=lbls, y=[mo.flex_fte for mo in mos], name="Flex FTE",
                marker_color="rgba(239,68,68,0.4)", row=2, col=1)

    # Hiring mode markers on FTE panel
    shed_x = [lbls[i] for i, mo in enumerate(mos) if mo.hiring_mode == "shed_pause"]
    shed_y = [mos[i].paid_fte for i, mo in enumerate(mos) if mo.hiring_mode == "shed_pause"]
    if shed_x:
        fig.add_scatter(x=shed_x, y=shed_y, mode="markers", name="Shed (natural)",
                        marker=dict(symbol="triangle-down", size=10, color="#f59e0b",
                                    line=dict(color="#92400e", width=1)), row=2, col=1)

    fig.update_layout(height=650, template="plotly_white",
                      legend=dict(orientation="h", y=-0.14),
                      xaxis2=dict(tickangle=-45))
    st.plotly_chart(fig, use_container_width=True)

    # Zone strip
    fig_z = go.Figure(go.Bar(x=lbls, y=[1]*36,
                              marker_color=[ZONE_COLORS[mo.zone] for mo in mos],
                              showlegend=False,
                              hovertext=[f"{mlabel(mo)}: {mo.zone} — {mo.patients_per_provider_per_shift:.1f} pts/prov | {mo.hiring_mode}" for mo in mos]))
    fig_z.update_layout(height=65, margin=dict(t=2,b=2,l=2,r=2),
                        yaxis=dict(visible=False), xaxis=dict(visible=False),
                        template="plotly_white")
    st.plotly_chart(fig_z, use_container_width=True)

    # Hiring mode legend
    hm_counts = {m: sum(1 for mo in mos if mo.hiring_mode == m)
                 for m in ["growth","replacement","shed_pause","freeze_flu","none"]}
    labels_hm = {"growth":"🟦 Growth hire","replacement":"🟪 Replacement",
                 "shed_pause":"🟨 Shed (natural)","freeze_flu":"⬜ Flu freeze","none":"— No action"}
    st.caption("  ·  ".join(f"{labels_hm[k]}: {v} months" for k, v in hm_counts.items() if v > 0))

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Shift Coverage
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🏥 Shift Coverage Model")
    pol = active_policy()
    mos = pol.months
    lbls = [mlabel(mo) for mo in mos]

    e1,e2,e3,e4 = st.columns(4)
    e1.metric("Shift Slots/Week", f"{cfg.shift_slots_per_week:.0f}")
    e2.metric("Shifts/Week per FTE", f"{cfg.shifts_per_week_per_fte:.2f}")
    e3.metric("FTE per Shift Slot",  f"{cfg.fte_per_shift_slot:.2f}")
    e4.metric("Baseline FTE Needed", f"{(base_visits/budget_ppp)*cfg.fte_per_shift_slot:.2f}")

    prov_needed   = [mo.demand_providers_per_shift for mo in mos]
    prov_on_floor = [mo.providers_on_floor for mo in mos]
    flex_prov     = [mo.flex_fte / cfg.fte_per_shift_slot if cfg.fte_per_shift_slot else 0 for mo in mos]
    gap           = [mo.shift_coverage_gap for mo in mos]

    fig_cov = go.Figure()
    fig_cov.add_scatter(x=lbls, y=prov_needed, name="Providers Needed/Shift",
                        mode="lines+markers", line=dict(color="#ef4444", width=2.5, dash="dot"))
    fig_cov.add_scatter(x=lbls, y=prov_on_floor, name="Providers on Floor (perm)",
                        mode="lines+markers", line=dict(color="#3b82f6", width=2.5))
    fig_cov.add_bar(x=lbls, y=flex_prov, name="Flex Providers", marker_color="rgba(245,158,11,0.6)")
    fig_cov.update_layout(height=380, template="plotly_white", barmode="overlay",
                          title="Concurrent Providers: Needed vs On Floor",
                          xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.28),
                          yaxis_title="Concurrent Providers")
    st.plotly_chart(fig_cov, use_container_width=True)

    gap_colors = ["#ef4444" if g > 0.05 else ("#f59e0b" if g > -0.05 else "#10b981") for g in gap]
    fig_gap = go.Figure(go.Bar(x=lbls, y=gap, marker_color=gap_colors,
                                hovertext=[f"{mlabel(mo)}: {'+' if g>0 else ''}{g:.2f} providers" for mo,g in zip(mos,gap)]))
    fig_gap.add_hline(y=0, line_color="gray", line_width=1)
    fig_gap.update_layout(height=260, template="plotly_white",
                          title="Coverage Gap (+ = understaffed, − = overstaffed)",
                          xaxis_tickangle=-45, yaxis_title="Providers")
    st.plotly_chart(fig_gap, use_container_width=True)

    df_shift = pd.DataFrame([{
        "Month": mlabel(mo), "Quarter": f"Q{mo.quarter}",
        "Visits/Day": round(mo.demand_visits_per_day, 1),
        "Seasonal Mult": f"{mo.seasonal_multiplier:.2f}x",
        "Providers/Shift Needed": round(mo.demand_providers_per_shift, 2),
        "FTE Required": round(mo.demand_fte_required, 2),
        "Paid FTE": round(mo.paid_fte, 2),
        "Effective FTE": round(mo.effective_fte, 2),
        "Providers on Floor": round(mo.providers_on_floor, 2),
        "Flex Providers": round(mo.flex_fte / cfg.fte_per_shift_slot if cfg.fte_per_shift_slot else 0, 2),
        "Coverage Gap": round(mo.shift_coverage_gap, 2),
        "Hiring Mode": mo.hiring_mode,
        "Zone": mo.zone,
    } for mo in mos])

    def style_z(val):
        return {"Green":"background-color:#d1fae5","Yellow":"background-color:#fef3c7",
                "Red":"background-color:#fee2e2"}.get(val,"")
    def style_gap(val):
        try:
            f = float(val)
            if f > 0.1:  return "color:#ef4444;font-weight:600"
            if f < -0.1: return "color:#10b981"
        except: pass
        return ""
    def style_hm(val):
        c = {"growth":"background-color:#dbeafe","replacement":"background-color:#ede9fe",
             "shed_pause":"background-color:#fef3c7","freeze_flu":"background-color:#f1f5f9"}.get(val,"")
        return c

    st.dataframe(
        df_shift.style
            .applymap(style_z,   subset=["Zone"])
            .applymap(style_gap, subset=["Coverage Gap"])
            .applymap(style_hm,  subset=["Hiring Mode"]),
        use_container_width=True, height=480,
    )
    st.download_button("⬇️ Download Shift Coverage CSV",
                       df_shift.to_csv(index=False), "psm_shift_coverage.csv", "text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Seasonality & Demand
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("📅 Seasonality & Demand Profile")
    st.caption("How quarterly volume impacts shape monthly demand — and what that means for FTE requirements.")

    pol = active_policy()
    mos = pol.months

    # ── Quarterly impact summary ──────────────────────────────────────────────
    st.markdown("#### Quarterly Volume Settings")
    qcols = st.columns(4)
    for qi, (qname, impact, color) in enumerate(zip(QUARTER_NAMES, quarterly_impacts, Q_COLORS)):
        with qcols[qi]:
            visits_q = base_visits * (1 + impact) * peak_factor
            fte_q    = (visits_q / budget_ppp) * cfg.fte_per_shift_slot
            st.metric(
                qname,
                f"{'+' if impact>=0 else ''}{impact*100:.0f}%",
                delta=f"{visits_q:.0f} visits/day → {fte_q:.1f} FTE needed"
            )

    # ── Annual demand curve (Year 1) ──────────────────────────────────────────
    st.markdown("#### Annual Demand Curve (Year 1)")
    st.caption("Same chart shown above the tabs — reproduced here for reference alongside the tables below.")
    yr1 = [mo for mo in mos if mo.year == 1]
    st.plotly_chart(
        render_hero_chart(pol, cfg, quarterly_impacts, base_visits, budget_ppp, peak_factor,
                          title="Annual Demand Curve — Year 1 Detail"),
        use_container_width=True
    )

    # ── Quarterly summary table ───────────────────────────────────────────────
    st.markdown("#### Quarterly Demand Summary (36-Month Avg)")
    q_rows = []
    for qi in range(1, 5):
        q_mos = [mo for mo in mos if mo.quarter == qi]
        q_rows.append({
            "Quarter":          QUARTER_NAMES[qi-1],
            "Vol Impact":       f"{'+' if quarterly_impacts[qi-1]>=0 else ''}{quarterly_impacts[qi-1]*100:.0f}%",
            "Avg Visits/Day":   f"{np.mean([mo.demand_visits_per_day for mo in q_mos]):.1f}",
            "Avg FTE Required": f"{np.mean([mo.demand_fte_required for mo in q_mos]):.2f}",
            "Avg Paid FTE":     f"{np.mean([mo.paid_fte for mo in q_mos]):.2f}",
            "Avg Pts/Prov":     f"{np.mean([mo.patients_per_provider_per_shift for mo in q_mos]):.1f}",
            "Red Months":       sum(1 for mo in q_mos if mo.zone == "Red"),
            "Shed Months":      sum(1 for mo in q_mos if mo.hiring_mode == "shed_pause"),
        })
    st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)

    # ── Shed pathway visualization ────────────────────────────────────────────
    st.markdown("#### Natural Attrition Shed — Post-Winter FTE Trajectory")
    st.caption("Shows how FTE naturally walks down from Winter peak through spring/summer "
               "via attrition before the next winter ramp. No forced terminations.")

    fig_shed = go.Figure()
    fig_shed.add_scatter(x=[mlabel(mo) for mo in mos], y=[mo.paid_fte for mo in mos],
                         mode="lines+markers", name="Paid FTE",
                         line=dict(color="#6366f1", width=2.5),
                         marker=dict(
                             color=[HIRE_COLORS.get(mo.hiring_mode,"#e2e8f0") for mo in mos],
                             size=10, line=dict(color="white", width=1.5)
                         ))
    fig_shed.add_hline(y=best.winter_fte, line_dash="dot", line_color="#3b82f6",
                       annotation_text=f"Winter FTE ({best.winter_fte:.1f})")
    fig_shed.add_hline(y=best.base_fte, line_dash="dash", line_color="#6366f1",
                       annotation_text=f"Base FTE ({best.base_fte:.1f})")
    fig_shed.add_hline(y=best.base_fte * cfg.summer_shed_floor_pct,
                       line_dash="dot", line_color="#10b981",
                       annotation_text=f"Summer Floor ({best.base_fte*cfg.summer_shed_floor_pct:.1f})")

    # Shade summer months
    for i, mo in enumerate(mos):
        if mo.quarter == 3:
            fig_shed.add_vrect(x0=i-0.5, x1=i+0.5,
                               fillcolor="rgba(245,158,11,0.08)", layer="below", line_width=0)

    fig_shed.update_layout(height=360, template="plotly_white",
                           title="Paid FTE Over 36 Months — Colored by Hiring Mode",
                           xaxis_tickangle=-45, yaxis_title="Paid FTE")

    # Legend for hiring modes
    for hm, color in HIRE_COLORS.items():
        if hm != "none":
            fig_shed.add_scatter(x=[None], y=[None], mode="markers",
                                 marker=dict(color=color, size=10),
                                 name=hm.replace("_"," ").title())
    st.plotly_chart(fig_shed, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Cost Breakdown
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("3-Year Cost & Risk Breakdown")
    pol = active_policy()
    s2  = pol.summary
    mos = pol.months

    labels_c = ["Permanent","Flex","Turnover","Lost Revenue","Burnout Penalty","Overstaff Penalty"]
    vals_c   = [s2["total_permanent_cost"], s2["total_flex_cost"], s2["total_turnover_cost"],
                s2["total_lost_revenue"],   s2["total_burnout_penalty"], s2["total_overstaff_penalty"]]
    colors_c = ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626","#10b981"]

    col_l, col_r = st.columns([1,1])
    with col_l:
        fig_pie = go.Figure(go.Pie(labels=labels_c, values=vals_c,
                                    marker_colors=colors_c, hole=0.4, textinfo="label+percent"))
        fig_pie.update_layout(title="3-Year Cost Mix", height=380, template="plotly_white")
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_r:
        df_c = pd.DataFrame({"Component":labels_c,"3-Year Total":[f"${v:,.0f}" for v in vals_c]})
        st.dataframe(df_c, use_container_width=True, hide_index=True)
        st.metric("Total 3-Year", f"${sum(vals_c):,.0f}")
        st.metric("Annual Avg",   f"${sum(vals_c)/3:,.0f}")
        st.metric("SWB/Visit",    f"${s2['annual_swb_per_visit']:.2f}")
        st.metric("Annual Visits",f"{s2['annual_visits']:,.0f}")

    # Quarterly cost breakdown
    st.markdown("#### Cost by Quarter (3-Year Avg)")
    q_cost_rows = []
    for qi in range(1,5):
        q_mos = [mo for mo in mos if mo.quarter == qi]
        factor = 3  # 3 years
        q_cost_rows.append({
            "Quarter": QUARTER_NAMES[qi-1],
            "Perm Cost": f"${sum(mo.permanent_cost for mo in q_mos)/factor:,.0f}",
            "Flex Cost":  f"${sum(mo.flex_cost for mo in q_mos)/factor:,.0f}",
            "Turnover":   f"${sum(mo.turnover_cost for mo in q_mos)/factor:,.0f}",
            "Burnout Pen":f"${sum(mo.burnout_penalty for mo in q_mos)/factor:,.0f}",
            "Lost Rev":   f"${sum(mo.lost_revenue for mo in q_mos)/factor:,.0f}",
        })
    st.dataframe(pd.DataFrame(q_cost_rows), use_container_width=True, hide_index=True)

    df_ms = pd.DataFrame([{
        "Month": mlabel(mo), "Permanent": mo.permanent_cost,
        "Flex": mo.flex_cost, "Turnover": mo.turnover_cost,
        "Lost Revenue": mo.lost_revenue, "Burnout": mo.burnout_penalty,
    } for mo in mos])
    fig_stk = go.Figure()
    for col_, color in zip(["Permanent","Flex","Turnover","Lost Revenue","Burnout"],
                           ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626"]):
        fig_stk.add_bar(x=df_ms["Month"], y=df_ms[col_], name=col_, marker_color=color)
    fig_stk.update_layout(barmode="stack", height=380, template="plotly_white",
                          title="Monthly Cost Stack", xaxis_tickangle=-45,
                          legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig_stk, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Manual Override
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("🎛️ Manual Override")
    col_a, col_b = st.columns(2)
    with col_a:
        manual_b = st.slider("Base FTE", 1.0, 25.0,
                             float(st.session_state.get("manual_b", best.base_fte)), 0.5)
    with col_b:
        manual_w = st.slider("Winter FTE", manual_b, 35.0,
                             float(max(st.session_state.get("manual_w", best.winter_fte), manual_b)), 0.5)

    man_pol = simulate_policy(manual_b, manual_w, cfg)
    st.session_state.manual_policy = man_pol
    ms = man_pol.summary

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Score", f"${man_pol.total_score:,.0f}",
              delta=f"${man_pol.total_score-s['total_score']:+,.0f}", delta_color="inverse")
    m2.metric("Red Months", ms["red_months"],
              delta=f"{ms['red_months']-s['red_months']:+d}", delta_color="inverse")
    m3.metric("SWB/Visit", f"${ms['annual_swb_per_visit']:.2f}",
              delta="⚠️ Violation" if ms["swb_violation"] else "✅ OK")
    m4.metric("Summer Floor FTE", f"{manual_b * cfg.summer_shed_floor_pct:.1f}")
    m5.metric("Annual Visits", f"{ms['annual_visits']:,.0f}")

    mols = man_pol.months
    lbls_ = [mlabel(mo) for mo in best.months]

    fig_cmp = go.Figure()
    fig_cmp.add_scatter(x=lbls_, y=[mo.patients_per_provider_per_shift for mo in best.months],
                        name=f"Optimal (B={best.base_fte}, W={best.winter_fte})",
                        line=dict(color="#10b981", width=2.5))
    fig_cmp.add_scatter(x=lbls_, y=[mo.patients_per_provider_per_shift for mo in mols],
                        name=f"Manual (B={manual_b}, W={manual_w})",
                        line=dict(color="#3b82f6", width=2.5, dash="dash"))
    fig_cmp.add_hline(y=budget, line_dash="dash", line_color="gray", annotation_text="Budget")
    fig_cmp.add_hline(y=budget + cfg.red_threshold_above, line_dash="dot",
                      line_color="#ef4444", annotation_text="Red")
    fig_cmp.update_layout(height=380, template="plotly_white",
                          title="Load Comparison: Optimal vs Manual",
                          xaxis_tickangle=-45, yaxis_title="Pts/Prov/Shift",
                          legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig_cmp, use_container_width=True)

    # FTE trajectory comparison
    fig_fte = go.Figure()
    fig_fte.add_scatter(x=lbls_, y=[mo.paid_fte for mo in best.months],
                        name=f"Optimal Paid FTE", line=dict(color="#10b981", width=2))
    fig_fte.add_scatter(x=lbls_, y=[mo.paid_fte for mo in mols],
                        name=f"Manual Paid FTE", line=dict(color="#3b82f6", width=2, dash="dash"))
    fig_fte.add_scatter(x=lbls_, y=[mo.demand_fte_required for mo in best.months],
                        name="FTE Required", line=dict(color="#f59e0b", width=2, dash="dot"))
    for i, mo in enumerate(best.months):
        if mo.quarter == 3:
            fig_fte.add_vrect(x0=i-0.5, x1=i+0.5,
                              fillcolor="rgba(245,158,11,0.07)", layer="below", line_width=0)
    fig_fte.update_layout(height=320, template="plotly_white",
                          title="FTE Trajectory (shaded = summer shed window)",
                          xaxis_tickangle=-45, yaxis_title="FTE",
                          legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig_fte, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Policy Heatmap
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("🗺️ Policy Score Heatmap")
    if st.session_state.all_policies:
        all_p  = st.session_state.all_policies
        b_vals = sorted(set(round(p.base_fte,1) for p in all_p))
        w_vals = sorted(set(round(p.winter_fte,1) for p in all_p))
        b_idx  = {v:i for i,v in enumerate(b_vals)}
        w_idx  = {v:i for i,v in enumerate(w_vals)}
        mat    = np.full((len(w_vals),len(b_vals)), np.nan)
        for p in all_p:
            bi = b_idx.get(round(p.base_fte,1))
            wi = w_idx.get(round(p.winter_fte,1))
            if bi is not None and wi is not None:
                mat[wi][bi] = p.total_score
        vmin, vmax = np.nanmin(mat), np.nanpercentile(mat, 95)
        fig_h = go.Figure(go.Heatmap(z=mat, x=[str(v) for v in b_vals], y=[str(v) for v in w_vals],
                                      colorscale="RdYlGn_r", zmin=vmin, zmax=vmax,
                                      colorbar=dict(title="Score ($)")))
        fig_h.add_scatter(x=[str(round(best.base_fte,1))], y=[str(round(best.winter_fte,1))],
                          mode="markers",
                          marker=dict(symbol="star", size=18, color="white",
                                      line=dict(color="black", width=2)), name="Optimal")
        fig_h.update_layout(height=520, template="plotly_white",
                            title="Policy Score — ★ = Optimal",
                            xaxis_title="Base FTE", yaxis_title="Winter FTE")
        st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.info("Run the optimizer to see the heatmap.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — Req Timing
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("⏱️ Requisition Timing Calculator")
    lead_days   = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(lead_days / 30))

    t1,t2,t3 = st.columns(3)
    t1.metric("Flu Anchor Month", MONTH_NAMES[cfg.flu_anchor_month-1])
    t2.metric("Post Req By",      MONTH_NAMES[best.req_post_month-1])
    t3.metric("Total Lead Time",  f"{lead_days}d / {lead_months}mo")

    st.markdown(f"""
    | Phase | Days |
    |---|---|
    | Sign offer | {cfg.days_to_sign} |
    | Credential | {cfg.days_to_credential} |
    | Ramp to independence | {cfg.days_to_independent} |
    | **Total** | **{lead_days}** |
    """)

    phases = [("📋 Post → Sign", cfg.days_to_sign, "#6366f1"),
              ("🏥 Sign → Credentialed", cfg.days_to_credential, "#3b82f6"),
              ("🎓 Credentialed → Independent", cfg.days_to_independent, "#10b981")]
    fig_tl = go.Figure()
    start = 0
    for label, dur, color in phases:
        fig_tl.add_bar(x=[dur], y=["Timeline"], orientation="h",
                       base=[start], name=label, marker_color=color,
                       text=f"{label} ({dur}d)", textposition="inside")
        start += dur
    fig_tl.add_vline(x=lead_days, line_dash="dash", line_color="#ef4444",
                     annotation_text=f"Independent ({MONTH_NAMES[cfg.flu_anchor_month-1]})")
    fig_tl.update_layout(height=175, template="plotly_white", barmode="stack",
                         xaxis_title="Days from Req Post", yaxis=dict(visible=False),
                         legend=dict(orientation="h", y=-0.5),
                         title=f"Post {MONTH_NAMES[best.req_post_month-1]} → "
                               f"Independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}")
    st.plotly_chart(fig_tl, use_container_width=True)
    st.info(f"💡 Post by **{MONTH_NAMES[best.req_post_month-1]}** to have "
            f"**{best.winter_fte:.1f} Winter FTE** independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 8 — Data Table
# ══════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("📊 Full 36-Month Data")
    pol = active_policy()
    df_full = pd.DataFrame([{
        "Month": mlabel(mo), "Quarter": f"Q{mo.quarter}",
        "Seasonal Mult": f"{mo.seasonal_multiplier:.2f}x",
        "Zone": mo.zone,
        "Hiring Mode": mo.hiring_mode,
        "Visits/Day": round(mo.demand_visits_per_day, 1),
        "Providers/Shift": round(mo.demand_providers_per_shift, 2),
        "FTE Required": round(mo.demand_fte_required, 2),
        "Paid FTE": round(mo.paid_fte, 2),
        "Effective FTE": round(mo.effective_fte, 2),
        "Providers on Floor": round(mo.providers_on_floor, 2),
        "Coverage Gap": round(mo.shift_coverage_gap, 2),
        "Pts/Prov/Shift": round(mo.patients_per_provider_per_shift, 1),
        "Perm Cost": f"${mo.permanent_cost:,.0f}",
        "Flex Cost": f"${mo.flex_cost:,.0f}",
        "Turnover Events": round(mo.turnover_events, 2),
        "Burnout Penalty": f"${mo.burnout_penalty:,.0f}",
        "Lost Revenue": f"${mo.lost_revenue:,.0f}",
    } for mo in pol.months])

    def sz(val):
        return {"Green":"background-color:#d1fae5","Yellow":"background-color:#fef3c7",
                "Red":"background-color:#fee2e2"}.get(val,"")

    st.dataframe(df_full.style.applymap(sz, subset=["Zone"]),
                 use_container_width=True, height=520)
    st.download_button("⬇️ Download CSV", df_full.to_csv(index=False),
                       "psm_36month.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────────────────
st.divider()
st.caption("PSM — Permanent Staffing Model · Urgent Care · Quarterly Seasonality · "
           "Natural Attrition Shed · Annual SWB/Visit Optimizer")
