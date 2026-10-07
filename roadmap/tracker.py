"""DB-backed tracking of checklist progress per deal."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CHECKLIST_STATUSES, ChecklistItem
from roadmap.checklists import checklist_for


def create_checklist_for_deal(session: Session, deal_id: int, checklist_type: str) -> list[ChecklistItem]:
    """Creates the checklist rows for a deal if none exist yet for this type. Idempotent."""
    existing = get_checklist(session, deal_id, checklist_type)
    if existing:
        return existing

    items = [
        ChecklistItem(deal_id=deal_id, checklist_type=checklist_type, order_index=i, item_text=text)
        for i, text in enumerate(checklist_for(checklist_type))
    ]
    session.add_all(items)
    session.commit()
    return items


def get_checklist(session: Session, deal_id: int, checklist_type: str | None = None) -> list[ChecklistItem]:
    stmt = select(ChecklistItem).where(ChecklistItem.deal_id == deal_id).order_by(ChecklistItem.order_index)
    if checklist_type:
        stmt = stmt.where(ChecklistItem.checklist_type == checklist_type)
    return list(session.scalars(stmt))


def update_item_status(session: Session, item: ChecklistItem, status: str, notes: str | None = None) -> None:
    if status not in CHECKLIST_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Must be one of {CHECKLIST_STATUSES}.")
    item.status = status
    if notes is not None:
        item.notes = notes
    item.completed_date = dt.date.today() if status == "done" else None
    session.commit()


def progress_pct(items: list[ChecklistItem]) -> float:
    if not items:
        return 0.0
    done = sum(1 for i in items if i.status == "done")
    return done / len(items)
