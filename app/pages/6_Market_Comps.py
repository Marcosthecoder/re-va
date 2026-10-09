import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.common import disclaimer_banner, money, require_login, session
from db.repository import get_deal, list_deals, load_property_input
from market.comps import add_comp, compare_to_comps, delete_comp, list_comps
from market.tax_lookup import SUPPORTED_COUNTIES, lookup_property_tax

st.set_page_config(page_title="RE-VA — Market", layout="wide")

s = session()
user = require_login(s)

st.title("Market Data")
disclaimer_banner()

tab_comps, tab_tax, tab_compare = st.tabs(["Rent comps", "Property tax lookup", "Compare a deal to comps"])

with tab_comps:
    st.subheader("Add a comp")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        county = st.selectbox("County", list(SUPPORTED_COUNTIES) + ["Other"], key="comp_county")
        municipality = st.text_input("Municipality", key="comp_municipality")
    with c2:
        bedrooms = st.number_input("Bedrooms", min_value=0.0, value=2.0, key="comp_beds")
        sqft = st.number_input("Sqft (0 = unknown)", min_value=0.0, value=0.0, key="comp_sqft")
    with c3:
        rent = st.number_input("Monthly rent", min_value=0.0, value=1000.0, key="comp_rent")
        source = st.text_input("Source (e.g. Zillow listing, Facebook group)", key="comp_source")
    with c4:
        notes = st.text_area("Notes", key="comp_notes", height=80)
    if st.button("Add comp"):
        add_comp(s, user.id, county, rent, bedrooms=bedrooms or None, sqft=sqft or None, municipality=municipality or None,
                  source=source or "manual", notes=notes or None)
        st.success("Added.")
        st.rerun()

    st.subheader("Stored comps")
    comps = list_comps(s, user.id)
    if not comps:
        st.caption("None yet.")
    else:
        for c in comps:
            cols = st.columns([5, 1])
            cols[0].write(f"{c.county} / {c.municipality or '-'} | {c.bedrooms or '?'}BR | {money(c.rent)}/mo | source: {c.source}")
            if cols[1].button("Delete", key=f"del_{c.id}"):
                delete_comp(s, c, user.id)
                st.rerun()

with tab_tax:
    st.caption("No automated county tax API is wired up — this always returns a manual-entry pointer, "
               "never a guessed number.")
    county = st.selectbox("County", list(SUPPORTED_COUNTIES) + ["Other"], key="tax_county")
    address = st.text_input("Address (optional)", key="tax_address")
    if st.button("Get guidance"):
        g = lookup_property_tax(county, address or None)
        st.info(g.guidance)
        st.warning(g.reassessment_note)

with tab_compare:
    deals = list_deals(s, user.id)
    if not deals:
        st.info("No deals yet.")
    else:
        options = {f"{d.deal_name} ({d.address})": d.id for d in deals}
        choice = st.selectbox("Deal", options=list(options))
        deal_row = get_deal(s, options[choice], user.id)
        deal = load_property_input(deal_row)
        comps = list_comps(s, user.id, county=deal.county)
        if not comps:
            st.warning(f"No comps stored for {deal.county} County yet — add some in the 'Rent comps' tab.")
        rows = []
        for u in deal.units:
            unit_comps = [c for c in comps if c.bedrooms is None or c.bedrooms == u.bedrooms]
            comparison = compare_to_comps(u.market_rent, unit_comps)
            rows.append({
                "Unit": u.label, "Market rent": u.market_rent, "Avg comp rent": comparison.average_comp_rent,
                "Comp count": comparison.comp_count, "Flag": comparison.flag,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch")
        st.caption("Flagged 'over_market'/'under_market' when a unit's rent is more than 15% off the comp average.")
