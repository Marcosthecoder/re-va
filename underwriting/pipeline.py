"""Wires a PropertyInput + InvestorProfile through the full engine -> (house
hack) -> verdict pipeline in one call. Used by the CLI and every Streamlit
page that needs a deal's full analysis, so that wiring lives in exactly one
place instead of being copy-pasted per caller.
"""
from __future__ import annotations

from dataclasses import dataclass

from underwriting import engine, house_hack, property_standards, verdict
from underwriting.models import PropertyInput
from underwriting.profile import InvestorProfile


@dataclass
class FullBundle:
    deal: PropertyInput
    thresholds: engine.Thresholds
    analysis: engine.AnalysisResult
    hh_bundle: verdict.HouseHackBundle | None
    verdict: verdict.Verdict


def analyze_deal(deal: PropertyInput, profile: InvestorProfile) -> FullBundle:
    """Run everything: core engine, house hack module (if applicable), and verdict."""
    thresholds = profile.underwriting_thresholds.to_engine_thresholds()
    analysis = engine.full_analysis(deal, thresholds)

    if not deal.is_house_hack:
        v = verdict.evaluate_core_verdict(analysis, thresholds)
        return FullBundle(deal=deal, thresholds=thresholds, analysis=analysis, hh_bundle=None, verdict=v)

    cash_close = house_hack.cash_to_close(deal, profile.investor.cash_on_hand)
    dti = house_hack.lender_dti_check(deal, profile.investor.monthly_gross_income, profile.investor.monthly_debt_payments)
    self_suff = house_hack.self_sufficiency_test(deal)
    loan_limit = house_hack.loan_limit_check(deal, profile.financing.fha_loan_limits_lehigh_2026)
    live_in = house_hack.live_in_phase(deal)
    mixed_use = property_standards.mixed_use_check(deal)
    flags = property_standards.property_standards_flags(deal)
    constraints = house_hack.HouseHackExtraConstraints(
        cash_on_hand=profile.investor.cash_on_hand,
        monthly_gross_income=profile.investor.monthly_gross_income,
        monthly_debt_payments=profile.investor.monthly_debt_payments,
        loan_limits=profile.financing.fha_loan_limits_lehigh_2026,
        max_owner_net_housing_cost=profile.underwriting_thresholds.max_owner_net_housing_cost,
    )
    max_price_hh = house_hack.house_hack_max_offer_price(deal, thresholds, constraints)
    hh_bundle = verdict.HouseHackBundle(
        live_in=live_in,
        dti=dti,
        self_sufficiency=self_suff,
        loan_limit=loan_limit,
        cash_close=cash_close,
        mixed_use=mixed_use,
        standards_flags=flags,
        max_offer_price_house_hack=max_price_hh,
        max_owner_net_housing_cost=profile.underwriting_thresholds.max_owner_net_housing_cost,
    )
    v = verdict.evaluate_house_hack_verdict(analysis, thresholds, hh_bundle)
    return FullBundle(deal=deal, thresholds=thresholds, analysis=analysis, hh_bundle=hh_bundle, verdict=v)
