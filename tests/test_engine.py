"""Hand-checked tests for the core underwriting engine."""
from __future__ import annotations

from datetime import date

import pytest

from tests.factories import simple_rental
from underwriting import engine
from underwriting.models import Unit


# ---------------------------------------------------------------------------
# Loan math
# ---------------------------------------------------------------------------


def test_amortized_payment_zero_rate_is_exact_division():
    assert engine.amortized_payment(120_000, 0.0, 10) == pytest.approx(1000.0)


def test_amortized_payment_zero_term_returns_principal():
    assert engine.amortized_payment(5000, 0.05, 0) == 5000


def test_amortized_payment_one_month_term():
    # n=1: the entire principal plus one month's interest is due immediately.
    payment = engine.amortized_payment(10_000, 0.12, 1 / 12)
    # amortization_years is in years; 1 month = 1/12 year -> n = round(1/12*12)=1
    assert payment == pytest.approx(10_000 * (1 + 0.01), rel=1e-6)


def test_amortized_payment_round_trips_to_zero_balance():
    """Independent check: simulate the loan month by month using the payment
    the function returns, and confirm the balance hits (approximately) zero
    exactly at the end of the term — this validates the formula itself,
    not just that it matches another formula."""
    principal, annual_rate, years = 80_000, 0.06, 30
    payment = engine.amortized_payment(principal, annual_rate, years)
    monthly_rate = annual_rate / 12
    balance = principal
    for _ in range(years * 12):
        interest = balance * monthly_rate
        balance = balance + interest - payment
    assert balance == pytest.approx(0.0, abs=0.05)


def test_remaining_balance_matches_manual_simulation():
    principal, annual_rate, years = 80_000, 0.06, 30
    payment = engine.amortized_payment(principal, annual_rate, years)
    monthly_rate = annual_rate / 12
    balance = principal
    for _ in range(60):  # 5 years
        balance = balance + balance * monthly_rate - payment
    assert engine.remaining_balance(principal, annual_rate, years, 60) == pytest.approx(balance, abs=0.05)


def test_remaining_balance_zero_rate():
    assert engine.remaining_balance(120_000, 0.0, 10, 60) == pytest.approx(60_000.0)


def test_remaining_balance_past_term_is_zero():
    assert engine.remaining_balance(80_000, 0.06, 30, 361) == 0.0


def test_compute_debt_service_no_mip():
    ds = engine.compute_debt_service(100_000, simple_rental().financing)
    assert ds.loan_amount == pytest.approx(80_000.0)
    assert ds.financed_upfront_mip == 0.0
    assert ds.monthly_mip == 0.0
    assert ds.annual_debt_service == pytest.approx(ds.monthly_principal_interest * 12)


def test_compute_debt_service_with_fha_mip():
    deal = simple_rental()
    financing = deal.financing.model_copy(
        update={"down_payment_pct": 0.035, "upfront_mip_pct": 0.0175, "annual_mip_pct": 0.0055}
    )
    ds = engine.compute_debt_service(100_000, financing)
    base_loan = 100_000 * 0.965
    expected_financed_mip = base_loan * 0.0175
    expected_loan_amount = base_loan + expected_financed_mip
    assert ds.loan_amount == pytest.approx(expected_loan_amount)
    assert ds.financed_upfront_mip == pytest.approx(expected_financed_mip)
    assert ds.monthly_mip == pytest.approx(expected_loan_amount * 0.0055 / 12)


# ---------------------------------------------------------------------------
# Rent roll / expenses
# ---------------------------------------------------------------------------


def test_gross_potential_rent_owner_unit_contributes_zero_in_place():
    units = [
        Unit(label="Owner", sqft=800, is_owner_unit=True, market_rent=1000),
        Unit(label="Tenant", sqft=800, market_rent=1000, current_rent=800),
    ]
    rr = engine.gross_potential_rent(units)
    assert rr.gross_potential_rent_monthly_market == 2000
    assert rr.gross_potential_rent_monthly_in_place == 800  # owner contributes 0, tenant pays 800
    assert rr.gross_potential_rent_annual_market == 24000
    assert rr.gross_potential_rent_annual_in_place == 9600


