"""
PSM Simulation Engine — v3
36-month staffing simulation with optimizer

Seasonality Model:
  Users set a volume impact % per quarter (e.g. +20% winter, -10% summer).
  These are applied as multiplicative modifiers on base visits/day.
  The resulting per-month seasonality index is:
      visits = base_visits * seasonal_multiplier(month)
  Flu uplift remains a separate additive layer (visits/day) on top of that.

Quarterly definitions (calendar months):
  Q1 = Jan, Feb, Mar
  Q2 = Apr, May, Jun
  Q3 = Jul, Aug, Sep
  Q4 = Oct, Nov, Dec

Staffing Policy (3 levels):
  Base FTE    — the year-round floor; never hire below this in normal ops
  Winter FTE  — targeted level for flu season (Nov–Feb); hired up before flu anchor
  Summer Floor — minimum FTE allowed during summer valley; attrition sheds naturally
                 to this level, no replacement hiring until demand recovers

Turnover Shed:
  Post-flu, the model does NOT force terminations.
  Natural attrition is the only shed mechanism.
  The optimizer sizes Base and Winter FTE knowing that turnover will
  organically walk headcount back down after the winter peak.
  During summer, replacement hiring is paused until paid_fte < summer_floor_fte,
  allowing the natural shed to complete before the cost of replacement is incurred.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


# ── Month → Quarter mapping (0-indexed calendar month) ───────────────────────
# Q1=0, Q2=1, Q3=2, Q4=3
MONTH_TO_QUARTER = [0, 0, 0,   # Jan Feb Mar  → Q1
                    1, 1, 1,   # Apr May Jun  → Q2
                    2, 2, 2,   # Jul Aug Sep  → Q3
                    3, 3, 3]   # Oct Nov Dec  → Q4

QUARTER_NAMES    = ["Q1 (Jan–Mar)", "Q2 (Apr–Jun)", "Q3 (Jul–Sep)", "Q4 (Oct–Dec)"]
QUARTER_LABELS   = ["Q1", "Q2", "Q3", "Q4"]


@dataclass
class ClinicConfig:
    # ── Demand ────────────────────────────────────────────────────────────────
    base_visits_per_day: float = 80.0
    budgeted_patients_per_provider_per_day: float = 36.0
    peak_factor: float = 1.10

    # Quarterly volume impact (fractional; 0.20 = +20%, -0.10 = -10%)
    # Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Nov-Dec
    quarterly_volume_impact: List[float] = field(
        default_factory=lambda: [0.20, 0.0, -0.10, 0.05]
    )

    # Additive flu uplift visits/day by calendar month (0-indexed)
    # Kept separate from the seasonality curve — represents illness-driven surge
    flu_uplift: List[float] = field(default_factory=lambda: [
        10.0, 8.0, 3.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 5.0, 8.0
    ])

    # ── Shift Coverage ────────────────────────────────────────────────────────
    operating_days_per_week: int = 7
    shifts_per_day: int = 1
    shift_hours: float = 12.0
    fte_shifts_per_week: float = 3.0
    fte_fraction: float = 0.9

    # ── Provider Economics ────────────────────────────────────────────────────
    annual_provider_cost_perm: float = 200_000
    annual_provider_cost_flex: float = 280_000
    net_revenue_per_visit: float = 110.0
    swb_target_per_visit: float = 32.0

    # ── Hiring Physics ────────────────────────────────────────────────────────
    days_to_sign: int = 30
    days_to_credential: int = 60
    days_to_independent: int = 90
    flu_anchor_month: int = 11   # 1-indexed; month provider must be independent by

    # ── Attrition & Turnover ─────────────────────────────────────────────────
    monthly_attrition_rate: float = 0.015   # natural; NOT accelerated
    turnover_replacement_cost_per_provider: float = 80_000

    # ── Summer shed floor ─────────────────────────────────────────────────────
    # During summer (Q3 months), replacement hiring is paused until paid FTE
    # drops below this fraction of base FTE. This lets natural attrition shed
    # post-winter surplus without immediately backfilling.
    summer_shed_floor_pct: float = 0.85    # e.g. 0.85 = don't replace until below 85% of base

    # ── Ramp Productivity ─────────────────────────────────────────────────────
    ramp_months: int = 3
    ramp_productivity: List[float] = field(default_factory=lambda: [0.4, 0.7, 0.9])

    # ── Penalty Weights ───────────────────────────────────────────────────────
    burnout_penalty_per_red_month: float = 50_000
    overstaff_penalty_per_fte_month: float = 3_000
    swb_violation_penalty: float = 500_000

    # ── Zone Thresholds (above budgeted pts/provider/shift) ──────────────────
    yellow_threshold_above: float = 4.0
    red_threshold_above: float = 8.0

    # ── Derived: shift coverage ───────────────────────────────────────────────
    @property
    def shift_slots_per_week(self) -> float:
        return self.operating_days_per_week * self.shifts_per_day

    @property
    def shifts_per_week_per_fte(self) -> float:
        return self.fte_shifts_per_week / self.fte_fraction

    @property
    def fte_per_shift_slot(self) -> float:
        return self.shift_slots_per_week / self.shifts_per_week_per_fte

    # ── Derived: seasonality index per month ─────────────────────────────────
    @property
    def seasonality_index(self) -> List[float]:
        """
        Per-month multiplier derived from quarterly_volume_impact.
        All months in a quarter share the same multiplier.
        e.g. Q1 impact=+0.20 → Jan/Feb/Mar each get 1.20
        """
        return [1.0 + self.quarterly_volume_impact[MONTH_TO_QUARTER[m]]
                for m in range(12)]


@dataclass
class MonthResult:
    month: int
    calendar_month: int
    year: int
    quarter: int                          # 1-4

    # Demand
    demand_visits_per_day: float
    seasonal_multiplier: float            # what the quarter contributed
    demand_providers_per_shift: float
    demand_fte_required: float

    # Supply
    paid_fte: float
    effective_fte: float
    flex_fte: float

    # Shift coverage
    providers_on_floor: float
    shift_coverage_gap: float

    # Load
    patients_per_provider_per_shift: float
    zone: str

    # Hiring state
    hiring_mode: str      # "growth", "replacement", "shed_pause", "freeze_flu"

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
def compute_demand(month_idx: int, cfg: ClinicConfig) -> Tuple[float, float, float, float]:
    """
    Returns (visits_per_day, seasonal_multiplier, providers_per_shift, fte_required).
    """
    cal = month_idx % 12
    seasonal_mult = cfg.seasonality_index[cal]
    visits = (
        cfg.base_visits_per_day * seasonal_mult * cfg.peak_factor
        + cfg.flu_uplift[cal]
    )
    providers_per_shift = visits / cfg.budgeted_patients_per_provider_per_day
    fte_required = providers_per_shift * cfg.fte_per_shift_slot
    return visits, seasonal_mult, providers_per_shift, fte_required


# ──────────────────────────────────────────────────────────────────────────────
def simulate_policy(base_fte: float, winter_fte: float, cfg: ClinicConfig,
                    horizon_months: int = 36) -> PolicyResult:
    """
    Simulate a 3-level staffing policy:
      - Winter FTE during flu season (Nov–Feb)
      - Base FTE year-round floor
      - Natural shed down to summer_shed_floor during Q3 (no forced terminations)

    Hiring rules:
      Flu season (Nov–Feb):  replacement only (no growth; 90-day notice enforced)
      Summer (Jul–Sep):      growth/replacement paused while paid_fte > summer_floor_fte
      Other months:          hire to reach Base FTE; hire extra for Winter if approaching flu
    """
    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months = int(np.ceil(total_lead_days / 30))
    req_post_month = max(1, cfg.flu_anchor_month - lead_months)

    # Summer floor: below this we backfill even in summer
    summer_floor_fte = base_fte * cfg.summer_shed_floor_pct

    months: List[MonthResult] = []
    paid_fte = base_fte
    ramp_cohorts: List[List] = []

    total_score = 0.0
    total_swb_cost = 0.0
    total_simulated_visits = 0.0

    flu_months    = {11, 12, 1, 2}   # Nov–Feb
    summer_months = {7, 8, 9}        # Jul–Sep (Q3)

    for m in range(horizon_months):
        cal_month = (m % 12) + 1        # 1-indexed
        year      = (m // 12) + 1
        quarter   = MONTH_TO_QUARTER[cal_month - 1] + 1   # 1-indexed

        in_flu    = cal_month in flu_months
        in_summer = cal_month in summer_months

        # ── Determine target FTE ──────────────────────────────────────────────
        if in_flu:
            target_fte = winter_fte
        elif in_summer:
            # In summer: let attrition shed. Floor = summer_shed_floor_fte
            target_fte = summer_floor_fte
        else:
            target_fte = base_fte

        # ── Attrition (always runs — this IS the shed mechanism) ─────────────
        attrition_events = paid_fte * cfg.monthly_attrition_rate
        paid_fte = max(0.0, paid_fte - attrition_events)
        turnover_events = attrition_events

        # ── Hiring decision ───────────────────────────────────────────────────
        hiring_mode = "none"

        if in_flu:
            # Flu season: replace only down to base_fte (no growth hiring)
            if paid_fte < base_fte:
                replacement = base_fte - paid_fte
                paid_fte += replacement
                ramp_cohorts.append([cfg.ramp_months, replacement])
                hiring_mode = "freeze_flu"
            else:
                hiring_mode = "freeze_flu"

        elif in_summer:
            # Summer: pause replacement until FTE drops below summer_floor_fte
            if paid_fte < summer_floor_fte:
                replacement = summer_floor_fte - paid_fte
                paid_fte += replacement
                ramp_cohorts.append([cfg.ramp_months, replacement])
                hiring_mode = "replacement"
            else:
                # Natural shed in progress — do nothing
                hiring_mode = "shed_pause"

        else:
            # Normal months: hire up to target
            if paid_fte < target_fte:
                new_hires = target_fte - paid_fte
                paid_fte += new_hires
                ramp_cohorts.append([cfg.ramp_months, new_hires])
                hiring_mode = "growth"
            else:
                hiring_mode = "none"

        # ── Ramp drag → Effective FTE ─────────────────────────────────────────
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

        # ── Demand ────────────────────────────────────────────────────────────
        visits_per_day, seasonal_mult, providers_per_shift, fte_required = compute_demand(m, cfg)

        # ── Providers on floor ────────────────────────────────────────────────
        fte_per_slot = cfg.fte_per_shift_slot
        providers_on_floor = (effective_fte / fte_per_slot) if fte_per_slot > 0 else 0.0
        shift_coverage_gap = providers_per_shift - providers_on_floor

        # ── Load & Zone ───────────────────────────────────────────────────────
        pts_per_prov = (visits_per_day / providers_on_floor) if providers_on_floor > 0 else 9999.0

        budget = cfg.budgeted_patients_per_provider_per_day
        if pts_per_prov <= budget + cfg.yellow_threshold_above:
            zone = "Green"
        elif pts_per_prov <= budget + cfg.red_threshold_above:
            zone = "Yellow"
        else:
            zone = "Red"

        # ── Flex FTE (absorbs load above yellow threshold) ────────────────────
        overload_pts = max(0.0, pts_per_prov - (budget + cfg.yellow_threshold_above))
        if overload_pts > 0 and providers_on_floor > 0:
            extra_providers = (overload_pts * providers_on_floor) / budget
            flex_fte = extra_providers * fte_per_slot
        else:
            flex_fte = 0.0

        overstaff_providers = max(0.0, providers_on_floor - providers_per_shift)

        # ── Costs ─────────────────────────────────────────────────────────────
        perm_cost = paid_fte * (cfg.annual_provider_cost_perm / 12)
        flex_cost = flex_fte * (cfg.annual_provider_cost_flex / 12)

        if zone == "Red":
            severity   = overload_pts / cfg.red_threshold_above
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

        total_swb_cost        += perm_cost + flex_cost
        total_simulated_visits += visits_per_day * 30

        months.append(MonthResult(
            month=m + 1,
            calendar_month=cal_month,
            year=year,
            quarter=quarter,
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
            burnout_penalty=burnout_pen,
            overstaff_penalty=overstaff_pen,
            lost_revenue=lost_revenue,
            turnover_events=turnover_events,
            turnover_cost=turnover_cost,
            cumulative_score=total_score,
        ))

    # ── SWB — annualised from actual simulation ───────────────────────────────
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
        # Quarterly demand averages (Year 1)
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
