"""Tests for auth.users (accounts) and auth.profile (per-user investor profile)."""
from __future__ import annotations

import pytest

from auth.profile import load_user_profile, raw_profile_dict, save_user_profile_updates
from auth.users import authenticate, create_user, get_user, hash_password, verify_password


def test_hash_password_is_not_plaintext_and_verifies():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong password", h) is False


def test_verify_password_handles_garbage_hash_gracefully():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_create_user_round_trip(db_session):
    user = create_user(db_session, "alice", "password123")
    assert user.id is not None
    assert user.username == "alice"
    assert user.password_hash != "password123"


def test_create_user_rejects_duplicate_username(db_session):
    create_user(db_session, "alice", "password123")
    with pytest.raises(ValueError, match="already taken"):
        create_user(db_session, "alice", "anotherpassword")


def test_create_user_rejects_short_password(db_session):
    with pytest.raises(ValueError, match="at least"):
        create_user(db_session, "bob", "short")


def test_create_user_rejects_bad_username(db_session):
    with pytest.raises(ValueError, match="Username"):
        create_user(db_session, "a", "password123")
    with pytest.raises(ValueError, match="Username"):
        create_user(db_session, "has a space", "password123")


def test_authenticate_success_and_failure(db_session):
    create_user(db_session, "alice", "password123")
    assert authenticate(db_session, "alice", "password123") is not None
    assert authenticate(db_session, "alice", "wrongpassword") is None
    assert authenticate(db_session, "nobody", "password123") is None


def test_get_user(db_session):
    user = create_user(db_session, "alice", "password123")
    assert get_user(db_session, user.id).username == "alice"
    assert get_user(db_session, 999999) is None


def test_load_user_profile_seeds_and_persists_on_first_use(db_session):
    user = create_user(db_session, "alice", "password123")
    assert user.profile_json is None

    profile = load_user_profile(db_session, user)
    assert profile.investor.cash_on_hand == 0
    assert profile.investor.ownership_pct is None  # seeded as "unknown" -> None
    assert user.profile_json is not None  # persisted after first load

    # Second load reads the persisted JSON rather than re-seeding.
    profile_again = load_user_profile(db_session, user)
    assert profile_again.investor.cash_on_hand == 0


def test_save_user_profile_updates_merges_and_validates(db_session):
    user = create_user(db_session, "alice", "password123")
    load_user_profile(db_session, user)  # seed first

    updated = save_user_profile_updates(
        db_session, user, {"investor": {"cash_on_hand": 5000, "max_price": 300000}}
    )
    assert updated.investor.cash_on_hand == 5000
    assert updated.investor.max_price == 300000

    reloaded = load_user_profile(db_session, user)
    assert reloaded.investor.cash_on_hand == 5000


def test_save_user_profile_updates_rejects_invalid_values(db_session):
    user = create_user(db_session, "alice", "password123")
    load_user_profile(db_session, user)
    with pytest.raises(Exception):  # pydantic ValidationError
        save_user_profile_updates(db_session, user, {"investor": {"credit_score": "not-a-number!!"}})


def test_raw_profile_dict_includes_financing_and_assumptions_sections(db_session):
    user = create_user(db_session, "alice", "password123")
    load_user_profile(db_session, user)
    raw = raw_profile_dict(user)
    assert "financing" in raw
    assert "assumptions" in raw
    assert "fha_loan_limits_lehigh_2026" in raw["financing"]


def test_two_users_have_independent_profiles(db_session):
    alice = create_user(db_session, "alice", "password123")
    bob = create_user(db_session, "bob", "password123")

    save_user_profile_updates(db_session, alice, {"investor": {"cash_on_hand": 1000}})
    save_user_profile_updates(db_session, bob, {"investor": {"cash_on_hand": 99999}})

    assert load_user_profile(db_session, alice).investor.cash_on_hand == 1000
    assert load_user_profile(db_session, bob).investor.cash_on_hand == 99999
