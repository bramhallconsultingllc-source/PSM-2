"""
PSM Simulation Engine
36-month staffing simulation with optimizer

FTE vs Shift Coverage:
  FTE is a labor supply unit, NOT a headcount-per-shift figure.
  The shift coverage model translates FTE → providers on the floor:

    providers_per_shift = visits_per_day / budgeted_pts_per_provider
    shift_slots_per_week = operating_days_per_week × shifts_per_day
    shifts_per_week_per_fte = fte_shifts_per_week / fte_fraction
    fte_per_shift_slot = shift_slots_per_week / shifts_per_week_per_fte

  Example (your numbers):
    80 visits ÷ 36 pts/prov = 2.22 providers/shift
    7 days × 1 shift = 7 slots/week
    0.9 FTE × (3 shifts / 0.9) = 3.33 shifts/week per FTE
    fte_per_shift_slot = 7 / 3.33 = 2.10 FTE per slot
    total_fte_needed = 2.22 providers × 2.10 FTE/slot = 4.66 FTE
    (your 5.18 used 1 slot per day × provider, this matches closely
     depending on rounding of 0.9 FTE fraction)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class ClinicConfig:
    # ── Demand ────────────────────────────────────────────────────────────────
    base_visits_per_day: float = 80.0
    budgeted_patients_per_provider_per_day: float = 36.0

    peak_factor: float = 1.10

    # Seasonality index by calendar month (Jan=index 0 … Dec=index 11)
    seasonality_index: List[float] = field(default_factory=lambda: [
        0.90, 0.88, 0.92, 0.95, 1.00, 1.05,
        1.10, 1.08, 1.02, 0.98, 1.05, 0.95
    ])

    # Additive flu uplift visits/day by calendar month
    flu_uplift: List[float] = field(default_factory=lambda: [
        15.0, 10.0, 5.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 5.0, 10.0
    ])

    # ── Shift Coverage ────────────────────────────────────────────────────────
    operating_days_per_week: int = 7
    shifts_per_day: int = 1               # concurrent shift types per day
    shift_hours: float = 12.0
    fte_shifts_per_week: float = 3.0      # shifts/week a provider works
    fte_fraction: float = 0.9             # FTE value of that contract

    # ── Provider Economics ────────────────────────────────────────────────────
    annual_provider_cost_perm: float = 200_000
    annual_provider_cost_flex: float = 280_000
    net_revenue_per_visit: float = 110.0
    swb_target_per_visit: float = 32.0

    # ── Hiring Physics ────────────────────────────────────────────────────────
    days_to_sign: int = 30
    days_to_credential: int = 60
    days_to_independent: int = 90
    flu_anchor_month: int = 11            # 1-indexed; month provider must be ready by

    # ── Attrition & Turnover ─────────────────────────────────────────────────
    monthly_attrition_rate: float = 0.015
    turnover_replacement_cost_per_provider: float = 80_000

    # ── Ramp Productivity ─────────────────────────────────────────────────────
    ramp_months: int = 3
    ramp_productivity: List[float] = field(default_factory=lambda: [0.4, 0.7, 0.9])

    # ── Penalty Weights ───────────────────────────────────────────────────────
    burnout_penalty_per_red_month: float = 50_000
    overstaff_penalty_per_fte_month: float = 3_000
    swb_violation_penalty: float = 500_000

    # ── Zone Thresholds ───────────────────────────────────────────────────────
    yellow_threshold_above: float = 4.0   # pts/provider above budget → Yellow
    red_threshold_above: float = 8.0      # pts/provider above budget → Red

    # ── Derived properties ────────────────────────────────────────────────────
    @property
    def shift_slots_per_week(self) -> float:
        """Total provider-shift slots to fill each week."""
        return self.operating_days_per_week * self.shifts_per_day

    @property
    def shifts_per_week_per_fte(self) -> float:
        """Shifts per week delivered by one 1.0-FTE equivalent."""
        return self.fte_shifts_per_week / self.fte_fraction

    @property
    def fte_per_shift_slot(self) -> float:
        """
        FTEs required to staff ONE concurrent provider slot, 7 days/week.
        e.g. 7 slots/wk ÷ (3 shifts/wk per 0.9 FTE = 3.33 eff shifts) = 2.10 FTE/slot
        """
        return self.shift_slots_per_week / self.shifts_per_week_per_fte


@dataclass
class MonthResult:
    month: int
    calendar_month: int
    year: int

    # Demand
    demand_visits_per_day: float
    demand_providers_per_shift: float    # concurrent providers needed on floor
    demand_fte_required: float           # FTEs needed to continuously staff those providers

    # Supply
    paid_fte: float
    effective_fte: float
    flex_fte: float

    # Shift coverage translation
    providers_on_floor: float            # effective_fte ÷ fte_per_shift_slot
    shift_coverage_gap: float            # providers_needed − providers_on_floor (+ = gap)

    # Load
    patients_per_provider_per_shift: float
    zone: str

    # Financials
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
    req_post_month: int
    months: List[MonthResult]
    total_score: float
    annual_swb_per_visit: float
    swb_violation: bool
    summary: Dict


# ──────────────────────────────────────────────────────────────────────────────
def compute_demand(month_idx: int, cfg: ClinicConfig) -> Tuple[float, float, float]:
    """
    Returns (visits_per_day, providers_per_shift, fte_required).

    providers_per_shift = concurrent providers needed on the floor
    fte_required        = FTEs to staff that coverage 7 days/week
    """
    cal = month_idx % 12
    visits = (
        cfg.base_visits_per_day
        * cfg.seasonality_index[cal]
        * cfg.peak_factor
        + cfg.flu_uplift[cal]
    )
    providers_per_shift = visits / cfg.budgeted_patients_per_provider_per_day
    fte_required = providers_per_shift * cfg.fte_per_shift_slot
    return visits, providers_per_shift, fte_required


# ──────────────────────────────────────────────────────────────────────────────
def simulate_policy(base_fte: float, winter_fte: float, cfg: ClinicConfig,
                    horizon_months: int = 36) -> PolicyResult:
    """Simulate a staffing policy over the horizon."""

    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(total_lead_days / 30))
    req_post_month = max(1, cfg.flu_anchor_month - lead_months)

    months: List[MonthResult] = []
    paid_fte = base_fte
    ramp_cohorts: List[List] = []   # [months_remaining, cohort_fte]

    total_score = 0.0
    total_swb_cost = 0.0
    total_simulated_visits = 0.0

    flu_season = {11, 12, 1, 2}

    for m in range(horizon_months):
        cal_month = (m % 12) + 1
        year = (m // 12) + 1
        in_flu = cal_month in flu_season
        target_fte = winter_fte if in_flu else base_fte

        # Attrition
        attrition_events = paid_fte * cfg.monthly_attrition_rate
        paid_fte = max(0.0, paid_fte - attrition_events)
        turnover_events = attrition_events

        # Hiring
        if paid_fte < target_fte and not in_flu:
            new_hires = target_fte - paid_fte
            paid_fte += new_hires
            ramp_cohorts.append([cfg.ramp_months, new_hires])
        elif paid_fte < base_fte and in_flu:
            replacement = base_fte - paid_fte
            paid_fte += replacement
            ramp_cohorts.append([cfg.ramp_months, replacement])

        # Ramp drag
        ramp_drag = 0.0
        surviving = []
        for cohort in ramp_cohorts:
            months_left, size = cohort
            ramp_idx = cfg.ramp_months - months_left
            if ramp_idx < len(cfg.ramp_productivity):
                ramp_drag += size * (1.0 - cfg.ramp_productivity[ramp_idx])
            cohort[0] -= 1
            if cohort[0] > 0:
                surviving.append(cohort)
        ramp_cohorts = surviving
        effective_fte = max(0.0, paid_fte - ramp_drag)

        # Demand
        visits_per_day, providers_per_shift, fte_required = compute_demand(m, cfg)

        # Translate effective FTE → providers on floor
        fte_per_slot = cfg.fte_per_shift_slot
        providers_on_floor = (effective_fte / fte_per_slot) if fte_per_slot > 0 else 0.0
        shift_coverage_gap = providers_per_shift - providers_on_floor

        # Load
        if providers_on_floor > 0:
            pts_per_prov = visits_per_day / providers_on_floor
        else:
            pts_per_prov = 9999.0

        budget = cfg.budgeted_patients_per_provider_per_day
        if pts_per_prov <= budget + cfg.yellow_threshold_above:
            zone = "Green"
        elif pts_per_prov <= budget + cfg.red_threshold_above:
            zone = "Yellow"
        else:
            zone = "Red"

        # Flex FTE to absorb overload
        overload_pts = max(0.0, pts_per_prov - (budget + cfg.yellow_threshold_above))
        if overload_pts > 0 and providers_on_floor > 0:
            extra_providers = (overload_pts * providers_on_floor) / budget
            flex_fte = extra_providers * fte_per_slot
        else:
            flex_fte = 0.0

        # Overstaff
        overstaff_providers = max(0.0, providers_on_floor - providers_per_shift)

        # Costs
        perm_cost = paid_fte * (cfg.annual_provider_cost_perm / 12)
        flex_cost = flex_fte * (cfg.annual_provider_cost_flex / 12)

        if zone == "Red":
            severity = overload_pts / cfg.red_threshold_above
            burnout_pen = cfg.burnout_penalty_per_red_month * (1 + severity ** 2)
        elif zone == "Yellow":
            burnout_pen = cfg.burnout_penalty_per_red_month * 0.2
        else:
            burnout_pen = 0.0

        overstaff_pen = overstaff_providers * fte_per_slot * cfg.overstaff_penalty_per_fte_month

        if zone == "Red":
            lost_visit_frac = min(0.3, overload_pts * 0.03)
            lost_revenue = lost_visit_frac * visits_per_day * 30 * cfg.net_revenue_per_visit
        else:
            lost_revenue = 0.0

        turnover_cost = turnover_events * cfg.turnover_replacement_cost_per_provider
        if zone in ("Yellow", "Red"):
            turnover_cost *= 1.3

        month_score = (perm_cost + flex_cost + burnout_pen + overstaff_pen
                       + lost_revenue + turnover_cost)
        total_score += month_score

        # SWB tracking — use actual simulated visits, not an estimate
        total_swb_cost += perm_cost + flex_cost
        total_simulated_visits += visits_per_day * 30

        months.append(MonthResult(
            month=m + 1,
            calendar_month=cal_month,
            year=year,
            demand_visits_per_day=visits_per_day,
            demand_providers_per_shift=providers_per_shift,
            demand_fte_required=fte_required,
            paid_fte=paid_fte,
            effective_fte=effective_fte,
            flex_fte=flex_fte,
            providers_on_floor=providers_on_floor,
            shift_coverage_gap=shift_coverage_gap,
            patients_per_provider_per_shift=pts_per_prov,
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

    # SWB — annualised from actual 36-month simulation
    annual_swb_cost = total_swb_cost / 3
    annual_visits   = total_simulated_visits / 3
    annual_swb      = annual_swb_cost / annual_visits if annual_visits > 0 else 0.0

    swb_violation = annual_swb > cfg.swb_target_per_visit
    if swb_violation:
        total_score += cfg.swb_violation_penalty

    red_m    = sum(1 for mo in months if mo.zone == "Red")
    yellow_m = sum(1 for mo in months if mo.zone == "Yellow")
    green_m  = sum(1 for mo in months if mo.zone == "Green")

    summary = {
        "total_score":             total_score,
        "red_months":              red_m,
        "yellow_months":           yellow_m,
        "green_months":            green_m,
        "avg_flex_fte":            float(np.mean([mo.flex_fte for mo in months])),
        "total_turnover_events":   sum(mo.turnover_events for mo in months),
        "annual_swb_per_visit":    annual_swb,
        "annual_visits":           annual_visits,
        "swb_violation":           swb_violation,
        "req_post_month":          req_post_month,
        "total_permanent_cost":    sum(mo.permanent_cost for mo in months),
        "total_flex_cost":         sum(mo.flex_cost for mo in months),
        "total_lost_revenue":      sum(mo.lost_revenue for mo in months),
        "total_turnover_cost":     sum(mo.turnover_cost for mo in months),
        "total_burnout_penalty":   sum(mo.burnout_penalty for mo in months),
        "total_overstaff_penalty": sum(mo.overstaff_penalty for mo in months),
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


# ──────────────────────────────────────────────────────────────────────────────
def optimize(cfg: ClinicConfig,
             b_range: Tuple[float, float, float] = (2, 20, 0.5),
             w_range_above: Tuple[float, float, float] = (0, 10, 0.5),
             horizon_months: int = 36) -> Tuple[PolicyResult, List[PolicyResult]]:
    """Grid search over (Base FTE, Winter FTE). Returns (best_policy, all_policies)."""
    b_vals = np.arange(b_range[0], b_range[1] + b_range[2], b_range[2])
    all_policies: List[PolicyResult] = []
    best_policy: Optional[PolicyResult] = None
    best_score = float("inf")

    for b in b_vals:
        w_vals = np.arange(b, b + w_range_above[1] + w_range_above[2], w_range_above[2])
        for w in w_vals:
            p = simulate_policy(float(round(b, 2)), float(round(w, 2)), cfg, horizon_months)
            all_policies.append(p)
            if p.total_score < best_score:
                best_score = p.total_score
                best_policy = p

    return best_policy, all_policies
