"""Tests for the investor profile loader."""
from __future__ import annotations

import pathlib

from underwriting.profile import _unknown_to_none, load_investor_profile

PROFILE = pathlib.Path(__file__).parent.parent / "config" / "investor_profile.yaml"


def test_unknown_to_none_converts_string():
    assert _unknown_to_none("unknown") is None
    assert _unknown_to_none("Unknown") is None


def test_unknown_to_none_passes_through_other_values():
    assert _unknown_to_none(0.5) == 0.5
    assert _unknown_to_none(None) is None


def test_load_real_investor_profile():
    profile = load_investor_profile(PROFILE)
    assert profile.investor.cash_on_hand == 3000
    assert profile.investor.ownership_pct is None  # "unknown" in the YAML
    assert profile.underwriting_thresholds.min_dscr == 1.15
    assert profile.financing.fha_loan_limits_lehigh_2026["one_unit"] == 541287
