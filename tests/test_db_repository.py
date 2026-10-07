"""Tests for db.repository CRUD helpers, against an isolated in-memory DB."""
from __future__ import annotations

import pathlib

import pytest

from db import repository
from underwriting.models import load_deal
from underwriting.pipeline import analyze_deal
from underwriting.profile import load_investor_profile

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PROFILE = pathlib.Path(__file__).parent.parent / "config" / "investor_profile.yaml"


def _yaml_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_create_deal_round_trips_through_yaml(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    assert row.id is not None
    assert row.deal_name == "123 Maple St Duplex"
    assert row.stage == "New"

    reloaded = repository.load_property_input(row)
    assert reloaded.price == deal.price
    assert reloaded.unit_count == deal.unit_count


def test_save_verdict_updates_summary_fields(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)

    repository.save_verdict(db_session, row, full.analysis.core, full.verdict)
    assert row.verdict_outcome == full.verdict.outcome
    assert row.verdict_target_price == pytest.approx(full.verdict.target_price)
    assert row.dscr == pytest.approx(full.analysis.core.dscr)


def test_save_verdict_handles_infinite_cash_on_cash(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")  # has cash_on_cash == inf
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    assert full.analysis.core.cash_on_cash_return == float("inf")

    repository.save_verdict(db_session, row, full.analysis.core, full.verdict)
    assert row.cash_on_cash is None  # stored as None rather than a literal inf


def test_list_deals_filters_by_stage(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    assert repository.list_deals(db_session, stage="New") == [row]
    assert repository.list_deals(db_session, stage="Closed") == []


def test_set_stage_validates_and_updates(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    repository.set_stage(db_session, row, "Negotiating")
    assert row.stage == "Negotiating"
    with pytest.raises(ValueError):
        repository.set_stage(db_session, row, "NotAStage")


def test_set_notes_and_get_deal(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    repository.set_notes(db_session, row, "Called the broker.")
    fetched = repository.get_deal(db_session, row.id)
    assert fetched.notes == "Called the broker."


def test_delete_deal_removes_it(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    deal_id = row.id
    repository.delete_deal(db_session, row)
    assert repository.get_deal(db_session, deal_id) is None


def test_save_deal_yaml_updates_core_fields(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"))
    edited = deal.model_copy(update={"price": 170_000, "deal_name": "Renamed Deal"})
    repository.save_deal_yaml(db_session, row, edited, _yaml_text("good_duplex.yaml"))
    assert row.price == 170_000
    assert row.deal_name == "Renamed Deal"
