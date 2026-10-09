import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.common import disclaimer_banner, require_login, session
from db.models import CHECKLIST_STATUSES
from db.repository import get_deal, list_deals
from roadmap.tracker import create_checklist_for_deal, get_checklist, progress_pct, update_item_status

st.set_page_config(page_title="RE-VA — Roadmap", layout="wide")

s = session()
user = require_login(s)

st.title("Closing Roadmap")
disclaimer_banner()

deals = list_deals(s, user.id)
if not deals:
    st.info("No deals yet. Go to **New Deal** to add one.")
    st.stop()

options = {f"{d.deal_name} ({d.address})": d.id for d in deals}
default_id = st.session_state.get("selected_deal_id", deals[0].id)
default_label = next((label for label, i in options.items() if i == default_id), list(options)[0])
choice = st.selectbox("Deal", options=list(options), index=list(options).index(default_label))
deal_row = get_deal(s, options[choice], user.id)
st.session_state["selected_deal_id"] = deal_row.id

checklist_type = "house_hack" if deal_row.is_house_hack else "commercial"
items = create_checklist_for_deal(s, deal_row.id, checklist_type)

progress = progress_pct(items)
st.progress(progress, text=f"{int(progress * 100)}% complete ({checklist_type.replace('_', ' ')} checklist)")

for item in items:
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.write(item.item_text)
            note = st.text_input("Notes", value=item.notes or "", key=f"note_{item.id}", label_visibility="collapsed",
                                  placeholder="Notes...")
        with c2:
            status = st.selectbox("Status", CHECKLIST_STATUSES, index=CHECKLIST_STATUSES.index(item.status), key=f"status_{item.id}")
            if item.completed_date:
                st.caption(f"Done {item.completed_date}")
        if status != item.status or note != (item.notes or ""):
            update_item_status(s, item, status, notes=note)
            st.rerun()
