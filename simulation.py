"""
PSM Simulation Engine — v5
36-month staffing simulation with optimizer.

Changes from v4:
  - flu_uplift removed: seasonality % is the only demand modifier
  - annual_attrition_rate replaces monthly_attrition_rate (÷12 internally)
  - support_staff config for MA, PSR, RT added (SWB-only, not graphed)
  - turnover_replacement_pct replaces flat dollar (% of annual salary)
  - burnout_penalty_pct replaces flat dollar (% of annual salary per red month)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import math

# ── Month → Quarter mapping (0-indexed) ──────────────────────────────────────
MONTH_TO_QUARTER = [0,0,0, 1,1,1, 2,2,2, 3,3,3]
QUARTER_NAMES    = ["Q1 (Jan–Mar)","Q2 (Apr–Jun)","Q3 (Jul–Sep)","Q4 (Oct–Dec)"]
QUARTER_LABELS   = ["Q1","Q2","Q3","Q4"]


@dataclass
class SupportStaffConfig:
    """
    Staffing and rate config for non-provider team members.
    Cost folds into SWB/visit only — not graphed or included in FTE optimizer.

    Ratios are per provider on floor per shift.
    RT is a flat per-shift constant regardless of provider count.
    """
    # Per-shift hourly rates (fully loaded BEFORE benefits/bonus/OT multiplier)
    physician_rate_hr:   float = 135.79
    app_rate_hr:         float = 62.00
    psr_rate_hr:         float = 21.23    # front desk / patient service rep
    ma_rate_hr:          float = 24.14    # medical assistant
    rt_rate_hr:          float = 31.36    # rad tech (flat 1 FTE per shift)
    supervisor_rate_hr:  float = 28.25

    # Provider-to-support ratios (per provider on floor)
    ma_ratio:            float = 1.0      # 1 MA per provider
    psr_ratio:           float = 1.0      # 1 PSR per provider
    rt_flat_fte:         float = 1.0      # constant regardless of provider count
    supervisor_hrs_mo:   float = 0.0      # physician supervision hrs/mo
    supervisor_admin_mo: float = 0.0      # supervisor admin hrs/mo

    # Total compensation multipliers
    benefits_load_pct:   float = 0.30     # 30% benefits load
    bonus_pct:           float = 0.10     # 10% bonus
    ot_sick_pct:         float = 0.04     # 4% OT + sick


    @property
    def total_multiplier(self) -> float:
        """Combined comp multiplier applied to base hourly cost."""
        return 1.0 + self.benefits_load_pct + self.bonus_pct + self.ot_sick_pct

    def monthly_support_cost(self, avg_providers_on_floor: float,
                              shift_hours: float,
                              operating_days_per_week: float) -> float:
        """
        Estimate monthly support staff cost for a given average provider count.
        avg_providers_on_floor: average concurrent providers across the month.
        """
        operating_days_mo = operating_days_per_week * (52 / 12)
        hours_per_staff_mo = shift_hours * operating_days_mo

        ma_cost  = (avg_providers_on_floor * self.ma_ratio *
                    self.ma_rate_hr * hours_per_staff_mo * self.total_multiplier)
        psr_cost = (avg_providers_on_floor * self.psr_ratio *
                    self.psr_rate_hr * hours_per_staff_mo * self.total_multiplier)
        rt_cost  = (self.rt_flat_fte *
                    self.rt_rate_hr * hours_per_staff_mo * self.total_multiplier)
        sup_cost = ((self.supervisor_hrs_mo + self.supervisor_admin_mo) *
                    self.supervisor_rate_hr * self.total_multiplier)

        return ma_cost + psr_cost + rt_cost + sup_cost


@dataclass
class ClinicConfig:
    # ── Demand ────────────────────────────────────────────────────────────────
    base_visits_per_day: float = 80.0
    budgeted_patients_per_provider_per_day: float = 36.0
    peak_factor: float = 1.10

    # Quarterly volume impact (fractional; 0.20 = +20%, -0.10 = -10%)
    quarterly_volume_impact: List[float] = field(
        default_factory=lambda: [0.20, 0.0, -0.10, 0.05]
    )

    # ── Shift Coverage ────────────────────────────────────────────────────────
    operating_days_per_week: int  = 7
    shifts_per_day:          int  = 1       # auto-computed in app, stored here
    shift_hours:             float = 12.0
    fte_shifts_per_week:     float = 3.0
    fte_fraction:            float = 0.9

    # ── Provider Economics ────────────────────────────────────────────────────
    annual_provider_cost_perm: float = 200_000
    annual_provider_cost_flex: float = 280_000
    net_revenue_per_visit:     float = 110.0
    swb_target_per_visit:      float = 32.0

    # ── Support Staff ─────────────────────────────────────────────────────────
    support: SupportStaffConfig = field(default_factory=SupportStaffConfig)

    # ── Hiring Physics ────────────────────────────────────────────────────────
    days_to_sign:        int = 30
    days_to_credential:  int = 60
    days_to_independent: int = 90
    flu_anchor_month:    int = 11   # 1-indexed

    # ── Attrition & Turnover ─────────────────────────────────────────────────
    # User inputs annual %; we store and use monthly rate = annual / 12
    annual_attrition_pct:  float = 18.0   # e.g. 18 = 18% per year
    # Replacement cost = this % of annual perm salary
    turnover_replacement_pct: float = 40.0  # e.g. 40 = 40% of $200k = $80k

    # ── Summer Shed Floor ────────────────────────────────────────────────────
    summer_shed_floor_pct: float = 0.85

    # ── Ramp Productivity ────────────────────────────────────────────────────
    ramp_months:      int = 3
    ramp_productivity: List[float] = field(default_factory=lambda: [0.4, 0.7, 0.9])

    # ── Penalty Weights ───────────────────────────────────────────────────────
    # Burnout = this % of annual salary per red month
    burnout_pct_per_red_month: float = 25.0   # e.g. 25 = 25% of $200k = $50k
    overstaff_penalty_per_fte_month: float = 3_000
    swb_violation_penalty: float = 500_000

    # ── Zone Thresholds ───────────────────────────────────────────────────────
    yellow_threshold_above: float = 4.0
    red_threshold_above:    float = 8.0

    # ── Derived properties ───────────────────────────────────────────────────
    @property
    def monthly_attrition_rate(self) -> float:
        return self.annual_attrition_pct / 100 / 12

    @property
    def turnover_replacement_cost_per_provider(self) -> float:
        return self.annual_provider_cost_perm * (self.turnover_replacement_pct / 100)

    @property
    def burnout_penalty_per_red_month(self) -> float:
        return self.annual_provider_cost_perm * (self.burnout_pct_per_red_month / 100)

    @property
    def shift_slots_per_week(self) -> float:
        return self.operating_days_per_week * self.shifts_per_day

    @property
    def shifts_per_week_per_fte(self) -> float:
        return self.fte_shifts_per_week / self.fte_fraction

    @property
    def fte_per_shift_slot(self) -> float:
        return self.shift_slots_per_week / self.shifts_per_week_per_fte

    @property
    def seasonality_index(self) -> List[float]:
        return [1.0 + self.quarterly_volume_impact[MONTH_TO_QUARTER[m]]
                for m in range(12)]


def auto_shifts_per_day(visits_per_day: float,
                        pts_per_provider: float,
                        peak_factor: float = 1.0) -> int:
    """
    Compute sensible shifts/day from demand and capacity.
    Logic: concurrent providers needed = visits / pts_per_provider (adjusted for peak).
    If 1 provider can handle the load in a single shift window → 1 shift.
    We cap at 3.
    """
    if pts_per_provider <= 0:
        return 1
    providers_needed = (visits_per_day * peak_factor) / pts_per_provider
    # Each "shift" adds one coverage window. If providers_needed > 1 concurrent,
    # a single slot needs multiple providers (not multiple shifts).
    # Shifts/day is about temporal coverage, not headcount.
    # Practical rule: 1 shift if hours ≥ 12, 2 if < 12 (need AM+PM), 3 if < 8.
    # Since shift_hours is a separate param, default to 1 here;
    # real override comes from hours/day ÷ shift_hours.
    return 1   # returned as sensible default; app uses hours-based logic


@dataclass
class MonthResult:
    month: int
    calendar_month: int
    year: int
    quarter: int

    demand_visits_per_day: float
    seasonal_multiplier: float
    demand_providers_per_shift: float
    demand_fte_required: float

    paid_fte: float
    effective_fte: float
    flex_fte: float

    providers_on_floor: float
    shift_coverage_gap: float
    patients_per_provider_per_shift: float
    zone: str
    hiring_mode: str

    permanent_cost: float
    flex_cost: float
    support_cost: float       # NEW: monthly support staff cost
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


def compute_demand(month_idx: int, cfg: ClinicConfig) -> Tuple[float, float, float, float]:
    """Returns (visits_per_day, seasonal_multiplier, providers_per_shift, fte_required)."""
    cal = month_idx % 12
    seasonal_mult = cfg.seasonality_index[cal]
    visits = cfg.base_visits_per_day * seasonal_mult * cfg.peak_factor
    providers_per_shift = visits / cfg.budgeted_patients_per_provider_per_day
    fte_required = providers_per_shift * cfg.fte_per_shift_slot
    return visits, seasonal_mult, providers_per_shift, fte_required


def simulate_policy(base_fte: float, winter_fte: float, cfg: ClinicConfig,
                    horizon_months: int = 36) -> PolicyResult:
    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(total_lead_days / 30))
    req_post_month = max(1, cfg.flu_anchor_month - lead_months)

    summer_floor_fte = base_fte * cfg.summer_shed_floor_pct

    months: List[MonthResult] = []
    paid_fte = base_fte
    ramp_cohorts: List[List] = []

    total_score           = 0.0
    total_swb_cost        = 0.0
    total_simulated_visits = 0.0

    flu_months    = {11, 12, 1, 2}
    summer_months = {7, 8, 9}

    monthly_attrition = cfg.monthly_attrition_rate
    turnover_replace_cost = cfg.turnover_replacement_cost_per_provider
    burnout_per_red = cfg.burnout_penalty_per_red_month

    for m in range(horizon_months):
        cal_month = (m % 12) + 1
        year      = (m // 12) + 1
        quarter   = MONTH_TO_QUARTER[cal_month - 1] + 1

        in_flu    = cal_month in flu_months
        in_summer = cal_month in summer_months

        if in_flu:
            target_fte = winter_fte
        elif in_summer:
            target_fte = summer_floor_fte
        else:
            target_fte = base_fte

        # Attrition
        attrition_events = paid_fte * monthly_attrition
        paid_fte = max(0.0, paid_fte - attrition_events)
        turnover_events = attrition_events

        # Hiring
        hiring_mode = "none"

        if in_flu:
            if paid_fte < base_fte:
                replacement = base_fte - paid_fte
                paid_fte += replacement
                ramp_cohorts.append([cfg.ramp_months, replacement])
                hiring_mode = "freeze_flu"
            else:
                hiring_mode = "freeze_flu"

        elif in_summer:
            if paid_fte < summer_floor_fte:
                replacement = summer_floor_fte - paid_fte
                paid_fte += replacement
                ramp_cohorts.append([cfg.ramp_months, replacement])
                hiring_mode = "replacement"
            else:
                hiring_mode = "shed_pause"

        else:
            if paid_fte < target_fte:
                new_hires = target_fte - paid_fte
                paid_fte += new_hires
                ramp_cohorts.append([cfg.ramp_months, new_hires])
                hiring_mode = "growth"

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
        visits_per_day, seasonal_mult, providers_per_shift, fte_required = compute_demand(m, cfg)

        # Providers on floor
        fte_per_slot = cfg.fte_per_shift_slot
        providers_on_floor = (effective_fte / fte_per_slot) if fte_per_slot > 0 else 0.0
        shift_coverage_gap = providers_per_shift - providers_on_floor

        # Load & Zone
        pts_per_prov = (visits_per_day / providers_on_floor) if providers_on_floor > 0 else 9999.0
        budget = cfg.budgeted_patients_per_provider_per_day

        if pts_per_prov <= budget + cfg.yellow_threshold_above:
            zone = "Green"
        elif pts_per_prov <= budget + cfg.red_threshold_above:
            zone = "Yellow"
        else:
            zone = "Red"

        # Flex FTE
        overload_pts = max(0.0, pts_per_prov - (budget + cfg.yellow_threshold_above))
        if overload_pts > 0 and providers_on_floor > 0:
            extra_providers = (overload_pts * providers_on_floor) / budget
            flex_fte = extra_providers * fte_per_slot
        else:
            flex_fte = 0.0

        overstaff_providers = max(0.0, providers_on_floor - providers_per_shift)

        # Provider costs
        perm_cost = paid_fte * (cfg.annual_provider_cost_perm / 12)
        flex_cost = flex_fte * (cfg.annual_provider_cost_flex / 12)

        # Support staff cost (SWB-only)
        support_cost = cfg.support.monthly_support_cost(
            avg_providers_on_floor=providers_on_floor,
            shift_hours=cfg.shift_hours,
            operating_days_per_week=cfg.operating_days_per_week,
        )

        # Penalties
        if zone == "Red":
            severity    = overload_pts / max(cfg.red_threshold_above, 1)
            burnout_pen = burnout_per_red * (1 + severity ** 2)
        elif zone == "Yellow":
            burnout_pen = burnout_per_red * 0.2
        else:
            burnout_pen = 0.0

        overstaff_pen = overstaff_providers * fte_per_slot * cfg.overstaff_penalty_per_fte_month

        if zone == "Red":
            lost_visit_frac = min(0.3, overload_pts * 0.03)
            lost_revenue = lost_visit_frac * visits_per_day * 30 * cfg.net_revenue_per_visit
        else:
            lost_revenue = 0.0

        turnover_cost = turnover_events * turnover_replace_cost
        if zone in ("Yellow", "Red"):
            turnover_cost *= 1.3

        month_score = (perm_cost + flex_cost + support_cost + burnout_pen
                       + overstaff_pen + lost_revenue + turnover_cost)
        total_score += month_score

        # SWB includes provider + support staff
        total_swb_cost         += perm_cost + flex_cost + support_cost
        total_simulated_visits += visits_per_day * 30

        months.append(MonthResult(
            month=m+1, calendar_month=cal_month, year=year, quarter=quarter,
            demand_visits_per_day=visits_per_day,
            seasonal_multiplier=seasonal_mult,
            demand_providers_per_shift=providers_per_shift,
            demand_fte_required=fte_required,
            paid_fte=paid_fte,
            effective_fte=effective_fte,
            flex_fte=flex_fte,
            providers_on_floor=providers_on_floor,
            shift_coverage_gap=shift_coverage_gap,
            patients_per_provider_per_shift=pts_per_prov,
            zone=zone,
            hiring_mode=hiring_mode,
            permanent_cost=perm_cost,
            flex_cost=flex_cost,
            support_cost=support_cost,
            burnout_penalty=burnout_pen,
            overstaff_penalty=overstaff_pen,
            lost_revenue=lost_revenue,
            turnover_events=turnover_events,
            turnover_cost=turnover_cost,
            cumulative_score=total_score,
        ))

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
        "total_support_cost":      sum(mo.support_cost for mo in months),
        "total_lost_revenue":      sum(mo.lost_revenue for mo in months),
        "total_turnover_cost":     sum(mo.turnover_cost for mo in months),
        "total_burnout_penalty":   sum(mo.burnout_penalty for mo in months),
        "total_overstaff_penalty": sum(mo.overstaff_penalty for mo in months),
        "q_avg_visits": {
            q: float(np.mean([mo.demand_visits_per_day for mo in months
                               if mo.year == 1 and mo.quarter == q]))
            for q in range(1, 5)
        },
        "q_avg_fte_required": {
            q: float(np.mean([mo.demand_fte_required for mo in months
                               if mo.year == 1 and mo.quarter == q]))
            for q in range(1, 5)
        },
    }

    return PolicyResult(
        base_fte=base_fte, winter_fte=winter_fte,
        req_post_month=req_post_month,
        months=months, total_score=total_score,
        annual_swb_per_visit=annual_swb,
        swb_violation=swb_violation,
        summary=summary,
    )


def optimize(cfg: ClinicConfig,
             b_range: Tuple[float, float, float] = (2, 20, 0.5),
             w_range_above: Tuple[float, float, float] = (0, 10, 0.5),
             horizon_months: int = 36) -> Tuple[PolicyResult, List[PolicyResult]]:
    """Grid search over (Base FTE, Winter FTE)."""
    b_vals = np.arange(b_range[0], b_range[1] + b_range[2], b_range[2])
    all_policies: List[PolicyResult] = []
    best_policy: Optional[PolicyResult] = None
    best_score = float("inf")

    for b in b_vals:
        w_vals = np.arange(b, b + w_range_above[1] + w_range_above[2], w_range_above[2])
        for w in w_vals:
            p = simulate_policy(float(round(b,2)), float(round(w,2)), cfg, horizon_months)
            all_policies.append(p)
            if p.total_score < best_score:
                best_score = p.total_score
                best_policy = p

    return best_policy, all_policies
