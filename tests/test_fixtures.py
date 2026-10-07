"""Integration tests for the 3 required sample house hack deals end-to-end:
load YAML -> pipeline.analyze_deal -> verdict. Mirrors exactly what the CLI
does (both go through underwriting.pipeline.analyze_deal now), so these
numbers were also eyeballed via `python -m cli.run_deal`.
"""
from __future__ import annotations

import pathlib

import pytest

from underwriting.models import load_deal
from underwriting.pipeline import analyze_deal
from underwriting.profile import load_investor_profile

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PROFILE = pathlib.Path(__file__).parent.parent / "config" / "investor_profile.yaml"


def _run(deal_file: str):
    deal = load_deal(FIXTURES / deal_file)
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    return deal, full


def test_good_duplex_pursues():
    deal, full = _run("good_duplex.yaml")
    v = full.verdict
    assert v.outcome == "PURSUE"
    assert v.target_price == pytest.approx(deal.price)
    assert all(r.passed for r in v.rules)


def test_marginal_triplex_negotiates():
    deal, full = _run("marginal_triplex.yaml")
    v = full.verdict
    assert v.outcome == "NEGOTIATE"
    assert v.target_price < deal.price
    assert full.hh_bundle.self_sufficiency.applicable is True
    assert full.hh_bundle.self_sufficiency.passed is True  # narrowly passes
    failed_names = {r.name for r in v.failed_rules}
    assert "DSCR" in failed_names
    assert "Breakeven occupancy" in failed_names


def test_bad_fourplex_fails_self_sufficiency_and_passes_on_the_deal():
    deal, full = _run("bad_fourplex.yaml")
    v = full.verdict
    assert full.hh_bundle.self_sufficiency.applicable is True
    assert full.hh_bundle.self_sufficiency.passed is False
    assert full.hh_bundle.self_sufficiency.gap > 0
    assert v.outcome == "PASS"
    assert v.target_price is None
    assert any(f.severity == "likely_fail" for f in full.hh_bundle.standards_flags)


def test_non_house_hack_deal_uses_core_verdict_path():
    from tests.factories import simple_rental
    from underwriting.engine import Thresholds
    from underwriting.pipeline import analyze_deal as _analyze

    deal = simple_rental()
    profile = load_investor_profile(PROFILE)
    full = _analyze(deal, profile)
    assert full.hh_bundle is None
    assert full.verdict.outcome in ("PURSUE", "NEGOTIATE", "PASS")
