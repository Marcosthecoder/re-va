"""FHA house hack underwriting. Runs alongside the core engine for an owner-occupied
2-4 unit (or majority-residential mixed-use) deal.

Expense item name convention: the full-payment calculation needs the itemized
property tax and insurance lines by name. A deal YAML feeding this module must
include expense_items named exactly ``property_tax`` and ``insurance``
(case-insensitive) — this is deal data, not something we'll silently assume.
"""
from __future__ import annotations

from dataclasses import dataclass

from underwriting import engine
from underwriting.models import ExpenseItem, PropertyInput


def _find_expense_annual(expense_items: list[ExpenseItem], name: str) -> float:
    for e in expense_items:
        if e.name.lower() == name.lower():
            return e.annual_amount
    raise ValueError(
        f"House hack payment calculation requires an expense item named '{name}' in expense_items, "
        "and none was found. Add it rather than letting the engine assume a value."
    )


@dataclass
class FullMonthlyPayment:
    principal_interest: float
    property_tax: float
    insurance: float
    mip: float
    total: float


def full_monthly_payment(property_input: PropertyInput) -> FullMonthlyPayment:
    """PITI + ongoing MIP: the full monthly housing payment for this deal at its current price."""
    debt_service = engine.compute_debt_service(property_input.price, property_input.financing)
    monthly_tax = _find_expense_annual(property_input.expense_items, "property_tax") / 12
    monthly_insurance = _find_expense_annual(property_input.expense_items, "insurance") / 12
    total = debt_service.monthly_principal_interest + monthly_tax + monthly_insurance + debt_service.monthly_mip
    return FullMonthlyPayment(
        principal_interest=debt_service.monthly_principal_interest,
        property_tax=monthly_tax,
        insurance=monthly_insurance,
        mip=debt_service.monthly_mip,
        total=total,
    )


@dataclass
class CashToCloseSummary:
    down_payment: float
    closing_costs: float
    seller_concessions: float
    down_payment_assistance: float
    total_cash_required: float
    cash_on_hand: float
    cash_gap: float
    covered: bool


def cash_to_close(property_input: PropertyInput, cash_on_hand: float) -> CashToCloseSummary:
    """Cash needed to close vs. cash actually on hand. Positive cash_gap means short by that amount."""
    price = property_input.price
    financing = property_input.financing
    down_payment = price * financing.down_payment_pct
    closing_costs = price * financing.closing_cost_pct
    concessions = min(property_input.seller_concessions_amount, price * financing.max_seller_concession_pct)
    assistance = property_input.down_payment_assistance_amount
    total_required = max(down_payment + closing_costs - concessions - assistance, 0.0)
    gap = total_required - cash_on_hand
    return CashToCloseSummary(
        down_payment=down_payment,
        closing_costs=closing_costs,
        seller_concessions=concessions,
        down_payment_assistance=assistance,
        total_cash_required=total_required,
        cash_on_hand=cash_on_hand,
        cash_gap=gap,
        covered=gap <= 0,
    )


@dataclass
class LiveInPhaseResult:
    full_monthly_payment: float
    owner_share_of_expenses: float
    other_units_rent_monthly: float
    vacancy_and_repair_adjustment: float
    net_rent_from_others: float
    net_monthly_housing_cost: float
    comparable_rent_estimate: float | None
    monthly_savings_vs_comparable: float | None


def live_in_phase(property_input: PropertyInput) -> LiveInPhaseResult:
    """Net monthly housing cost while the owner lives in one unit and rents the rest.

    Other units' rent is discounted by vacancy_pct + repairs_pct (from assumptions)
    before being credited against the payment, since that rent isn't guaranteed.
    """
    payment = full_monthly_payment(property_input)
    other_units = property_input.non_owner_units
    other_rent_monthly = sum(u.in_place_rent for u in other_units)
    assumptions = property_input.assumptions
    adjustment = other_rent_monthly * (assumptions.vacancy_pct + assumptions.repairs_pct)
    net_rent = other_rent_monthly - adjustment
    net_housing_cost = payment.total + property_input.owner_share_of_expenses - net_rent
    comparable = property_input.comparable_rent_estimate
    savings = (comparable - net_housing_cost) if comparable is not None else None
    return LiveInPhaseResult(
        full_monthly_payment=payment.total,
        owner_share_of_expenses=property_input.owner_share_of_expenses,
        other_units_rent_monthly=other_rent_monthly,
        vacancy_and_repair_adjustment=adjustment,
        net_rent_from_others=net_rent,
        net_monthly_housing_cost=net_housing_cost,
        comparable_rent_estimate=comparable,
        monthly_savings_vs_comparable=savings,
    )


@dataclass
class MoveOutPhaseResult:
    """Post move-out investor metrics: owner's former unit is now rented at market.

    This reuses the core engine's standard "fully rented at market" analysis —
    that is exactly what move-out looks like, so there's no separate formula here.
    """

    core: engine.CoreMetrics
    pro_forma: engine.ProForma


def move_out_phase(property_input: PropertyInput) -> MoveOutPhaseResult:
    core = engine.core_metrics(property_input)
    pro_forma = engine.five_year_pro_forma(property_input, core)
    return MoveOutPhaseResult(core=core, pro_forma=pro_forma)


