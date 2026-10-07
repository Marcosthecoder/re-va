"""Draft emails to brokers, lenders, and sellers. Drafts only — nothing in
this module (or anywhere in RE-VA) sends an email or contacts anyone. Every
draft is meant to be reviewed and sent by the user from their own inbox.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import OutreachDraft
from llm.client import call_claude
from underwriting.models import PropertyInput

_POLISH_SYSTEM_PROMPT = """You lightly polish real estate outreach email drafts for tone and clarity. \
Keep every fact and number exactly as given. Don't add new claims, numbers, or promises. Keep it concise \
and professional. Return ONLY the polished email body, no commentary."""


def draft_broker_email(deal: PropertyInput, questions: list[str] | None = None) -> tuple[str, str]:
    subject = f"Rent roll, T-12, and a few questions on {deal.address}"
    question_lines = "\n".join(f"- {q}" for q in (questions or [
        "Can you send the current rent roll and the last 12 months of actual operating expenses (T-12)?",
        "Are there any known code violations or deferred maintenance?",
    ]))
    body = f"""Hi,

I'm interested in {deal.address} (listed at ${deal.price:,.0f}). Before we go further, could you send:

- The current rent roll (unit, tenant, rent, lease start/end)
- The last 12 months of actual operating expenses (T-12), if available

A few other questions:
{question_lines}

Thanks,
"""
    return subject, body


def draft_lender_email(deal: PropertyInput, down_payment_pct: float = 0.035) -> tuple[str, str]:
    subject = f"FHA pre-approval / term sheet request — {deal.unit_count}-unit owner-occupied, ~${deal.price:,.0f}"
    body = f"""Hi,

I'm planning to buy a {deal.unit_count}-unit owner-occupied property in {deal.county} County, PA \
(approximate price ${deal.price:,.0f}), using FHA financing with {down_payment_pct:.1%} down. I'll be \
living in one unit and renting the others.

Could you send a term sheet or pre-approval letter, including:
- Current FHA interest rate and estimated closing costs
- Confirmation of how much of the other units' rent you'll count toward my qualifying income
- Any PHFA / Keystone Advantage Assistance programs I may qualify for

Thanks,
"""
    return subject, body


def draft_seller_financing_email(deal: PropertyInput) -> tuple[str, str]:
    subject = f"Question about {deal.address} — seller financing / concessions"
    body = f"""Hi,

I'm interested in {deal.address} and wanted to ask a couple of questions before submitting an offer:

- Would you consider seller financing, or a seller-paid rate buydown?
- Would you be open to seller concessions toward closing costs?

Thanks,
"""
    return subject, body


DRAFT_BUILDERS = {
    "broker": draft_broker_email,
    "lender": draft_lender_email,
    "seller": draft_seller_financing_email,
}


def polish_draft(subject: str, body: str, session: Session | None = None, deal_id: int | None = None) -> str:
    """Optional: ask Claude to tighten tone/clarity. Raises LLMNotConfigured if no API key —
    callers should catch that and just use the template body as-is."""
    return call_claude(
        purpose="outreach_polish",
        system=_POLISH_SYSTEM_PROMPT,
        user_message=f"Subject: {subject}\n\n{body}",
        session=session,
        deal_id=deal_id,
        max_tokens=600,
    )


def save_draft(session: Session, deal_id: int, draft_type: str, subject: str, body: str) -> OutreachDraft:
    if draft_type not in DRAFT_BUILDERS:
        raise ValueError(f"Unknown draft_type '{draft_type}'. Must be one of {list(DRAFT_BUILDERS)}.")
    draft = OutreachDraft(deal_id=deal_id, draft_type=draft_type, subject=subject, body=body)
    session.add(draft)
    session.commit()
    return draft


def list_drafts(session: Session, deal_id: int) -> list[OutreachDraft]:
    from sqlalchemy import select

    stmt = select(OutreachDraft).where(OutreachDraft.deal_id == deal_id).order_by(OutreachDraft.created_at.desc())
    return list(session.scalars(stmt))
