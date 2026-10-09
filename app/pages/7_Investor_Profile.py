import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.common import disclaimer_banner, load_profile, require_login, save_profile_updates, session
from auth.profile import raw_profile_dict

st.set_page_config(page_title="RE-VA — Investor Profile", layout="wide")

s = session()
user = require_login(s)

st.title("Investor Profile")
disclaimer_banner()
st.caption(
    "These are your investor-level settings and underwriting thresholds, used by every deal in your account. "
    "Nothing here is visible to other accounts."
)

profile = load_profile(s, user)
raw = raw_profile_dict(user)

st.subheader("Investor")
c1, c2 = st.columns(2)
with c1:
    cash_on_hand = st.number_input("Cash on hand ($)", min_value=0.0, value=float(profile.investor.cash_on_hand))
    target_price = st.number_input("Target price ($)", min_value=0.0, value=float(profile.investor.target_price))
    max_price = st.number_input("Max price / search ceiling ($)", min_value=0.0, value=float(profile.investor.max_price))
    monthly_gross_income = st.number_input("Monthly gross income ($)", min_value=0.0, value=float(profile.investor.monthly_gross_income))
    monthly_debt_payments = st.number_input("Monthly debt payments ($)", min_value=0.0, value=float(profile.investor.monthly_debt_payments))
with c2:
    credit_score = st.number_input("Credit score", min_value=300, max_value=850, value=int(profile.investor.credit_score))
    ownership_known = st.checkbox("Ownership percentage is documented", value=profile.investor.ownership_pct is not None)
    ownership_pct = st.number_input("Ownership %", min_value=0.0, max_value=1.0,
                                     value=float(profile.investor.ownership_pct or 0.0), format="%.2f",
                                     disabled=not ownership_known)
    years_of_returns = st.number_input("Years of tax returns with this income", min_value=0,
                                        value=int(profile.investor.years_of_tax_returns_with_this_income))
    co_borrower = st.text_input("Possible co-borrower", value=profile.investor.possible_co_borrower or "none")

st.subheader("Underwriting thresholds")
t1, t2, t3 = st.columns(3)
with t1:
    max_owner_net_housing_cost = st.number_input("Max owner net housing cost ($/mo)", min_value=0.0,
                                                   value=float(profile.underwriting_thresholds.max_owner_net_housing_cost))
    min_move_out_cash_flow = st.number_input("Min move-out cash flow ($/mo)", value=float(profile.underwriting_thresholds.min_move_out_cash_flow))
with t2:
    min_move_out_cash_on_cash = st.number_input("Min cash-on-cash", value=float(profile.underwriting_thresholds.min_move_out_cash_on_cash), format="%.3f")
    min_dscr = st.number_input("Min DSCR", value=float(profile.underwriting_thresholds.min_dscr), format="%.3f")
with t3:
    max_breakeven_occupancy = st.number_input("Max breakeven occupancy", value=float(profile.underwriting_thresholds.max_breakeven_occupancy), format="%.3f")

st.subheader("FHA loan limits (Lehigh Valley) — leave 0 for 'unknown, verify on HUD'")
loan_limits_raw = raw.get("financing", {}).get("fha_loan_limits_lehigh_2026", {}) or {}
l1, l2, l3, l4 = st.columns(4)
with l1:
    one_unit = st.number_input("1 unit", min_value=0.0, value=float(loan_limits_raw.get("one_unit") or 0))
with l2:
    two_unit = st.number_input("2 unit", min_value=0.0, value=float(loan_limits_raw.get("two_unit") or 0))
with l3:
    three_unit = st.number_input("3 unit", min_value=0.0, value=float(loan_limits_raw.get("three_unit") or 0))
with l4:
    four_unit = st.number_input("4 unit", min_value=0.0, value=float(loan_limits_raw.get("four_unit") or 0))

if st.button("Save", type="primary"):
    updates = {
        "investor": {
            "cash_on_hand": cash_on_hand, "target_price": target_price, "max_price": max_price,
            "monthly_gross_income": monthly_gross_income, "monthly_debt_payments": monthly_debt_payments,
            "credit_score": int(credit_score), "ownership_pct": ownership_pct if ownership_known else "unknown",
            "years_of_tax_returns_with_this_income": int(years_of_returns), "possible_co_borrower": co_borrower,
        },
        "underwriting_thresholds": {
            "max_owner_net_housing_cost": max_owner_net_housing_cost, "min_move_out_cash_flow": min_move_out_cash_flow,
            "min_move_out_cash_on_cash": min_move_out_cash_on_cash, "min_dscr": min_dscr,
            "max_breakeven_occupancy": max_breakeven_occupancy,
        },
        "financing": {
            "fha_loan_limits_lehigh_2026": {
                "one_unit": one_unit or None, "two_unit": two_unit or None,
                "three_unit": three_unit or None, "four_unit": four_unit or None,
            },
        },
    }
    save_profile_updates(s, user, updates)
    st.success("Saved.")
    st.rerun()
