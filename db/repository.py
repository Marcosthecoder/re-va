"""Thin, testable CRUD helpers around the ORM models, shared by every
Streamlit page so none of them talk to SQLAlchemy directly.

Every deal belongs to a user. ``get_deal`` and ``list_deals`` always filter
by ``user_id`` so one account can never read or modify another account's
deals, even by guessing an id.
"""
from __future__ import annotations

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import STAGES, Deal
from underwriting import engine, verdict
from underwriting.models import PropertyInput


def create_deal(session: Session, property_input: PropertyInput, yaml_content: str, user_id: int) -> Deal:
    deal = Deal(
        user_id=user_id,
        deal_name=property_input.deal_name,
        address=property_input.address,
        price=property_input.price,
        county=property_input.county,
        property_type=property_input.property_type,
        is_house_hack=property_input.is_house_hack,
        stage="New",
        yaml_content=yaml_content,
    )
    session.add(deal)
    session.commit()
    return deal


def load_property_input(deal: Deal) -> PropertyInput:
    """Reconstruct the deal's full PropertyInput from its stored YAML."""
    return PropertyInput(**yaml.safe_load(deal.yaml_content))


def save_deal_yaml(session: Session, deal: Deal, property_input: PropertyInput, yaml_content: str) -> None:
    """Persist edits made to a deal (e.g. corrected intake fields) back to the row."""
    deal.deal_name = property_input.deal_name
    deal.address = property_input.address
    deal.price = property_input.price
    deal.county = property_input.county
    deal.property_type = property_input.property_type
    deal.is_house_hack = property_input.is_house_hack
    deal.yaml_content = yaml_content
    session.commit()


def save_verdict(session: Session, deal: Deal, core: engine.CoreMetrics, v: verdict.Verdict) -> None:
    deal.verdict_outcome = v.outcome
    deal.verdict_target_price = v.target_price
    deal.dscr = core.dscr
    deal.cash_on_cash = core.cash_on_cash_return if core.cash_on_cash_return != float("inf") else None
    deal.max_offer_gap = (deal.price - v.target_price) if v.target_price is not None else None
    session.commit()


def list_deals(session: Session, user_id: int, stage: str | None = None) -> list[Deal]:
    stmt = select(Deal).where(Deal.user_id == user_id).order_by(Deal.updated_at.desc())
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    return list(session.scalars(stmt))


def get_deal(session: Session, deal_id: int, user_id: int) -> Deal | None:
    """Returns the deal only if it exists AND belongs to user_id, else None."""
    deal = session.get(Deal, deal_id)
    if deal is None or deal.user_id != user_id:
        return None
    return deal


def set_stage(session: Session, deal: Deal, stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Must be one of {STAGES}.")
    deal.stage = stage
    session.commit()


def set_notes(session: Session, deal: Deal, notes: str) -> None:
    deal.notes = notes
    session.commit()


def delete_deal(session: Session, deal: Deal) -> None:
    session.delete(deal)
    session.commit()
