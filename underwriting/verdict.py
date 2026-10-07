"""Rule-based verdict logic. No LLM involved — every rule is a plain comparison
against a threshold from the investor profile, and every rule's pass/fail and
the numbers behind it are shown.

Verdict meanings (buyer's perspective, not "approve the appraisal" PASS):
- PURSUE: every rule is met at the asking price.
- NEGOTIATE: not every rule is met at asking, but there's a lower price
  (``target_price``) at which every rule would be met.
- PASS: no price makes this deal meet every rule. Walk away.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from underwriting import engine, house_hack, property_standards


@dataclass
class RuleCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class Verdict:
    outcome: str  # "PURSUE" | "NEGOTIATE" | "PASS"
    target_price: float | None
    rules: list[RuleCheck]
    summary: str

    @property
    def failed_rules(self) -> list[RuleCheck]:
        return [r for r in self.rules if not r.passed]


def _core_rules(core: engine.CoreMetrics, thresholds: engine.Thresholds) -> list[RuleCheck]:
    return [
        RuleCheck(
            "DSCR",
            core.dscr >= thresholds.min_dscr,
            f"{core.dscr:.2f} vs. minimum {thresholds.min_dscr:.2f}",
        ),
        RuleCheck(
            "Cash-on-cash return",
            core.cash_on_cash_return >= thresholds.min_cash_on_cash,
            f"{core.cash_on_cash_return:.1%} vs. minimum {thresholds.min_cash_on_cash:.1%}",
        ),
        RuleCheck(
            "Monthly cash flow",
            core.cash_flow_before_tax_monthly >= thresholds.min_monthly_cash_flow,
            f"${core.cash_flow_before_tax_monthly:,.0f}/mo vs. minimum ${thresholds.min_monthly_cash_flow:,.0f}/mo",
        ),
        RuleCheck(
            "Breakeven occupancy",
            core.breakeven_occupancy <= thresholds.max_breakeven_occupancy,
            f"{core.breakeven_occupancy:.1%} vs. maximum {thresholds.max_breakeven_occupancy:.1%}",
        ),
    ]


def evaluate_core_verdict(analysis: engine.AnalysisResult, thresholds: engine.Thresholds) -> Verdict:
    """Verdict for a strategy-agnostic "fully rented at market" deal (rental/commercial)."""
    rules = _core_rules(analysis.core, thresholds)
    if all(r.passed for r in rules):
        return Verdict("PURSUE", analysis.price, rules, "All investment thresholds are met at the asking price.")
    if analysis.max_offer_price > 0:
        return Verdict(
            "NEGOTIATE",
            analysis.max_offer_price,
            rules,
            f"Thresholds aren't met at ${analysis.price:,.0f}, but would be at or below ${analysis.max_offer_price:,.0f}.",
        )
    return Verdict(
        "PASS",
        None,
        rules,
        "No price makes this deal meet the required thresholds — rent vs. expenses don't support this deal here.",
    )


@dataclass
class HouseHackBundle:
    """Pre-computed house-hack-specific results, passed in so this module stays pure rules."""

    live_in: house_hack.LiveInPhaseResult
    dti: house_hack.DTIResult
    self_sufficiency: house_hack.SelfSufficiencyResult
    loan_limit: house_hack.LoanLimitResult
    cash_close: house_hack.CashToCloseSummary
    mixed_use: property_standards.MixedUseResult
    standards_flags: list[property_standards.StandardsFlag]
    max_offer_price_house_hack: float
    max_owner_net_housing_cost: float


def evaluate_house_hack_verdict(analysis: engine.AnalysisResult, thresholds: engine.Thresholds, bundle: HouseHackBundle) -> Verdict:
    """Verdict for an FHA house hack deal: core rules plus house-hack-specific rules."""
    rules = _core_rules(analysis.core, thresholds)

    rules.append(
        RuleCheck(
            "Owner net housing cost (live-in phase)",
            bundle.live_in.net_monthly_housing_cost <= bundle.max_owner_net_housing_cost,
            f"${bundle.live_in.net_monthly_housing_cost:,.0f}/mo vs. maximum ${bundle.max_owner_net_housing_cost:,.0f}/mo",
        )
    )
    rules.append(
        RuleCheck(
            "Front DTI",
            bundle.dti.front_pass,
            f"{bundle.dti.front_dti:.1%} vs. maximum {bundle.dti.max_front_dti:.1%}",
        )
    )
    rules.append(
        RuleCheck(
            "Back DTI",
            bundle.dti.back_pass,
            f"{bundle.dti.back_dti:.1%} vs. maximum {bundle.dti.max_back_dti:.1%}",
        )
    )
    if bundle.self_sufficiency.applicable:
        rules.append(
            RuleCheck(
                "FHA self-sufficiency test (3-4 unit)",
                bundle.self_sufficiency.passed,
                f"75% of market rent ${bundle.self_sufficiency.seventy_five_pct_of_rent:,.0f}/mo vs. "
                f"full payment ${bundle.self_sufficiency.full_monthly_payment:,.0f}/mo "
                f"(gap ${bundle.self_sufficiency.gap:,.0f})",
            )
        )
    if bundle.loan_limit.status != "unknown_verify_hud":
        rules.append(
            RuleCheck(
                "FHA loan limit",
                bundle.loan_limit.status == "pass",
                f"Loan amount ${bundle.loan_limit.loan_amount:,.0f} vs. county limit ${bundle.loan_limit.limit:,.0f}",
            )
        )
    rules.append(
        RuleCheck(
            "Cash to close covered",
            bundle.cash_close.covered,
            f"Requires ${bundle.cash_close.total_cash_required:,.0f}, have ${bundle.cash_close.cash_on_hand:,.0f} "
            f"(gap ${max(bundle.cash_close.cash_gap, 0):,.0f})",
        )
    )
    rules.append(
        RuleCheck(
            "Mixed-use residential majority (51%+)",
            bundle.mixed_use.passed,
            "not applicable" if not bundle.mixed_use.applicable else f"{bundle.mixed_use.residential_pct:.1%} residential",
        )
    )

    hard_fail_flags = [f for f in bundle.standards_flags if f.severity == "likely_fail"]
    rules.append(
        RuleCheck(
            "FHA property condition standards",
            len(hard_fail_flags) == 0,
            "no likely-fail conditions flagged" if not hard_fail_flags else "; ".join(f.description for f in hard_fail_flags),
        )
    )

    if all(r.passed for r in rules):
        return Verdict("PURSUE", analysis.price, rules, "Every core and house-hack rule is met at the asking price.")
    if bundle.max_offer_price_house_hack > 0:
        return Verdict(
            "NEGOTIATE",
            bundle.max_offer_price_house_hack,
            rules,
            f"Rules aren't all met at ${analysis.price:,.0f}, but would be at or below "
            f"${bundle.max_offer_price_house_hack:,.0f}.",
        )
    return Verdict(
        "PASS",
        None,
        rules,
        "No price makes this deal meet every house-hack rule. Walk away or renegotiate the structure "
        "(seller concessions, assistance, co-borrower) rather than just the price.",
    )
