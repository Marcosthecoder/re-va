"""Core underwriting engine.

Treats every deal as if it were 100% rented at market rent — this is the
"fully rented investment" view used for cap rate, DSCR, cash-on-cash, the
5-year pro forma, and max offer price. For an owner-occupied house hack,
``house_hack.py`` runs alongside this module to model the live-in phase
(where one unit produces no rent) and reuses these same functions for the
post-move-out phase once the owner's unit is rented at market.

All math here is pure Python. No LLM call ever computes a number — Claude
is only used elsewhere (intake, reports, coach) to explain numbers this
module already produced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from underwriting.models import ExpenseItem, PropertyInput

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class RentRollSummary:
    gross_potential_rent_monthly_market: float
    gross_potential_rent_annual_market: float
    gross_potential_rent_monthly_in_place: float
    gross_potential_rent_annual_in_place: float


@dataclass
class ExpenseLine:
    name: str
    annual_amount: float
    source: str


@dataclass
class OperatingExpenseSummary:
    items: list[ExpenseLine]
    total_annual: float


@dataclass
class DebtServiceSummary:
    loan_amount: float
    financed_upfront_mip: float
    monthly_principal_interest: float
    monthly_mip: float
    annual_debt_service: float


@dataclass
class CoreMetrics:
    rent_roll: RentRollSummary
    operating_expenses: OperatingExpenseSummary
    noi_annual: float
    noi_annual_in_place: float
    cap_rate_market: float
    cap_rate_in_place: float
    debt_service: DebtServiceSummary
    dscr: float
    cash_flow_before_tax_annual: float
    cash_flow_before_tax_monthly: float
    total_cash_required: float
    cash_on_cash_return: float
    breakeven_occupancy: float


@dataclass
class ProFormaYear:
    year: int
    gross_potential_rent: float
    effective_gross_income: float
    operating_expenses: float
    noi: float
    cash_flow_before_tax: float
    loan_balance_end_of_year: float


@dataclass
class ExitAnalysis:
    exit_noi_forward: float
    exit_cap_rate: float
    exit_value: float
    selling_costs: float
    loan_balance_at_exit: float
    net_sale_proceeds: float


@dataclass
class ProForma:
    years: list[ProFormaYear]
    exit: ExitAnalysis
    irr: float | None
    equity_multiple: float


@dataclass
class LeaseRolloverFlag:
    unit_label: str
    lease_end: date | None
    months_to_expiry: float | None
    income_share_pct: float


@dataclass
class SensitivityCell:
    price: float
    interest_rate: float
    vacancy_pct: float
    dscr: float
    cash_on_cash: float


@dataclass
class ScenarioResult:
    name: str
    core: CoreMetrics
    pro_forma: ProForma


@dataclass
class Thresholds:
    """Generic 'fully rented' pass/fail thresholds, loaded from the investor profile."""

    min_dscr: float
    min_cash_on_cash: float
    min_monthly_cash_flow: float
    max_breakeven_occupancy: float


@dataclass
class AnalysisResult:
    deal_name: str
    price: float
    core: CoreMetrics
    pro_forma: ProForma
    max_offer_price: float
    lease_rollover_flags: list[LeaseRolloverFlag]
    sensitivity_table: list[SensitivityCell]
    scenarios: dict[str, ScenarioResult] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loan math
# ---------------------------------------------------------------------------


def amortized_payment(principal: float, annual_rate: float, years: int) -> float:
    """Monthly principal + interest payment for a fully amortizing fixed-rate loan."""
    n = years * 12
    if n <= 0:
        return principal
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / n
    factor = (1 + monthly_rate) ** n
    return principal * (monthly_rate * factor) / (factor - 1)


def remaining_balance(principal: float, annual_rate: float, years: int, months_elapsed: int) -> float:
    """Outstanding loan balance after ``months_elapsed`` monthly payments."""
    n = years * 12
    if months_elapsed >= n:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        payment = principal / n
        return max(principal - payment * months_elapsed, 0.0)
    payment = amortized_payment(principal, annual_rate, years)
    factor = (1 + monthly_rate) ** months_elapsed
    balance = principal * factor - payment * ((factor - 1) / monthly_rate)
    return max(balance, 0.0)


def compute_debt_service(price: float, financing) -> DebtServiceSummary:
    """Loan amount (with upfront MIP financed in, if any), monthly P&I, and monthly MIP."""
    base_loan = price * (1 - financing.down_payment_pct)
    financed_mip = base_loan * financing.upfront_mip_pct
    loan_amount = base_loan + financed_mip
    monthly_pi = amortized_payment(loan_amount, financing.interest_rate, financing.amortization_years)
    monthly_mip = loan_amount * financing.annual_mip_pct / 12
    annual_debt_service = (monthly_pi + monthly_mip) * 12
    return DebtServiceSummary(
        loan_amount=loan_amount,
        financed_upfront_mip=financed_mip,
        monthly_principal_interest=monthly_pi,
        monthly_mip=monthly_mip,
        annual_debt_service=annual_debt_service,
    )


# ---------------------------------------------------------------------------
# Income and expenses
# ---------------------------------------------------------------------------


def gross_potential_rent(units) -> RentRollSummary:
    """Monthly/annual GPR at market rent, and at today's actual (in-place) rent.

    A unit marked ``is_owner_unit`` contributes 0 to the in-place figures
    (the owner doesn't pay rent to themselves) but still contributes its
    market rent to the market figures, since that's what it would rent for
    if it weren't owner-occupied.
    """
    monthly_market = sum(u.market_rent for u in units)
    monthly_in_place = sum(u.in_place_rent for u in units)
    return RentRollSummary(
        gross_potential_rent_monthly_market=monthly_market,
        gross_potential_rent_annual_market=monthly_market * 12,
        gross_potential_rent_monthly_in_place=monthly_in_place,
        gross_potential_rent_annual_in_place=monthly_in_place * 12,
    )


def _grow_expense_items(expense_items: list[ExpenseItem], growth_pct: float, years_elapsed: int) -> list[ExpenseItem]:
    return [
        ExpenseItem(name=e.name, annual_amount=e.annual_amount * (1 + growth_pct) ** years_elapsed, source=e.source)
        for e in expense_items
    ]


def compute_operating_expenses(expense_items: list[ExpenseItem], egi_annual: float, assumptions, building_sqft: float) -> OperatingExpenseSummary:
    """Itemized expenses plus the three assumption-driven computed lines.

    Management and repairs scale with effective gross income; the capex
    reserve scales with building square footage. Each computed line is
    labeled ``source="assumption"`` so it's never mistaken for seller data.
    """
    items = [ExpenseLine(name=e.name, annual_amount=e.annual_amount, source=e.source) for e in expense_items]
    items.append(ExpenseLine("management_fee", egi_annual * assumptions.management_pct, "assumption"))
    items.append(ExpenseLine("repairs_and_maintenance", egi_annual * assumptions.repairs_pct, "assumption"))
    items.append(ExpenseLine("capex_reserve", building_sqft * assumptions.capex_reserve_per_sqft, "assumption"))
    total = sum(i.annual_amount for i in items)
    return OperatingExpenseSummary(items=items, total_annual=total)


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------


def core_metrics(property_input: PropertyInput) -> CoreMetrics:
    """The full "fully rented at market" analysis for one deal at its current price."""
    price = property_input.price
    financing = property_input.financing
    assumptions = property_input.assumptions
    building_sqft = property_input.building_sqft

    rent_roll = gross_potential_rent(property_input.units)

    vacancy_loss_market = rent_roll.gross_potential_rent_annual_market * assumptions.vacancy_pct
    egi_market = rent_roll.gross_potential_rent_annual_market - vacancy_loss_market

    vacancy_loss_in_place = rent_roll.gross_potential_rent_annual_in_place * assumptions.vacancy_pct
    egi_in_place = rent_roll.gross_potential_rent_annual_in_place - vacancy_loss_in_place

    opex_market = compute_operating_expenses(property_input.expense_items, egi_market, assumptions, building_sqft)
    opex_in_place = compute_operating_expenses(property_input.expense_items, egi_in_place, assumptions, building_sqft)

    noi_market = egi_market - opex_market.total_annual
    noi_in_place = egi_in_place - opex_in_place.total_annual

    cap_rate_market = noi_market / price if price else 0.0
    cap_rate_in_place = noi_in_place / price if price else 0.0

    debt_service = compute_debt_service(price, financing)
    dscr = noi_market / debt_service.annual_debt_service if debt_service.annual_debt_service else float("inf")

    cfbt_annual = noi_market - debt_service.annual_debt_service
    cfbt_monthly = cfbt_annual / 12

    down_payment_amount = price * financing.down_payment_pct
    closing_costs_amount = price * financing.closing_cost_pct
    concessions = min(property_input.seller_concessions_amount, price * financing.max_seller_concession_pct)
    assistance = property_input.down_payment_assistance_amount
    total_cash_required = max(down_payment_amount + closing_costs_amount - concessions - assistance, 0.0)

    cash_on_cash = cfbt_annual / total_cash_required if total_cash_required > 0 else float("inf")

    breakeven_occupancy = (
        (opex_market.total_annual + debt_service.annual_debt_service) / rent_roll.gross_potential_rent_annual_market
        if rent_roll.gross_potential_rent_annual_market
        else float("inf")
    )

    return CoreMetrics(
        rent_roll=rent_roll,
        operating_expenses=opex_market,
        noi_annual=noi_market,
        noi_annual_in_place=noi_in_place,
        cap_rate_market=cap_rate_market,
        cap_rate_in_place=cap_rate_in_place,
        debt_service=debt_service,
        dscr=dscr,
        cash_flow_before_tax_annual=cfbt_annual,
        cash_flow_before_tax_monthly=cfbt_monthly,
        total_cash_required=total_cash_required,
        cash_on_cash_return=cash_on_cash,
        breakeven_occupancy=breakeven_occupancy,
    )


# ---------------------------------------------------------------------------
# IRR
# ---------------------------------------------------------------------------


def _npv(rate: float, cash_flows: list[float]) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))


def irr(cash_flows: list[float], lo: float = -0.99, hi: float = 10.0, tol: float = 1e-6, max_iter: int = 200) -> float | None:
    """Internal rate of return via bisection on NPV(rate) = 0.

    Returns None if the cash flow pattern has no root in [lo, hi] (e.g. the
    deal never returns the invested cash under any discount rate in range).
    """
    f_lo, f_hi = _npv(lo, cash_flows), _npv(hi, cash_flows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, cash_flows)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# 5-year pro forma
# ---------------------------------------------------------------------------


def five_year_pro_forma(property_input: PropertyInput, core: CoreMetrics) -> ProForma:
    """Multi-year pro forma (length = assumptions.hold_years) with rent/expense growth,
    loan paydown, exit value at a cap-rate-spread-adjusted forward cap rate, IRR, and
    equity multiple on cash invested.
    """
    assumptions = property_input.assumptions
    financing = property_input.financing
    building_sqft = property_input.building_sqft
    hold_years = assumptions.hold_years
    gpr0 = core.rent_roll.gross_potential_rent_annual_market
    debt_service = core.debt_service
    annual_debt_service = debt_service.annual_debt_service

    years: list[ProFormaYear] = []
    for t in range(1, hold_years + 1):
        gpr_t = gpr0 * (1 + assumptions.rent_growth_pct) ** (t - 1)
        egi_t = gpr_t * (1 - assumptions.vacancy_pct)
        grown_items = _grow_expense_items(property_input.expense_items, assumptions.expense_growth_pct, t - 1)
        opex_t = compute_operating_expenses(grown_items, egi_t, assumptions, building_sqft)
        noi_t = egi_t - opex_t.total_annual
        cfbt_t = noi_t - annual_debt_service
        balance_t = remaining_balance(debt_service.loan_amount, financing.interest_rate, financing.amortization_years, t * 12)
        years.append(ProFormaYear(t, gpr_t, egi_t, opex_t.total_annual, noi_t, cfbt_t, balance_t))

    forward_gpr = gpr0 * (1 + assumptions.rent_growth_pct) ** hold_years
    forward_egi = forward_gpr * (1 - assumptions.vacancy_pct)
    forward_items = _grow_expense_items(property_input.expense_items, assumptions.expense_growth_pct, hold_years)
    forward_opex = compute_operating_expenses(forward_items, forward_egi, assumptions, building_sqft)
    exit_noi_forward = forward_egi - forward_opex.total_annual
    exit_cap_rate = core.cap_rate_market + assumptions.exit_cap_rate_spread
    exit_value = exit_noi_forward / exit_cap_rate if exit_cap_rate else 0.0
    selling_costs = exit_value * assumptions.disposition_cost_pct
    loan_balance_at_exit = years[-1].loan_balance_end_of_year
    net_sale_proceeds = exit_value - loan_balance_at_exit - selling_costs

    exit_analysis = ExitAnalysis(
        exit_noi_forward=exit_noi_forward,
        exit_cap_rate=exit_cap_rate,
        exit_value=exit_value,
        selling_costs=selling_costs,
        loan_balance_at_exit=loan_balance_at_exit,
        net_sale_proceeds=net_sale_proceeds,
    )

    cash_flows = [-core.total_cash_required]
    for y in years[:-1]:
        cash_flows.append(y.cash_flow_before_tax)
    cash_flows.append(years[-1].cash_flow_before_tax + net_sale_proceeds)

    irr_value = irr(cash_flows)
    total_inflows = sum(y.cash_flow_before_tax for y in years) + net_sale_proceeds
    equity_multiple = total_inflows / core.total_cash_required if core.total_cash_required > 0 else float("inf")

    return ProForma(years=years, exit=exit_analysis, irr=irr_value, equity_multiple=equity_multiple)


# ---------------------------------------------------------------------------
# Max offer price
# ---------------------------------------------------------------------------


def _satisfies_thresholds(core: CoreMetrics, thresholds: Thresholds) -> bool:
    return (
        core.dscr >= thresholds.min_dscr
        and core.cash_on_cash_return >= thresholds.min_cash_on_cash
        and core.cash_flow_before_tax_monthly >= thresholds.min_monthly_cash_flow
        and core.breakeven_occupancy <= thresholds.max_breakeven_occupancy
    )


def max_offer_price(
    property_input: PropertyInput,
    thresholds: Thresholds,
    extra_predicate=None,
    price_lo: float = 100.0,
    tol: float = 100.0,
) -> float:
    """Highest price at which the deal still meets every threshold.

    Raising price only ever increases debt service, which can only worsen
    DSCR, cash-on-cash, cash flow, and breakeven occupancy — so satisfaction
    is monotonically non-increasing in price, and we can binary search for
    the boundary. ``extra_predicate(price) -> bool`` lets callers (e.g. the
    house hack module) fold in additional monotonic constraints such as DTI
    or a loan limit.
    """

    def satisfied(price: float) -> bool:
        core = core_metrics(property_input.model_copy(update={"price": price}))
        if not _satisfies_thresholds(core, thresholds):
            return False
        if extra_predicate is not None and not extra_predicate(price):
            return False
        return True

    if not satisfied(price_lo):
        return 0.0

    hi = max(property_input.price * 3, price_lo * 2, 1_000_000.0)
    while satisfied(hi) and hi < 1e9:
        hi *= 2

    lo = price_lo
    for _ in range(60):
        mid = (lo + hi) / 2
        if satisfied(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return lo


# ---------------------------------------------------------------------------
# Sensitivity table
# ---------------------------------------------------------------------------


def sensitivity_table(
    property_input: PropertyInput,
    price_deltas: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10),
    rate_deltas: tuple[float, ...] = (-0.01, 0.0, 0.01),
    vacancy_deltas: tuple[float, ...] = (0.0, 0.05, 0.10),
) -> list[SensitivityCell]:
    """DSCR and cash-on-cash across a grid of price x interest rate x vacancy."""
    cells: list[SensitivityCell] = []
    for pd in price_deltas:
        price = property_input.price * (1 + pd)
        for rd in rate_deltas:
            rate = property_input.financing.interest_rate + rd
            if rate <= 0:
                continue
            for vd in vacancy_deltas:
                vacancy = min(property_input.assumptions.vacancy_pct + vd, 0.9)
                variant = property_input.model_copy(
                    update={
                        "price": price,
                        "financing": property_input.financing.model_copy(update={"interest_rate": rate}),
                        "assumptions": property_input.assumptions.model_copy(update={"vacancy_pct": vacancy}),
                    }
                )
                core = core_metrics(variant)
                cells.append(SensitivityCell(price=price, interest_rate=rate, vacancy_pct=vacancy, dscr=core.dscr, cash_on_cash=core.cash_on_cash_return))
    return cells


# ---------------------------------------------------------------------------
# Lease rollover risk
# ---------------------------------------------------------------------------


def lease_rollover_risk(property_input: PropertyInput) -> list[LeaseRolloverFlag]:
    """Flags any lease expiring within 24 months of the deal's as-of date, with its income share."""
    as_of = property_input.effective_as_of_date
    gpr_annual_market = sum(u.market_rent for u in property_input.units) * 12
    flags: list[LeaseRolloverFlag] = []
    for u in property_input.units:
        if u.lease_end is None:
            continue
        months_to_expiry = (u.lease_end.year - as_of.year) * 12 + (u.lease_end.month - as_of.month)
        if u.lease_end.day < as_of.day:
            months_to_expiry -= 1
        income_share = (u.market_rent * 12) / gpr_annual_market if gpr_annual_market else 0.0
        if months_to_expiry <= 24:
            flags.append(
                LeaseRolloverFlag(unit_label=u.label, lease_end=u.lease_end, months_to_expiry=months_to_expiry, income_share_pct=income_share)
            )
    return flags


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIO_MULTIPLIERS = {
    "downside": {"vacancy_mult": 1.5, "rent_growth_mult": 0.0, "expense_growth_mult": 1.5, "exit_spread_add": 0.005},
    "base": {"vacancy_mult": 1.0, "rent_growth_mult": 1.0, "expense_growth_mult": 1.0, "exit_spread_add": 0.0},
    "upside": {"vacancy_mult": 0.5, "rent_growth_mult": 1.5, "expense_growth_mult": 0.75, "exit_spread_add": 0.0},
}
"""Code-level scenario assumptions (not in the investor profile). Documented here so
they're easy to find and adjust; every scenario output is labeled with its name."""


def run_scenarios(property_input: PropertyInput) -> dict[str, ScenarioResult]:
    """Downside / base / upside variants of the same deal, built by scaling assumptions."""
    results: dict[str, ScenarioResult] = {}
    a = property_input.assumptions
    for name, mult in SCENARIO_MULTIPLIERS.items():
        new_assumptions = a.model_copy(
            update={
                "vacancy_pct": min(a.vacancy_pct * mult["vacancy_mult"], 0.9),
                "rent_growth_pct": a.rent_growth_pct * mult["rent_growth_mult"],
                "expense_growth_pct": a.expense_growth_pct * mult["expense_growth_mult"],
                "exit_cap_rate_spread": a.exit_cap_rate_spread + mult["exit_spread_add"],
            }
        )
        variant = property_input.model_copy(update={"assumptions": new_assumptions})
        core = core_metrics(variant)
        pro_forma = five_year_pro_forma(variant, core)
        results[name] = ScenarioResult(name=name, core=core, pro_forma=pro_forma)
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def full_analysis(property_input: PropertyInput, thresholds: Thresholds) -> AnalysisResult:
    """Run every core-engine calculation for one deal and return a single structured result."""
    core = core_metrics(property_input)
    pro_forma = five_year_pro_forma(property_input, core)
    max_price = max_offer_price(property_input, thresholds)
    rollover = lease_rollover_risk(property_input)
    sensitivity = sensitivity_table(property_input)
    scenarios = run_scenarios(property_input)
    return AnalysisResult(
        deal_name=property_input.deal_name,
        price=property_input.price,
        core=core,
        pro_forma=pro_forma,
        max_offer_price=max_price,
        lease_rollover_flags=rollover,
        sensitivity_table=sensitivity,
        scenarios=scenarios,
    )
