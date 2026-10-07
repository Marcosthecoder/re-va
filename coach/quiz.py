"""Static quiz bank on core underwriting concepts. Deterministic, no LLM —
these are fixed facts, not something worth risking a hallucinated answer on.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuizQuestion:
    id: str
    topic: str
    question: str
    choices: tuple[str, ...]
    correct_index: int
    explanation: str


QUIZ_BANK: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        "noi_1", "NOI",
        "What is Net Operating Income (NOI)?",
        ("Rent minus the mortgage payment", "Effective gross income minus operating expenses, before debt service",
         "Price minus down payment", "Cash flow after taxes"),
        1,
        "NOI = effective gross income - operating expenses. It deliberately excludes the mortgage "
        "(debt service) and income taxes, so you can compare properties regardless of how they're financed.",
    ),
    QuizQuestion(
        "noi_2", "NOI",
        "Does a higher property tax bill increase or decrease NOI, all else equal?",
        ("Increase it", "Decrease it", "No effect", "Only affects cap rate, not NOI"),
        1,
        "Property tax is an operating expense, so a higher bill lowers NOI directly.",
    ),
    QuizQuestion(
        "caprate_1", "Cap Rate",
        "How is cap rate calculated?",
        ("NOI / Price", "Cash flow / Down payment", "Price / NOI", "Rent / Price"),
        0,
        "Cap rate = NOI / purchase price. It's a quick, financing-independent way to compare how "
        "expensive one income property is relative to another.",
    ),
    QuizQuestion(
        "caprate_2", "Cap Rate",
        "If two similar duplexes have the same NOI but one costs more, which has the lower cap rate?",
        ("The cheaper one", "The more expensive one", "They're equal", "Cap rate doesn't depend on price"),
        1,
        "Cap rate = NOI/price, so for the same NOI, a higher price means a lower cap rate "
        "(you're paying more for the same income).",
    ),
    QuizQuestion(
        "dscr_1", "DSCR",
        "What does a DSCR of 1.15 mean?",
        ("The property loses $1.15 for every dollar of rent", "NOI is 1.15x the annual debt service — 15% cushion",
         "The loan covers 115% of the price", "Cash-on-cash return is 15%"),
        1,
        "DSCR (Debt Service Coverage Ratio) = NOI / annual debt service. 1.15 means the property's NOI "
        "covers the loan payment with 15% room to spare before cash flow goes negative.",
    ),
    QuizQuestion(
        "dscr_2", "DSCR",
        "A DSCR below 1.0 means:",
        ("The property is a great deal", "NOI doesn't fully cover the mortgage payment",
         "The down payment was too small", "Vacancy is zero"),
        1,
        "Below 1.0, the property's own income can't cover its debt service — you'd need outside cash every month.",
    ),
    QuizQuestion(
        "nnn_1", "NNN Leases",
        "In a triple-net (NNN) lease, who typically pays property taxes, insurance, and maintenance?",
        ("The landlord", "The tenant", "Split 50/50 automatically", "Neither — the county does"),
        1,
        "NNN = 'triple net': the tenant pays the three 'nets' (taxes, insurance, maintenance) on top of "
        "base rent, common in commercial leases. Residential leases are almost always gross or modified gross instead.",
    ),
    QuizQuestion(
        "nnn_2", "NNN Leases",
        "Which lease type is most common for a residential duplex/triplex unit?",
        ("NNN", "Gross lease (landlord pays operating expenses)", "Ground lease", "Percentage lease"),
        1,
        "Residential leases are almost always gross (or modified gross) — the landlord pays taxes, "
        "insurance, and most maintenance out of the rent collected.",
    ),
    QuizQuestion(
        "dd_1", "Due Diligence",
        "Before closing on a multi-unit property, which of these should you verify?",
        ("Only the asking price", "Current leases, security deposits held, and actual expenses (T-12)",
         "Just the paint color", "Nothing — the appraisal covers everything"),
        1,
        "Leases, security deposits, and a trailing-12-month expense history are core due diligence — "
        "they tell you what you're actually buying, not just what the listing claims.",
    ),
    QuizQuestion(
        "dd_2", "Due Diligence",
        "Why does a lease expiring in the next few months matter during due diligence?",
        ("It doesn't — leases auto-renew forever", "That tenant's rent may be at risk if they don't renew",
         "It only matters for commercial property", "It affects the loan interest rate directly"),
        1,
        "A lease expiring soon is a rollover risk: if that tenant doesn't renew, you could lose that "
        "unit's income (and face turnover costs) right after closing.",
    ),
)


def get_quiz(topic: str | None = None) -> list[QuizQuestion]:
    if topic is None:
        return list(QUIZ_BANK)
    return [q for q in QUIZ_BANK if q.topic.lower() == topic.lower()]


def topics() -> list[str]:
    seen: list[str] = []
    for q in QUIZ_BANK:
        if q.topic not in seen:
            seen.append(q.topic)
    return seen


def check_answer(question: QuizQuestion, selected_index: int) -> bool:
    return selected_index == question.correct_index
