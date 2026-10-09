import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app.common import disclaimer_banner, esc, load_profile, money, pct, require_login, session
from db.models import STAGES
from db.repository import get_deal, list_deals, load_property_input, save_verdict, set_notes, set_stage
from llm.client import LLMNotConfigured
from reports.explain import explain_report
from reports.pdf_export import build_pdf
from reports.report_builder import build_report
from reports.sheets_export import SheetsNotConfigured, export_to_sheet, is_configured as sheets_configured
from underwriting.pipeline import analyze_deal
from underwriting.self_employed import self_employed_qualifying_income

st.set_page_config(page_title="RE-VA — Deal Detail", layout="wide")

s = session()
user = require_login(s)

st.title("Deal Detail")
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

profile = load_profile(s, user)
deal = load_property_input(deal_row)
full = analyze_deal(deal, profile)
analysis, v, hh = full.analysis, full.verdict, full.hh_bundle
save_verdict(s, deal_row, analysis.core, v)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

c1, c2 = st.columns([3, 1])
with c1:
    st.subheader(f"{deal.deal_name} — {deal.address}")
    st.caption(esc(f"{deal.county} County | {deal.property_type} | {deal.unit_count} unit(s) | asking {money(deal.price)}"))
with c2:
    new_stage = st.selectbox("Pipeline stage", options=list(STAGES), index=list(STAGES).index(deal_row.stage))
    if new_stage != deal_row.stage:
        set_stage(s, deal_row, new_stage)
        st.rerun()

verdict_box = {"PURSUE": st.success, "NEGOTIATE": st.warning, "PASS": st.error}[v.outcome]
target = f" Target price: {money(v.target_price)}." if v.target_price else ""
verdict_box(esc(f"**{v.outcome}** — {v.summary}{target}"))

notes = st.text_area("Notes", value=deal_row.notes or "", height=80)
if st.button("Save notes"):
    set_notes(s, deal_row, notes)
    st.success("Saved.")

tabs = st.tabs(["Summary", "Rent Roll & Expenses", "Pro Forma & Scenarios", "House Hack", "Verdict Detail", "Report & Export"])

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
with tabs[0]:
    core = analysis.core
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("NOI (market)", money(core.noi_annual))
    m2.metric("Cap rate (market)", pct(core.cap_rate_market))
    m3.metric("DSCR", f"{core.dscr:.2f}")
    m4.metric("Cash-on-cash", pct(core.cash_on_cash_return))
    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Cash flow", f"{money(core.cash_flow_before_tax_monthly)}/mo")
    m6.metric("Cash required", money(core.total_cash_required))
    m7.metric("Breakeven occupancy", pct(core.breakeven_occupancy))
    m8.metric("Max offer (core)", money(analysis.max_offer_price))

    if hh is not None:
        st.markdown("**House hack**")
        h1, h2, h3 = st.columns(3)
        h1.metric("Full monthly payment", money(hh.live_in.full_monthly_payment))
        h2.metric("Net housing cost (live-in)", money(hh.live_in.net_monthly_housing_cost))
        h3.metric("Max offer (house hack)", money(hh.max_offer_price_house_hack))

    if analysis.lease_rollover_flags:
        st.markdown("**Lease rollover risk (next 24 months)**")
        for f in analysis.lease_rollover_flags:
            st.write(esc(f"- {f.unit_label}: expires {f.lease_end} ({f.months_to_expiry} months), {pct(f.income_share_pct)} of market GPR"))

    if hh is not None and hh.standards_flags:
        st.markdown("**Property standards flags**")
        for flag in hh.standards_flags:
            (st.error if flag.severity == "likely_fail" else st.warning)(esc(f"[{flag.severity}] {flag.code}: {flag.description}"))

