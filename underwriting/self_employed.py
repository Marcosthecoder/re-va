"""Self-employed qualifying income for a buyer with 25%+ ownership in a business.

FHA treats anyone with 25% or more ownership in a business as self-employed for
qualifying purposes, generally requiring two years of personal and business tax
returns. This module never invents a qualifying income figure when the history
isn't there yet — it reports what's missing and when it's expected to resolve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

DEFAULT_CHECKLIST = [
    "File tax returns on time every year between now and applying for the mortgage",
    "Keep business and personal bank accounts completely separate",
    "Avoid aggressively writing off income on the business return — it lowers taxes "
    "but also lowers the income a lender will count",
    "Save 3+ months of the full mortgage payment in reserves",
    "Get the exact ownership percentage in the business documented in writing",
    "Confirm how commission/override income will be documented going forward "
    "(W-2, 1099, K-1, or owner draw) — the type changes what a lender can count and when",
]


def _add_months(d: date, months: int) -> date:
    total_month = d.month - 1 + months
    year = d.year + total_month // 12
    month = total_month % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


@dataclass
class QualifyingIncomeResult:
    years_available: int
    years_required: int
    calculable: bool
    yearly_net_incomes: list[float]
    qualifying_monthly_income: float | None
    declining_income: bool
    mortgage_ready_date: date | None
    months_until_ready: int | None
    checklist: list[str] = field(default_factory=lambda: list(DEFAULT_CHECKLIST))
    notes: list[str] = field(default_factory=list)


def self_employed_qualifying_income(
    ownership_pct: float | None,
    years_of_tax_returns: int,
    yearly_net_incomes: list[float],
    as_of_date: date | None = None,
    years_required: int = 2,
    decline_threshold_pct: float = 0.10,
) -> QualifyingIncomeResult:
    """Average of the last ``years_required`` years of net (after write-off) income.

    ``yearly_net_incomes`` must be in chronological order (oldest first). If fewer
    years exist than ``years_required``, no qualifying income is calculated —
    instead a mortgage-ready date is projected from how many years are missing.
    """
    as_of = as_of_date or date.today()
    calculable = years_of_tax_returns >= years_required and len(yearly_net_incomes) >= years_required

    qualifying_monthly_income: float | None = None
    declining = False
    if calculable:
        last_n = yearly_net_incomes[-years_required:]
        qualifying_monthly_income = (sum(last_n) / len(last_n)) / 12
        if len(last_n) == 2 and last_n[1] < last_n[0] * (1 - decline_threshold_pct):
            declining = True

    years_missing = max(years_required - years_of_tax_returns, 0)
    months_until_ready = None
    mortgage_ready_date = None
    if not calculable:
        months_until_ready = years_missing * 12
        mortgage_ready_date = _add_months(as_of, months_until_ready)

    notes: list[str] = []
    if ownership_pct is None:
        notes.append(
            "Ownership percentage is not documented. If it's 25% or more, this self-employed "
            "income module applies and a lender will need 2 years of returns before counting it. "
            "Get the percentage in writing."
        )
    elif ownership_pct < 0.25:
        notes.append(
            f"Ownership percentage ({ownership_pct:.0%}) is below the 25% self-employed threshold — "
            "a lender may be able to treat this income as wage income instead, which has different "
            "documentation requirements than this module assumes. Confirm with a lender."
        )
    if declining:
        notes.append(
            "Income declined by more than "
            f"{decline_threshold_pct:.0%} year over year. Lenders often use the lower year, require a "
            "written explanation, or decline to count the income at all — confirm with a lender before "
            "relying on the average above."
        )

    return QualifyingIncomeResult(
        years_available=years_of_tax_returns,
        years_required=years_required,
        calculable=calculable,
        yearly_net_incomes=list(yearly_net_incomes),
        qualifying_monthly_income=qualifying_monthly_income,
        declining_income=declining,
        mortgage_ready_date=mortgage_ready_date,
        months_until_ready=months_until_ready,
        notes=notes,
    )


@dataclass
class CoBorrowerResult:
    co_borrower_monthly_income: float
    co_borrower_monthly_debts: float
    combined_monthly_income: float
    combined_monthly_debts: float
    note: str


def apply_co_borrower(
    monthly_gross_income: float,
    monthly_debt_payments: float,
    co_borrower_monthly_income: float,
    co_borrower_monthly_debts: float,
) -> CoBorrowerResult:
    """Combines a non-occupant co-borrower's income/debts with the buyer's own.

    Feed the combined figures back into ``house_hack.lender_dti_check`` and
    ``house_hack.house_hack_max_offer_price`` to see how a co-borrower changes
    qualification and the achievable price.
    """
    return CoBorrowerResult(
        co_borrower_monthly_income=co_borrower_monthly_income,
        co_borrower_monthly_debts=co_borrower_monthly_debts,
        combined_monthly_income=monthly_gross_income + co_borrower_monthly_income,
        combined_monthly_debts=monthly_debt_payments + co_borrower_monthly_debts,
        note=(
            "Combined figures include the co-borrower's income and debts. Re-run lender_dti_check and "
            "house_hack_max_offer_price with these combined numbers to see the new timeline and max price."
        ),
    )
