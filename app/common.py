"""Shared helpers for every Streamlit page: DB session access, login/signup,
per-user profile loading/saving, and small formatting utilities. Each page
file inserts the repo root onto sys.path itself (see the top of Home.py /
any pages/*.py) before importing this module, since Streamlit doesn't put
the repo root on sys.path automatically.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session

from auth.profile import load_user_profile, raw_profile_dict, save_user_profile_updates
from auth.users import authenticate, create_user, get_user, invite_code_required, verify_invite_code
from db.models import User
from db.session import get_session, init_db
from underwriting.profile import InvestorProfile

ROOT = Path(__file__).resolve().parent.parent

DISCLAIMER = (
    "Decision support only — not legal, tax, or financial advice. Verify every number with a lender, "
    "attorney, and inspector before buying. RE-VA never contacts anyone or executes a transaction for you."
)


@st.cache_resource
def _ensure_db() -> bool:
    init_db()
    return True


def session():
    """A fresh DB session. Call once per page render, before require_login()."""
    _ensure_db()
    return get_session()


def require_login(s: Session) -> User:
    """Blocks the rest of the page behind a login/signup form.

    Returns the signed-in User (also rendering a "log out" control in the
    sidebar) if already authenticated, or renders the auth form and calls
    st.stop() otherwise — the caller's code after this line never runs for
    a signed-out visitor.
    """
    user_id = st.session_state.get("user_id")
    if user_id is not None:
        user = get_user(s, user_id)
        if user is not None:
            _render_account_sidebar(user)
            return user
        del st.session_state["user_id"]

    st.title("RE-VA — sign in")
    st.caption(DISCLAIMER)
    st.caption(
        "Each account has its own deals, comps, and investor profile — nothing you enter is shared "
        "with other accounts on this app."
    )
    tab_login, tab_signup = st.tabs(["Log in", "Create account"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            user = authenticate(s, username, password)
            if user is None:
                st.error("Incorrect username or password.")
            else:
                st.session_state["user_id"] = user.id
                st.rerun()

    with tab_signup:
        code_needed = invite_code_required()
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username", key="signup_username")
            new_password = st.text_input("Choose a password (8+ characters)", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm password", type="password", key="signup_confirm")
            invite_code = st.text_input("Invite code", key="signup_invite_code") if code_needed else ""
            submitted_signup = st.form_submit_button("Create account", type="primary")
        if submitted_signup:
            if new_password != confirm_password:
                st.error("Passwords don't match.")
            elif code_needed and not verify_invite_code(invite_code):
                st.error("Incorrect invite code.")
            else:
                try:
                    user = create_user(s, new_username, new_password)
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.session_state["user_id"] = user.id
                    st.rerun()

    st.stop()


def _render_account_sidebar(user: User) -> None:
    with st.sidebar:
        st.caption(f"Signed in as **{user.username}**")
        if st.button("Log out"):
            del st.session_state["user_id"]
            st.rerun()


def load_profile(s: Session, user: User) -> InvestorProfile:
    return load_user_profile(s, user)


def save_profile_updates(s: Session, user: User, updates: dict) -> None:
    save_user_profile_updates(s, user, updates)


def load_financing_defaults(user: User) -> dict:
    """Raw `financing:` section of this user's profile, used to prefill new-deal
    forms. The InvestorProfile model only captures a narrow slice of this section
    (loan limits, owner_occupy_months) — the rest (rate, MIP, DTI caps, etc.) is a
    per-deal FinancingTerms input, so we read it from the raw stored dict instead."""
    financing = dict(raw_profile_dict(user).get("financing", {}))
    financing.pop("fha_loan_limits_lehigh_2026", None)
    financing.pop("owner_occupy_months", None)
    return financing


def load_assumptions_defaults(user: User) -> dict:
    return dict(raw_profile_dict(user).get("assumptions", {}))


def disclaimer_banner() -> None:
    st.caption(DISCLAIMER)


def money(x: float | None) -> str:
    if x is None:
        return "n/a"
    if x in (float("inf"), float("-inf")):
        return "n/a"
    return f"${x:,.0f}"


def pct(x: float | None) -> str:
    if x is None or x in (float("inf"), float("-inf")):
        return "n/a"
    return f"{x:.1%}"


def esc(text: str) -> str:
    """Streamlit's markdown renderer treats a pair of '$' as inline LaTeX math,
    which mangles any free text with two or more dollar amounts (e.g. "$398/mo
    vs. minimum $200/mo"). Call this on any dynamic string passed to st.write,
    st.success, st.error, st.warning, st.info, st.caption, or st.markdown.
    Not needed for st.metric, st.table, or st.dataframe — those don't render markdown."""
    return text.replace("$", "\\$")
