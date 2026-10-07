"""Hand-checked tests for the self-employed qualifying income module."""
from __future__ import annotations

from datetime import date

import pytest

from underwriting.self_employed import apply_co_borrower, self_employed_qualifying_income


def test_not_calculable_with_zero_years_sets_mortgage_ready_date():
    result = self_employed_qualifying_income(
        ownership_pct=None,
        years_of_tax_returns=0,
        yearly_net_incomes=[],
        as_of_date=date(2026, 10, 6),
    )
    assert result.calculable is False
    assert result.qualifying_monthly_income is None
    assert result.months_until_ready == 24
    assert result.mortgage_ready_date == date(2028, 10, 6)
    assert any("Ownership percentage is not documented" in n for n in result.notes)


def test_calculable_with_two_years_averages_them():
    result = self_employed_qualifying_income(
        ownership_pct=0.5,
        years_of_tax_returns=2,
        yearly_net_incomes=[48_000, 60_000],
    )
    assert result.calculable is True
    assert result.qualifying_monthly_income == pytest.approx((48_000 + 60_000) / 2 / 12)
    assert result.mortgage_ready_date is None


def test_declining_income_flagged():
    result = self_employed_qualifying_income(
        ownership_pct=0.5,
        years_of_tax_returns=2,
        yearly_net_incomes=[80_000, 60_000],  # 25% drop
    )
    assert result.declining_income is True
    assert any("declined" in n for n in result.notes)


def test_stable_income_not_flagged_declining():
    result = self_employed_qualifying_income(
        ownership_pct=0.5,
        years_of_tax_returns=2,
        yearly_net_incomes=[60_000, 61_000],
    )
    assert result.declining_income is False


def test_one_year_of_three_required_sets_remaining_timeline():
    result = self_employed_qualifying_income(
        ownership_pct=1.0,
        years_of_tax_returns=1,
        yearly_net_incomes=[50_000],
        years_required=2,
        as_of_date=date(2026, 1, 15),
    )
    assert result.calculable is False
    assert result.months_until_ready == 12
    assert result.mortgage_ready_date == date(2027, 1, 15)


def test_ownership_below_threshold_notes_different_treatment():
    result = self_employed_qualifying_income(ownership_pct=0.10, years_of_tax_returns=2, yearly_net_incomes=[50_000, 51_000])
    assert any("below the 25%" in n for n in result.notes)


def test_apply_co_borrower_combines_income_and_debts():
    result = apply_co_borrower(
        monthly_gross_income=8000,
        monthly_debt_payments=0,
        co_borrower_monthly_income=5000,
        co_borrower_monthly_debts=400,
    )
    assert result.combined_monthly_income == 13_000
    assert result.combined_monthly_debts == 400
