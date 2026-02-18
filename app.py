"""
PSM — Permanent Staffing Model
Urgent Care Staffing Optimizer
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from simulation import ClinicConfig, simulate_policy, optimize, MonthResult

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PSM — Urgent Care Staffing",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
.metric-green { color: #10b981; }
.metric-yellow { color: #f59e0b; }
.metric-red { color: #ef4444; }
.zone-green  { background:#d1fae5; color:#065f46; border-radius:6px; padding:2px 8px; font-weight:600; }
.zone-yellow { background:#fef3c7; color:#92400e; border-radius:6px; padding:2px 8px; font-weight:600; }
.zone-red    { background:#fee2e2; color:#991b1b; border-radius:6px; padding:2px 8px; font-weight:600; }
h1 { color: #1e3a5f; }
h2 { color: #1e3a5f; border-bottom: 2px solid #3b82f6; padding-bottom: 4px; }
h3 { color: #1e3a5f; }
.stTabs [data-baseweb="tab"] { font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

ZONE_COLORS = {"Green": "#10b981", "Yellow": "#f59e0b", "Red": "#ef4444"}

# ── Session state defaults ────────────────────────────────────────────────────
def init_state():
    defaults = dict(
        optimized=False,
        best_policy=None,
        manual_policy=None,
        cfg=None,
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Clinic Profile
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/color/96/hospital-room.png", width=60)
    st.title("Clinic Profile")

    with st.expander("📊 Demand", expanded=True):
        base_visits = st.number_input("Base Visits/Day", 20.0, 300.0, 80.0, 5.0)
        budget_ppp  = st.number_input("Budgeted Pts/Provider/Day", 10.0, 40.0, 18.0, 1.0)
        peak_factor = st.slider("Peak Factor", 1.00, 1.30, 1.10, 0.01)
        flu_anchor  = st.selectbox("Flu Anchor Month", options=list(range(1,13)),
                                   index=10, format_func=lambda x: MONTH_NAMES[x-1])

    with st.expander("💰 Economics"):
        perm_cost   = st.number_input("Annual Perm Provider Cost ($)", 100_000, 500_000, 200_000, 10_000, format="%d")
        flex_cost   = st.number_input("Annual Flex Provider Cost ($)", 100_000, 600_000, 280_000, 10_000, format="%d")
        rev_visit   = st.number_input("Net Revenue/Visit ($)", 50.0, 300.0, 110.0, 5.0)
        swb_target  = st.number_input("SWB Target ($/Visit)", 10.0, 100.0, 32.0, 1.0)

    with st.expander("⏱️ Hiring Physics"):
        days_sign   = st.number_input("Days to Sign", 7, 120, 30, 7)
        days_cred   = st.number_input("Days to Credential", 7, 180, 60, 7)
        days_ind    = st.number_input("Days to Independence", 14, 180, 90, 7)
        attrition   = st.slider("Monthly Attrition Rate", 0.005, 0.05, 0.015, 0.005,
                                 format="%.3f")
        turnover_rc = st.number_input("Turnover Replacement Cost/Provider ($)",
                                       20_000, 300_000, 80_000, 5_000, format="%d")

    with st.expander("⚠️ Penalty Weights"):
        burnout_pen  = st.number_input("Burnout Penalty/Red Month ($)", 10_000, 500_000, 50_000, 10_000, format="%d")
        overstaff_pen = st.number_input("Overstaff Penalty/FTE-Month ($)", 500, 20_000, 3_000, 500, format="%d")
        swb_pen      = st.number_input("SWB Violation Penalty ($)", 50_000, 2_000_000, 500_000, 50_000, format="%d")

    run_optimizer = st.button("🚀 Run Optimizer", type="primary", use_container_width=True)

# ── Build config ──────────────────────────────────────────────────────────────
cfg = ClinicConfig(
    base_visits_per_day=base_visits,
    budgeted_patients_per_provider_per_day=budget_ppp,
    peak_factor=peak_factor,
    flu_anchor_month=flu_anchor,
    annual_provider_cost_perm=perm_cost,
    annual_provider_cost_flex=flex_cost,
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
st.session_state.cfg = cfg

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.title("🏥 PSM — Permanent Staffing Model")
st.caption("Urgent Care Staffing Optimizer · 36-Month Horizon")

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
    st.success(f"✅ Optimizer complete — {len(all_policies):,} policies evaluated")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.optimized:
    st.info("👈 Configure your clinic profile in the sidebar, then click **Run Optimizer** to get started.")

    # Show demand preview
    st.subheader("Demand Preview")
    demand_data = []
    for i in range(12):
        v = (base_visits * cfg.seasonality_index[i] * peak_factor + cfg.flu_uplift[i])
        p = v / budget_ppp
        demand_data.append({"Month": MONTH_NAMES[i], "Visits/Day": round(v,1), "Providers Needed": round(p,1)})
    df_demand = pd.DataFrame(demand_data)
    fig = go.Figure()
    fig.add_bar(x=df_demand["Month"], y=df_demand["Visits/Day"], name="Visits/Day",
                marker_color="#3b82f6")
    fig.add_scatter(x=df_demand["Month"], y=df_demand["Providers Needed"] * 4,
                    name="Providers Needed (×4 scale)", mode="lines+markers",
                    line=dict(color="#f59e0b", width=3), yaxis="y2")
    fig.update_layout(
        title="Annual Demand Profile (Year 1)",
        yaxis=dict(title="Visits/Day"),
        yaxis2=dict(title="Providers Needed", overlaying="y", side="right"),
        legend=dict(orientation="h", y=-0.2),
        height=400, template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION PANEL
# ══════════════════════════════════════════════════════════════════════════════
best = st.session_state.best_policy
s = best.summary
lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent

req_month_name = MONTH_NAMES[best.req_post_month - 1]

st.subheader("📋 Recommended Staffing Policy")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Base FTE", f"{best.base_fte:.1f}", help="Year-round permanent staffing")
c2.metric("Winter FTE", f"{best.winter_fte:.1f}", help="Flu-season target staffing level")
c3.metric("Post Req By", req_month_name, help=f"Latest month to post req ({lead_days} day lead)")
c4.metric("Annual SWB/Visit", f"${s['annual_swb_per_visit']:.2f}",
          delta=f"Target: ${cfg.swb_target_per_visit:.2f}",
          delta_color="inverse" if s["swb_violation"] else "normal")
c5.metric("3-Year Policy Score", f"${s['total_score']:,.0f}",
          help="Lower = better (sum of costs + penalties)")

if s["swb_violation"]:
    st.error("⚠️ This policy exceeds the SWB/Visit target. Consider reducing Base or Winter FTE.")
else:
    st.success(f"✅ SWB constraint satisfied — ${s['annual_swb_per_visit']:.2f}/visit vs ${cfg.swb_target_per_visit:.2f} target")

# Zone summary
z1, z2, z3 = st.columns(3)
z1.metric("🟢 Green Months", s["green_months"], help="Sustainable load")
z2.metric("🟡 Yellow Months", s["yellow_months"], help="Stretch — manageable")
z3.metric("🔴 Red Months", s["red_months"], help="Burnout risk — penalized")

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tabs = st.tabs(["📈 36-Month Load", "💵 Cost Breakdown", "🎛️ Manual Override",
                "🗺️ Policy Heatmap", "📅 Req Timing", "📊 Data Table"])

# ─── Tab 1: 36-Month Load ─────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("36-Month Load & Staffing View")

    policy_to_show = st.session_state.get("manual_policy") or best
    months = policy_to_show.months

    df = pd.DataFrame([{
        "Month": f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}",
        "m": mo.month,
        "Pts/Prov/Day": round(mo.patients_per_provider_day, 1),
        "Budget PPD": cfg.budgeted_patients_per_provider_per_day,
        "Effective FTE": round(mo.effective_fte, 2),
        "Paid FTE": round(mo.paid_fte, 2),
        "Flex FTE": round(mo.flex_fte, 2),
        "Providers Needed": round(mo.demand_providers_needed, 2),
        "Zone": mo.zone,
    } for mo in months])

    zone_color_map = {m: ZONE_COLORS[months[i].zone] for i, m in enumerate(df["Month"])}

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Load (Patients/Provider/Day)", "Staffing (FTE)"),
                        row_heights=[0.55, 0.45])

    # Background zone shading
    for i, mo in enumerate(months):
        color = {"Green":"rgba(16,185,129,0.08)","Yellow":"rgba(245,158,11,0.12)","Red":"rgba(239,68,68,0.15)"}[mo.zone]
        fig.add_vrect(x0=i-0.5, x1=i+0.5, fillcolor=color, layer="below",
                      line_width=0, row=1, col=1)

    fig.add_scatter(x=df["Month"], y=df["Pts/Prov/Day"],
                    mode="lines+markers", name="Pts/Prov/Day",
                    line=dict(color="#3b82f6", width=2.5),
                    marker=dict(color=[ZONE_COLORS[mo.zone] for mo in months], size=8),
                    row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day, line_dash="dash",
                  line_color="#10b981", annotation_text="Budget", row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.yellow_threshold_above,
                  line_dash="dot", line_color="#f59e0b", annotation_text="Yellow", row=1, col=1)
    fig.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.red_threshold_above,
                  line_dash="dot", line_color="#ef4444", annotation_text="Red", row=1, col=1)

    fig.add_scatter(x=df["Month"], y=df["Paid FTE"], name="Paid FTE",
                    mode="lines", line=dict(color="#6366f1", width=2), row=2, col=1)
    fig.add_scatter(x=df["Month"], y=df["Effective FTE"], name="Effective FTE",
                    mode="lines", line=dict(color="#3b82f6", width=2, dash="dash"), row=2, col=1)
    fig.add_scatter(x=df["Month"], y=df["Providers Needed"], name="Providers Needed",
                    mode="lines", line=dict(color="#f59e0b", width=2, dash="dot"), row=2, col=1)
    fig.add_bar(x=df["Month"], y=df["Flex FTE"], name="Flex FTE",
                marker_color="rgba(239,68,68,0.4)", row=2, col=1)

    fig.update_layout(height=620, template="plotly_white",
                      legend=dict(orientation="h", y=-0.12),
                      xaxis2=dict(tickangle=-45))
    st.plotly_chart(fig, use_container_width=True)

    # Zone timeline bar
    fig2 = go.Figure(go.Bar(
        x=df["Month"],
        y=[1]*36,
        marker_color=[ZONE_COLORS[mo.zone] for mo in months],
        showlegend=False,
        hovertext=[f"{df['Month'].iloc[i]}: {mo.zone} ({df['Pts/Prov/Day'].iloc[i]} pts/prov/day)"
                   for i, mo in enumerate(months)],
    ))
    fig2.update_layout(height=80, margin=dict(t=10,b=10,l=10,r=10),
                       yaxis=dict(visible=False), xaxis=dict(visible=False),
                       template="plotly_white", title="Zone Timeline")
    st.plotly_chart(fig2, use_container_width=True)

# ─── Tab 2: Cost Breakdown ────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("3-Year Cost & Risk Breakdown")

    policy_to_show = st.session_state.get("manual_policy") or best
    s2 = policy_to_show.summary

    cost_labels = ["Permanent Cost", "Flex Cost", "Turnover Cost", "Lost Revenue", "Burnout Penalty", "Overstaff Penalty"]
    cost_vals   = [s2["total_permanent_cost"], s2["total_flex_cost"], s2["total_turnover_cost"],
                   s2["total_lost_revenue"], s2["total_burnout_penalty"],
                   sum(mo.overstaff_penalty for mo in policy_to_show.months)]
    cost_colors = ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626","#10b981"]

    c1, c2 = st.columns([1, 1])
    with c1:
        fig_pie = go.Figure(go.Pie(labels=cost_labels, values=cost_vals,
                                    marker=dict(colors=cost_colors),
                                    hole=0.4, textinfo="label+percent"))
        fig_pie.update_layout(title="3-Year Cost Mix", height=400, template="plotly_white")
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        df_costs = pd.DataFrame({"Component": cost_labels, "Amount": cost_vals})
        df_costs["Amount"] = df_costs["Amount"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(df_costs, use_container_width=True, hide_index=True)

        total = sum(cost_vals)
        st.metric("Total 3-Year Policy Cost", f"${total:,.0f}")
        st.metric("Annual Average Cost", f"${total/3:,.0f}")
        st.metric("SWB/Visit (Annual Avg)", f"${s2['annual_swb_per_visit']:.2f}")

    # Monthly cost stacks
    months = policy_to_show.months
    df_m = pd.DataFrame([{
        "Month": f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}",
        "Permanent": mo.permanent_cost,
        "Flex": mo.flex_cost,
        "Turnover": mo.turnover_cost,
        "Lost Revenue": mo.lost_revenue,
        "Burnout Penalty": mo.burnout_penalty,
    } for mo in months])

    fig3 = go.Figure()
    for col, color in zip(["Permanent","Flex","Turnover","Lost Revenue","Burnout Penalty"],
                          ["#3b82f6","#6366f1","#f59e0b","#ef4444","#dc2626"]):
        fig3.add_bar(x=df_m["Month"], y=df_m[col], name=col, marker_color=color)
    fig3.update_layout(barmode="stack", height=400, template="plotly_white",
                       title="Monthly Cost Stack", xaxis_tickangle=-45,
                       legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig3, use_container_width=True)

# ─── Tab 3: Manual Override ───────────────────────────────────────────────────
with tabs[2]:
    st.subheader("🎛️ Manual Override — See Consequences Instantly")
    st.caption("Adjust Base and Winter FTE to explore tradeoffs vs the optimized policy.")

    col_a, col_b = st.columns(2)
    with col_a:
        manual_b = st.slider("Base FTE", 1.0, 25.0,
                             float(st.session_state.get("manual_b", best.base_fte)), 0.5)
    with col_b:
        manual_w = st.slider("Winter FTE", manual_b, 30.0,
                             float(max(st.session_state.get("manual_w", best.winter_fte), manual_b)), 0.5)

    manual_policy = simulate_policy(manual_b, manual_w, cfg)
    st.session_state.manual_policy = manual_policy
    ms = manual_policy.summary

    # Comparison metrics
    st.markdown("#### Policy Comparison")
    m1,m2,m3,m4 = st.columns(4)
    score_delta = manual_policy.total_score - best.total_score
    m1.metric("Policy Score", f"${manual_policy.total_score:,.0f}",
              delta=f"${score_delta:+,.0f} vs optimal", delta_color="inverse")
    m2.metric("🔴 Red Months", ms["red_months"],
              delta=f"{ms['red_months']-s['red_months']:+d} vs optimal", delta_color="inverse")
    m3.metric("SWB/Visit", f"${ms['annual_swb_per_visit']:.2f}",
              delta=f"{'⚠️ Violation' if ms['swb_violation'] else '✅ OK'}")
    m4.metric("Avg Flex FTE", f"{ms['avg_flex_fte']:.1f}",
              delta=f"{ms['avg_flex_fte']-s['avg_flex_fte']:+.1f} vs optimal", delta_color="inverse")

    # Side-by-side load chart
    opt_ppd = [mo.patients_per_provider_day for mo in best.months]
    man_ppd = [mo.patients_per_provider_day for mo in manual_policy.months]
    month_labels = [f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}" for mo in best.months]

    fig_cmp = go.Figure()
    fig_cmp.add_scatter(x=month_labels, y=opt_ppd, name=f"Optimal (B={best.base_fte}, W={best.winter_fte})",
                        line=dict(color="#10b981", width=2.5))
    fig_cmp.add_scatter(x=month_labels, y=man_ppd, name=f"Manual (B={manual_b}, W={manual_w})",
                        line=dict(color="#3b82f6", width=2.5, dash="dash"))
    fig_cmp.add_hline(y=cfg.budgeted_patients_per_provider_per_day, line_dash="dash",
                      line_color="gray", annotation_text="Budget")
    fig_cmp.add_hline(y=cfg.budgeted_patients_per_provider_per_day + cfg.red_threshold_above,
                      line_dash="dot", line_color="#ef4444", annotation_text="Red Zone")
    fig_cmp.update_layout(height=400, template="plotly_white",
                          title="Load Comparison: Optimal vs Manual",
                          xaxis_tickangle=-45,
                          legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig_cmp, use_container_width=True)

# ─── Tab 4: Policy Heatmap ────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🗺️ Policy Score Heatmap")
    st.caption("Total policy score across all (Base FTE, Winter FTE) combinations evaluated by the optimizer.")

    if "all_policies" in st.session_state:
        all_p = st.session_state.all_policies
        b_vals = sorted(set(round(p.base_fte,1) for p in all_p))
        w_vals = sorted(set(round(p.winter_fte,1) for p in all_p))

        score_matrix = np.full((len(w_vals), len(b_vals)), np.nan)
        b_idx = {v:i for i,v in enumerate(b_vals)}
        w_idx = {v:i for i,v in enumerate(w_vals)}
        for p in all_p:
            bi = b_idx.get(round(p.base_fte,1))
            wi = w_idx.get(round(p.winter_fte,1))
            if bi is not None and wi is not None:
                score_matrix[wi][bi] = p.total_score

        # Clip to reasonable range for color scale
        vmax = np.nanpercentile(score_matrix, 95)
        vmin = np.nanmin(score_matrix)

        fig_heat = go.Figure(go.Heatmap(
            z=score_matrix,
            x=[str(v) for v in b_vals],
            y=[str(v) for v in w_vals],
            colorscale="RdYlGn_r",
            zmin=vmin, zmax=vmax,
            colorbar=dict(title="Policy Score ($)"),
        ))
        # Mark optimal
        fig_heat.add_scatter(
            x=[str(round(best.base_fte,1))],
            y=[str(round(best.winter_fte,1))],
            mode="markers",
            marker=dict(symbol="star", size=16, color="white",
                        line=dict(color="black", width=2)),
            name="Optimal",
        )
        fig_heat.update_layout(
            height=500, template="plotly_white",
            title="Policy Score Heatmap (lower = better)",
            xaxis_title="Base FTE",
            yaxis_title="Winter FTE",
        )
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Run the optimizer to generate the heatmap.")

# ─── Tab 5: Req Timing ────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("📅 Requisition Timing Calculator")

    lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(lead_days / 30))

    st.markdown(f"""
    **Lead Time Breakdown:**
    - Days to Sign: **{cfg.days_to_sign}**
    - Days to Credential: **{cfg.days_to_credential}**
    - Days to Independence: **{cfg.days_to_independent}**
    - **Total: {lead_days} days ({lead_months} months)**
    """)

    flu_anchor_name = MONTH_NAMES[cfg.flu_anchor_month - 1]
    req_month_name = MONTH_NAMES[best.req_post_month - 1]

    col1, col2, col3 = st.columns(3)
    col1.metric("Flu Anchor Month", flu_anchor_name,
                help="Target month for provider to be independent")
    col2.metric("Post Req By", req_month_name,
                help="Latest month to post requisition")
    col3.metric("Lead Time", f"{lead_days} days / {lead_months} months")

    # Timeline visualization
    months_list = MONTH_NAMES * 2
    fig_tl = go.Figure()

    req_m = best.req_post_month - 1  # 0-indexed
    flu_m = cfg.flu_anchor_month - 1

    phases = [
        ("Post Req → Sign", req_m, cfg.days_to_sign // 30, "#6366f1"),
        ("Sign → Credential", req_m + cfg.days_to_sign//30, cfg.days_to_credential//30, "#3b82f6"),
        ("Credential → Independent", req_m + (cfg.days_to_sign + cfg.days_to_credential)//30,
         cfg.days_to_independent//30, "#10b981"),
    ]

    for label, start, dur, color in phases:
        fig_tl.add_bar(
            x=[months_list[start + i] for i in range(max(1, dur))],
            y=[1]*max(1, dur),
            name=label,
            marker_color=color,
            text=label,
            textposition="inside",
        )

    fig_tl.add_vline(x=flu_m - req_m, line_dash="dash", line_color="#ef4444",
                     annotation_text=f"Flu Anchor ({flu_anchor_name})")

    fig_tl.update_layout(
        barmode="stack", height=250, template="plotly_white",
        title=f"Req Timeline: Post in {req_month_name} → Independent by {flu_anchor_name}",
        yaxis=dict(visible=False),
        showlegend=True,
        legend=dict(orientation="h", y=-0.3),
    )
    st.plotly_chart(fig_tl, use_container_width=True)

    st.info(f"""
    💡 **Action Required:** To have your winter FTE of **{best.winter_fte:.1f}** providers
    independent and productive by **{flu_anchor_name}**, you must post the requisition
    no later than **{req_month_name}**. This accounts for {lead_days} days of total lead time
    ({cfg.days_to_sign}d sign + {cfg.days_to_credential}d credential + {cfg.days_to_independent}d ramp).
    """)

# ─── Tab 6: Data Table ────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("📊 Full 36-Month Data")
    policy_to_show = st.session_state.get("manual_policy") or best
    df_full = pd.DataFrame([{
        "Month": f"Y{mo.year}-{MONTH_NAMES[mo.calendar_month-1]}",
        "Zone": mo.zone,
        "Visits/Day": round(mo.demand_visits, 1),
        "Providers Needed": round(mo.demand_providers_needed, 2),
        "Paid FTE": round(mo.paid_fte, 2),
        "Effective FTE": round(mo.effective_fte, 2),
        "Flex FTE": round(mo.flex_fte, 2),
        "Pts/Prov/Day": round(mo.patients_per_provider_day, 1),
        "Perm Cost": f"${mo.permanent_cost:,.0f}",
        "Flex Cost": f"${mo.flex_cost:,.0f}",
        "Turnover Events": round(mo.turnover_events, 2),
        "Burnout Penalty": f"${mo.burnout_penalty:,.0f}",
        "Lost Revenue": f"${mo.lost_revenue:,.0f}",
        "Month Score": f"${mo.permanent_cost+mo.flex_cost+mo.burnout_penalty+mo.lost_revenue+mo.turnover_cost:,.0f}",
    } for mo in policy_to_show.months])

    def color_zone(val):
        colors = {"Green":"background-color:#d1fae5","Yellow":"background-color:#fef3c7","Red":"background-color:#fee2e2"}
        return colors.get(val, "")

    st.dataframe(
        df_full.style.applymap(color_zone, subset=["Zone"]),
        use_container_width=True, height=500,
    )

    csv = df_full.to_csv(index=False)
    st.download_button("⬇️ Download CSV", csv, "psm_36month_data.csv", "text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.caption("PSM — Permanent Staffing Model · Built for Urgent Care Operators · "
           "Optimize annual SWB/Visit while minimizing burnout & turnover risk")
