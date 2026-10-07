"""Hand-checked tests for the FHA house hack module."""
from __future__ import annotations

import pytest

from tests.factories import house_hack_duplex
from underwriting import engine, house_hack


def test_full_monthly_payment_hand_checked():
    deal = house_hack_duplex()
    payment = house_hack.full_monthly_payment(deal)

    base_loan = 200_000 * 0.965
    financed_mip = base_loan * 0.0175
    loan_amount = base_loan + financed_mip
    expected_mip_monthly = loan_amount * 0.0055 / 12
    expected_tax_monthly = 2400 / 12
    expected_insurance_monthly = 1200 / 12

    assert payment.property_tax == pytest.approx(expected_tax_monthly)
    assert payment.insurance == pytest.approx(expected_insurance_monthly)
    assert payment.mip == pytest.approx(expected_mip_monthly)
    assert payment.total == pytest.approx(
        payment.principal_interest + expected_tax_monthly + expected_insurance_monthly + expected_mip_monthly
    )


def test_full_monthly_payment_requires_named_expense_items():
    deal = house_hack_duplex(expense_items=[])
    with pytest.raises(ValueError, match="property_tax"):
        house_hack.full_monthly_payment(deal)


def test_cash_to_close_hand_checked_no_help():
    deal = house_hack_duplex()
    result = house_hack.cash_to_close(deal, cash_on_hand=3000)
    assert result.down_payment == pytest.approx(200_000 * 0.035)
    assert result.closing_costs == pytest.approx(200_000 * 0.03)
    assert result.total_cash_required == pytest.approx(7000 + 6000)
    assert result.cash_gap == pytest.approx(13_000 - 3000)
    assert result.covered is False


def test_cash_to_close_with_concessions_and_assistance_can_cover():
    deal = house_hack_duplex(seller_concessions_amount=200_000 * 0.06, down_payment_assistance_amount=5000)
    result = house_hack.cash_to_close(deal, cash_on_hand=3000)
    # required = 7000 + 6000 - 12000 - 5000 = -4000 -> clamped to 0
    assert result.total_cash_required == 0.0
    assert result.covered is True


def test_cash_to_close_concessions_capped_at_profile_max_pct():
    deal = house_hack_duplex(seller_concessions_amount=1_000_000)  # way more than the seller is allowed to give
    result = house_hack.cash_to_close(deal, cash_on_hand=0)
    assert result.seller_concessions == pytest.approx(200_000 * 0.06)


def test_live_in_phase_hand_checked():
    deal = house_hack_duplex(comparable_rent_estimate=1100)
    result = house_hack.live_in_phase(deal)

    other_rent = 1000  # the one rented unit, at its current (= market) rent
    adjustment = other_rent * (0.10 + 0.07)  # vacancy_pct + repairs_pct
    net_rent = other_rent - adjustment
    payment = house_hack.full_monthly_payment(deal).total

    assert result.other_units_rent_monthly == other_rent
    assert result.vacancy_and_repair_adjustment == pytest.approx(adjustment)
    assert result.net_rent_from_others == pytest.approx(net_rent)
    assert result.net_monthly_housing_cost == pytest.approx(payment - net_rent)
    assert result.monthly_savings_vs_comparable == pytest.approx(1100 - result.net_monthly_housing_cost)


def test_live_in_phase_owner_share_of_expenses_adds_to_cost():
    cheap = house_hack_duplex(owner_share_of_expenses=0)
    with_share = house_hack_duplex(owner_share_of_expenses=150)
    cost_without = house_hack.live_in_phase(cheap).net_monthly_housing_cost
    cost_with = house_hack.live_in_phase(with_share).net_monthly_housing_cost
    assert cost_with == pytest.approx(cost_without + 150)


def test_move_out_phase_matches_core_engine_full_rental():
    deal = house_hack_duplex()
    move_out = house_hack.move_out_phase(deal)
    core = engine.core_metrics(deal)
    assert move_out.core.noi_annual == core.noi_annual
    assert move_out.core.cash_flow_before_tax_annual == core.cash_flow_before_tax_annual


def test_lender_dti_check_hand_checked():
    deal = house_hack_duplex()
    result = house_hack.lender_dti_check(deal, monthly_gross_income=8000, monthly_debt_payments=0)

    other_units_market_rent = 1000  # the non-owner unit's market rent
    rental_credit = other_units_market_rent * 0.75
    effective_income = 8000 + rental_credit
    payment = house_hack.full_monthly_payment(deal).total

    assert result.rental_income_credit == pytest.approx(rental_credit)
    assert result.effective_monthly_income == pytest.approx(effective_income)
    assert result.front_dti == pytest.approx(payment / effective_income)
    assert result.back_dti == pytest.approx(payment / effective_income)  # no other debts
    assert result.front_pass == (result.front_dti <= 0.31)


