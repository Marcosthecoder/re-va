"""Tests for market.comps and market.tax_lookup."""
from __future__ import annotations

import pytest

from market.comps import add_comp, compare_to_comps, delete_comp, list_comps
from market.tax_lookup import estimate_annual_tax_from_millage, lookup_property_tax, reassessment_note


def test_compare_to_comps_no_comps_returns_flag():
    result = compare_to_comps(1200, [])
    assert result.flag == "no_comps"
    assert result.average_comp_rent is None


def test_compare_to_comps_in_line():
    class Comp:
        def __init__(self, rent):
            self.rent = rent

    comps = [Comp(1000), Comp(1050), Comp(950)]
    result = compare_to_comps(1000, comps)  # avg = 1000, exactly in line
    assert result.flag == "in_line"
    assert result.average_comp_rent == 1000


def test_compare_to_comps_over_market():
    class Comp:
        def __init__(self, rent):
            self.rent = rent

    comps = [Comp(1000), Comp(1000)]
    result = compare_to_comps(1200, comps)  # 20% over avg of 1000
    assert result.flag == "over_market"
    assert result.pct_difference == pytest.approx(0.20)


def test_compare_to_comps_under_market():
    class Comp:
        def __init__(self, rent):
            self.rent = rent

    comps = [Comp(1000), Comp(1000)]
    result = compare_to_comps(800, comps)  # 20% under avg of 1000
    assert result.flag == "under_market"


def test_add_list_delete_comp_round_trip(db_session, user):
    comp = add_comp(db_session, user.id, "Lehigh", 1100, bedrooms=2, sqft=800, municipality="Allentown", source="test")
    assert comp.id is not None
    comps = list_comps(db_session, user.id, county="Lehigh")
    assert comp in comps

    delete_comp(db_session, comp, user.id)
    assert list_comps(db_session, user.id, county="Lehigh") == []


def test_list_comps_filters_by_bedrooms(db_session, user):
    add_comp(db_session, user.id, "Lehigh", 1000, bedrooms=1)
    add_comp(db_session, user.id, "Lehigh", 1500, bedrooms=3)
    two_br = list_comps(db_session, user.id, county="Lehigh", bedrooms=1)
    assert len(two_br) == 1
    assert two_br[0].rent == 1000


def test_list_comps_does_not_include_other_users_comps(db_session, user):
    from auth.users import create_user

    other = create_user(db_session, "otheruser", "otherpassword123")
    add_comp(db_session, other.id, "Lehigh", 1000)
    assert list_comps(db_session, user.id, county="Lehigh") == []


def test_delete_comp_rejects_wrong_owner(db_session, user):
    from auth.users import create_user

    other = create_user(db_session, "otheruser", "otherpassword123")
    comp = add_comp(db_session, other.id, "Lehigh", 1000)
    with pytest.raises(PermissionError):
        delete_comp(db_session, comp, user.id)


def test_lookup_property_tax_is_always_manual_entry():
    result = lookup_property_tax("Lehigh", "123 Main St")
    assert result.status == "manual_entry_required"
    assert "123 Main St" in result.guidance
    assert "county_record" in result.guidance


def test_lookup_property_tax_flags_unsupported_county():
    result = lookup_property_tax("Westmoreland")
    assert "verify locally" in result.county


def test_reassessment_note_mentions_county():
    assert "Lehigh" in reassessment_note("Lehigh")


def test_estimate_annual_tax_from_millage():
    # 1 mill = $1 per $1000 assessed value
    assert estimate_annual_tax_from_millage(200_000, 25) == 5000.0


def test_estimate_annual_tax_from_millage_rejects_negative():
    with pytest.raises(ValueError):
        estimate_annual_tax_from_millage(-1, 25)
