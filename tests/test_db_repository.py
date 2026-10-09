"""Tests for db.repository CRUD helpers, against an isolated in-memory DB."""
from __future__ import annotations

import pathlib

import pytest

from auth.users import create_user
from db import repository
from underwriting.models import load_deal
from underwriting.pipeline import analyze_deal
from underwriting.profile import load_investor_profile

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PROFILE = pathlib.Path(__file__).parent.parent / "config" / "investor_profile.yaml"


def _yaml_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_create_deal_round_trips_through_yaml(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    assert row.id is not None
    assert row.user_id == user.id
    assert row.deal_name == "123 Maple St Duplex"
    assert row.stage == "New"

    reloaded = repository.load_property_input(row)
    assert reloaded.price == deal.price
    assert reloaded.unit_count == deal.unit_count


def test_save_verdict_updates_summary_fields(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)

    repository.save_verdict(db_session, row, full.analysis.core, full.verdict)
    assert row.verdict_outcome == full.verdict.outcome
    assert row.verdict_target_price == pytest.approx(full.verdict.target_price)
    assert row.dscr == pytest.approx(full.analysis.core.dscr)


def test_save_verdict_handles_infinite_cash_on_cash(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")  # has cash_on_cash == inf
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    profile = load_investor_profile(PROFILE)
    full = analyze_deal(deal, profile)
    assert full.analysis.core.cash_on_cash_return == float("inf")

    repository.save_verdict(db_session, row, full.analysis.core, full.verdict)
    assert row.cash_on_cash is None  # stored as None rather than a literal inf


def test_list_deals_filters_by_stage(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    assert repository.list_deals(db_session, user.id, stage="New") == [row]
    assert repository.list_deals(db_session, user.id, stage="Closed") == []


def test_list_deals_does_not_include_other_users_deals(db_session, user):
    other = create_user(db_session, "otheruser", "otherpassword123")
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=other.id)
    assert repository.list_deals(db_session, user.id) == []
    assert len(repository.list_deals(db_session, other.id)) == 1


def test_get_deal_returns_none_for_wrong_user(db_session, user):
    other = create_user(db_session, "otheruser", "otherpassword123")
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=other.id)
    assert repository.get_deal(db_session, row.id, user.id) is None
    assert repository.get_deal(db_session, row.id, other.id) is row


def test_get_deal_returns_none_for_nonexistent_id(db_session, user):
    assert repository.get_deal(db_session, 999999, user.id) is None


def test_set_stage_validates_and_updates(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    repository.set_stage(db_session, row, "Negotiating")
    assert row.stage == "Negotiating"
    with pytest.raises(ValueError):
        repository.set_stage(db_session, row, "NotAStage")


def test_set_notes_and_get_deal(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    repository.set_notes(db_session, row, "Called the broker.")
    fetched = repository.get_deal(db_session, row.id, user.id)
    assert fetched.notes == "Called the broker."


def test_delete_deal_removes_it(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    deal_id = row.id
    repository.delete_deal(db_session, row)
    assert repository.get_deal(db_session, deal_id, user.id) is None


def test_save_deal_yaml_updates_core_fields(db_session, user):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    row = repository.create_deal(db_session, deal, _yaml_text("good_duplex.yaml"), user_id=user.id)
    edited = deal.model_copy(update={"price": 170_000, "deal_name": "Renamed Deal"})
    repository.save_deal_yaml(db_session, row, edited, _yaml_text("good_duplex.yaml"))
    assert row.price == 170_000
    assert row.deal_name == "Renamed Deal"