def test_gross_potential_rent_vacant_unit_falls_back_to_market():
    units = [Unit(label="Vacant", sqft=500, market_rent=900, current_rent=None)]
    rr = engine.gross_potential_rent(units)
    assert rr.gross_potential_rent_monthly_in_place == 900


def test_compute_operating_expenses_hand_checked():
    from underwriting.models import Assumptions, ExpenseItem

    items = [ExpenseItem(name="tax", annual_amount=2000, source="county_record")]
    assumptions = Assumptions(
        vacancy_pct=0.1, management_pct=0.10, repairs_pct=0.05, capex_reserve_per_sqft=1.0,
        rent_growth_pct=0, expense_growth_pct=0, exit_cap_rate_spread=0, hold_years=1,
    )
    summary = engine.compute_operating_expenses(items, egi_annual=10_000, assumptions=assumptions, building_sqft=500)
    # management = 10000*0.10=1000, repairs=10000*0.05=500, capex=500*1.0=500
    assert summary.total_annual == pytest.approx(2000 + 1000 + 500 + 500)
    names = {i.name for i in summary.items}
    assert {"tax", "management_fee", "repairs_and_maintenance", "capex_reserve"} <= names


# ---------------------------------------------------------------------------
# Core metrics (fully hand-checked, single rented unit, no MIP)
# ---------------------------------------------------------------------------


def test_core_metrics_hand_checked():
    deal = simple_rental()
    core = engine.core_metrics(deal)

    # GPR = $1000/mo * 12 = $12,000; vacancy 10% -> EGI = $10,800
    assert core.rent_roll.gross_potential_rent_annual_market == 12_000
    # opex: management 10800*0.05=540, repairs 10800*0.05=540, capex 1000sqft*0.10=100 -> 1180
    assert core.operating_expenses.total_annual == pytest.approx(1180.0)
    # NOI = 10800 - 1180 = 9620
    assert core.noi_annual == pytest.approx(9620.0)
    assert core.cap_rate_market == pytest.approx(9620.0 / 100_000)
    # current_rent == market_rent here, so in-place equals market
    assert core.noi_annual_in_place == pytest.approx(core.noi_annual)

    # Debt service: loan = 80,000 at 6%/30yr, no MIP
    assert core.debt_service.loan_amount == pytest.approx(80_000.0)
    assert core.dscr == pytest.approx(core.noi_annual / core.debt_service.annual_debt_service)

    # Cash required: down 20,000 + closing 2,000 = 22,000 (no concessions/assistance)
    assert core.total_cash_required == pytest.approx(22_000.0)
    assert core.cash_on_cash_return == pytest.approx(core.cash_flow_before_tax_annual / 22_000.0)

    expected_breakeven = (core.operating_expenses.total_annual + core.debt_service.annual_debt_service) / 12_000.0
    assert core.breakeven_occupancy == pytest.approx(expected_breakeven)


def test_core_metrics_zero_rent_breakeven_is_infinite():
    deal = simple_rental(units=[Unit(label="Free unit", sqft=1000, market_rent=0, current_rent=0)])
    core = engine.core_metrics(deal)
    assert core.breakeven_occupancy == float("inf")


def test_core_metrics_zero_cash_required_gives_infinite_cash_on_cash():
    # No down payment, no closing costs -> nothing invested -> cash-on-cash is undefined (inf).
    deal = simple_rental(
        financing=simple_rental().financing.model_copy(update={"down_payment_pct": 0.0, "closing_cost_pct": 0.0})
    )
    core = engine.core_metrics(deal)
    assert core.total_cash_required == 0.0
    assert core.cash_on_cash_return == float("inf")


# ---------------------------------------------------------------------------
# IRR
# ---------------------------------------------------------------------------


def test_irr_simple_known_value():
    # -100 today, +110 in one year -> IRR = 10%
    assert engine.irr([-100, 110]) == pytest.approx(0.10, abs=1e-4)