# ---------------------------------------------------------------------------
# Rent roll & expenses
# ---------------------------------------------------------------------------
with tabs[1]:
    st.markdown("**Rent roll**")
    unit_rows = [
        {"Unit": u.label, "Owner unit": u.is_owner_unit, "Beds": u.bedrooms, "Sqft": u.sqft,
         "Market rent": u.market_rent, "Current rent": u.current_rent, "Tenant": u.tenant_name,
         "Lease end": u.lease_end}
        for u in deal.units
    ]
    st.dataframe(pd.DataFrame(unit_rows), width="stretch")
    rr = core.rent_roll
    st.caption(esc(
        f"GPR market: {money(rr.gross_potential_rent_monthly_market)}/mo | "
        f"GPR in-place: {money(rr.gross_potential_rent_monthly_in_place)}/mo"
    ))

    st.markdown("**Operating expenses (annual, market-based)**")
    expense_rows = [{"Line item": i.name, "Annual": i.annual_amount, "Source": i.source} for i in core.operating_expenses.items]
    st.dataframe(pd.DataFrame(expense_rows), width="stretch")
    st.caption(esc(f"Total: {money(core.operating_expenses.total_annual)}/yr"))

# ---------------------------------------------------------------------------
# Pro forma & scenarios
# ---------------------------------------------------------------------------
with tabs[2]:
    pf = analysis.pro_forma
    st.markdown("**5-year pro forma**")
    pf_rows = [
        {"Year": y.year, "GPR": y.gross_potential_rent, "EGI": y.effective_gross_income, "OpEx": y.operating_expenses,
         "NOI": y.noi, "Cash flow": y.cash_flow_before_tax, "Loan balance": y.loan_balance_end_of_year}
        for y in pf.years
    ]
    st.dataframe(pd.DataFrame(pf_rows), width="stretch")
    st.line_chart(pd.DataFrame(pf_rows).set_index("Year")[["NOI", "Cash flow"]])

    e1, e2, e3 = st.columns(3)
    e1.metric("Exit value", money(pf.exit.exit_value))
    e2.metric("Net sale proceeds", money(pf.exit.net_sale_proceeds))
    e3.metric("IRR", pct(pf.irr))
    st.caption(f"Equity multiple: {pf.equity_multiple:.2f}x | Exit cap rate: {pct(pf.exit.exit_cap_rate)}")

    st.markdown("**Scenarios**")
    scenario_rows = [
        {"Scenario": name, "NOI": sc.core.noi_annual, "Cash flow/mo": sc.core.cash_flow_before_tax_monthly,
         "Cash-on-cash": sc.core.cash_on_cash_return, "IRR": sc.pro_forma.irr}
        for name, sc in analysis.scenarios.items()
    ]
    st.dataframe(pd.DataFrame(scenario_rows), width="stretch")

