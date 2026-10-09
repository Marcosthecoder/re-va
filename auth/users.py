"""Username/password accounts for the hosted, multi-user deployment.

Each account gets its own deals, rent comps, and investor profile — nothing
here is shared between users. Passwords are hashed with bcrypt; this module
never stores or logs a plaintext password. There's no email verification or
password reset flow — it's intentionally minimal for a small personal tool,
not a general-purpose auth system.
"""
from __future__ import annotations

import os
import re

import bcrypt
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User

load_dotenv()

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,30}$")
MIN_PASSWORD_LENGTH = 8


def invite_code_required() -> bool:
    """True once SIGNUP_INVITE_CODE is set in the environment. Signup stays
    open (no code needed) until you set one — e.g. for local dev, or before
    you've decided to lock a hosted deployment down."""
    return bool(os.environ.get("SIGNUP_INVITE_CODE"))


def verify_invite_code(code: str) -> bool:
    """Always True if no SIGNUP_INVITE_CODE is configured; otherwise an exact match."""
    expected = os.environ.get("SIGNUP_INVITE_CODE")
    if not expected:
        return True
    return code == expected


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _validate_credentials(username: str, password: str) -> None:
    if not USERNAME_PATTERN.match(username):
        raise ValueError("Username must be 3-30 characters: letters, numbers, underscore, or dash only.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def create_user(session: Session, username: str, password: str) -> User:
    """Creates a new account. Raises ValueError if the username is invalid or already taken."""
    _validate_credentials(username, password)
    existing = session.scalar(select(User).where(User.username == username))
    if existing is not None:
        raise ValueError(f"Username '{username}' is already taken.")
    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    """Returns the User if the username/password match, else None."""
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)
