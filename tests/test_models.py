"""Tests for PropertyInput/Unit validation and derived properties."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.factories import house_hack_duplex, simple_rental
from underwriting.models import Unit, load_deal

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_unit_in_place_rent_owner_unit_is_always_zero():
    owner = Unit(label="Owner", sqft=500, is_owner_unit=True, market_rent=1200, current_rent=999)
    assert owner.in_place_rent == 0.0


def test_unit_in_place_rent_falls_back_to_market_when_vacant():
    vacant = Unit(label="Vacant", sqft=500, market_rent=900)
    assert vacant.in_place_rent == 900


def test_unit_in_place_rent_uses_current_rent_when_set():
    rented = Unit(label="Rented", sqft=500, market_rent=900, current_rent=750)
    assert rented.in_place_rent == 750


def test_house_hack_requires_exactly_one_owner_unit():
    with pytest.raises(ValidationError):
        house_hack_duplex(units=[u.model_copy(update={"is_owner_unit": False}) for u in house_hack_duplex().units])


def test_house_hack_rejects_two_owner_units():
    units = house_hack_duplex().units
    units[1] = units[1].model_copy(update={"is_owner_unit": True})
    with pytest.raises(ValidationError):
        house_hack_duplex(units=units)


def test_non_house_hack_rejects_owner_unit_flag():
    with pytest.raises(ValidationError):
        simple_rental(units=[Unit(label="A", sqft=500, is_owner_unit=True, market_rent=1000)], is_house_hack=False)


def test_building_sqft_sums_units_when_not_overridden():
    deal = house_hack_duplex()
    assert deal.building_sqft == 1600


def test_building_sqft_uses_override_when_set():
    deal = house_hack_duplex(total_building_sqft=5000)
    assert deal.building_sqft == 5000


def test_owner_unit_and_non_owner_units_properties():
    deal = house_hack_duplex()
    assert deal.owner_unit.label == "Owner unit"
    assert [u.label for u in deal.non_owner_units] == ["Rented unit"]


def test_owner_unit_is_none_for_non_house_hack_deal():
    deal = simple_rental()
    assert deal.owner_unit is None


def test_load_deal_from_yaml():
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    assert deal.deal_name == "123 Maple St Duplex"
    assert deal.unit_count == 2
