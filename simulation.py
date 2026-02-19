"""
PSM Simulation Engine — v6
36-month staffing simulation with optimizer.

Key architecture changes from v5:
  - Load-band optimizer: target a pts/APC range, not a hard FTE number.
    FTE targets derived monthly from demand × band parameters.
  - Attrition-as-burnout-function: overwork drives attrition above base rate.
    effective_monthly_attrition = base_rate × (1 + overload_factor × excess_load_pct)
  - Explicit hire calendar: each hire event recorded with calendar date.
  - Marginal APC analysis: compare_marginal_fte() utility.
  - Stress test: simulate_stress() applies volume shocks to any policy.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import math

MONTH_TO_QUARTER = [0,0,0, 1,1,1, 2,2,2, 3,3,3]
QUARTER_NAMES    = ["Q1 (Jan–Mar)","Q2 (Apr–Jun)","Q3 (Jul–Sep)","Q4 (Oct–Dec)"]
QUARTER_LABELS   = ["Q1","Q2","Q3","Q4"]
MONTH_NAMES_SIM  = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]


# ══════════════════════════════════════════════════════════════════════════════
# SUPPORT STAFF CONFIG
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class SupportStaffConfig:
    """
    Support staff rates and ratios. Cost folds into SWB/visit only.
    Ratios are per APC on floor per shift. RT is flat per-shift.
    Supervision costs added only when hours > 0.
    """
    physician_rate_hr:   float = 135.79
    app_rate_hr:         float = 62.00
    psr_rate_hr:         float = 21.23
    ma_rate_hr:          float = 24.14
    rt_rate_hr:          float = 31.36
    supervisor_rate_hr:  float = 28.25

    ma_ratio:            float = 1.0
    psr_ratio:           float = 1.0
    rt_flat_fte:         float = 1.0
    supervisor_hrs_mo:   float = 0.0
    supervisor_admin_mo: float = 0.0

    benefits_load_pct:   float = 0.30
    bonus_pct:           float = 0.10
    ot_sick_pct:         float = 0.04

    @property
    def total_multiplier(self) -> float:
        return 1.0 + self.benefits_load_pct + self.bonus_pct + self.ot_sick_pct

    def monthly_support_cost(self, avg_providers_on_floor: float,
                              shift_hours: float,
                              operating_days_per_week: float) -> float:
        operating_days_mo  = operating_days_per_week * (52 / 12)
        hours_per_staff_mo = shift_hours * operating_days_mo

        ma_cost  = avg_providers_on_floor * self.ma_ratio  * self.ma_rate_hr  * hours_per_staff_mo * self.total_multiplier
        psr_cost = avg_providers_on_floor * self.psr_ratio * self.psr_rate_hr * hours_per_staff_mo * self.total_multiplier
        rt_cost  = self.rt_flat_fte       * self.rt_rate_hr * hours_per_staff_mo * self.total_multiplier

        phys_sup_cost = (self.supervisor_hrs_mo   * self.physician_rate_hr  * self.total_multiplier
                         if self.supervisor_hrs_mo   > 0 else 0.0)
        sup_admin_cost= (self.supervisor_admin_mo * self.supervisor_rate_hr * self.total_multiplier
                         if self.supervisor_admin_mo > 0 else 0.0)

        return ma_cost + psr_cost + rt_cost + phys_sup_cost + sup_admin_cost


# ══════════════════════════════════════════════════════════════════════════════
# CLINIC CONFIG
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ClinicConfig:
    # ── Demand ───────────────────────────────────────────────────────────────
    base_visits_per_day: float = 80.0
    budgeted_patients_per_provider_per_day: float = 36.0
    peak_factor: float = 1.10
    quarterly_volume_impact: List[float] = field(
        default_factory=lambda: [0.20, 0.0, -0.10, 0.05])
    annual_growth_pct:  float = 10.0   # % YoY volume growth (compounded monthly)

    # ── Shift Coverage ────────────────────────────────────────────────────────
    operating_days_per_week: int   = 7
    shifts_per_day:          int   = 1
    shift_hours:             float = 12.0
    fte_shifts_per_week:     float = 3.0
    fte_fraction:            float = 0.9

    # ── Load Band (NEW) ───────────────────────────────────────────────────────
    # Instead of targeting hard FTE levels, we target a pts/APC load range.
    # The optimizer searches over (load_band_lo, load_band_hi) pairs.
    # FTE target each month = visits / load_target, where load_target slides
    # within the band based on season.
    # load_band_lo: comfortable load floor (hire if load would exceed this)
    # load_band_hi: max acceptable load (never exceed this without flex)
    # load_winter_target: target load during flu season (can be higher, more
    #   efficient use of temporarily boosted capacity)
    load_band_lo:        float = 30.0   # hire up if load would fall below this
    load_band_hi:        float = 38.0   # trigger flex above this
    load_winter_target:  float = 36.0   # target during Nov-Feb (tighter margin)
    use_load_band:       bool  = True   # False = legacy Base/Winter FTE mode

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
    flu_anchor_month:    int = 11

    # ── Attrition & Turnover ─────────────────────────────────────────────────
    annual_attrition_pct:     float = 18.0
    turnover_replacement_pct: float = 40.0

    # Overload-driven attrition multiplier (NEW)
    # When pts/APC exceeds budget, attrition rate scales up:
    #   effective_rate = base_rate × (1 + overload_attrition_factor × excess_pct)
    # e.g. factor=1.5: running 20% over budget → attrition × 1.30
    overload_attrition_factor: float = 1.5

    # ── Summer Shed ───────────────────────────────────────────────────────────
    summer_shed_floor_pct: float = 0.85

    # ── Ramp Productivity ────────────────────────────────────────────────────
    ramp_months:       int = 3
    ramp_productivity: List[float] = field(default_factory=lambda: [0.4, 0.7, 0.9])

    # ── Fixed Overhead ───────────────────────────────────────────────────────
    monthly_fixed_overhead: float = 0.0   # optional: rent, non-clinical, etc.

    # ── Penalty Weights ───────────────────────────────────────────────────────
    burnout_pct_per_red_month:       float = 25.0
    overstaff_penalty_per_fte_month: float = 3_000
    swb_violation_penalty:           float = 500_000

    # ── Zone Thresholds ───────────────────────────────────────────────────────
    # Zone thresholds — pts/APC above budget that triggers each zone.
    # Budget (36) is the GREEN ceiling: any load above budget enters Yellow.
    # yellow_threshold_above = 0 means Yellow starts immediately above budget.
    # red_threshold_above = 4 means Red starts at budget + 4 (e.g. 40 pts/APC).
    yellow_threshold_above: float = 0.0   # Green: <= budget; Yellow: budget < x <= budget+4
    red_threshold_above:    float = 4.0   # Red:   > budget + 4

    # ── Derived ───────────────────────────────────────────────────────────────
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
        """Total shift slots to fill per week (operating days x shifts/day)."""
        return self.operating_days_per_week * self.shifts_per_day

    @property
    def shifts_per_week_per_fte(self) -> float:
        """Shifts per week a single FTE is contracted to work."""
        return self.fte_shifts_per_week / self.fte_fraction

    @property
    def fte_per_shift_slot(self) -> float:
        """
        FTE required to keep ONE concurrent provider slot filled continuously.

        Logic: one slot needs operating_days_per_week shifts covered per week.
        One APC works fte_shifts_per_week shifts/week (regardless of fte_fraction,
        which only affects cost — not scheduling coverage).
        shifts_per_day is already captured in demand (providers_per_shift) to
        determine how many concurrent slots are needed; it must NOT multiply
        the FTE-per-slot conversion again or it double-counts.

        Example: 7 operating days, 3 shifts/week per APC ->
            fte_per_slot = 7 / 3 = 2.33
            (need 2.33 APCs to keep 1 concurrent slot filled every day)
        """
        if self.fte_shifts_per_week <= 0:
            return 1.0
        return self.operating_days_per_week / self.fte_shifts_per_week

    @property
    def seasonality_index(self) -> List[float]:
        return [1.0 + self.quarterly_volume_impact[MONTH_TO_QUARTER[m]]
                for m in range(12)]


# ══════════════════════════════════════════════════════════════════════════════
# HIRE EVENT — explicit calendar record
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class HireEvent:
    simulation_month: int     # 1-indexed position in 36-month run
    calendar_month:   int     # 1-12
    year:             int     # 1-3
    fte_hired:        float
    mode:             str     # "growth" | "attrition_replace" | "winter_ramp" | "floor_protect"
    post_by_month:    int     # calendar month req must be posted by
    post_by_year:     int
    independent_month: int    # calendar month APC will be independent
    independent_year:  int


# ══════════════════════════════════════════════════════════════════════════════
# MONTH RESULT
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class MonthResult:
    month:          int
    calendar_month: int
    year:           int
    quarter:        int

    demand_visits_per_day:        float
    seasonal_multiplier:          float
    demand_providers_per_shift:   float
    demand_fte_required:          float

    paid_fte:       float
    effective_fte:  float
    flex_fte:       float

    providers_on_floor:              float
    shift_coverage_gap:              float
    patients_per_provider_per_shift: float
    zone:           str
    hiring_mode:    str

    # Load band metrics (NEW)
    load_band_lo:   float   # configured floor
    load_band_hi:   float   # configured ceiling
    within_band:    bool    # True if load is within target band

    # Attrition (NEW: includes overload-driven component)
    effective_attrition_rate: float   # actual rate this month (base + overload)
    overload_attrition_delta: float   # extra attrition due to overwork

    permanent_cost:    float
    flex_cost:         float
    support_cost:      float
    burnout_penalty:   float
    overstaff_penalty: float
    lost_revenue:      float
    turnover_events:   float
    turnover_cost:     float
    cumulative_score:  float
    # EBITDA fields
    revenue_captured:    float
    visits_captured:     float
    throughput_factor:   float
    ebitda_contribution: float
    cumulative_ebitda:   float


@dataclass
class PolicyResult:
    base_fte:         float
    winter_fte:       float
    req_post_month:   int
    months:           List[MonthResult]
    hire_events:      List[HireEvent]    # NEW: explicit hire calendar
    total_score:      float
    annual_swb_per_visit: float
    swb_violation:    bool
    summary:          Dict

    ebitda_summary:    Optional[Dict] = None
    # Marginal analysis (NEW) — populated by compare_marginal_fte()
    marginal_analysis: Optional[Dict] = None


# ══════════════════════════════════════════════════════════════════════════════
# DEMAND COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════
def compute_demand(month_idx: int, cfg: ClinicConfig,
                   volume_shock: float = 0.0) -> Tuple[float, float, float, float]:
    """
    Returns (visits_per_day, seasonal_multiplier, providers_per_shift, fte_required).
    volume_shock: fractional additive shock (0.15 = +15% for stress test).
    Growth is compounded monthly: (1 + annual_rate)^(month/12).
    """
    cal = month_idx % 12
    seasonal_mult = cfg.seasonality_index[cal]
    growth_mult = (1.0 + cfg.annual_growth_pct / 100.0) ** (month_idx / 12.0)
    visits = cfg.base_visits_per_day * seasonal_mult * cfg.peak_factor * growth_mult * (1.0 + volume_shock)
    providers_per_shift = visits / cfg.budgeted_patients_per_provider_per_day
    fte_required = providers_per_shift * cfg.fte_per_shift_slot
    return visits, seasonal_mult, providers_per_shift, fte_required


def fte_for_load_target(visits_per_day: float, load_target: float,
                         cfg: ClinicConfig) -> float:
    """FTE needed to achieve a specific pts/APC load."""
    if load_target <= 0:
        return 0.0
    providers_needed = visits_per_day / load_target
    return providers_needed * cfg.fte_per_shift_slot


# ══════════════════════════════════════════════════════════════════════════════
# CORE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════
def simulate_policy(base_fte: float, winter_fte: float, cfg: ClinicConfig,
                    horizon_months: int = 36,
                    volume_shocks: Optional[Dict[int, float]] = None) -> PolicyResult:
    """
    Simulate a staffing policy over horizon_months.

    base_fte / winter_fte: used when cfg.use_load_band=False (legacy mode)
                           OR as initial seed when use_load_band=True.
    volume_shocks: dict of {simulation_month_1indexed: fractional_shock}
                   e.g. {13: 0.15} = +15% volume in month 13
    """
    if volume_shocks is None:
        volume_shocks = {}

    total_lead_days = cfg.days_to_sign + cfg.days_to_credential + cfg.days_to_independent
    lead_months     = int(np.ceil(total_lead_days / 30))
    req_post_month  = max(1, cfg.flu_anchor_month - lead_months)

    # Flu season: anchor month + 3 months forward
    flu_months = set()
    for offset in range(4):
        flu_months.add(((cfg.flu_anchor_month - 1 + offset) % 12) + 1)

    # Pre-flu window: ramp_months before flu anchor so new hires are
    # independent BY the flu anchor month. Uses ramp_months (not lead_months)
    # because lead time is for req posting; ramp is the onboarding period.
    # e.g. anchor=Dec, ramp=1 month → pre-flu fires in November only.
    pre_flu_months = set()
    for offset in range(1, cfg.ramp_months + 1):
        pre_flu_months.add(((cfg.flu_anchor_month - 1 - offset) % 12) + 1)

    summer_months = {7, 8, 9}

    months:       List[MonthResult] = []
    hire_events:  List[HireEvent]   = []

    paid_fte      = base_fte
    ramp_cohorts: List[List] = []   # [[months_remaining, fte_size], ...]

    total_score            = 0.0
    total_swb_cost         = 0.0
    total_simulated_visits = 0.0
    total_ebitda           = 0.0

    base_monthly_attrition    = cfg.monthly_attrition_rate
    turnover_replace_cost     = cfg.turnover_replacement_cost_per_provider
    burnout_per_red           = cfg.burnout_penalty_per_red_month
    budget                    = cfg.budgeted_patients_per_provider_per_day
    fte_per_slot              = cfg.fte_per_shift_slot

    # Initialize paid_fte based on the starting calendar month and the policy
    # being tested.  The optimizer searches over (base_fte, winter_fte) — use
    # those values directly as the initial condition rather than recomputing.
    #
    # If the simulation starts in a flu month → seed at winter_fte (already
    # staffed for peak season).  Otherwise seed at base_fte.
    # Seed from actual month-0 demand at midband load — always decoupled from
    # base_fte/winter_fte so the hire calendar shows the full journey from day 1.
    _start_visits, _, _, _ = compute_demand(0, cfg)
    if cfg.use_load_band:
        _mid     = (cfg.load_band_lo + cfg.load_band_hi) / 2.0
        paid_fte = fte_for_load_target(_start_visits, _mid, cfg)
    else:
        paid_fte = base_fte   # legacy explicit-policy mode

    summer_floor_fte = paid_fte * cfg.summer_shed_floor_pct  # updated below

    for m in range(horizon_months):
        cal_month = (m % 12) + 1
        year      = (m // 12) + 1
        quarter   = MONTH_TO_QUARTER[cal_month - 1] + 1

        in_flu     = cal_month in flu_months
        in_pre_flu = cal_month in pre_flu_months
        in_summer  = cal_month in summer_months

        # Volume shock for stress testing
        shock = volume_shocks.get(m + 1, 0.0)

        # Demand this month
        visits_per_day, seasonal_mult, providers_per_shift, fte_required = \
            compute_demand(m, cfg, shock)

        # ── Determine FTE target ──────────────────────────────────────────────
        if cfg.use_load_band:
            if in_flu or in_pre_flu:
                # Pre-flu + flu: hire to winter load target — this is the key
                # seasonal lever. Higher load_winter_target = less staff, lower = more.
                # winter_fte acts as an explicit minimum floor if set.
                band_target = fte_for_load_target(visits_per_day, cfg.load_winter_target, cfg)
                target_fte  = max(band_target, winter_fte) if winter_fte > 0 else band_target
            elif in_summer:
                # Summer: aim for midband — comfortable, not overstaffed
                mid_load   = (cfg.load_band_lo + cfg.load_band_hi) / 2
                target_fte = fte_for_load_target(visits_per_day, mid_load, cfg)
            else:
                # Normal: aim for midband
                mid_load   = (cfg.load_band_lo + cfg.load_band_hi) / 2
                target_fte = fte_for_load_target(visits_per_day, mid_load, cfg)

            # Hard floor: never let FTE drop below what would push load above hi
            floor_fte  = fte_for_load_target(visits_per_day, cfg.load_band_hi, cfg)
            summer_floor_fte = floor_fte * cfg.summer_shed_floor_pct
        else:
            # Legacy mode
            if in_flu:
                target_fte = winter_fte
            elif in_summer:
                target_fte = base_fte * cfg.summer_shed_floor_pct
            else:
                target_fte = base_fte
            summer_floor_fte = base_fte * cfg.summer_shed_floor_pct

        # ── Attrition (overload-responsive) ──────────────────────────────────
        # Compute current load using last month's effective FTE as proxy
        # (we don't have this month's yet — use paid_fte as approximation)
        current_providers = (paid_fte / fte_per_slot) if fte_per_slot > 0 else 0
        current_load      = (visits_per_day / current_providers) if current_providers > 0 else budget
        excess_pct        = max(0.0, (current_load - budget) / budget)
        effective_monthly_attrition = base_monthly_attrition * (
            1.0 + cfg.overload_attrition_factor * excess_pct
        )
        overload_attrition_delta = effective_monthly_attrition - base_monthly_attrition

        fte_before_attrition = paid_fte
        attrition_events     = paid_fte * effective_monthly_attrition
        paid_fte             = max(0.0, paid_fte - attrition_events)
        turnover_events      = attrition_events

        # ── Hiring decision ───────────────────────────────────────────────────
        # Simple rule: hire to target every month except summer (allow natural shed).
        # The load-band target already encodes seasonality — flu months get a
        # tighter/higher target via load_winter_target.
        # No freeze, no pre-flu window — demand-responsive hiring every month.
        hiring_mode = "none"

        if in_summer:
            if paid_fte < summer_floor_fte:
                new_hires = summer_floor_fte - paid_fte
                paid_fte += new_hires
                ramp_cohorts.append([cfg.ramp_months, new_hires])
                _log_hire(hire_events, m, cal_month, year, new_hires,
                          "floor_protect", lead_months, cfg)
                hiring_mode = "floor_protect"
            else:
                hiring_mode = "shed_pause"

        elif paid_fte < target_fte:
            new_hires = target_fte - paid_fte
            paid_fte += new_hires
            ramp_cohorts.append([cfg.ramp_months, new_hires])
            mode = ("winter_ramp" if in_flu or in_pre_flu
                    else "growth" if new_hires > attrition_events * 1.05
                    else "attrition_replace")
            _log_hire(hire_events, m, cal_month, year, new_hires,
                      mode, lead_months, cfg)
            hiring_mode = mode

        elif paid_fte > target_fte * 1.05 and not in_flu:
            # Modest passive shed outside flu season — don't force layoffs,
            # just let attrition bring it down
            hiring_mode = "shed_passive"

        else:
            hiring_mode = "maintain"

        # ── Ramp drag ─────────────────────────────────────────────────────────
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

        # ── Providers on floor ────────────────────────────────────────────────
        providers_on_floor = (effective_fte / fte_per_slot) if fte_per_slot > 0 else 0.0
        shift_coverage_gap = providers_per_shift - providers_on_floor

        # ── Load & Zone ───────────────────────────────────────────────────────
        pts_per_prov = (visits_per_day / providers_on_floor) if providers_on_floor > 0 else 9999.0

        if pts_per_prov <= budget + cfg.yellow_threshold_above:
            zone = "Green"
        elif pts_per_prov <= budget + cfg.red_threshold_above:
            zone = "Yellow"
        else:
            zone = "Red"

        within_band = cfg.load_band_lo <= pts_per_prov <= cfg.load_band_hi

        # ── Flex FTE ──────────────────────────────────────────────────────────
        overload_pts = max(0.0, pts_per_prov - (budget + cfg.yellow_threshold_above))
        if overload_pts > 0 and providers_on_floor > 0:
            extra_providers = (overload_pts * providers_on_floor) / budget
            flex_fte = extra_providers * fte_per_slot
        else:
            flex_fte = 0.0

        overstaff_providers = max(0.0, providers_on_floor - providers_per_shift)

        # ── Costs ─────────────────────────────────────────────────────────────
        perm_cost    = paid_fte  * (cfg.annual_provider_cost_perm / 12)
        flex_cost    = flex_fte  * (cfg.annual_provider_cost_flex / 12)
        support_cost = cfg.support.monthly_support_cost(
            providers_on_floor, cfg.shift_hours, cfg.operating_days_per_week)

        if zone == "Red":
            severity    = overload_pts / max(cfg.red_threshold_above, 1)
            burnout_pen = burnout_per_red * (1 + severity ** 2)
        elif zone == "Yellow":
            burnout_pen = burnout_per_red * 0.2
        else:
            burnout_pen = 0.0

        overstaff_pen = overstaff_providers * fte_per_slot * cfg.overstaff_penalty_per_fte_month

        # ── Throughput degradation & revenue captured ───────────────────────
        if zone == "Green":
            throughput_factor = 1.00
        elif zone == "Yellow":
            throughput_factor = 0.95
        else:
            throughput_factor = 0.85

        visits_captured  = visits_per_day * 30 * throughput_factor
        revenue_captured = visits_captured * cfg.net_revenue_per_visit
        lost_revenue     = (visits_per_day * 30 - visits_captured) * cfg.net_revenue_per_visit

        # ── Turnover cost ─────────────────────────────────────────────────────
        turnover_cost = turnover_events * turnover_replace_cost
        if zone in ("Yellow", "Red"):
            turnover_cost *= 1.3

        # ── EBITDA contribution: Revenue − SWB − Flex − Turnover − Burnout − Fixed
        fixed_cost     = cfg.monthly_fixed_overhead
        ebitda_month   = (revenue_captured
                          - (perm_cost + support_cost)
                          - flex_cost
                          - turnover_cost
                          - burnout_pen
                          - fixed_cost)
        total_ebitda  += ebitda_month

        # ── Legacy score (optimizer still minimizes cost for heatmap) ────────
        month_score = (perm_cost + flex_cost + support_cost + burnout_pen
                       + overstaff_pen + lost_revenue + turnover_cost)
        total_score += month_score

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
            load_band_lo=cfg.load_band_lo,
            load_band_hi=cfg.load_band_hi,
            within_band=within_band,
            effective_attrition_rate=effective_monthly_attrition,
            overload_attrition_delta=overload_attrition_delta,
            permanent_cost=perm_cost,
            flex_cost=flex_cost,
            support_cost=support_cost,
            burnout_penalty=burnout_pen,
            overstaff_penalty=overstaff_pen,
            lost_revenue=lost_revenue,
            turnover_events=turnover_events,
            turnover_cost=turnover_cost,
            cumulative_score=total_score,
            revenue_captured=revenue_captured,
            visits_captured=visits_captured,
            throughput_factor=throughput_factor,
            ebitda_contribution=ebitda_month,
            cumulative_ebitda=total_ebitda,
        ))

    # ── SWB ───────────────────────────────────────────────────────────────────
    annual_swb_cost = total_swb_cost / 3
    annual_visits   = total_simulated_visits / 3
    annual_swb      = annual_swb_cost / annual_visits if annual_visits > 0 else 0.0
    swb_violation   = annual_swb > cfg.swb_target_per_visit
    if swb_violation:
        total_score += cfg.swb_violation_penalty

    red_m    = sum(1 for mo in months if mo.zone == "Red")
    yellow_m = sum(1 for mo in months if mo.zone == "Yellow")
    green_m  = sum(1 for mo in months if mo.zone == "Green")

    # EBITDA waterfall
    total_revenue_captured = sum(mo.revenue_captured for mo in months)
    total_swb_3yr          = sum(mo.permanent_cost + mo.support_cost for mo in months)
    total_flex_3yr         = sum(mo.flex_cost for mo in months)
    total_turnover_3yr     = sum(mo.turnover_cost for mo in months)
    total_burnout_3yr      = sum(mo.burnout_penalty for mo in months)
    total_fixed_3yr        = cfg.monthly_fixed_overhead * 36
    total_visits_captured  = sum(mo.visits_captured for mo in months)
    total_visits_demanded  = sum(mo.demand_visits_per_day * 30 for mo in months)

    summary = {
        "total_score":              total_score,
        "red_months":               red_m,
        "yellow_months":            yellow_m,
        "green_months":             green_m,
        "avg_flex_fte":             float(np.mean([mo.flex_fte for mo in months])),
        "total_turnover_events":    sum(mo.turnover_events for mo in months),
        "annual_swb_per_visit":     annual_swb,
        "annual_visits":            annual_visits,
        "swb_violation":            swb_violation,
        "req_post_month":           req_post_month,
        "total_permanent_cost":     sum(mo.permanent_cost for mo in months),
        "total_flex_cost":          sum(mo.flex_cost for mo in months),
        "total_support_cost":       sum(mo.support_cost for mo in months),
        "total_lost_revenue":       sum(mo.lost_revenue for mo in months),
        "total_turnover_cost":      sum(mo.turnover_cost for mo in months),
        "total_burnout_penalty":    sum(mo.burnout_penalty for mo in months),
        "total_overstaff_penalty":  sum(mo.overstaff_penalty for mo in months),
        "total_overload_attrition": sum(mo.overload_attrition_delta for mo in months),
        "pct_months_in_band":       sum(1 for mo in months if mo.within_band) / len(months) * 100,
        "total_ebitda_3yr":         total_ebitda,
        "total_revenue_captured":   total_revenue_captured,
        "total_swb_3yr":            total_swb_3yr,
        "total_flex_3yr":           total_flex_3yr,
        "total_turnover_3yr":       total_turnover_3yr,
        "total_burnout_3yr":        total_burnout_3yr,
        "total_fixed_3yr":          total_fixed_3yr,
        "total_visits_captured":    total_visits_captured,
        "total_visits_demanded":    total_visits_demanded,
        "visit_capture_rate":       total_visits_captured / total_visits_demanded if total_visits_demanded > 0 else 1.0,
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

    ebitda_summary = {
        "revenue":      total_revenue_captured,
        "swb":          total_swb_3yr,
        "flex":         total_flex_3yr,
        "turnover":     total_turnover_3yr,
        "burnout":      total_burnout_3yr,
        "fixed":        total_fixed_3yr,
        "ebitda":       total_ebitda,
        "capture_rate": total_visits_captured / total_visits_demanded if total_visits_demanded > 0 else 1.0,
    }

    result = PolicyResult(
        base_fte=base_fte, winter_fte=winter_fte,
        req_post_month=req_post_month,
        months=months,
        hire_events=hire_events,
        total_score=total_score,
        annual_swb_per_visit=annual_swb,
        swb_violation=swb_violation,
        summary=summary,
        ebitda_summary=ebitda_summary,
    )
    return result


def _log_hire(hire_events: List[HireEvent], sim_m: int, cal_month: int, year: int,
              fte_hired: float, mode: str, lead_months: int, cfg: ClinicConfig):
    """Record a hire event with back-calculated posting date."""
    post_cal_month = cal_month - lead_months
    post_year      = year
    while post_cal_month <= 0:
        post_cal_month += 12
        post_year      -= 1
    post_year = max(1, post_year)

    # When will this APC be independent?
    indep_cal = cal_month  # they're hired this month, independent after ramp
    indep_year = year
    ramp_offset = cfg.ramp_months
    indep_cal = indep_cal + ramp_offset
    while indep_cal > 12:
        indep_cal  -= 12
        indep_year += 1

    hire_events.append(HireEvent(
        simulation_month=sim_m + 1,
        calendar_month=cal_month,
        year=year,
        fte_hired=fte_hired,
        mode=mode,
        post_by_month=post_cal_month,
        post_by_year=post_year,
        independent_month=indep_cal,
        independent_year=indep_year,
    ))


# ══════════════════════════════════════════════════════════════════════════════
# MARGINAL APC ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
def compare_marginal_fte(pol: PolicyResult, cfg: ClinicConfig,
                         delta_fte: float = 0.5) -> Dict:
    """
    Re-simulate with base_fte + delta_fte and compare outcomes.
    Returns a dict with cost delta, red months saved, SWB impact, payback months.
    """
    new_base  = pol.base_fte + delta_fte
    new_wint  = pol.winter_fte + delta_fte
    pol_plus  = simulate_policy(new_base, new_wint, cfg)

    s0 = pol.summary
    s1 = pol_plus.summary

    annual_cost_delta = (
        (s1["total_permanent_cost"] - s0["total_permanent_cost"]) / 3
        + (s1["total_flex_cost"]     - s0["total_flex_cost"])     / 3
    )
    annual_savings = (
        (s0["total_burnout_penalty"] - s1["total_burnout_penalty"]) / 3
        + (s0["total_lost_revenue"]  - s1["total_lost_revenue"])   / 3
        + (s0["total_turnover_cost"] - s1["total_turnover_cost"])   / 3
    )
    net_annual = annual_savings - annual_cost_delta
    payback_months = (-annual_cost_delta / (annual_savings / 12)
                      if annual_savings > 0 else float("inf"))

    # Month-by-month load comparison (year 1)
    yr1_base = [mo.patients_per_provider_per_shift for mo in pol.months if mo.year == 1]
    yr1_plus = [mo.patients_per_provider_per_shift for mo in pol_plus.months if mo.year == 1]

    return {
        "delta_fte":          delta_fte,
        "annual_cost_delta":  annual_cost_delta,
        "annual_savings":     annual_savings,
        "net_annual":         net_annual,
        "payback_months":     payback_months,
        "red_months_saved":   s0["red_months"]   - s1["red_months"],
        "yellow_months_saved":s0["yellow_months"] - s1["yellow_months"],
        "swb_delta":          s1["annual_swb_per_visit"] - s0["annual_swb_per_visit"],
        "attrition_saved":    s0["total_overload_attrition"] - s1["total_overload_attrition"],
        "pct_months_in_band_delta": s1["pct_months_in_band"] - s0["pct_months_in_band"],
        "yr1_load_base":      yr1_base,
        "yr1_load_plus":      yr1_plus,
        "score_delta":        s1["total_score"] - s0["total_score"],
        "pol_plus":           pol_plus,
    }


# ══════════════════════════════════════════════════════════════════════════════
# STRESS TEST
# ══════════════════════════════════════════════════════════════════════════════
def simulate_stress(pol: PolicyResult, cfg: ClinicConfig,
                    shock_start_month: int, shock_duration_months: int,
                    shock_magnitude: float) -> PolicyResult:
    """
    Re-run simulation with a volume shock applied to a window of months.
    shock_start_month: 1-indexed simulation month
    shock_magnitude:   fractional (0.15 = +15% volume)
    """
    shocks = {
        m: shock_magnitude
        for m in range(shock_start_month, shock_start_month + shock_duration_months)
    }
    return simulate_policy(pol.base_fte, pol.winter_fte, cfg,
                           volume_shocks=shocks)


# ══════════════════════════════════════════════════════════════════════════════
# OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
def optimize(cfg: ClinicConfig,
             b_range:         Tuple[float, float, float] = (2,   20,  0.5),
             w_range_above:   Tuple[float, float, float] = (0,   10,  0.5),
             horizon_months:  int = 36) -> Tuple[PolicyResult, List[PolicyResult]]:
    """
    Grid search that maximizes 3-year EBITDA contribution:
        Revenue Captured − SWB − Flex − Turnover − Burnout − Fixed

    In load-band mode the simulation derives FTE targets from demand each month,
    so base_fte/winter_fte are used as the flu-season hiring floor — the optimizer
    searches over how aggressively to staff for the flu season.  Higher winter_fte
    = better flu coverage but higher SWB; the EBITDA objective finds the sweet spot.

    In legacy mode (use_load_band=False) the grid search over (base_fte, winter_fte)
    controls staffing levels directly.
    """
    b_vals = np.arange(b_range[0], b_range[1] + b_range[2], b_range[2])
    all_policies: List[PolicyResult] = []
    best_policy:  Optional[PolicyResult] = None
    best_ebitda   = float("-inf")

    for b in b_vals:
        w_vals = np.arange(b, b + w_range_above[1] + w_range_above[2], w_range_above[2])
        for w in w_vals:
            p = simulate_policy(float(round(b, 2)), float(round(w, 2)), cfg, horizon_months)
            all_policies.append(p)
            ebitda = p.ebitda_summary["ebitda"] if p.ebitda_summary else -p.total_score
            if ebitda > best_ebitda:
                best_ebitda = ebitda
                best_policy = p

    # Attach marginal analysis to best policy
    if best_policy is not None:
        best_policy.marginal_analysis = compare_marginal_fte(best_policy, cfg)

    return best_policy, all_policies
