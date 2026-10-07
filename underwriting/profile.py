"""Loader for config/investor_profile.yaml.

Keeps investor-level facts (cash on hand, income, thresholds, FHA loan limits)
separate from deal-level facts (price, rent roll, financing terms), which live
in each deal YAML as a PropertyInput.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from underwriting.engine import Thresholds


def _unknown_to_none(value):
    if isinstance(value, str) and value.strip().lower() == "unknown":
        return None
    return value


class InvestorSection(BaseModel):
    name: str
    market: str
    strategy: str
    target_price: float
    max_price: float
    cash_on_hand: float
    timeline_months: Optional[int] = None
    monthly_gross_income: float
    monthly_debt_payments: float = 0.0
    credit_score: int
    ownership_pct: Optional[float] = None
    years_of_tax_returns_with_this_income: int = 0
    possible_co_borrower: Optional[str] = None


class ThresholdsSection(BaseModel):
    max_owner_net_housing_cost: float
    min_move_out_cash_flow: float
    min_move_out_cash_on_cash: float
    min_dscr: float
    max_breakeven_occupancy: float

    def to_engine_thresholds(self) -> Thresholds:
        return Thresholds(
            min_dscr=self.min_dscr,
            min_cash_on_cash=self.min_move_out_cash_on_cash,
            min_monthly_cash_flow=self.min_move_out_cash_flow,
            max_breakeven_occupancy=self.max_breakeven_occupancy,
        )


class FinancingSection(BaseModel):
    owner_occupy_months: int = 12
    fha_loan_limits_lehigh_2026: dict = Field(default_factory=dict)


class InvestorProfile(BaseModel):
    investor: InvestorSection
    financing: FinancingSection
    underwriting_thresholds: ThresholdsSection


def load_investor_profile(path: str | Path) -> InvestorProfile:
    """Load and validate the investor profile YAML, normalizing "unknown" strings to None."""
    raw = yaml.safe_load(Path(path).read_text())
    raw["investor"]["ownership_pct"] = _unknown_to_none(raw["investor"].get("ownership_pct"))
    return InvestorProfile(**raw)
