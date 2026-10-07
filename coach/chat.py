"""Explains real estate terms/metrics using the user's own deal as the example.
Grounded only in numbers already in ``reports.report_builder.ReportData`` (or
no deal at all, for a generic explanation) — never asked to compute anything.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from llm.client import call_claude
from reports.report_builder import ReportData

_SYSTEM_PROMPT = """You are a patient real estate coach for a first-time home buyer doing an FHA house hack \
in the Lehigh Valley, PA. Explain concepts clearly and simply. When the user's own deal numbers are given, \
use THAT deal as the worked example — reference its actual numbers, don't invent new ones. Never calculate \
a new number yourself; only explain or reference numbers you were given. Keep answers conversational and \
under ~300 words unless the question clearly needs more."""


def _deal_context_block(report: ReportData | None) -> str:
    if report is None:
        return "No specific deal is loaded right now — answer generically."
    lines = [f"The user's current deal: {report.deal_name} ({report.address}), verdict {report.verdict_outcome}."]
    lines += [f"  {k}: {v}" for k, v in report.key_metrics.items()]
    return "\n".join(lines)


def ask(
    question: str,
    report: ReportData | None = None,
    history: list[tuple[str, str]] | None = None,
    session: Session | None = None,
    deal_id: int | None = None,
) -> str:
    """Ask the coach a question. ``history`` is a list of (question, answer) pairs
    for simple multi-turn context; kept short since this isn't meant to be a long thread.
    """
    turns = []
    for prior_q, prior_a in (history or [])[-4:]:
        turns.append(f"Q: {prior_q}\nA: {prior_a}")
    turns.append(f"Context:\n{_deal_context_block(report)}\n\nQuestion: {question}")
    user_message = "\n\n---\n\n".join(turns)

    return call_claude(
        purpose="coach_chat",
        system=_SYSTEM_PROMPT,
        user_message=user_message,
        session=session,
        deal_id=deal_id,
        max_tokens=800,
    )
