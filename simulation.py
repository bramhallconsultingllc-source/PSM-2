"""
PSM Simulation Engine
36-month staffing simulation with optimizer
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class ClinicConfig:
    # Demand
    base_visits_per_day: float = 80.0
    budgeted_patients_per_provider_per_day: float = 18.0
    peak_factor: float = 1.10

    # Seasonality (index by month 1-12, 1.0 = baseline)
    seasonality_index: List[float] = field(default_factory=lambda: [
        0.90, 0.88, 0.92, 0.95, 1.00, 1.05,
        1.10, 1.08, 1.02, 0.98, 1.05, 0.95
    ])

    # Flu uplift by month (additive visits/day)
    flu_uplift: List[float] = field(default_factory=lambda: [
        15.0, 10.0, 5.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 5.0, 10.0
    ])

    # Provider economics
    annual_provider_cost_perm: float = 200_000
    annual_provider_cost_flex: float = 280_000  # premium rate
    net_revenue_per_visit: float = 110.0

    # SWB constraint (annual salary+wages+benefits per visit)
    swb_target_per_visit: float = 32.0
    annual_total_visits_estimate: float = 30_000

    # Hiring physics
    days_to_sign: int = 30
    days_to_credential: int = 60
    days_to_independent: int = 90  # ramp period after start
    flu_anchor_month: int = 11  # November = month 11 (1-indexed)

    # Attrition
    monthly_attrition_rate: float = 0.015  # 1.5%/month ≈ 18%/year

    # Turnover replacement cost
    turnover_replacement_cost_per_provider: float = 80_000

    # Ramp productivity curve (fraction of full productivity during ramp)
    ramp_months: int = 3
    ramp_productivity: List[float] = field(default_factory=lambda: [0.4, 0.7, 0.9])

    # Penalty weights
    burnout_penalty_per_red_month: float = 50_000
    overstaff_penalty_per_fte_month: float = 3_000
    swb_violation_penalty: float = 500_000

    # Yellow zone threshold (above budgeted)
    yellow_threshold_above: float = 3.0   # pts/provider/day above budget
    red_threshold_above: float = 6.0      # pts/provider/day above budget


@dataclass
class MonthResult:
    month: int               # 1-36
    calendar_month: int      # 1-12
    year: int                # 1-3
    demand_visits: float
    demand_providers_needed: float
    paid_fte: float
    effective_fte: float
    flex_fte: float
    patients_per_provider_day: float
    zone: str                # Green / Yellow / Red
    permanent_cost: float
    flex_cost: float
    burnout_penalty: float
    overstaff_penalty: float
    lost_revenue: float
    turnover_events: float
    turnover_cost: float
    cumulative_score: float


@dataclass
class PolicyResult:
    base_fte: float
    winter_fte: float
    req_post_month: int      # month to post requisition
    months: List[MonthResult]
    total_score: float
    annual_swb_per_visit: float
    swb_violation: bool
    summary: Dict


def compute_demand(month_idx: int, cfg: ClinicConfig) -> Tuple[float, float]:
    """Return (visits_per_day, providers_needed) for a given month index (0-based)."""
    cal = month_idx % 12  # 0-indexed calendar month
    visits = (
        cfg.base_visits_per_day
        * cfg.seasonality_index[cal]
        * cfg.peak_factor
        + cfg.flu_uplift[cal]
    )
    providers_needed = visits / cfg.budgeted_patients_per_provider_per_day
    return visits, providers_needed


def compute_req_post_month(winter_fte: float, base_fte: float, flu_anchor_month: int,
                            cfg: ClinicConfig) -> int:
    """
    Calculate latest month to post req so provider is independent by flu anchor.
    Returns calendar month (1-indexed) in year 1.
    """
    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(total_lead_days / 30))
    post_month = flu_anchor_month - lead_months
    if post_month < 1:
        post_month = post_month + 12  # prior year
    return post_month


def simulate_policy(base_fte: float, winter_fte: float, cfg: ClinicConfig,
                    horizon_months: int = 36) -> PolicyResult:
    """Simulate a staffing policy over the horizon and return full results."""

    # Lead time calculation
    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(total_lead_days / 30))
    flu_anchor = cfg.flu_anchor_month  # 1-indexed
    req_post_month = max(1, flu_anchor - lead_months)

    months: List[MonthResult] = []
    paid_fte = base_fte
    # Track ramp cohorts: list of (remaining_ramp_months, cohort_size)
    ramp_cohorts: List[List] = []

    total_score = 0.0
    total_annual_swb_cost = 0.0
    total_annual_visits = 0.0

    for m in range(horizon_months):
        cal_month = (m % 12) + 1     # 1-12
        year = (m // 12) + 1         # 1-3

        # Determine target FTE for this month
        # Flu season: Nov, Dec, Jan, Feb (months 11,12,1,2)
        flu_months = {11, 12, 1, 2}
        in_flu = cal_month in flu_months
        target_fte = winter_fte if in_flu else base_fte

        # Apply attrition to paid FTE
        attrition_events = paid_fte * cfg.monthly_attrition_rate
        paid_fte = max(0.0, paid_fte - attrition_events)
        turnover_events = attrition_events

        # Hiring decision:
        # During flu season: only replacement hiring (no growth hiring)
        # Outside flu: hire to reach target
        hiring_freeze_growth = in_flu
        if paid_fte < target_fte and not hiring_freeze_growth:
            new_hires = target_fte - paid_fte
            paid_fte += new_hires
            ramp_cohorts.append([cfg.ramp_months, new_hires])
        elif paid_fte < base_fte and in_flu:
            # Replacement only
            replacement = base_fte - paid_fte
            paid_fte += replacement
            ramp_cohorts.append([cfg.ramp_months, replacement])
        elif paid_fte > target_fte:
            # Natural shed via turnover; don't force fire
            pass

        # Compute effective FTE (ramp-adjusted)
        ramp_drag = 0.0
        new_ramp_cohorts = []
        for cohort in ramp_cohorts:
            months_left, size = cohort
            ramp_idx = cfg.ramp_months - months_left  # 0,1,2
            if ramp_idx < len(cfg.ramp_productivity):
                productivity = cfg.ramp_productivity[ramp_idx]
                ramp_drag += size * (1.0 - productivity)
            cohort[0] -= 1
            if cohort[0] > 0:
                new_ramp_cohorts.append(cohort)
        ramp_cohorts = new_ramp_cohorts
        effective_fte = max(0.0, paid_fte - ramp_drag)

        # Demand
        visits_per_day, providers_needed = compute_demand(m, cfg)

        # Load
        if effective_fte > 0:
            pts_per_prov_day = visits_per_day / effective_fte
        else:
            pts_per_prov_day = 9999.0

        budget = cfg.budgeted_patients_per_provider_per_day
        if pts_per_prov_day <= budget + cfg.yellow_threshold_above:
            zone = "Green"
        elif pts_per_prov_day <= budget + cfg.red_threshold_above:
            zone = "Yellow"
        else:
            zone = "Red"

        # Flex FTE needed
        overload = max(0.0, pts_per_prov_day - (budget + cfg.yellow_threshold_above))
        if overload > 0 and effective_fte > 0:
            extra_visits = overload * effective_fte
            flex_fte = extra_visits / cfg.budgeted_patients_per_provider_per_day
        else:
            flex_fte = 0.0

        # Overstaff
        slack = max(0.0, effective_fte - providers_needed)
        overstaff_fte = slack

        # Costs
        perm_cost = paid_fte * (cfg.annual_provider_cost_perm / 12)
        flex_cost = flex_fte * (cfg.annual_provider_cost_flex / 12)

        if zone == "Red":
            burnout_pen = cfg.burnout_penalty_per_red_month * (1 + (overload / cfg.red_threshold_above) ** 2)
        elif zone == "Yellow":
            burnout_pen = cfg.burnout_penalty_per_red_month * 0.2
        else:
            burnout_pen = 0.0

        overstaff_pen = overstaff_fte * cfg.overstaff_penalty_per_fte_month

        # Lost revenue: only in red zone — assume 10% visits lost per red point
        if zone == "Red":
            lost_visit_fraction = min(0.3, overload * 0.05)
            lost_revenue = lost_visit_fraction * visits_per_day * 30 * cfg.net_revenue_per_visit
        else:
            lost_revenue = 0.0

        # Turnover cost
        turnover_cost = turnover_events * cfg.turnover_replacement_cost_per_provider
        if zone in ("Yellow", "Red"):
            turnover_cost *= 1.3  # overload amplification

        month_score = (perm_cost + flex_cost + burnout_pen + overstaff_pen
                       + lost_revenue + turnover_cost)
        total_score += month_score

        # SWB tracking
        total_annual_swb_cost += perm_cost + flex_cost
        total_annual_visits += visits_per_day * 30

        months.append(MonthResult(
            month=m + 1,
            calendar_month=cal_month,
            year=year,
            demand_visits=visits_per_day,
            demand_providers_needed=providers_needed,
            paid_fte=paid_fte,
            effective_fte=effective_fte,
            flex_fte=flex_fte,
            patients_per_provider_day=pts_per_prov_day,
            zone=zone,
            permanent_cost=perm_cost,
            flex_cost=flex_cost,
            burnout_penalty=burnout_pen,
            overstaff_penalty=overstaff_pen,
            lost_revenue=lost_revenue,
            turnover_events=turnover_events,
            turnover_cost=turnover_cost,
            cumulative_score=total_score,
        ))

    # SWB constraint
    annual_swb = total_annual_swb_cost / 3 / (total_annual_visits / 36)
    swb_violation = annual_swb > cfg.swb_target_per_visit
    if swb_violation:
        total_score += cfg.swb_violation_penalty

    # Summary stats
    red_months = sum(1 for mo in months if mo.zone == "Red")
    yellow_months = sum(1 for mo in months if mo.zone == "Yellow")
    green_months = sum(1 for mo in months if mo.zone == "Green")
    avg_flex = np.mean([mo.flex_fte for mo in months])
    total_turnover = sum(mo.turnover_events for mo in months)

    summary = {
        "total_score": total_score,
        "red_months": red_months,
        "yellow_months": yellow_months,
        "green_months": green_months,
        "avg_flex_fte": avg_flex,
        "total_turnover_events": total_turnover,
        "annual_swb_per_visit": annual_swb,
        "swb_violation": swb_violation,
        "req_post_month": req_post_month,
        "total_permanent_cost": sum(mo.permanent_cost for mo in months),
        "total_flex_cost": sum(mo.flex_cost for mo in months),
        "total_lost_revenue": sum(mo.lost_revenue for mo in months),
        "total_turnover_cost": sum(mo.turnover_cost for mo in months),
        "total_burnout_penalty": sum(mo.burnout_penalty for mo in months),
    }

    return PolicyResult(
        base_fte=base_fte,
        winter_fte=winter_fte,
        req_post_month=req_post_month,
        months=months,
        total_score=total_score,
        annual_swb_per_visit=annual_swb,
        swb_violation=swb_violation,
        summary=summary,
    )


def optimize(cfg: ClinicConfig,
             b_range: Tuple[float, float, float] = (2, 20, 0.5),
             w_range_above: Tuple[float, float, float] = (0, 10, 0.5),
             horizon_months: int = 36) -> Tuple[PolicyResult, List[PolicyResult]]:
    """
    Grid search over (Base FTE, Winter FTE) combinations.
    Returns (best_policy, all_policies).
    """
    b_vals = np.arange(b_range[0], b_range[1] + b_range[2], b_range[2])
    all_policies = []

    best_policy = None
    best_score = float("inf")

    for b in b_vals:
        w_vals = np.arange(b, b + w_range_above[1] + w_range_above[2], w_range_above[2])
        for w in w_vals:
            policy = simulate_policy(float(b), float(w), cfg, horizon_months)
            all_policies.append(policy)
            if policy.total_score < best_score:
                best_score = policy.total_score
                best_policy = policy

    return best_policy, all_policies
