"""Tests for reports.report_builder: rule-based risks/strengths/questions."""
from __future__ import annotations

import pathlib

from underwriting.models import load_deal
from underwriting.pipeline import analyze_deal
from underwriting.profile import load_investor_profile
from reports.report_builder import build_report

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PROFILE = pathlib.Path(__file__).parent.parent / "config" / "investor_profile.yaml"


def _report_for(deal_file: str):
    deal = load_deal(FIXTURES / deal_file)
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    return build_report(deal, full.analysis, full.verdict, full.hh_bundle)


def test_good_duplex_report_has_strengths_and_no_hard_risks():
    report = _report_for("good_duplex.yaml")
    assert report.verdict_outcome == "PURSUE"
    assert len(report.strengths) >= 1
    assert len(report.risks) >= 1  # falls back to the "no major risks" placeholder
    assert all("likely_fail" not in r for r in report.risks)


def test_marginal_triplex_report_flags_lease_rollover_risk():
    report = _report_for("marginal_triplex.yaml")
    assert any("lease expires" in r for r in report.risks)


def test_bad_fourplex_report_flags_property_condition_in_top_risks():
    # Property condition flags are appended first in _top_risks, so with 3
    # likely-fail flags on this fixture they fill the top-3 cap before
    # self-sufficiency/cash-gap risks get a slot -- that's the intended priority.
    report = _report_for("bad_fourplex.yaml")
    risk_text = " ".join(report.risks)
    assert "property condition" in risk_text.lower()
    assert len(report.risks) == 3
    assert report.verdict_outcome == "PASS"


def test_bad_fourplex_self_sufficiency_and_cash_gap_are_real_even_if_not_in_top_risks():
    deal = load_deal(FIXTURES / "bad_fourplex.yaml")
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    assert full.hh_bundle.self_sufficiency.passed is False
    assert full.hh_bundle.cash_close.covered is False


def test_bad_fourplex_questions_ask_about_price_reduction_and_concessions():
    report = _report_for("bad_fourplex.yaml")
    question_text = " ".join(report.questions)
    assert "price reduction" in question_text.lower()
    assert "closing costs" in question_text.lower() or "rate buydown" in question_text.lower()


def test_questions_always_ask_for_t12_and_violations():
    report = _report_for("good_duplex.yaml")
    question_text = " ".join(report.questions).lower()
    assert "t-12" in question_text
    assert "violations" in question_text


def test_key_metrics_include_house_hack_fields_when_applicable():
    report = _report_for("good_duplex.yaml")
    assert "Full monthly payment" in report.key_metrics
    assert "House-hack max offer" in report.key_metrics


def test_rule_detail_mirrors_verdict_rules():
    report = _report_for("marginal_triplex.yaml")
    assert any("FAIL" in line and "DSCR" in line for line in report.rule_detail)


def test_strong_dscr_and_missing_comp_rent_are_flagged():
    from tests.factories import simple_rental
    from underwriting import engine, verdict

    deal = simple_rental()  # DSCR ~1.67, no house hack, comparable_rent_estimate unset
    assert deal.comparable_rent_estimate is None
    thresholds = engine.Thresholds(min_dscr=1.0, min_cash_on_cash=0.0, min_monthly_cash_flow=-10_000, max_breakeven_occupancy=1.0)
    analysis = engine.full_analysis(deal, thresholds)
    assert analysis.core.dscr >= 1.3
    v = verdict.evaluate_core_verdict(analysis, thresholds)

    report = build_report(deal, analysis, v, None)
    assert any("Strong DSCR" in s for s in report.strengths)
    assert any("comparable units renting" in q for q in report.questions)


def test_house_hack_report_asks_about_utilities_and_assumption_sourced_tax():
    from tests.factories import house_hack_duplex
    from underwriting.models import ExpenseItem
    from underwriting.pipeline import analyze_deal

    deal = house_hack_duplex(
        expense_items=[
            ExpenseItem(name="property_tax", annual_amount=2400, source="assumption"),
            ExpenseItem(name="insurance", annual_amount=1200, source="assumption"),
        ]
    )
    assert deal.separate_utilities is None
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    report = build_report(deal, full.analysis, full.verdict, full.hh_bundle)

    question_text = " ".join(report.questions).lower()
    assert "separately metered" in question_text
    assert "assessment be reset" in question_text