def test_irr_two_year_known_value():
    # -100, 0, +121 -> 10% for two years (121 = 100*1.1^2)
    assert engine.irr([-100, 0, 121]) == pytest.approx(0.10, abs=1e-4)


def test_irr_no_root_returns_none():
    # All-positive cash flows: NPV is positive at every rate in [lo, hi] -> no root.
    assert engine.irr([100, 100, 100]) is None


def test_irr_exact_root_at_lo_bound():
    # NPV([0]) is 0 at any rate, including the lower bound -> short-circuits immediately.
    assert engine.irr([0]) == -0.99


def test_irr_exact_root_at_hi_bound():
    # -100 + 1100/(1+10.0) == 0 exactly -> short-circuits at the upper bound.
    assert engine.irr([-100, 1100]) == 10.0


def test_irr_falls_back_to_midpoint_without_converging():
    # max_iter=1 forces the loop to exit before reaching tol, exercising the fallback return.
    result = engine.irr([-100, 110], max_iter=1, tol=0.0)
    assert result is not None


# ---------------------------------------------------------------------------
# Pro forma
# ---------------------------------------------------------------------------


def test_five_year_pro_forma_length_and_growth():
    deal = simple_rental(assumptions=simple_rental().assumptions.model_copy(update={"hold_years": 5}))
    core = engine.core_metrics(deal)
    pf = engine.five_year_pro_forma(deal, core)
    assert len(pf.years) == 5
    assert pf.years[0].year == 1
    # Rent grows 2%/yr
    assert pf.years[1].gross_potential_rent == pytest.approx(pf.years[0].gross_potential_rent * 1.02)
    # Loan balance strictly decreases year over year
    balances = [y.loan_balance_end_of_year for y in pf.years]
    assert balances == sorted(balances, reverse=True)
    assert pf.equity_multiple > 0


def test_pro_forma_exit_value_uses_cap_rate_spread():
    deal = simple_rental()
    core = engine.core_metrics(deal)
    pf = engine.five_year_pro_forma(deal, core)
    assert pf.exit.exit_cap_rate == pytest.approx(core.cap_rate_market + deal.assumptions.exit_cap_rate_spread)
    assert pf.exit.exit_value == pytest.approx(pf.exit.exit_noi_forward / pf.exit.exit_cap_rate)
    assert pf.exit.net_sale_proceeds == pytest.approx(
        pf.exit.exit_value - pf.exit.loan_balance_at_exit - pf.exit.selling_costs
    )


# ---------------------------------------------------------------------------
# Max offer price
# ---------------------------------------------------------------------------


def test_max_offer_price_zero_when_structurally_failing():
    # Expenses alone exceed income even with near-zero debt -> no price works.
    from underwriting.models import Assumptions, ExpenseItem

    deal = simple_rental(
        expense_items=[ExpenseItem(name="tax", annual_amount=50_000, source="county_record")],
    )
    thresholds = engine.Thresholds(min_dscr=1.15, min_cash_on_cash=0.10, min_monthly_cash_flow=200, max_breakeven_occupancy=0.85)
    assert engine.max_offer_price(deal, thresholds) == 0.0


def test_max_offer_price_is_monotonic_boundary():
    deal = simple_rental()
    thresholds = engine.Thresholds(min_dscr=1.15, min_cash_on_cash=0.10, min_monthly_cash_flow=50, max_breakeven_occupancy=0.85)
    max_price = engine.max_offer_price(deal, thresholds)
    assert max_price > 0
    core_at_max = engine.core_metrics(deal.model_copy(update={"price": max_price}))
    # At the boundary, thresholds should be (approximately) just satisfied.
    assert core_at_max.dscr >= thresholds.min_dscr - 1e-3
    core_above = engine.core_metrics(deal.model_copy(update={"price": max_price + 5000}))
    assert (
        core_above.dscr < thresholds.min_dscr
        or core_above.cash_flow_before_tax_monthly < thresholds.min_monthly_cash_flow
        or core_above.cash_on_cash_return < thresholds.min_cash_on_cash
        or core_above.breakeven_occupancy > thresholds.max_breakeven_occupancy
    )


