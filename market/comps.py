"""Stored rent comps (user-entered) and comparison against a deal's rents."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import RentComp

OVER_UNDER_THRESHOLD = 0.15


def add_comp(
    session: Session,
    user_id: int,
    county: str,
    rent: float,
    bedrooms: float | None = None,
    sqft: float | None = None,
    municipality: str | None = None,
    source: str = "manual",
    notes: str | None = None,
) -> RentComp:
    comp = RentComp(
        user_id=user_id, county=county, municipality=municipality, bedrooms=bedrooms, sqft=sqft, rent=rent, source=source, notes=notes
    )
    session.add(comp)
    session.commit()
    return comp


def list_comps(session: Session, user_id: int, county: str | None = None, bedrooms: float | None = None) -> list[RentComp]:
    stmt = select(RentComp).where(RentComp.user_id == user_id).order_by(RentComp.date_entered.desc())
    if county:
        stmt = stmt.where(RentComp.county == county)
    if bedrooms is not None:
        stmt = stmt.where(RentComp.bedrooms == bedrooms)
    return list(session.scalars(stmt))


def delete_comp(session: Session, comp: RentComp, user_id: int) -> None:
    if comp.user_id != user_id:
        raise PermissionError("This comp belongs to a different account.")
    session.delete(comp)
    session.commit()


@dataclass
class CompComparison:
    unit_rent: float
    average_comp_rent: float | None
    comp_count: int
    pct_difference: float | None  # (unit_rent - avg) / avg
    flag: str  # "over_market" | "under_market" | "in_line" | "no_comps"


def compare_to_comps(unit_rent: float, comps: list[RentComp]) -> CompComparison:
    """Flags a unit's rent as >15% over or under the average of the given comps."""
    if not comps:
        return CompComparison(unit_rent=unit_rent, average_comp_rent=None, comp_count=0, pct_difference=None, flag="no_comps")

    avg = sum(c.rent for c in comps) / len(comps)
    pct_diff = (unit_rent - avg) / avg if avg else 0.0
    if pct_diff > OVER_UNDER_THRESHOLD:
        flag = "over_market"
    elif pct_diff < -OVER_UNDER_THRESHOLD:
        flag = "under_market"
    else:
        flag = "in_line"
    return CompComparison(unit_rent=unit_rent, average_comp_rent=avg, comp_count=len(comps), pct_difference=pct_diff, flag=flag)
