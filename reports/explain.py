"""Plain-English explanation of an already-built report, for a first-time buyer.
The only numbers Claude sees are the ones already in ReportData — it narrates,
it doesn't calculate. Raises llm.client.LLMNotConfigured if no API key is set;
the caller (Streamlit page) should catch that and show a setup hint.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from llm.client import call_claude
from reports.report_builder import ReportData

_SYSTEM_PROMPT = """You explain a real estate deal to a first-time home buyer in plain English. \
You are given a verdict and a fixed set of already-computed numbers, risks, and strengths. \
Explain what they mean and why they matter. Do NOT introduce any number that isn't given to you, \
and do NOT recompute or second-guess the numbers. Keep it to 4-6 short paragraphs. Be direct about \
whether this looks like a good first deal, but make clear you're explaining the numbers, not replacing \
a lender, attorney, or inspector."""


def explain_report(report: ReportData, session: Session | None = None, deal_id: int | None = None) -> str:
    lines = [
        f"Deal: {report.deal_name} ({report.address})",
        f"Verdict: {report.verdict_outcome}" + (f", target price {report.verdict_target_price:,.0f}" if report.verdict_target_price else ""),
        "Key metrics:",
    ]
    lines += [f"  - {k}: {v}" for k, v in report.key_metrics.items()]
    lines.append("Top risks: " + "; ".join(report.risks))
    lines.append("Top strengths: " + "; ".join(report.strengths))

    return call_claude(
        purpose="report_explanation",
        system=_SYSTEM_PROMPT,
        user_message="\n".join(lines),
        session=session,
        deal_id=deal_id,
        max_tokens=1200,
    )