def test_max_offer_price_expands_search_range_when_thresholds_are_very_loose():
    deal = simple_rental()
    thresholds = engine.Thresholds(
        min_dscr=0.0, min_cash_on_cash=-1e9, min_monthly_cash_flow=-1e9, max_breakeven_occupancy=1e9
    )
    # Nothing binds within a normal range, forcing the hi*=2 expansion loop to run
    # until it hits the 1e9 search cap.
    max_price = engine.max_offer_price(deal, thresholds)
    assert max_price > 1_000_000


def test_max_offer_price_extra_predicate_can_only_tighten():
    deal = simple_rental()
    thresholds = engine.Thresholds(min_dscr=1.0, min_cash_on_cash=0.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=1.0)
    unconstrained = engine.max_offer_price(deal, thresholds)
    constrained = engine.max_offer_price(deal, thresholds, extra_predicate=lambda p: p <= 50_000)
    assert constrained <= unconstrained
    assert constrained <= 50_000 + 100  # tolerance


# ---------------------------------------------------------------------------
# Sensitivity table
# ---------------------------------------------------------------------------


def test_sensitivity_table_skips_non_positive_interest_rates():
    deal = simple_rental(financing=simple_rental().financing.model_copy(update={"interest_rate": 0.005}))
    cells = engine.sensitivity_table(deal, price_deltas=(0.0,), rate_deltas=(-0.01, 0.0), vacancy_deltas=(0.0,))
    # rate -0.01 would go to -0.005 <= 0 and must be skipped, leaving only the rate_delta=0.0 cell.
    assert len(cells) == 1


def test_sensitivity_table_higher_vacancy_lowers_cash_on_cash():
    deal = simple_rental()
    cells = engine.sensitivity_table(deal, price_deltas=(0.0,), rate_deltas=(0.0,), vacancy_deltas=(0.0, 0.10))
    assert len(cells) == 2
    low_vacancy, high_vacancy = cells
    assert high_vacancy.cash_on_cash < low_vacancy.cash_on_cash


# ---------------------------------------------------------------------------
# Lease rollover risk
# ---------------------------------------------------------------------------


def test_lease_rollover_flags_unit_expiring_soon():
    units = [
        Unit(label="A", sqft=500, market_rent=1000, lease_end=date(2027, 1, 1)),
        Unit(label="B", sqft=500, market_rent=1000, lease_end=date(2030, 1, 1)),
    ]
    deal = simple_rental(units=units, as_of_date=date(2026, 10, 6))
    flags = engine.lease_rollover_risk(deal)
    assert len(flags) == 1
    assert flags[0].unit_label == "A"
    assert flags[0].income_share_pct == pytest.approx(0.5)


def test_lease_rollover_no_flags_when_no_lease_end():
    deal = simple_rental()
    assert engine.lease_rollover_risk(deal) == []


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_scenarios_downside_worse_than_upside():
    deal = simple_rental()
    scenarios = engine.run_scenarios(deal)
    assert set(scenarios) == {"downside", "base", "upside"}
    assert scenarios["downside"].core.noi_annual < scenarios["base"].core.noi_annual
    assert scenarios["base"].core.noi_annual < scenarios["upside"].core.noi_annual


# ---------------------------------------------------------------------------
# Full analysis wiring
# ---------------------------------------------------------------------------


def test_full_analysis_returns_all_sections():
    deal = simple_rental()
    thresholds = engine.Thresholds(min_dscr=1.0, min_cash_on_cash=0.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=1.0)
    result = engine.full_analysis(deal, thresholds)
    assert result.deal_name == "Simple Rental"
    assert result.core is not None
    assert result.pro_forma is not None
    assert result.max_offer_price >= 0
    assert isinstance(result.sensitivity_table, list) and len(result.sensitivity_table) > 0
    assert set(result.scenarios) == {"downside", "base", "upside"}