# ---------------------------------------------------------------------------
# House hack
# ---------------------------------------------------------------------------
with tabs[3]:
    if hh is None:
        st.info("Not a house hack deal.")
    else:
        st.markdown("**Cash to close**")
        cc = hh.cash_close
        st.table(pd.DataFrame([
            {"Item": "Down payment", "Amount": money(cc.down_payment)},
            {"Item": "Closing costs", "Amount": money(cc.closing_costs)},
            {"Item": "Seller concessions", "Amount": f"-{money(cc.seller_concessions)}"},
            {"Item": "Down payment assistance", "Amount": f"-{money(cc.down_payment_assistance)}"},
            {"Item": "TOTAL REQUIRED", "Amount": money(cc.total_cash_required)},
            {"Item": "Cash on hand", "Amount": money(cc.cash_on_hand)},
            {"Item": "Gap (covered if <= 0)", "Amount": money(cc.cash_gap)},
        ]).set_index("Item"))

        st.markdown("**Live-in phase net housing cost**")
        li = hh.live_in
        st.table(pd.DataFrame([
            {"Item": "Full monthly payment", "Amount": money(li.full_monthly_payment)},
            {"Item": "Owner's share of expenses", "Amount": money(li.owner_share_of_expenses)},
            {"Item": "Other units' rent", "Amount": money(li.other_units_rent_monthly)},
            {"Item": "Less vacancy + repairs", "Amount": f"-{money(li.vacancy_and_repair_adjustment)}"},
            {"Item": "Net rent credited", "Amount": money(li.net_rent_from_others)},
            {"Item": "NET MONTHLY HOUSING COST", "Amount": money(li.net_monthly_housing_cost)},
        ]).set_index("Item"))
        if li.comparable_rent_estimate is not None:
            st.caption(esc(f"Comparable apartment rent: {money(li.comparable_rent_estimate)} | "
                       f"Monthly savings vs. renting: {money(li.monthly_savings_vs_comparable)}"))

        st.markdown("**Lender qualification (DTI)**")
        dti = hh.dti
        st.write(esc(f"Effective monthly income: {money(dti.effective_monthly_income)}"))
        st.write(f"Front DTI: {pct(dti.front_dti)} (max {pct(dti.max_front_dti)}) -> {'PASS' if dti.front_pass else 'FAIL'}")
        st.write(f"Back DTI: {pct(dti.back_dti)} (max {pct(dti.max_back_dti)}) -> {'PASS' if dti.back_pass else 'FAIL'}")

        st.markdown("**FHA self-sufficiency test (3-4 unit)**")
        ss = hh.self_sufficiency
        if ss.applicable:
            st.write(esc(f"75% of total market rent: {money(ss.seventy_five_pct_of_rent)}/mo vs. full payment {money(ss.full_monthly_payment)}/mo "
                     f"-> {'PASS' if ss.passed else 'FAIL'} (gap {money(ss.gap)})"))
        else:
            st.write(f"Not applicable ({deal.unit_count} units).")

        st.markdown("**FHA loan limit**")
        ll = hh.loan_limit
        if ll.status == "unknown_verify_hud":
            st.write(esc(f"Loan amount {money(ll.loan_amount)} — county limit not set in profile. **Verify on HUD lookup.**"))
        else:
            st.write(esc(f"Loan amount {money(ll.loan_amount)} vs. limit {money(ll.limit)} -> {ll.status.upper()}"))

        st.markdown("**Self-employed qualifying income**")
        if profile.investor.ownership_pct is None or profile.investor.ownership_pct >= 0.25:
            se = self_employed_qualifying_income(
                ownership_pct=profile.investor.ownership_pct,
                years_of_tax_returns=profile.investor.years_of_tax_returns_with_this_income,
                yearly_net_incomes=[],
            )
            if se.calculable:
                st.write(esc(f"Qualifying monthly income: {money(se.qualifying_monthly_income)}"))
            else:
                st.write(f"Not yet calculable — {se.years_available} of {se.years_required} required years of returns on file.")
                st.write(f"Projected mortgage-ready date: {se.mortgage_ready_date} ({se.months_until_ready} months away)")
            for n in se.notes:
                st.caption(esc(n))
        else:
            st.caption("Ownership below 25% — self-employed income rules may not apply; confirm with a lender.")

# ---------------------------------------------------------------------------
# Verdict detail
# ---------------------------------------------------------------------------
with tabs[4]:
    for r in v.rules:
        (st.success if r.passed else st.error)(esc(f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}"))

# ---------------------------------------------------------------------------
# Report & export
# ---------------------------------------------------------------------------
with tabs[5]:
    report = build_report(deal, analysis, v, hh)
    st.markdown("**Top risks**")
    for r in report.risks:
        st.write(esc(f"- {r}"))
    st.markdown("**Top strengths**")
    for strength in report.strengths:
        st.write(esc(f"- {strength}"))
    st.markdown("**Questions to ask the broker/seller**")
    for q in report.questions:
        st.write(esc(f"- {q}"))

    explanation = None
    if st.button("Generate plain-English explanation (uses Claude)"):
        try:
            explanation = explain_report(report, session=s, deal_id=deal_row.id)
            st.session_state[f"explanation_{deal_row.id}"] = explanation
        except LLMNotConfigured as e:
            st.warning(str(e))
    explanation = st.session_state.get(f"explanation_{deal_row.id}", explanation)
    if explanation:
        st.markdown("**In plain English**")
        st.write(esc(explanation))

    pdf_bytes = build_pdf(report, explanation=explanation)
    st.download_button("Download one-page PDF report", data=pdf_bytes, file_name=f"{deal.deal_name.replace(' ', '_')}_report.pdf", mime="application/pdf")

    if sheets_configured():
        if st.button("Export to Google Sheets"):
            try:
                url = export_to_sheet(report)
                st.success(f"Exported: {url}")
            except SheetsNotConfigured as e:
                st.warning(str(e))
    else:
        st.caption("Google Sheets export isn't configured — set GOOGLE_SHEETS_CREDENTIALS_PATH in .env to enable it.")
