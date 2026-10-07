"""Assembles the one-page deal report: key metrics, top risks/strengths, and
broker questions. Everything here is rule-based from numbers the underwriting
engine already computed — no LLM, no new math. The plain-English write-up
(reports.explain) is the only LLM-touched piece, and it only narrates numbers
already in this report.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from underwriting import engine, verdict
from underwriting.models import PropertyInput


@dataclass
class ReportData:
    deal_name: str
    address: str
    price: float
    is_house_hack: bool
    verdict_outcome: str
    verdict_target_price: float | None
    key_metrics: dict[str, str]
    risks: list[str]
    strengths: list[str]
    questions: list[str]
    rule_detail: list[str] = field(default_factory=list)


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    return "n/a" if x in (float("inf"), float("-inf")) else f"{x:.1%}"


def _top_risks(deal: PropertyInput, analysis: engine.AnalysisResult, bundle: verdict.HouseHackBundle | None) -> list[str]:
    risks: list[str] = []

    if bundle is not None:
        for flag in bundle.standards_flags:
            if flag.severity == "likely_fail":
                risks.append(f"Property condition: {flag.description}")
        if bundle.self_sufficiency.applicable and not bundle.self_sufficiency.passed:
            risks.append(
                f"FHA self-sufficiency test fails by {_money(bundle.self_sufficiency.gap)}/mo "
                "— the appraiser can kill this loan structure even if everything else works."
            )
        if not bundle.cash_close.covered:
            risks.append(f"Cash to close is short by {_money(bundle.cash_close.cash_gap)} at the asking price.")
        if not (bundle.dti.front_pass and bundle.dti.back_pass):
            risks.append(f"DTI exceeds lender limits (front {_pct(bundle.dti.front_dti)}, back {_pct(bundle.dti.back_dti)}).")

    if analysis.core.dscr < 1.0:
        risks.append(f"DSCR is below 1.0 ({analysis.core.dscr:.2f}) — the property doesn't cover its own debt service.")
    if analysis.core.breakeven_occupancy > 0.90:
        risks.append(f"Breakeven occupancy is {_pct(analysis.core.breakeven_occupancy)} — very little room for vacancy.")
    for flag in analysis.lease_rollover_flags:
        if flag.income_share_pct > 0.25:
            risks.append(
                f"Unit '{flag.unit_label}' lease expires in {flag.months_to_expiry} months and is "
                f"{_pct(flag.income_share_pct)} of gross rent — losing it would hurt."
            )

    return risks[:3] if risks else ["No major risks flagged by the rules above — still get an inspection and lender quote."]


def _top_strengths(deal: PropertyInput, analysis: engine.AnalysisResult, bundle: verdict.HouseHackBundle | None) -> list[str]:
    strengths: list[str] = []
    core = analysis.core

    if core.dscr >= 1.3:
        strengths.append(f"Strong DSCR of {core.dscr:.2f} — comfortable cushion over the loan payment.")
    if core.cash_on_cash_return >= 0.15:
        strengths.append(f"Cash-on-cash return of {_pct(core.cash_on_cash_return)} is well above a typical bar.")
    if bundle is not None and bundle.live_in.monthly_savings_vs_comparable is not None and bundle.live_in.monthly_savings_vs_comparable > 0:
        strengths.append(
            f"Living here costs {_money(bundle.live_in.monthly_savings_vs_comparable)}/mo less than renting "
            "a comparable apartment nearby."
        )
    if bundle is not None and bundle.self_sufficiency.applicable and bundle.self_sufficiency.passed:
        strengths.append("Passes the FHA self-sufficiency test.")
    if not analysis.lease_rollover_flags:
        strengths.append("No leases expiring within 24 months.")
    if bundle is not None and not any(f.severity == "likely_fail" for f in bundle.standards_flags):
        strengths.append("No likely FHA appraisal red flags from the property condition inputs.")

    return strengths[:3] if strengths else ["Nothing stands out as a clear strength yet — this deal needs the price to move."]


def _broker_questions(deal: PropertyInput, analysis: engine.AnalysisResult, bundle: verdict.HouseHackBundle | None) -> list[str]:
    questions = [
        "Can you send the last 12 months of actual operating expenses (T-12) and the current rent roll?",
        "Are there any known code violations, open permits, or deferred maintenance?",
    ]
    if deal.comparable_rent_estimate is None:
        questions.append("What are comparable units renting for in this immediate area right now?")
    if analysis.lease_rollover_flags:
        units = ", ".join(f.unit_label for f in analysis.lease_rollover_flags)
        questions.append(f"Do the tenants in {units} intend to renew when their leases expire?")
    if bundle is not None:
        if bundle.self_sufficiency.applicable and not bundle.self_sufficiency.passed:
            questions.append("Would the seller consider a price reduction to meet the FHA self-sufficiency test?")
        if not bundle.cash_close.covered:
            questions.append("Is the seller open to additional seller-paid closing costs or a rate buydown?")
        if deal.separate_utilities is None:
            questions.append("Are utilities separately metered per unit, or is everything on one meter?")
    if any(e.source == "assumption" for e in analysis.core.operating_expenses.items if e.name in ("property_tax", "insurance")):
        questions.append("What's the current property tax bill, and will the assessment be reset after sale?")
    return questions


def build_report(
    deal: PropertyInput,
    analysis: engine.AnalysisResult,
    v: verdict.Verdict,
    bundle: verdict.HouseHackBundle | None = None,
) -> ReportData:
    core = analysis.core
    key_metrics = {
        "Price": _money(analysis.price),
        "NOI (market)": f"{_money(core.noi_annual)}/yr",
        "Cap rate (market)": _pct(core.cap_rate_market),
        "DSCR": f"{core.dscr:.2f}",
        "Cash flow": f"{_money(core.cash_flow_before_tax_monthly)}/mo",
        "Cash-on-cash": _pct(core.cash_on_cash_return),
        "Total cash required": _money(core.total_cash_required),
        "Max offer price": _money(analysis.max_offer_price),
    }
    if bundle is not None:
        key_metrics["Full monthly payment"] = _money(bundle.live_in.full_monthly_payment)
        key_metrics["Net housing cost (live-in)"] = _money(bundle.live_in.net_monthly_housing_cost)
        key_metrics["House-hack max offer"] = _money(bundle.max_offer_price_house_hack)

    return ReportData(
        deal_name=deal.deal_name,
        address=deal.address,
        price=deal.price,
        is_house_hack=deal.is_house_hack,
        verdict_outcome=v.outcome,
        verdict_target_price=v.target_price,
        key_metrics=key_metrics,
        risks=_top_risks(deal, analysis, bundle),
        strengths=_top_strengths(deal, analysis, bundle),
        questions=_broker_questions(deal, analysis, bundle),
        rule_detail=[f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}" for r in v.rules],
    )
