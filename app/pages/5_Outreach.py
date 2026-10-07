import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.common import disclaimer_banner, load_profile, session
from db.repository import get_deal, list_deals, load_property_input
from llm.client import LLMNotConfigured
from outreach.drafts import DRAFT_BUILDERS, list_drafts, polish_draft, save_draft
from reports.report_builder import build_report
from underwriting.pipeline import analyze_deal

st.set_page_config(page_title="RE-VA — Outreach", layout="wide")
st.title("Outreach Drafts")
disclaimer_banner()
st.caption("Drafts only. Nothing here is ever sent automatically — copy into your own email client and review before sending.")

s = session()
deals = list_deals(s)
if not deals:
    st.info("No deals yet. Go to **New Deal** to add one.")
    st.stop()

options = {f"{d.deal_name} ({d.address})": d.id for d in deals}
default_id = st.session_state.get("selected_deal_id", deals[0].id)
default_label = next((label for label, i in options.items() if i == default_id), list(options)[0])
choice = st.selectbox("Deal", options=list(options), index=list(options).index(default_label))
deal_row = get_deal(s, options[choice])
st.session_state["selected_deal_id"] = deal_row.id

deal = load_property_input(deal_row)
profile = load_profile()

draft_type = st.selectbox("Draft type", list(DRAFT_BUILDERS))

if st.button("Generate draft"):
    builder = DRAFT_BUILDERS[draft_type]
    if draft_type == "broker":
        full = analyze_deal(deal, profile)
        report = build_report(deal, full.analysis, full.verdict, full.hh_bundle)
        subject, body = builder(deal, report.questions)
    elif draft_type == "lender":
        subject, body = builder(deal, profile.investor.ownership_pct and 0.035 or deal.financing.down_payment_pct)
    else:
        subject, body = builder(deal)
    st.session_state["draft_subject"] = subject
    st.session_state["draft_body"] = body

subject = st.text_input("Subject", value=st.session_state.get("draft_subject", ""))
body = st.text_area("Body", value=st.session_state.get("draft_body", ""), height=220)

c1, c2 = st.columns(2)
with c1:
    if st.button("Polish with Claude") and body:
        try:
            polished = polish_draft(subject, body, session=s, deal_id=deal_row.id)
            st.session_state["draft_body"] = polished
            st.rerun()
        except LLMNotConfigured as e:
            st.warning(str(e))
with c2:
    if st.button("Save draft", type="primary") and body:
        save_draft(s, deal_row.id, draft_type, subject, body)
        st.success("Saved.")

st.divider()
st.subheader("Saved drafts for this deal")
saved = list_drafts(s, deal_row.id)
if not saved:
    st.caption("None yet.")
for d in saved:
    with st.expander(f"[{d.draft_type}] {d.subject} — {d.created_at.strftime('%Y-%m-%d %H:%M')}"):
        st.text(d.body)
