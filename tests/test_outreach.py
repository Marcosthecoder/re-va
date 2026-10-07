"""Tests for outreach.drafts: template content and DB persistence."""
from __future__ import annotations

import pathlib

import pytest

from db import repository
from outreach.drafts import (
    DRAFT_BUILDERS,
    draft_broker_email,
    draft_lender_email,
    draft_seller_financing_email,
    list_drafts,
    save_draft,
)
from underwriting.models import load_deal

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _deal():
    return load_deal(FIXTURES / "good_duplex.yaml")


def test_draft_broker_email_includes_address_and_price():
    subject, body = draft_broker_email(_deal())
    assert "123 Maple St, Allentown, PA" in subject
    assert "$165,000" in body
    assert "rent roll" in body.lower()


def test_draft_broker_email_includes_custom_questions():
    subject, body = draft_broker_email(_deal(), questions=["Is the roof under warranty?"])
    assert "Is the roof under warranty?" in body


def test_draft_lender_email_includes_unit_count_and_down_payment():
    subject, body = draft_lender_email(_deal(), down_payment_pct=0.035)
    assert "2-unit" in subject
    assert "3.5%" in body


def test_draft_seller_financing_email_asks_about_concessions():
    subject, body = draft_seller_financing_email(_deal())
    assert "seller financing" in body.lower()
    assert "concessions" in body.lower()


def test_draft_builders_registry_matches_functions():
    assert set(DRAFT_BUILDERS) == {"broker", "lender", "seller"}
    assert DRAFT_BUILDERS["broker"] is draft_broker_email


def test_save_and_list_drafts(db_session):
    deal = _deal()
    row = repository.create_deal(db_session, deal, (FIXTURES / "good_duplex.yaml").read_text())
    subject, body = draft_broker_email(deal)
    saved = save_draft(db_session, row.id, "broker", subject, body)
    assert saved.id is not None

    drafts = list_drafts(db_session, row.id)
    assert len(drafts) == 1
    assert drafts[0].subject == subject


def test_save_draft_rejects_unknown_type(db_session):
    deal = _deal()
    row = repository.create_deal(db_session, deal, (FIXTURES / "good_duplex.yaml").read_text())
    with pytest.raises(ValueError):
        save_draft(db_session, row.id, "carrier_pigeon", "subj", "body")