@dataclass
class DTIResult:
    effective_monthly_income: float
    rental_income_credit: float
    front_dti: float
    back_dti: float
    max_front_dti: float
    max_back_dti: float
    front_pass: bool
    back_pass: bool


def lender_dti_check(property_input: PropertyInput, monthly_gross_income: float, monthly_debt_payments: float) -> DTIResult:
    """Front/back DTI using the lender's rental income credit on the OTHER units' market rent.

    The owner's own unit never counts as income for this calculation.
    """
    payment = full_monthly_payment(property_input).total
    other_units_market_rent = sum(u.market_rent for u in property_input.non_owner_units)
    rental_credit = other_units_market_rent * property_input.financing.rental_income_credit_pct
    effective_income = monthly_gross_income + rental_credit
    front = payment / effective_income if effective_income else float("inf")
    back = (payment + monthly_debt_payments) / effective_income if effective_income else float("inf")
    return DTIResult(
        effective_monthly_income=effective_income,
        rental_income_credit=rental_credit,
        front_dti=front,
        back_dti=back,
        max_front_dti=property_input.financing.max_front_dti,
        max_back_dti=property_input.financing.max_back_dti,
        front_pass=front <= property_input.financing.max_front_dti,
        back_pass=back <= property_input.financing.max_back_dti,
    )


@dataclass
class SelfSufficiencyResult:
    applicable: bool
    total_market_rent_monthly: float
    seventy_five_pct_of_rent: float
    full_monthly_payment: float
    gap: float
    passed: bool


def self_sufficiency_test(property_input: PropertyInput) -> SelfSufficiencyResult:
    """FHA self-sufficiency test, required for 3 and 4 unit properties only:
    75% of TOTAL market rent (every unit, including the owner's) must cover
    the full monthly payment. ``gap`` > 0 means it fails by that many dollars/month.
    """
    unit_count = property_input.unit_count
    applicable = unit_count in (3, 4)
    total_market_rent = sum(u.market_rent for u in property_input.units)
    threshold_income = total_market_rent * 0.75
    payment = full_monthly_payment(property_input).total
    gap = payment - threshold_income
    passed = (not applicable) or (threshold_income >= payment)
    return SelfSufficiencyResult(
        applicable=applicable,
        total_market_rent_monthly=total_market_rent,
        seventy_five_pct_of_rent=threshold_income,
        full_monthly_payment=payment,
        gap=gap,
        passed=passed,
    )


@dataclass
class LoanLimitResult:
    unit_count: int
    loan_amount: float
    limit: float | None
    status: str  # "pass" | "fail" | "unknown_verify_hud"


_UNIT_COUNT_KEY = {1: "one_unit", 2: "two_unit", 3: "three_unit", 4: "four_unit"}


def loan_limit_check(property_input: PropertyInput, loan_limits: dict) -> LoanLimitResult:
    """Compares the loan amount against the county's FHA loan limit for this unit count.

    ``loan_limits`` is the profile's fha_loan_limits_lehigh_2026 dict. A missing or
    null limit for this unit count returns "unknown_verify_hud" rather than a fake pass.
    """
    debt_service = engine.compute_debt_service(property_input.price, property_input.financing)
    key = _UNIT_COUNT_KEY.get(property_input.unit_count)
    limit = loan_limits.get(key) if key else None
    if limit is None:
        status = "unknown_verify_hud"
    elif debt_service.loan_amount <= limit:
        status = "pass"
    else:
        status = "fail"
    return LoanLimitResult(unit_count=property_input.unit_count, loan_amount=debt_service.loan_amount, limit=limit, status=status)


@dataclass
class HouseHackExtraConstraints:
    """Inputs needed to extend max-offer-price search with house-hack-specific limits."""

    cash_on_hand: float
    monthly_gross_income: float
    monthly_debt_payments: float
    loan_limits: dict
    max_owner_net_housing_cost: float


def house_hack_max_offer_price(
    property_input: PropertyInput,
    thresholds: engine.Thresholds,
    constraints: HouseHackExtraConstraints,
) -> float:
    """Max offer price meeting core thresholds AND cash-to-close, DTI, self-sufficiency,
    loan limit, and owner net housing cost constraints. All are monotonic in price
    (higher price never helps any of them), so this folds into the same bisection
    the core engine uses via ``extra_predicate``.
    """

    def extra(price: float) -> bool:
        variant = property_input.model_copy(update={"price": price})
        if not cash_to_close(variant, constraints.cash_on_hand).covered:
            return False
        dti = lender_dti_check(variant, constraints.monthly_gross_income, constraints.monthly_debt_payments)
        if not (dti.front_pass and dti.back_pass):
            return False
        if not self_sufficiency_test(variant).passed:
            return False
        if loan_limit_check(variant, constraints.loan_limits).status == "fail":
            return False
        if live_in_phase(variant).net_monthly_housing_cost > constraints.max_owner_net_housing_cost:
            return False
        return True

    return engine.max_offer_price(property_input, thresholds, extra_predicate=extra)
