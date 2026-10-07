"""Pydantic input models for the underwriting engine.

These models describe a single deal. Nothing in this module performs
financial math — it only validates and structures the inputs that
``engine.py``, ``house_hack.py``, ``self_employed.py``, and
``property_standards.py`` consume.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

LeaseType = Literal["gross", "NNN", "modified_gross"]
ExpenseSource = Literal["seller_provided", "county_record", "assumption"]


class Unit(BaseModel):
    """One rentable unit in the property (residential or commercial)."""

    label: str
    bedrooms: float = 0
    sqft: float = Field(gt=0)
    is_owner_unit: bool = False
    market_rent: float = Field(ge=0, description="Monthly market rent for this unit")
    current_rent: Optional[float] = Field(
        default=None,
        description="Monthly contract rent actually being collected now. "
        "None means vacant, or owner-occupied.",
    )
    tenant_name: Optional[str] = None
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    lease_type: Optional[LeaseType] = None

    @property
    def in_place_rent(self) -> float:
        """Rent actually collectible today: current rent, else market rent."""
        if self.is_owner_unit:
            return 0.0
        return self.current_rent if self.current_rent is not None else self.market_rent


class ExpenseItem(BaseModel):
    """A single itemized annual operating expense, with its data source."""

    name: str
    annual_amount: float = Field(ge=0)
    source: ExpenseSource = "assumption"


class FinancingTerms(BaseModel):
    """Financing terms. Defaults are generic; FHA specifics are opt-in via the MIP fields."""

    method: Literal["fha", "conventional", "commercial_loan", "cash", "seller_finance"] = "fha"
    down_payment_pct: float = Field(ge=0, le=1)
    interest_rate: float = Field(ge=0, le=1)
    amortization_years: int = Field(default=30, gt=0)
    upfront_mip_pct: float = Field(default=0.0, ge=0, le=1)
    annual_mip_pct: float = Field(default=0.0, ge=0, le=1)
    closing_cost_pct: float = Field(default=0.0, ge=0, le=1)
    max_seller_concession_pct: float = Field(default=0.0, ge=0, le=1)
    rental_income_credit_pct: float = Field(default=0.75, ge=0, le=1)
    max_front_dti: float = Field(default=0.31, gt=0, le=1)
    max_back_dti: float = Field(default=0.43, gt=0, le=1)


class Assumptions(BaseModel):
    """Modeling assumptions. Every field here must be labeled as an assumption in output."""

    vacancy_pct: float = Field(ge=0, le=1)
    management_pct: float = Field(ge=0, le=1)
    repairs_pct: float = Field(ge=0, le=1)
    capex_reserve_per_sqft: float = Field(ge=0)
    rent_growth_pct: float
    expense_growth_pct: float
    exit_cap_rate_spread: float
    hold_years: int = Field(default=5, gt=0)
    disposition_cost_pct: float = Field(default=0.06, ge=0, le=1)


class PropertyInput(BaseModel):
    """Full description of one deal, as loaded from a deal YAML file."""

    deal_name: str
    address: str
    price: float = Field(gt=0)
    county: str
    property_type: str
    units: list[Unit] = Field(min_length=1)
    expense_items: list[ExpenseItem] = Field(default_factory=list)
    financing: FinancingTerms
    assumptions: Assumptions

    # House hack context (ignored by the core engine, used by house_hack.py)
    is_house_hack: bool = False
    owner_occupy_months: int = 12
    seller_concessions_amount: float = Field(default=0.0, ge=0)
    down_payment_assistance_amount: float = Field(default=0.0, ge=0)
    comparable_rent_estimate: Optional[float] = Field(
        default=None, description="Market rent for a comparable apartment, for live-in comparison"
    )
    owner_share_of_expenses: float = Field(
        default=0.0, ge=0, description="Monthly expenses owner pays directly (e.g. shared utilities) not in expense_items"
    )

    # Property standards / FHA appraisal risk inputs
    residential_sqft: Optional[float] = Field(default=None, ge=0)
    total_building_sqft: Optional[float] = Field(default=None, ge=0)
    year_built: Optional[int] = None
    roof_remaining_life_years: Optional[float] = None
    peeling_paint: bool = False
    unsafe_electrical: bool = False
    missing_handrails: bool = False
    no_permanent_heat_source: bool = False
    separate_utilities: Optional[bool] = None

    as_of_date: Optional[date] = Field(default=None, description="Reference date for lease rollover checks; defaults to today")

    @model_validator(mode="after")
    def _check_one_owner_unit_max(self) -> "PropertyInput":
        owner_units = [u for u in self.units if u.is_owner_unit]
        if self.is_house_hack and len(owner_units) != 1:
            raise ValueError("A house hack deal must have exactly one unit marked is_owner_unit=true")
        if owner_units and not self.is_house_hack:
            raise ValueError("A unit is marked is_owner_unit but is_house_hack is false")
        return self

    @property
    def unit_count(self) -> int:
        return len(self.units)

    @property
    def owner_unit(self) -> Optional[Unit]:
        for u in self.units:
            if u.is_owner_unit:
                return u
        return None

    @property
    def non_owner_units(self) -> list[Unit]:
        return [u for u in self.units if not u.is_owner_unit]

    @property
    def building_sqft(self) -> float:
        if self.total_building_sqft is not None:
            return self.total_building_sqft
        return sum(u.sqft for u in self.units)

    @property
    def effective_as_of_date(self) -> date:
        return self.as_of_date or date.today()


def load_deal(path: str | Path) -> PropertyInput:
    """Load and validate one deal YAML file into a PropertyInput."""
    raw = yaml.safe_load(Path(path).read_text())
    return PropertyInput(**raw)
