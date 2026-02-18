"""
PSM — Permanent Staffing Model
Urgent Care Staffing Optimizer
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from simulation import ClinicConfig, simulate_policy, optimize

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PSM — Urgent Care Staffing",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
h1 { color: #1e3a5f; }
h2 { color: #1e3a5f; border-bottom: 2px solid #3b82f6; padding-bottom: 4px; }
h3 { color: #1e3a5f; }
.stTabs [data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]
ZONE_COLORS = {"Green": "#10b981", "Yellow": "#f59e0b", "Red": "#ef4444"}

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in dict(optimized=False, best_policy=None, manual_policy=None, all_policies=[]).items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🏥 Clinic Profile")

    with st.expander("📊 Demand", expanded=True):
        base_visits = st.number_input("Base Visits/Day", 20.0, 300.0, 80.0, 5.0)
        budget_ppp  = st.number_input("Budgeted Pts/Provider/Shift", 10.0, 60.0, 36.0, 1.0,
                                       help="How many patients can one provider see per shift")
        peak_factor = st.slider("Peak Factor", 1.00, 1.30, 1.10, 0.01)
        flu_anchor  = st.selectbox("Flu Anchor Month", list(range(1,13)), index=10,
                                    format_func=lambda x: MONTH_NAMES[x-1])

    with st.expander("🕐 Shift Structure", expanded=True):
        op_days     = st.number_input("Operating Days/Week", 1, 7, 7)
        shifts_day  = st.number_input("Shifts/Day", 1, 3, 1,
                                       help="Concurrent shift types (e.g. 1 for single 12-hr shift)")
        shift_hrs   = st.number_input("Hours/Shift", 4.0, 24.0, 12.0, 0.5)
        fte_shifts  = st.number_input("Shifts/Week per Provider", 1.0, 7.0, 3.0, 0.5,
                                       help="How many shifts/week a provider works")
        fte_frac    = st.number_input("FTE Fraction of that Contract", 0.1, 1.0, 0.9, 0.05,
                                       help="e.g. 3×12-hr shifts is typically 0.9 FTE")

    with st.expander("💰 Economics"):
        perm_cost   = st.number_input("Annual Perm Provider Cost ($)", 100_000, 500_000, 200_000, 10_000, format="%d")
        flex_cost_i = st.number_input("Annual Flex Provider Cost ($)", 100_000, 600_000, 280_000, 10_000, format="%d")
        rev_visit   = st.number_input("Net Revenue/Visit ($)", 50.0, 300.0, 110.0, 5.0)
        swb_target  = st.number_input("SWB Target ($/Visit)", 5.0, 100.0, 32.0, 1.0,
                                       help="Annual salary+wages+benefits per visit target")

    with st.expander("⏱️ Hiring Physics"):
        days_sign   = st.number_input("Days to Sign", 7, 120, 30, 7)
        days_cred   = st.number_input("Days to Credential", 7, 180, 60, 7)
        days_ind    = st.number_input("Days to Independence", 14, 180, 90, 7)
        attrition   = st.slider("Monthly Attrition Rate", 0.005, 0.05, 0.015, 0.005, format="%.3f")
        turnover_rc = st.number_input("Turnover Replace Cost/Provider ($)", 20_000, 300_000, 80_000, 5_000, format="%d")

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
    operating_days_per_week=int(op_days),
    shifts_per_day=int(shifts_day),
    shift_hours=shift_hrs,
    fte_shifts_per_week=fte_shifts,
    fte_fraction=fte_frac,
    flu_anchor_month=flu_anchor,
    annual_provider_cost_perm=perm_cost,
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

# Sidebar derived summary
with st.sidebar:
    st.divider()
    st.caption("**Shift Math (baseline)**")
    pps_base = base_visits / budget_ppp
    total_fte_needed = pps_base * cfg.fte_per_shift_slot
    st.caption(f"Providers/shift needed: **{pps_base:.2f}**")
    st.caption(f"FTE/shift slot: **{cfg.fte_per_shift_slot:.2f}**")
    st.caption(f"Total FTE needed: **{total_fte_needed:.2f}**")
    st.caption(f"_(at base visits, no seasonality)_")

# ══════════════════════════════════════════════════════════════════════════════
# RUN OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
if run_optimizer:
    with st.spinner("Running 36-month simulation grid search…"):
        best, all_policies = optimize(cfg)
    st.session_state.best_policy = best
    st.session_state.all_policies = all_policies
    st.session_state.optimized = True
    st.session_state.manual_b = best.base_fte
    st.session_state.manual_w = best.winter_fte
    st.session_state.manual_policy = None
    st.success(f"✅ Optimizer complete — {len(all_policies):,} policies evaluated")

# ══════════════════════════════════════════════════════════════════════════════
# PRE-OPTIMIZER STATE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.optimized:
    st.title("🏥 PSM — Permanent Staffing Model")
    st.info("👈 Configure your clinic profile and click **Run Optimizer** to begin.")

    st.subheader("Shift Coverage Preview (Baseline Demand)")
    col1, col2, col3, col4 = st.columns(4)
    pps = base_visits / budget_ppp
    col1.metric("Visits/Day", f"{base_visits:.0f}")
    col2.metric("Providers/Shift Needed", f"{pps:.2f}")
    col3.metric("FTE per Shift Slot", f"{cfg.fte_per_shift_slot:.2f}")
    col4.metric("Total FTE Required", f"{pps * cfg.fte_per_shift_slot:.2f}")

    st.caption(f"""
    **How this works:** {base_visits:.0f} visits ÷ {budget_ppp:.0f} pts/provider = **{pps:.2f} providers/shift** on the floor.
    To staff {pps:.2f} concurrent providers, {int(op_days)} days/week, with providers working {fte_shifts:.0f}×{shift_hrs:.0f}-hr shifts
    ({fte_frac} FTE each): you need **{pps * cfg.fte_per_shift_slot:.2f} FTE** in total.
    _(Flu season and seasonality will change these numbers month-to-month.)_
    """)

    # Annual demand chart
    demand_rows = []
    for i in range(12):
        v = base_visits * cfg.seasonality_index[i] * peak_factor + cfg.flu_uplift[i]
        pps_m = v / budget_ppp
        demand_rows.append({
            "Month": MONTH_NAMES[i],
            "Visits/Day": round(v, 1),
            "Providers/Shift": round(pps_m, 2),
            "FTE Required": round(pps_m * cfg.fte_per_shift_slot, 2),
        })
    df_d = pd.DataFrame(demand_rows)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=df_d["Month"], y=df_d["Visits/Day"], name="Visits/Day",
                marker_color="#3b82f6")
    fig.add_scatter(x=df_d["Month"], y=df_d["FTE Required"], name="FTE Required",
                    mode="lines+markers", line=dict(color="#f59e0b", width=3),
                    secondary_y=True)
    fig.update_layout(height=380, template="plotly_white",
                      title="Annual Demand & FTE Requirement (Year 1, no seasonality phase yet)",
                      legend=dict(orientation="h", y=-0.2))
    fig.update_yaxes(title_text="Visits/Day", secondary_y=False)
    fig.update_yaxes(title_text="FTE Required", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏥 PSM — Permanent Staffing Model")
st.caption("Urgent Care Staffing Optimizer · 36-Month Horizon")

best = st.session_state.best_policy
s    = best.summary
lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent

# ── Recommendation bar ────────────────────────────────────────────────────────
st.subheader("📋 Recommended Staffing Policy")
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Base FTE",    f"{best.base_fte:.1f}",   help="Year-round permanent FTE")
c2.metric("Winter FTE",  f"{best.winter_fte:.1f}",  help="Flu-season FTE target")
c3.metric("Post Req By", MONTH_NAMES[best.req_post_month-1],
          help=f"Latest req post month ({lead_days}d lead time)")
c4.metric("SWB/Visit",   f"${s['annual_swb_per_visit']:.2f}",
          delta=f"Target ${cfg.swb_target_per_visit:.2f}",
          delta_color="inverse" if s["swb_violation"] else "normal")
c5.metric("Annual Visits (est)", f"{s['annual_visits']:,.0f}",
          help="Derived from 36-month simulation")
c6.metric("3-Year Score", f"${s['total_score']:,.0f}", help="Lower = better")

if s["swb_violation"]:
    st.error("⚠️ SWB/Visit target exceeded. Consider reducing Base or Winter FTE.")
else:
    st.success(f"✅ SWB satisfied — ${s['annual_swb_per_visit']:.2f}/visit vs ${cfg.swb_target_per_visit:.2f} target")

z1,z2,z3 = st.columns(3)
z1.metric("🟢 Green Months", s["green_months"])
z2.metric("🟡 Yellow Months", s["yellow_months"])
z3.metric("🔴 Red Months",    s["red_months"])

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📈 36-Month Load",
    "🏥 Shift Coverage Model",
    "💵 Cost Breakdown",
    "🎛️ Manual Override",
    "🗺️ Policy Heatmap",
    "📅 Req Timing",
    "📊 Data Table",
])

# ─── helpers ──────────────────────────────────────────────────────────────────
def active_policy():
    return st.session_state.get("manual_policy") or best

def month_label(mo):
    return f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}"

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 36-Month Load
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("36-Month Load & Staffing")
    pol = active_policy()
    mos = pol.months
    labels = [month_label(mo) for mo in mos]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Load (Pts/Provider/Shift)", "Staffing (FTE)"),
                        row_heights=[0.55, 0.45])

    for i, mo in enumerate(mos):
        bg = {"Green":"rgba(16,185,129,0.08)","Yellow":"rgba(245,158,11,0.12)",
              "Red":"rgba(239,68,68,0.15)"}[mo.zone]
        fig.add_vrect(x0=i-0.5, x1=i+0.5, fillcolor=bg, layer="below", line_width=0, row=1, col=1)

    fig.add_scatter(x=labels, y=[mo.patients_per_provider_per_shift for mo in mos],
                    mode="lines+markers", name="Pts/Prov/Shift",
                    line=dict(color="#3b82f6", width=2.5),
                    marker=dict(color=[ZONE_COLORS[mo.zone] for mo in mos], size=8),
                    row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day,
                  line_dash="dash", line_color="#10b981", annotation_text="Budget", row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.yellow_threshold_above,
                  line_dash="dot", line_color="#f59e0b", annotation_text="Yellow", row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.red_threshold_above,
                  line_dash="dot", line_color="#ef4444", annotation_text="Red", row=1, col=1)

    fig.add_scatter(x=labels, y=[mo.paid_fte for mo in mos],
                    name="Paid FTE", mode="lines", line=dict(color="#6366f1", width=2), row=2, col=1)
    fig.add_scatter(x=labels, y=[mo.effective_fte for mo in mos],
                    name="Effective FTE", mode="lines", line=dict(color="#3b82f6", width=2, dash="dash"), row=2, col=1)
    fig.add_scatter(x=labels, y=[mo.demand_fte_required for mo in mos],
                    name="FTE Required", mode="lines", line=dict(color="#f59e0b", width=2, dash="dot"), row=2, col=1)
    fig.add_bar(x=labels, y=[mo.flex_fte for mo in mos],
                name="Flex FTE", marker_color="rgba(239,68,68,0.4)", row=2, col=1)

    fig.update_layout(height=620, template="plotly_white",
                      legend=dict(orientation="h", y=-0.14),
                      xaxis2=dict(tickangle=-45))
    st.plotly_chart(fig, use_container_width=True)

    # Zone timeline strip
    fig2 = go.Figure(go.Bar(
        x=labels, y=[1]*36,
        marker_color=[ZONE_COLORS[mo.zone] for mo in mos],
        showlegend=False,
        hovertext=[f"{month_label(mo)}: {mo.zone} — {mo.patients_per_provider_per_shift:.1f} pts/prov" for mo in mos],
    ))
    fig2.update_layout(height=70, margin=dict(t=5,b=5,l=5,r=5),
                       yaxis=dict(visible=False), xaxis=dict(visible=False),
                       template="plotly_white")
    st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Shift Coverage Model
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🏥 Shift Coverage Model")
    st.caption("Translates FTE into providers on the floor and shift slots filled each month.")

    pol = active_policy()
    mos = pol.months

    # ── Static shift math explainer ──────────────────────────────────────────
    st.markdown("#### How FTE converts to providers on the floor")
    e1,e2,e3,e4 = st.columns(4)
    e1.metric("Shift Slots/Week", f"{cfg.shift_slots_per_week:.0f}",
              help=f"{int(op_days)} days × {int(shifts_day)} shift(s)/day")
    e2.metric("Shifts/Week per FTE", f"{cfg.shifts_per_week_per_fte:.2f}",
              help=f"{fte_shifts} shifts ÷ {fte_frac} FTE fraction")
    e3.metric("FTE per Shift Slot", f"{cfg.fte_per_shift_slot:.2f}",
              help="FTEs needed to staff ONE concurrent provider slot continuously")
    e4.metric("Implied FTE at Base Demand",
              f"{(base_visits / budget_ppp) * cfg.fte_per_shift_slot:.2f}",
              help=f"{base_visits/budget_ppp:.2f} providers/shift × {cfg.fte_per_shift_slot:.2f} FTE/slot")

    st.info(f"""
    **Reading this model:** {base_visits:.0f} visits/day ÷ {budget_ppp:.0f} pts/provider = **{base_visits/budget_ppp:.2f} providers needed on the floor per shift.**
    To keep {base_visits/budget_ppp:.2f} providers staffed across {int(op_days)} days/week — with each provider working
    {fte_shifts:.0f}×{shift_hrs:.0f}-hr shifts ({fte_frac} FTE) — you need **{(base_visits/budget_ppp)*cfg.fte_per_shift_slot:.2f} FTE** on payroll at baseline.
    Seasonality and flu uplift increase demand each month; the charts below show how the policy tracks against it.
    """)

    st.markdown("#### Monthly Shift Coverage — 36 Months")

    labels = [month_label(mo) for mo in mos]
    prov_needed  = [mo.demand_providers_per_shift for mo in mos]
    prov_on_floor= [mo.providers_on_floor for mo in mos]
    flex_prov    = [mo.flex_fte / cfg.fte_per_shift_slot if cfg.fte_per_shift_slot > 0 else 0 for mo in mos]
    gap          = [mo.shift_coverage_gap for mo in mos]

    fig_cov = go.Figure()
    fig_cov.add_scatter(x=labels, y=prov_needed, name="Providers Needed/Shift",
                        mode="lines+markers", line=dict(color="#ef4444", width=2.5, dash="dot"),
                        marker=dict(size=7))
    fig_cov.add_scatter(x=labels, y=prov_on_floor, name="Providers on Floor (perm)",
                        mode="lines+markers", line=dict(color="#3b82f6", width=2.5),
                        marker=dict(size=7))
    fig_cov.add_bar(x=labels, y=flex_prov, name="Flex Providers Added",
                    marker_color="rgba(245,158,11,0.6)")
    fig_cov.update_layout(
        height=400, template="plotly_white", barmode="overlay",
        title="Concurrent Providers: Needed vs On Floor",
        xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.25),
        yaxis_title="Concurrent Providers",
    )
    st.plotly_chart(fig_cov, use_container_width=True)

    # Coverage gap chart
    gap_colors = ["#ef4444" if g > 0 else "#10b981" for g in gap]
    fig_gap = go.Figure(go.Bar(
        x=labels, y=gap,
        marker_color=gap_colors,
        name="Coverage Gap",
        hovertext=[f"{month_label(mo)}: {'Gap' if g>0 else 'Surplus'} {abs(g):.2f} providers" for mo, g in zip(mos, gap)],
    ))
    fig_gap.add_hline(y=0, line_color="gray", line_width=1)
    fig_gap.update_layout(
        height=280, template="plotly_white",
        title="Shift Coverage Gap (+ = understaffed, − = overstaffed)",
        xaxis_tickangle=-45,
        yaxis_title="Providers",
    )
    st.plotly_chart(fig_gap, use_container_width=True)

    # Monthly shift coverage table
    st.markdown("#### Monthly Staffing Detail")
    df_shift = pd.DataFrame([{
        "Month": month_label(mo),
        "Visits/Day": round(mo.demand_visits_per_day, 1),
        "Providers/Shift Needed": round(mo.demand_providers_per_shift, 2),
        "FTE Required": round(mo.demand_fte_required, 2),
        "Paid FTE": round(mo.paid_fte, 2),
        "Effective FTE": round(mo.effective_fte, 2),
        "Providers on Floor": round(mo.providers_on_floor, 2),
        "Flex Providers": round(mo.flex_fte / cfg.fte_per_shift_slot if cfg.fte_per_shift_slot else 0, 2),
        "Coverage Gap": round(mo.shift_coverage_gap, 2),
        "Pts/Prov/Shift": round(mo.patients_per_provider_per_shift, 1),
        "Zone": mo.zone,
    } for mo in mos])

    def style_zone(val):
        return {
            "Green":  "background-color:#d1fae5",
            "Yellow": "background-color:#fef3c7",
            "Red":    "background-color:#fee2e2",
        }.get(val, "")

    def style_gap(val):
        try:
            if float(val) > 0.1:  return "color:#ef4444; font-weight:600"
            if float(val) < -0.1: return "color:#10b981"
        except: pass
        return ""

    styled = (df_shift.style
              .applymap(style_zone, subset=["Zone"])
              .applymap(style_gap,  subset=["Coverage Gap"]))
    st.dataframe(styled, use_container_width=True, height=500)

    csv_shift = df_shift.to_csv(index=False)
    st.download_button("⬇️ Download Shift Coverage CSV", csv_shift,
                       "psm_shift_coverage.csv", "text/csv")

    # ── Annual summary by year ────────────────────────────────────────────────
    st.markdown("#### Annual Shift Coverage Summary")
    for yr in [1, 2, 3]:
        yr_mos = [mo for mo in mos if mo.year == yr]
        avg_needed   = np.mean([mo.demand_providers_per_shift for mo in yr_mos])
        avg_on_floor = np.mean([mo.providers_on_floor for mo in yr_mos])
        avg_fte_req  = np.mean([mo.demand_fte_required for mo in yr_mos])
        avg_paid     = np.mean([mo.paid_fte for mo in yr_mos])
        peak_needed  = max(mo.demand_providers_per_shift for mo in yr_mos)
        peak_fte_req = max(mo.demand_fte_required for mo in yr_mos)

        with st.expander(f"Year {yr} Summary"):
            a,b_,c,d_ = st.columns(4)
            a.metric("Avg Providers/Shift Needed",  f"{avg_needed:.2f}")
            b_.metric("Avg Providers on Floor",     f"{avg_on_floor:.2f}")
            c.metric("Avg FTE Required",             f"{avg_fte_req:.2f}")
            d_.metric("Avg Paid FTE",                f"{avg_paid:.2f}")
            e_,f_ = st.columns(2)
            e_.metric("Peak Providers/Shift (month)", f"{peak_needed:.2f}")
            f_.metric("Peak FTE Required (month)",    f"{peak_fte_req:.2f}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Cost Breakdown
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("3-Year Cost & Risk Breakdown")
    pol = active_policy()
    s2  = pol.summary

    labels_c = ["Permanent Cost","Flex Cost","Turnover Cost",
                "Lost Revenue","Burnout Penalty","Overstaff Penalty"]
    vals_c   = [s2["total_permanent_cost"], s2["total_flex_cost"], s2["total_turnover_cost"],
                s2["total_lost_revenue"],   s2["total_burnout_penalty"], s2["total_overstaff_penalty"]]
    colors_c = ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626","#10b981"]

    col_l, col_r = st.columns([1,1])
    with col_l:
        fig_pie = go.Figure(go.Pie(labels=labels_c, values=vals_c,
                                    marker_colors=colors_c, hole=0.4,
                                    textinfo="label+percent"))
        fig_pie.update_layout(title="3-Year Cost Mix", height=400, template="plotly_white")
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_r:
        df_c = pd.DataFrame({"Component": labels_c, "Amount ($)": [f"${v:,.0f}" for v in vals_c]})
        st.dataframe(df_c, use_container_width=True, hide_index=True)
        st.metric("Total 3-Year Cost", f"${sum(vals_c):,.0f}")
        st.metric("Annual Average",    f"${sum(vals_c)/3:,.0f}")
        st.metric("SWB/Visit",         f"${s2['annual_swb_per_visit']:.2f}")

    mos = pol.months
    df_ms = pd.DataFrame([{
        "Month":          month_label(mo),
        "Permanent":      mo.permanent_cost,
        "Flex":           mo.flex_cost,
        "Turnover":       mo.turnover_cost,
        "Lost Revenue":   mo.lost_revenue,
        "Burnout Penalty":mo.burnout_penalty,
    } for mo in mos])

    fig_stk = go.Figure()
    for col_, color in zip(["Permanent","Flex","Turnover","Lost Revenue","Burnout Penalty"],
                           ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626"]):
        fig_stk.add_bar(x=df_ms["Month"], y=df_ms[col_], name=col_, marker_color=color)
    fig_stk.update_layout(barmode="stack", height=400, template="plotly_white",
                          title="Monthly Cost Stack", xaxis_tickangle=-45,
                          legend=dict(orientation="h", y=-0.28))
    st.plotly_chart(fig_stk, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Manual Override
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("🎛️ Manual Override — See Consequences Instantly")

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

    st.markdown("#### Comparison vs Optimal")
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Policy Score", f"${man_pol.total_score:,.0f}",
              delta=f"${man_pol.total_score-s['total_score']:+,.0f}", delta_color="inverse")
    m2.metric("🔴 Red Months", ms["red_months"],
              delta=f"{ms['red_months']-s['red_months']:+d}", delta_color="inverse")
    m3.metric("SWB/Visit", f"${ms['annual_swb_per_visit']:.2f}",
              delta="⚠️ Violation" if ms["swb_violation"] else "✅ OK")
    m4.metric("Avg Flex FTE", f"{ms['avg_flex_fte']:.1f}",
              delta=f"{ms['avg_flex_fte']-s['avg_flex_fte']:+.1f}", delta_color="inverse")
    m5.metric("Annual Visits", f"{ms['annual_visits']:,.0f}")

    month_labels_ = [month_label(mo) for mo in best.months]
    fig_cmp = go.Figure()
    fig_cmp.add_scatter(x=month_labels_, y=[mo.patients_per_provider_per_shift for mo in best.months],
                        name=f"Optimal (B={best.base_fte}, W={best.winter_fte})",
                        line=dict(color="#10b981", width=2.5))
    fig_cmp.add_scatter(x=month_labels_, y=[mo.patients_per_provider_per_shift for mo in man_pol.months],
                        name=f"Manual (B={manual_b}, W={manual_w})",
                        line=dict(color="#3b82f6", width=2.5, dash="dash"))
    fig_cmp.add_hline(y=cfg.budgeted_patients_per_provider_per_day,
                      line_dash="dash", line_color="gray", annotation_text="Budget")
    fig_cmp.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.red_threshold_above,
                      line_dash="dot", line_color="#ef4444", annotation_text="Red")
    fig_cmp.update_layout(height=420, template="plotly_white",
                          title="Load Comparison: Optimal vs Manual",
                          xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.25),
                          yaxis_title="Pts/Provider/Shift")
    st.plotly_chart(fig_cmp, use_container_width=True)

    # Also show shift coverage comparison
    fig_cov2 = go.Figure()
    fig_cov2.add_scatter(x=month_labels_,
                         y=[mo.demand_providers_per_shift for mo in best.months],
                         name="Providers Needed", line=dict(color="#ef4444", width=2, dash="dot"))
    fig_cov2.add_scatter(x=month_labels_,
                         y=[mo.providers_on_floor for mo in best.months],
                         name=f"Floor: Optimal (B={best.base_fte})",
                         line=dict(color="#10b981", width=2))
    fig_cov2.add_scatter(x=month_labels_,
                         y=[mo.providers_on_floor for mo in man_pol.months],
                         name=f"Floor: Manual (B={manual_b})",
                         line=dict(color="#3b82f6", width=2, dash="dash"))
    fig_cov2.update_layout(height=320, template="plotly_white",
                           title="Providers on Floor: Optimal vs Manual",
                           xaxis_tickangle=-45, legend=dict(orientation="h", y=-0.3),
                           yaxis_title="Concurrent Providers")
    st.plotly_chart(fig_cov2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Policy Heatmap
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("🗺️ Policy Score Heatmap")

    if st.session_state.all_policies:
        all_p = st.session_state.all_policies
        b_vals = sorted(set(round(p.base_fte,1) for p in all_p))
        w_vals = sorted(set(round(p.winter_fte,1) for p in all_p))
        b_idx  = {v:i for i,v in enumerate(b_vals)}
        w_idx  = {v:i for i,v in enumerate(w_vals)}
        mat    = np.full((len(w_vals), len(b_vals)), np.nan)
        for p in all_p:
            bi = b_idx.get(round(p.base_fte,1))
            wi = w_idx.get(round(p.winter_fte,1))
            if bi is not None and wi is not None:
                mat[wi][bi] = p.total_score

        vmin = np.nanmin(mat)
        vmax = np.nanpercentile(mat, 95)
        fig_h = go.Figure(go.Heatmap(z=mat, x=[str(v) for v in b_vals],
                                      y=[str(v) for v in w_vals],
                                      colorscale="RdYlGn_r", zmin=vmin, zmax=vmax,
                                      colorbar=dict(title="Policy Score ($)")))
        fig_h.add_scatter(x=[str(round(best.base_fte,1))],
                          y=[str(round(best.winter_fte,1))],
                          mode="markers",
                          marker=dict(symbol="star", size=18, color="white",
                                      line=dict(color="black", width=2)),
                          name="Optimal")
        fig_h.update_layout(height=520, template="plotly_white",
                            title="Policy Score (lower = better) — ★ = Optimal",
                            xaxis_title="Base FTE", yaxis_title="Winter FTE")
        st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.info("Run the optimizer to generate the heatmap.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Req Timing
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("📅 Requisition Timing Calculator")
    lead_days  = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months= int(np.ceil(lead_days / 30))

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

    # Gantt-style timeline
    phases = [
        ("📋 Post Req → Sign",          cfg.days_to_sign),
        ("🏥 Sign → Credentialed",       cfg.days_to_credential),
        ("🎓 Credentialed → Independent",cfg.days_to_independent),
    ]
    colors_t = ["#6366f1","#3b82f6","#10b981"]
    fig_tl = go.Figure()
    start = 0
    for (label, dur), color in zip(phases, colors_t):
        fig_tl.add_bar(x=[dur], y=["Timeline"], orientation="h",
                       base=[start], name=label, marker_color=color,
                       text=f"{label} ({dur}d)", textposition="inside")
        start += dur
    fig_tl.add_vline(x=lead_days, line_dash="dash", line_color="#ef4444",
                     annotation_text=f"Independent ({MONTH_NAMES[cfg.flu_anchor_month-1]})")
    fig_tl.update_layout(height=180, template="plotly_white", barmode="stack",
                         xaxis_title="Days from Req Post",
                         legend=dict(orientation="h", y=-0.5),
                         yaxis=dict(visible=False),
                         title=f"Req Timeline: Post {MONTH_NAMES[best.req_post_month-1]} → "
                               f"Independent by {MONTH_NAMES[cfg.flu_anchor_month-1]}")
    st.plotly_chart(fig_tl, use_container_width=True)

    st.info(f"""
    💡 To have **{best.winter_fte:.1f} FTE** independent by **{MONTH_NAMES[cfg.flu_anchor_month-1]}**,
    post the requisition no later than **{MONTH_NAMES[best.req_post_month-1]}**.
    This accounts for {cfg.days_to_sign}d to sign + {cfg.days_to_credential}d to credential
    + {cfg.days_to_independent}d to reach independence = **{lead_days} days total**.
    """)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — Data Table
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("📊 Full 36-Month Data")
    pol = active_policy()
    df_full = pd.DataFrame([{
        "Month":              month_label(mo),
        "Zone":               mo.zone,
        "Visits/Day":         round(mo.demand_visits_per_day, 1),
        "Providers/Shift":    round(mo.demand_providers_per_shift, 2),
        "FTE Required":       round(mo.demand_fte_required, 2),
        "Paid FTE":           round(mo.paid_fte, 2),
        "Effective FTE":      round(mo.effective_fte, 2),
        "Providers on Floor": round(mo.providers_on_floor, 2),
        "Flex FTE":           round(mo.flex_fte, 2),
        "Coverage Gap":       round(mo.shift_coverage_gap, 2),
        "Pts/Prov/Shift":     round(mo.patients_per_provider_per_shift, 1),
        "Perm Cost":          f"${mo.permanent_cost:,.0f}",
        "Flex Cost":          f"${mo.flex_cost:,.0f}",
        "Turnover Events":    round(mo.turnover_events, 2),
        "Burnout Penalty":    f"${mo.burnout_penalty:,.0f}",
        "Lost Revenue":       f"${mo.lost_revenue:,.0f}",
    } for mo in pol.months])

    def style_zone_full(val):
        return {"Green":"background-color:#d1fae5","Yellow":"background-color:#fef3c7",
                "Red":"background-color:#fee2e2"}.get(val,"")

    st.dataframe(df_full.style.applymap(style_zone_full, subset=["Zone"]),
                 use_container_width=True, height=520)
    st.download_button("⬇️ Download CSV", df_full.to_csv(index=False),
                       "psm_36month_data.csv", "text/csv")

# ──────────────────────────────────────────────────────────────────────────────
st.divider()
st.caption("PSM — Permanent Staffing Model · Urgent Care Staffing Optimizer · "
           "Minimize operational pain while satisfying annual SWB/Visit constraints")
