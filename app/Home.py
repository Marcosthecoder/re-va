import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from app.common import disclaimer_banner, load_profile, money, pct, require_login, session
from db.models import STAGES
from db.repository import list_deals

st.set_page_config(page_title="RE-VA — Pipeline", layout="wide")

s = session()
user = require_login(s)

st.title("RE-VA — Real Estate Virtual Assistant")
disclaimer_banner()

profile = load_profile(s, user)

col1, col2, col3 = st.columns(3)
col1.metric("Cash on hand", money(profile.investor.cash_on_hand))
col2.metric("Search ceiling", money(profile.investor.max_price))
col3.metric("Strategy", profile.investor.strategy.replace("_", " "))

st.divider()
st.subheader("Deal pipeline")

deals = list_deals(s, user.id)
if not deals:
    st.info("No deals yet. Go to **New Deal** in the sidebar to add your first one.")
else:
    stage_filter = st.multiselect("Filter by stage", options=list(STAGES), default=list(STAGES))
    rows = []
    for d in deals:
        if d.stage not in stage_filter:
            continue
        rows.append(
            {
                "id": d.id,
                "Deal": d.deal_name,
                "Stage": d.stage,
                "Verdict": d.verdict_outcome or "not run",
                "Price": d.price,
                "DSCR": d.dscr,
                "Cash-on-cash": d.cash_on_cash,
                "Max offer gap": d.max_offer_gap,
                "Updated": d.updated_at.strftime("%Y-%m-%d") if d.updated_at else "",
            }
        )

    if rows:
        df = pd.DataFrame(rows).set_index("id")
        st.dataframe(
            df,
            width="stretch",
            column_config={
                "Price": st.column_config.NumberColumn(format="$%d"),
                "DSCR": st.column_config.NumberColumn(format="%.2f"),
                "Cash-on-cash": st.column_config.NumberColumn(format="%.1%%"),
                "Max offer gap": st.column_config.NumberColumn(format="$%d"),
            },
        )

        st.caption("Open a deal:")
        options = {f"{d.deal_name} ({d.address})": d.id for d in deals if d.stage in stage_filter}
        if options:
            choice = st.selectbox("Deal", options=list(options), label_visibility="collapsed")
            if st.button("Open Deal Detail", type="primary"):
                st.session_state["selected_deal_id"] = options[choice]
                st.switch_page("pages/2_Deal_Detail.py")
    else:
        st.info("No deals match the selected stage filter.")

st.divider()
if st.button("+ Add a new deal"):
    st.switch_page("pages/1_New_Deal.py")
