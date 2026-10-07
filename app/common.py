"""Shared helpers for every Streamlit page: DB session access, profile
loading/saving, and the disclaimer banner. Each page file inserts the repo
root onto sys.path itself (see the top of Home.py / any pages/*.py) before
importing this module, since Streamlit doesn't put the repo root on
sys.path automatically.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from db.session import get_session, init_db
from underwriting.profile import InvestorProfile, load_investor_profile

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "config" / "investor_profile.yaml"

DISCLAIMER = (
    "Decision support only — not legal, tax, or financial advice. Verify every number with a lender, "
    "attorney, and inspector before buying. RE-VA never contacts anyone or executes a transaction for you."
)


@st.cache_resource
def _ensure_db() -> bool:
    init_db()
    return True


def session():
    """A fresh DB session. Call once per page render."""
    _ensure_db()
    return get_session()


def load_profile() -> InvestorProfile:
    return load_investor_profile(PROFILE_PATH)


def save_profile_updates(updates: dict) -> None:
    """Merge a nested dict of updates into the YAML file and write it back.

    Note: this rewrites the whole file, so hand-written comments in
    investor_profile.yaml are lost on save. The page warns about this.
    """
    raw = yaml.safe_load(PROFILE_PATH.read_text())
    for section, values in updates.items():
        raw.setdefault(section, {})
        raw[section].update(values)
    PROFILE_PATH.write_text(yaml.safe_dump(raw, sort_keys=False))


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


def load_financing_defaults() -> dict:
    """Raw `financing:` section of investor_profile.yaml, used to prefill new-deal
    forms. The InvestorProfile model only captures a narrow slice of this section
    (loan limits, owner_occupy_months) — the rest (rate, MIP, DTI caps, etc.) is a
    per-deal FinancingTerms input, so we read it straight from YAML here instead."""
    raw = yaml.safe_load(PROFILE_PATH.read_text())
    financing = dict(raw.get("financing", {}))
    financing.pop("fha_loan_limits_lehigh_2026", None)
    financing.pop("owner_occupy_months", None)
    return financing


def load_assumptions_defaults() -> dict:
    raw = yaml.safe_load(PROFILE_PATH.read_text())
    return dict(raw.get("assumptions", {}))
