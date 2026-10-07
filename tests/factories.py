"""Small builders for hand-checkable PropertyInput fixtures used across tests."""
from __future__ import annotations

from underwriting.models import Assumptions, ExpenseItem, FinancingTerms, PropertyInput, Unit


def simple_rental(**overrides) -> PropertyInput:
    """One rented unit, round numbers chosen so every intermediate value is
    easy to hand-check: price $100,000, rent $1,000/mo, 20% down, 6%/30yr,
    no MIP (not FHA), 10% vacancy, 5%/5% management/repairs, $0.10/sqft capex.
    """
    base = dict(
        deal_name="Simple Rental",
        address="1 Test St",
        price=100_000,
        county="Lehigh",
        property_type="single_family",
        units=[Unit(label="Unit 1", sqft=1000, market_rent=1000, current_rent=1000)],
        expense_items=[],
        financing=FinancingTerms(
            method="conventional",
            down_payment_pct=0.20,
            interest_rate=0.06,
            amortization_years=30,
            upfront_mip_pct=0.0,
            annual_mip_pct=0.0,
            closing_cost_pct=0.02,
            max_seller_concession_pct=0.0,
        ),
        assumptions=Assumptions(
            vacancy_pct=0.10,
            management_pct=0.05,
            repairs_pct=0.05,
            capex_reserve_per_sqft=0.10,
            rent_growth_pct=0.02,
            expense_growth_pct=0.02,
            exit_cap_rate_spread=0.005,
            hold_years=1,
            disposition_cost_pct=0.0,
        ),
    )
    base.update(overrides)
    return PropertyInput(**base)


def house_hack_duplex(**overrides) -> PropertyInput:
    """2-unit owner-occupied FHA deal with round numbers for house_hack.py tests."""
    base = dict(
        deal_name="Test Duplex",
        address="2 Test Ave",
        price=200_000,
        county="Lehigh",
        property_type="duplex",
        units=[
            Unit(label="Owner unit", sqft=800, is_owner_unit=True, market_rent=1000),
            Unit(label="Rented unit", sqft=800, market_rent=1000, current_rent=1000),
        ],
        expense_items=[
            ExpenseItem(name="property_tax", annual_amount=2400, source="county_record"),
            ExpenseItem(name="insurance", annual_amount=1200, source="seller_provided"),
        ],
        financing=FinancingTerms(
            method="fha",
            down_payment_pct=0.035,
            interest_rate=0.06,
            amortization_years=30,
            upfront_mip_pct=0.0175,
            annual_mip_pct=0.0055,
            closing_cost_pct=0.03,
            max_seller_concession_pct=0.06,
            rental_income_credit_pct=0.75,
            max_front_dti=0.31,
            max_back_dti=0.43,
        ),
        assumptions=Assumptions(
            vacancy_pct=0.10,
            management_pct=0.08,
            repairs_pct=0.07,
            capex_reserve_per_sqft=0.25,
            rent_growth_pct=0.02,
            expense_growth_pct=0.03,
            exit_cap_rate_spread=0.005,
            hold_years=5,
            disposition_cost_pct=0.06,
        ),
        is_house_hack=True,
        owner_occupy_months=12,
    )
    base.update(overrides)
    return PropertyInput(**base)
