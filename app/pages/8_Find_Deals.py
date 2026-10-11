import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.common import disclaimer_banner, esc, money, require_login, session
from sourcing.hud_feed import HudFeedError, HudReoListing, fetch_hud_reo, filter_lehigh_valley
from sourcing.rentcast import (
    MULTI_FAMILY_2_4_UNIT,
    RentCastError,
    RentCastListing,
    is_configured as rentcast_configured,
    search_sale_listings,
)

st.set_page_config(page_title="RE-VA — Find Deals", layout="wide")

s = session()
user = require_login(s)

st.title("Find Deals")
disclaimer_banner()
st.caption(
    "Both sources below are free. Neither replaces your own search — they're a starting lead list. "
    "Always verify price, unit count, and current status before you rely on anything here."
)


def _hud_prefill(listing: HudReoListing) -> dict:
    return {
        "deal_name": f"HUD REO — {listing.address}",
        "address": f"{listing.address}, {listing.city}, {listing.state} {listing.zip_code or ''}".strip(),
        "county": listing.county_guess or "Other",
    }


def _rentcast_prefill(listing: RentCastListing) -> dict:
    return {
        "deal_name": listing.formatted_address or "RentCast listing",
        "address": listing.formatted_address or "",
        "price": listing.price or 0,
        "county": listing.county if listing.county in ("Lehigh", "Northampton") else "Other",
    }


def _use_as_new_deal(prefill: dict, key: str) -> None:
    if st.button("Use as New Deal", key=key):
        st.session_state["prefill"] = prefill
        st.switch_page("pages/1_New_Deal.py")


tab_hud, tab_rentcast = st.tabs(["HUD-owned foreclosures (free)", "Active listings — RentCast (free tier)"])

with tab_hud:
    st.write(
        "Pulls from HUD's own public open-data feed of properties HUD currently owns (unsold REO/foreclosures) "
        "— not from hudhomestore.gov directly, since that site blocks automated access. "
        "This feed has **no price, unit count, or bid-deadline field** — click through to each listing's "
        "HUD Home Store page to check those before doing anything with it."
    )
    show_all_pa = st.checkbox("Show all of PA (default: Lehigh Valley cities only)", value=False)
    if st.button("Search HUD inventory"):
        try:
            with st.spinner("Querying HUD's property feed..."):
                listings = fetch_hud_reo(state_code="PA")
        except HudFeedError as e:
            st.error(esc(str(e)))
            listings = []
        if not show_all_pa:
            listings = filter_lehigh_valley(listings)
        st.session_state["hud_results"] = listings
        if not listings:
            st.info(
                "No matching HUD-owned properties right now. This dataset is small nationally (a few hundred "
                "at any time) and Lehigh Valley inventory is often empty — try 'Show all of PA' or check back later."
            )

    for listing in st.session_state.get("hud_results", []):
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.write(f"**{listing.address}**")
                st.caption(f"{listing.city}, {listing.state} {listing.zip_code or ''} · county: {listing.county_guess or 'unknown'}")
            with c2:
                st.caption(f"Case #{listing.case_num}")
                if listing.date_acquired:
                    st.caption(f"HUD-acquired {listing.date_acquired.isoformat()}")
                st.link_button("Check price/status on HUD Home Store", listing.hudhomestore_url)
            with c3:
                _use_as_new_deal(_hud_prefill(listing), key=f"hud_use_{listing.case_num}")

with tab_rentcast:
    if not rentcast_configured():
        st.info(
            "Not set up yet. RentCast's free Developer plan gives 50 requests/month, no credit card:\n\n"
            "1. Create an account and generate a key at https://app.rentcast.io/app/api\n"
            "2. Add `RENTCAST_API_KEY=your-key` to your `.env` file (or this app's deployed Secrets)\n"
            "3. Reload this page."
        )
    else:
        with st.form("rentcast_search"):
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                city = st.text_input("City", value="Allentown")
            with rc2:
                property_type = st.selectbox(
                    "Property type", [MULTI_FAMILY_2_4_UNIT, "Single Family", "Condo", "Townhouse"], index=0
                )
            with rc3:
                max_price = st.number_input("Max price ($, 0 = no limit)", min_value=0.0, value=500000.0, step=10000.0)
            submitted = st.form_submit_button("Search RentCast", type="primary")

        if submitted:
            try:
                with st.spinner("Querying RentCast..."):
                    listings = search_sale_listings(
                        city=city or None,
                        state="PA",
                        property_type=property_type,
                        max_price=max_price or None,
                    )
            except RentCastError as e:
                st.error(esc(str(e)))
                listings = []
            st.session_state["rentcast_results"] = listings
            if not listings:
                st.info("No active listings matched that search.")

        for listing in st.session_state.get("rentcast_results", []):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1:
                    st.write(f"**{listing.formatted_address or 'Unknown address'}**")
                    st.caption(f"{listing.property_type or '?'} · {listing.bedrooms or '?'} bd / {listing.bathrooms or '?'} ba · {listing.square_footage or '?'} sqft")
                with c2:
                    st.write(money(listing.price))
                    st.caption(f"{listing.days_on_market or '?'} days on market · {listing.status or '?'}")
                    if listing.mls_number:
                        st.caption(esc(f"MLS #{listing.mls_number} ({listing.mls_name or ''})"))
                with c3:
                    _use_as_new_deal(_rentcast_prefill(listing), key=f"rentcast_use_{listing.id}")
