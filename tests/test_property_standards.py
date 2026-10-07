"""Tests for FHA property standards flags and the mixed-use check."""
from __future__ import annotations

from tests.factories import house_hack_duplex
from underwriting.property_standards import mixed_use_check, property_standards_flags


def test_no_flags_on_clean_property():
    deal = house_hack_duplex(year_built=2000, roof_remaining_life_years=15)
    assert property_standards_flags(deal) == []


def test_lead_paint_flag_requires_both_old_and_peeling():
    old_no_paint_issue = house_hack_duplex(year_built=1960, peeling_paint=False)
    assert not any(f.code == "lead_paint" for f in property_standards_flags(old_no_paint_issue))

    old_with_paint_issue = house_hack_duplex(year_built=1960, peeling_paint=True)
    flags = property_standards_flags(old_with_paint_issue)
    assert any(f.code == "lead_paint" and f.severity == "likely_fail" for f in flags)

    new_with_paint_issue = house_hack_duplex(year_built=2005, peeling_paint=True)
    assert not any(f.code == "lead_paint" for f in property_standards_flags(new_with_paint_issue))


def test_roof_life_flag():
    deal = house_hack_duplex(roof_remaining_life_years=1)
    assert any(f.code == "roof_life" for f in property_standards_flags(deal))
    deal_ok = house_hack_duplex(roof_remaining_life_years=10)
    assert not any(f.code == "roof_life" for f in property_standards_flags(deal_ok))


def test_handrails_electrical_heat_flags():
    deal = house_hack_duplex(missing_handrails=True, unsafe_electrical=True, no_permanent_heat_source=True)
    codes = {f.code for f in property_standards_flags(deal)}
    assert {"handrails", "electrical", "heat_source"} <= codes
    assert all(f.severity == "likely_fail" for f in property_standards_flags(deal))


def test_shared_utilities_is_a_warning_not_a_hard_fail():
    deal = house_hack_duplex(separate_utilities=False)
    flags = property_standards_flags(deal)
    assert any(f.code == "shared_utilities" and f.severity == "warning" for f in flags)


def test_separate_utilities_true_or_unknown_no_flag():
    assert not any(f.code == "shared_utilities" for f in property_standards_flags(house_hack_duplex(separate_utilities=True)))
    assert not any(f.code == "shared_utilities" for f in property_standards_flags(house_hack_duplex(separate_utilities=None)))


def test_mixed_use_not_applicable_for_plain_residential():
    deal = house_hack_duplex(property_type="duplex")
    result = mixed_use_check(deal)
    assert result.applicable is False
    assert result.passed is True


def test_mixed_use_applicable_via_property_type_and_checks_51_pct():
    failing = house_hack_duplex(property_type="mixed_use_residential_majority", residential_sqft=600, total_building_sqft=1600)
    result = mixed_use_check(failing)
    assert result.applicable is True
    assert result.residential_pct == 0.375
    assert result.passed is False

    passing = house_hack_duplex(property_type="mixed_use_residential_majority", residential_sqft=1000, total_building_sqft=1600)
    assert mixed_use_check(passing).passed is True


def test_mixed_use_applicable_via_explicit_residential_sqft_override():
    deal = house_hack_duplex(property_type="duplex", residential_sqft=800, total_building_sqft=1600)
    result = mixed_use_check(deal)
    assert result.applicable is True
    assert result.residential_pct == 0.5
    assert result.passed is False
