"""SQLAlchemy ORM models for everything that needs to persist across runs.

The full deal (rent roll, financing, assumptions) is stored as the YAML text
it came from in ``Deal.yaml_content`` and reloaded into a PropertyInput via
``underwriting.models.load_deal``-equivalent parsing when needed, rather than
being re-normalized into many relational tables. Pipeline stage, verdict
summary, checklist progress, outreach drafts, rent comps, and every LLM call
are real rows so they survive a restart.

Every Deal and RentComp belongs to a User (``user_id``), so the hosted,
multi-user deployment keeps each signed-in user's deals and data separate.
ChecklistItem and OutreachDraft are scoped indirectly through their deal.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STAGES = ("New", "Underwriting", "Negotiating", "Under Contract", "Closed", "Passed")
CHECKLIST_TYPES = ("house_hack", "commercial")
CHECKLIST_STATUSES = ("not_started", "in_progress", "done")
OUTREACH_TYPES = ("broker", "lender", "seller")


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    profile_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    deal_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300))
    price: Mapped[float] = mapped_column(Float)
    county: Mapped[str] = mapped_column(String(100))
    property_type: Mapped[str] = mapped_column(String(100))
    is_house_hack: Mapped[bool] = mapped_column(default=False)
    stage: Mapped[str] = mapped_column(String(30), default="New")
    yaml_content: Mapped[str] = mapped_column(Text)

    verdict_outcome: Mapped[str | None] = mapped_column(String(20), default=None)
    verdict_target_price: Mapped[float | None] = mapped_column(Float, default=None)
    dscr: Mapped[float | None] = mapped_column(Float, default=None)
    cash_on_cash: Mapped[float | None] = mapped_column(Float, default=None)
    max_offer_gap: Mapped[float | None] = mapped_column(Float, default=None)

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    checklist_items: Mapped[list["ChecklistItem"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    outreach_drafts: Mapped[list["OutreachDraft"]] = relationship(back_populates="deal", cascade="all, delete-orphan")


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    checklist_type: Mapped[str] = mapped_column(String(20))
    order_index: Mapped[int] = mapped_column(Integer)
    item_text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    due_date: Mapped[dt.date | None] = mapped_column(default=None)
    completed_date: Mapped[dt.date | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    deal: Mapped["Deal"] = relationship(back_populates="checklist_items")


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"))
    draft_type: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    deal: Mapped["Deal"] = relationship(back_populates="outreach_drafts")


class RentComp(Base):
    __tablename__ = "rent_comps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    county: Mapped[str] = mapped_column(String(100))
    municipality: Mapped[str | None] = mapped_column(String(100), default=None)
    bedrooms: Mapped[float | None] = mapped_column(Float, default=None)
    sqft: Mapped[float | None] = mapped_column(Float, default=None)
    rent: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    date_entered: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    purpose: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    prompt_excerpt: Mapped[str] = mapped_column(Text)
    response_excerpt: Mapped[str] = mapped_column(Text)
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("deals.id"), default=None)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
