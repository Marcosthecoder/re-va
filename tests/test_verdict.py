"""Tests for rule-based verdict logic (core + house hack)."""
from __future__ import annotations

from tests.factories import simple_rental
from underwriting import engine, house_hack, property_standards, verdict
from underwriting.models import ExpenseItem


def test_core_verdict_pursue_when_everything_passes():
    deal = simple_rental()
    thresholds = engine.Thresholds(min_dscr=1.0, min_cash_on_cash=0.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=1.0)
    analysis = engine.full_analysis(deal, thresholds)
    v = verdict.evaluate_core_verdict(analysis, thresholds)
    assert v.outcome == "PURSUE"
    assert v.target_price == analysis.price
    assert all(r.passed for r in v.rules)


def test_core_verdict_negotiate_when_fixable_by_lower_price():
    deal = simple_rental()
    # Tight enough to fail at asking price, loose enough to be fixable.
    thresholds = engine.Thresholds(min_dscr=2.0, min_cash_on_cash=0.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=1.0)
    analysis = engine.full_analysis(deal, thresholds)
    v = verdict.evaluate_core_verdict(analysis, thresholds)
    assert v.outcome == "NEGOTIATE"
    assert v.target_price == analysis.max_offer_price
    assert v.target_price < analysis.price
    assert any(not r.passed for r in v.rules)


def test_core_verdict_pass_when_structurally_unfixable():
    deal = simple_rental(expense_items=[ExpenseItem(name="tax", annual_amount=50_000, source="county_record")])
    thresholds = engine.Thresholds(min_dscr=1.15, min_cash_on_cash=0.10, min_monthly_cash_flow=200, max_breakeven_occupancy=0.85)
    analysis = engine.full_analysis(deal, thresholds)
    v = verdict.evaluate_core_verdict(analysis, thresholds)
    assert v.outcome == "PASS"
    assert v.target_price is None


def _passing_bundle(**overrides) -> verdict.HouseHackBundle:
    base = dict(
        live_in=house_hack.LiveInPhaseResult(500, 0, 1000, 170, 830, 500, 1100, 600),
        dti=house_hack.DTIResult(9000, 750, 0.15, 0.15, 0.31, 0.43, True, True),
        self_sufficiency=house_hack.SelfSufficiencyResult(False, 2000, 1500, 1000, -500, True),
        loan_limit=house_hack.LoanLimitResult(2, 150_000, None, "unknown_verify_hud"),
        cash_close=house_hack.CashToCloseSummary(5000, 4000, 0, 0, 9000, 9000, 0, True),
        mixed_use=property_standards.MixedUseResult(False, None, True),
        standards_flags=[],
        max_offer_price_house_hack=200_000,
        max_owner_net_housing_cost=800,
    )
    base.update(overrides)
    return verdict.HouseHackBundle(**base)


def _minimal_analysis(price: float = 200_000) -> engine.AnalysisResult:
    deal = simple_rental(price=price)
    thresholds = engine.Thresholds(min_dscr=0.0, min_cash_on_cash=-1.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=2.0)
    return engine.full_analysis(deal, thresholds), thresholds


def test_house_hack_verdict_pursue_when_all_pass():
    analysis, thresholds = _minimal_analysis()
    bundle = _passing_bundle()
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    assert v.outcome == "PURSUE"
    assert all(r.passed for r in v.rules)


def test_house_hack_verdict_self_sufficiency_failure_triggers_negotiate():
    analysis, thresholds = _minimal_analysis()
    bundle = _passing_bundle(
        self_sufficiency=house_hack.SelfSufficiencyResult(True, 1800, 1350, 1600, 250, False)
    )
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    assert v.outcome == "NEGOTIATE"
    rule = next(r for r in v.rules if "self-sufficiency" in r.name.lower())
    assert rule.passed is False


def test_house_hack_verdict_pass_when_max_offer_price_is_zero():
    analysis, thresholds = _minimal_analysis()
    bundle = _passing_bundle(
        self_sufficiency=house_hack.SelfSufficiencyResult(True, 1800, 1350, 1600, 250, False),
        max_offer_price_house_hack=0.0,
    )
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    assert v.outcome == "PASS"
    assert v.target_price is None


def test_house_hack_verdict_skips_loan_limit_rule_when_unknown():
    analysis, thresholds = _minimal_analysis()
    bundle = _passing_bundle(loan_limit=house_hack.LoanLimitResult(2, 150_000, None, "unknown_verify_hud"))
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    assert not any("loan limit" in r.name.lower() for r in v.rules)


def test_house_hack_verdict_includes_loan_limit_rule_when_known():
    analysis, thresholds = _minimal_analysis()
    bundle = _passing_bundle(loan_limit=house_hack.LoanLimitResult(2, 150_000, 200_000, "pass"))
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    assert any("loan limit" in r.name.lower() and r.passed for r in v.rules)


def test_house_hack_verdict_hard_fails_on_property_standards():
    analysis, thresholds = _minimal_analysis()
    flag = property_standards.StandardsFlag("roof_life", "Roof needs replacement", "likely_fail")
    bundle = _passing_bundle(standards_flags=[flag])
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    rule = next(r for r in v.rules if "property condition" in r.name.lower())
    assert rule.passed is False
    assert "Roof needs replacement" in rule.detail


def test_house_hack_verdict_warning_flags_do_not_fail_the_rule():
    analysis, thresholds = _minimal_analysis()
    flag = property_standards.StandardsFlag("shared_utilities", "Utilities not separately metered", "warning")
    bundle = _passing_bundle(standards_flags=[flag])
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, bundle)
    rule = next(r for r in v.rules if "property condition" in r.name.lower())
    assert rule.passed is True