def test_lender_dti_check_back_dti_includes_other_debts():
    deal = house_hack_duplex()
    result = house_hack.lender_dti_check(deal, monthly_gross_income=8000, monthly_debt_payments=500)
    payment = house_hack.full_monthly_payment(deal).total
    assert result.back_dti == pytest.approx((payment + 500) / result.effective_monthly_income)
    assert result.back_dti > result.front_dti


def test_self_sufficiency_not_applicable_for_duplex():
    deal = house_hack_duplex()
    result = house_hack.self_sufficiency_test(deal)
    assert result.applicable is False
    assert result.passed is True


def test_self_sufficiency_applicable_and_failing_for_triplex():
    from underwriting.models import Unit

    deal = house_hack_duplex(
        property_type="triplex",
        units=[
            Unit(label="Owner", sqft=500, is_owner_unit=True, market_rent=400),
            Unit(label="U2", sqft=500, market_rent=400, current_rent=400),
            Unit(label="U3", sqft=500, market_rent=400, current_rent=400),
        ],
        price=400_000,
    )
    result = house_hack.self_sufficiency_test(deal)
    payment = house_hack.full_monthly_payment(deal).total
    assert result.applicable is True
    assert result.total_market_rent_monthly == 1200
    assert result.seventy_five_pct_of_rent == pytest.approx(900)
    assert result.gap == pytest.approx(payment - 900)
    assert result.passed is (900 >= payment)
    assert result.passed is False  # by construction: price is far too high for this rent


def test_loan_limit_check_pass_fail_and_unknown():
    deal = house_hack_duplex()
    ds = engine.compute_debt_service(deal.price, deal.financing)

    passing = house_hack.loan_limit_check(deal, {"two_unit": ds.loan_amount + 1})
    assert passing.status == "pass"

    failing = house_hack.loan_limit_check(deal, {"two_unit": ds.loan_amount - 1})
    assert failing.status == "fail"

    unknown = house_hack.loan_limit_check(deal, {"two_unit": None})
    assert unknown.status == "unknown_verify_hud"

    missing_key = house_hack.loan_limit_check(deal, {})
    assert missing_key.status == "unknown_verify_hud"


def test_house_hack_max_offer_price_binds_on_dti():
    deal = house_hack_duplex()
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=1e9, monthly_gross_income=100, monthly_debt_payments=0, loan_limits={}, max_owner_net_housing_cost=1e9
    )
    # Income is so low that even a near-zero price fails DTI -> max price is 0.
    assert house_hack.house_hack_max_offer_price(deal, thresholds, constraints) == 0.0


def test_house_hack_max_offer_price_binds_on_self_sufficiency():
    from underwriting.models import Unit

    deal = house_hack_duplex(
        property_type="triplex",
        price=400_000,
        units=[
            Unit(label="Owner", sqft=500, is_owner_unit=True, market_rent=400),
            Unit(label="U2", sqft=500, market_rent=400, current_rent=400),
            Unit(label="U3", sqft=500, market_rent=400, current_rent=400),
        ],
    )
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=1e9, monthly_gross_income=1e6, monthly_debt_payments=0, loan_limits={}, max_owner_net_housing_cost=1e9
    )
    max_price = house_hack.house_hack_max_offer_price(deal, thresholds, constraints)
    assert 0 < max_price < 400_000
    passing = house_hack.self_sufficiency_test(deal.model_copy(update={"price": max_price}))
    assert passing.passed is True


def test_house_hack_max_offer_price_binds_on_loan_limit():
    deal = house_hack_duplex()
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=1e9,
        monthly_gross_income=1e6,
        monthly_debt_payments=0,
        loan_limits={"two_unit": 100_000},
        max_owner_net_housing_cost=1e9,
    )
    max_price = house_hack.house_hack_max_offer_price(deal, thresholds, constraints)
    assert 0 < max_price < deal.price
    at_max = house_hack.loan_limit_check(deal.model_copy(update={"price": max_price}), constraints.loan_limits)
    assert at_max.loan_amount <= 100_000 + 1.0


def test_house_hack_max_offer_price_binds_on_owner_net_housing_cost():
    deal = house_hack_duplex()
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=1e9, monthly_gross_income=1e6, monthly_debt_payments=0, loan_limits={}, max_owner_net_housing_cost=100
    )
    max_price = house_hack.house_hack_max_offer_price(deal, thresholds, constraints)
    assert 0 < max_price < deal.price
    at_max = house_hack.live_in_phase(deal.model_copy(update={"price": max_price}))
    assert at_max.net_monthly_housing_cost <= 101


def test_house_hack_max_offer_price_respects_cash_constraint():
    deal = house_hack_duplex()
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=3000,
        monthly_gross_income=8000,
        monthly_debt_payments=0,
        loan_limits={},
        max_owner_net_housing_cost=10_000,
    )
    max_price = house_hack.house_hack_max_offer_price(deal, thresholds, constraints)
    assert max_price > 0
    # At the resulting price, cash to close must be (approximately) exactly covered.
    variant = deal.model_copy(update={"price": max_price})
    close = house_hack.cash_to_close(variant, cash_on_hand=3000)
    assert close.total_cash_required <= 3000 + 50
