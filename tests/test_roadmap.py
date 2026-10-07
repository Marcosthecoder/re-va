"""Tests for roadmap.checklists and roadmap.tracker."""
from __future__ import annotations

import pathlib

import pytest

from db import repository
from roadmap.checklists import COMMERCIAL_CHECKLIST, HOUSE_HACK_CHECKLIST, checklist_for
from roadmap.tracker import create_checklist_for_deal, get_checklist, progress_pct, update_item_status
from underwriting.models import load_deal

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_checklist_for_house_hack_matches_constant():
    assert checklist_for("house_hack") == list(HOUSE_HACK_CHECKLIST)


def test_checklist_for_commercial_matches_constant():
    assert checklist_for("commercial") == list(COMMERCIAL_CHECKLIST)


def test_checklist_for_unknown_type_raises():
    with pytest.raises(ValueError):
        checklist_for("something_else")


def _make_deal_row(db_session):
    deal = load_deal(FIXTURES / "good_duplex.yaml")
    return repository.create_deal(db_session, deal, (FIXTURES / "good_duplex.yaml").read_text())


def test_create_checklist_for_deal_is_idempotent(db_session):
    row = _make_deal_row(db_session)
    first = create_checklist_for_deal(db_session, row.id, "house_hack")
    second = create_checklist_for_deal(db_session, row.id, "house_hack")
    assert len(first) == len(HOUSE_HACK_CHECKLIST)
    assert [i.id for i in first] == [i.id for i in second]  # no duplicate rows created


def test_create_checklist_items_are_ordered(db_session):
    row = _make_deal_row(db_session)
    items = create_checklist_for_deal(db_session, row.id, "house_hack")
    assert [i.order_index for i in items] == list(range(len(items)))
    assert items[0].item_text == HOUSE_HACK_CHECKLIST[0]


def test_get_checklist_filters_by_type(db_session):
    row = _make_deal_row(db_session)
    create_checklist_for_deal(db_session, row.id, "house_hack")
    only_house_hack = get_checklist(db_session, row.id, "house_hack")
    only_commercial = get_checklist(db_session, row.id, "commercial")
    assert len(only_house_hack) == len(HOUSE_HACK_CHECKLIST)
    assert only_commercial == []


def test_update_item_status_sets_completed_date(db_session):
    row = _make_deal_row(db_session)
    items = create_checklist_for_deal(db_session, row.id, "house_hack")
    update_item_status(db_session, items[0], "done", notes="finished")
    assert items[0].status == "done"
    assert items[0].notes == "finished"
    assert items[0].completed_date is not None


def test_update_item_status_clears_completed_date_when_reopened(db_session):
    row = _make_deal_row(db_session)
    items = create_checklist_for_deal(db_session, row.id, "house_hack")
    update_item_status(db_session, items[0], "done")
    assert items[0].completed_date is not None
    update_item_status(db_session, items[0], "in_progress")
    assert items[0].completed_date is None


def test_update_item_status_rejects_unknown_status(db_session):
    row = _make_deal_row(db_session)
    items = create_checklist_for_deal(db_session, row.id, "house_hack")
    with pytest.raises(ValueError):
        update_item_status(db_session, items[0], "done_done")


def test_progress_pct():
    assert progress_pct([]) == 0.0

    row = type("Row", (), {"status": "done"})()
    not_done = type("Row", (), {"status": "not_started"})()
    assert progress_pct([row, not_done]) == 0.5
    assert progress_pct([row, row]) == 1.0
