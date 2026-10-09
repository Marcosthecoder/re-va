"""Per-user investor profile, stored as JSON on the User row instead of a
shared YAML file — each signed-in user edits their own cash on hand, income,
and thresholds without touching anyone else's.

New accounts are seeded from config/investor_profile.yaml's structure (same
shape, generic starting numbers) so the schema stays identical to the
single-user CLI/file-based path in underwriting.profile.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from db.models import User
from underwriting.profile import InvestorProfile, investor_profile_from_dict

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "investor_profile.yaml"


def _seed_raw_profile() -> dict:
    """A fresh, generic starting profile for a brand-new account: same structure as
    config/investor_profile.yaml, but with placeholder investor-specific numbers
    zeroed out rather than copying the repo owner's actual financial details."""
    raw = yaml.safe_load(DEFAULT_PROFILE_PATH.read_text())
    raw["investor"].update(
        {
            "name": "",
            "cash_on_hand": 0,
            "target_price": 0,
            "max_price": 0,
            "monthly_gross_income": 0,
            "monthly_debt_payments": 0,
            "credit_score": 620,
            "ownership_pct": "unknown",
            "years_of_tax_returns_with_this_income": 0,
            "possible_co_borrower": "none",
        }
    )
    return raw


def _load_raw(user: User) -> dict:
    if user.profile_json:
        return json.loads(user.profile_json)
    return _seed_raw_profile()


def load_user_profile(session: Session, user: User) -> InvestorProfile:
    """Loads this user's profile, seeding and persisting a fresh one on first use."""
    if not user.profile_json:
        raw = _seed_raw_profile()
        user.profile_json = json.dumps(raw)
        session.commit()
    else:
        raw = json.loads(user.profile_json)
    return investor_profile_from_dict(raw)


def raw_profile_dict(user: User) -> dict:
    """The full raw dict (incl. financing/assumptions sections not modeled by
    InvestorProfile), for prefilling the New Deal form."""
    return _load_raw(user)


def save_user_profile_updates(session: Session, user: User, updates: dict) -> InvestorProfile:
    """Merges a nested dict of updates (e.g. {"investor": {...}, "underwriting_thresholds": {...}})
    into this user's stored profile and validates the result before saving."""
    raw = _load_raw(user)
    for section, values in updates.items():
        raw.setdefault(section, {})
        raw[section].update(values)
    profile = investor_profile_from_dict(raw)  # raises if invalid; don't save a broken profile
    user.profile_json = json.dumps(raw)
    session.commit()
    return profile
