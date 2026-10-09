import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import math

import pandas as pd
import streamlit as st
import yaml
from pydantic import ValidationError

from app.common import disclaimer_banner, load_assumptions_defaults, load_financing_defaults, require_login, session
from db.repository import create_deal
from intake.extractor import extract_from_pdf, extract_from_text, parse_rent_roll_csv, parse_rent_roll_xlsx
from intake.schemas import IntakeResult
from llm.client import LLMNotConfigured
from roadmap.tracker import create_checklist_for_deal
from underwriting.models import PropertyInput

st.set_page_config(page_title="RE-VA — New Deal", layout="wide")

s = session()
user = require_login(s)

st.title("New Deal")
disclaimer_banner()

DEFAULT_UNITS = pd.DataFrame(
    [
        {"label": "Unit A", "bedrooms": 2, "sqft": 800.0, "is_owner_unit": True, "market_rent": 1000.0,
         "current_rent": None, "tenant_name": "", "lease_start": None, "lease_end": None, "lease_type": None},
        {"label": "Unit B", "bedrooms": 2, "sqft": 800.0, "is_owner_unit": False, "market_rent": 1000.0,
         "current_rent": 1000.0, "tenant_name": "", "lease_start": None, "lease_end": None, "lease_type": "gross"},
    ]
)
DEFAULT_EXPENSES = pd.DataFrame(
    [
        {"name": "property_tax", "annual_amount": 0.0, "source": "county_record"},
        {"name": "insurance", "annual_amount": 0.0, "source": "seller_provided"},
    ]
)

st.session_state.setdefault("units_df", DEFAULT_UNITS)
st.session_state.setdefault("expenses_df", DEFAULT_EXPENSES)
st.session_state.setdefault("import_version", 0)
st.session_state.setdefault("prefill", {})


# ---------------------------------------------------------------------------
# Intake helpers
# ---------------------------------------------------------------------------

with st.expander("Import from a listing (paste text / PDF) or a rent roll (CSV / XLSX)", expanded=False):
    tab_text, tab_file = st.tabs(["Paste listing text / PDF", "Upload rent roll CSV / XLSX"])

    with tab_text:
        pasted = st.text_area("Paste listing text here", height=150)
        pdf_file = st.file_uploader("...or upload a listing/offering memo PDF", type=["pdf"], key="pdf_uploader")
        if st.button("Extract with Claude"):
            try:
                if pdf_file is not None:
                    result: IntakeResult = extract_from_pdf(pdf_file.read())
                elif pasted.strip():
                    result = extract_from_text(pasted)
                else:
                    st.warning("Paste some text or upload a PDF first.")
                    result = None
            except LLMNotConfigured as e:
                st.warning(str(e))
                result = None
            except ValueError as e:
                st.error(f"Extraction failed: {e}")
                result = None

            if result is not None:
                d = result.deal_dict
                st.session_state["prefill"] = d
                if d.get("units"):
                    st.session_state["units_df"] = pd.DataFrame(d["units"])
                if d.get("expense_items"):
                    st.session_state["expenses_df"] = pd.DataFrame(d["expense_items"])
                st.session_state["import_version"] += 1
                st.success("Extracted. Review every field below before creating the deal — nothing is saved yet.")
                if result.confidence:
                    st.write("Confidence per field:")
                    st.json(result.confidence)
                if result.unresolved_notes:
                    st.write("Things to double-check:")
                    for n in result.unresolved_notes:
                        st.write(f"- {n}")
                st.rerun()

    with tab_file:
        roll_file = st.file_uploader("Rent roll file", type=["csv", "xlsx"], key="roll_uploader")
        if roll_file is not None and st.button("Parse rent roll"):
            if roll_file.name.lower().endswith(".csv"):
                rows = parse_rent_roll_csv(roll_file.read())
            else:
                rows = parse_rent_roll_xlsx(roll_file.read())
            if rows:
                st.session_state["units_df"] = pd.DataFrame(rows)
                st.session_state["import_version"] += 1
                st.success(f"Parsed {len(rows)} unit row(s). Review below.")
                st.rerun()
            else:
                st.warning("Couldn't find any recognizable columns in that file.")

prefill = st.session_state["prefill"]

# ---------------------------------------------------------------------------
# Scalar fields
# ---------------------------------------------------------------------------

st.subheader("Deal basics")
c1, c2 = st.columns(2)
with c1:
    deal_name = st.text_input("Deal name", value=prefill.get("deal_name", ""))
    address = st.text_input("Address", value=prefill.get("address", ""))
    price = st.number_input("Price ($)", min_value=0.0, value=float(prefill.get("price", 0) or 0), step=1000.0)
    county = st.selectbox("County", ["Lehigh", "Northampton", "Other"],
                           index=["Lehigh", "Northampton", "Other"].index(prefill["county"]) if prefill.get("county") in ("Lehigh", "Northampton") else 0)
    property_type = st.selectbox(
        "Property type",
        ["duplex", "triplex", "fourplex", "mixed_use_residential_majority", "single_family", "other"],
        index=0,
    )
    is_house_hack = st.checkbox("This is a house hack (I'll live in one unit)", value=True)
    owner_occupy_months = st.number_input("Owner-occupy months (FHA requirement)", min_value=0, value=12)
with c2:
    year_built = st.number_input("Year built (0 = unknown)", min_value=0, value=int(prefill.get("year_built", 0) or 0))
    comparable_rent_estimate = st.number_input("Comparable apartment rent nearby ($/mo, 0 = unknown)", min_value=0.0,
                                                value=float(prefill.get("comparable_rent_estimate", 0) or 0))
    seller_concessions_amount = st.number_input("Seller concessions you expect ($)", min_value=0.0, value=0.0)
    down_payment_assistance_amount = st.number_input("Down payment assistance (PHFA/Keystone, $)", min_value=0.0, value=0.0)
    owner_share_of_expenses = st.number_input("Your monthly share of shared expenses ($)", min_value=0.0, value=0.0)

with st.expander("Property condition (for FHA appraisal risk flags) and mixed-use check"):
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        peeling_paint = st.checkbox("Peeling/chipping paint")
        unsafe_electrical = st.checkbox("Unsafe/exposed electrical")
    with cc2:
        missing_handrails = st.checkbox("Missing handrails")
        no_permanent_heat_source = st.checkbox("No permanent heat source")
    with cc3:
        separate_utilities_choice = st.selectbox("Utilities separately metered?", ["Unknown", "Yes", "No"])
    rc1, rc2 = st.columns(2)
    with rc1:
        residential_sqft = st.number_input("Residential sqft (mixed-use only, 0 = n/a)", min_value=0.0, value=0.0)
    with rc2:
        total_building_sqft_override = st.number_input("Total building sqft override (0 = sum of unit sqft)", min_value=0.0, value=0.0)

st.subheader("Units")
st.caption("Edit, add, or delete rows. The owner's unit (house hack) must have exactly one 'is_owner_unit' checked.")
units_editor_key = f"units_editor_{st.session_state['import_version']}"
units_df = st.data_editor(
    st.session_state["units_df"],
    num_rows="dynamic",
    key=units_editor_key,
    column_config={
        "is_owner_unit": st.column_config.CheckboxColumn("Owner unit?"),
        "bedrooms": st.column_config.NumberColumn(min_value=0),
        "sqft": st.column_config.NumberColumn(min_value=0),
        "market_rent": st.column_config.NumberColumn(min_value=0),
        "current_rent": st.column_config.NumberColumn(min_value=0),
        "lease_start": st.column_config.DateColumn(),
        "lease_end": st.column_config.DateColumn(),
        "lease_type": st.column_config.SelectboxColumn(options=["gross", "NNN", "modified_gross"]),
    },
    width="stretch",
)

st.subheader("Operating expenses")
st.caption("Include 'property_tax' and 'insurance' line items if this is a house hack — the payment calc needs them by name.")
expenses_editor_key = f"expenses_editor_{st.session_state['import_version']}"
expenses_df = st.data_editor(
    st.session_state["expenses_df"],
    num_rows="dynamic",
    key=expenses_editor_key,
    column_config={
        "annual_amount": st.column_config.NumberColumn(min_value=0),
        "source": st.column_config.SelectboxColumn(options=["seller_provided", "county_record", "assumption"]),
    },
    width="stretch",
)

with st.expander("Financing and assumptions (prefilled from your investor profile — edit per deal if needed)"):
    fin_defaults = load_financing_defaults(user)
    assum_defaults = load_assumptions_defaults(user)
    f1, f2, f3 = st.columns(3)
    with f1:
        down_payment_pct = st.number_input("Down payment %", value=float(fin_defaults.get("down_payment_pct", 0.035)), format="%.4f")
        interest_rate = st.number_input("Interest rate", value=float(fin_defaults.get("interest_rate", 0.065)), format="%.4f")
        amortization_years = st.number_input("Amortization years", value=30, min_value=1)
    with f2:
        upfront_mip_pct = st.number_input("Upfront MIP %", value=float(fin_defaults.get("upfront_mip_pct", 0.0175)), format="%.4f")
        annual_mip_pct = st.number_input("Annual MIP %", value=float(fin_defaults.get("annual_mip_pct", 0.0055)), format="%.4f")
        closing_cost_pct = st.number_input("Closing cost %", value=float(fin_defaults.get("closing_cost_pct", 0.03)), format="%.4f")
    with f3:
        max_seller_concession_pct = st.number_input("Max seller concession %", value=float(fin_defaults.get("max_seller_concession_pct", 0.06)), format="%.4f")
        rental_income_credit_pct = st.number_input("Rental income credit %", value=float(fin_defaults.get("rental_income_credit_pct", 0.75)), format="%.4f")

    a1, a2, a3 = st.columns(3)
    with a1:
        vacancy_pct = st.number_input("Vacancy %", value=float(assum_defaults.get("vacancy_pct", 0.10)), format="%.4f")
        management_pct = st.number_input("Management %", value=float(assum_defaults.get("management_pct", 0.08)), format="%.4f")
    with a2:
        repairs_pct = st.number_input("Repairs %", value=float(assum_defaults.get("repairs_pct", 0.07)), format="%.4f")
        capex_reserve_per_sqft = st.number_input("Capex reserve $/sqft", value=float(assum_defaults.get("capex_reserve_per_sqft", 0.25)), format="%.4f")
    with a3:
        rent_growth_pct = st.number_input("Rent growth %/yr", value=float(assum_defaults.get("rent_growth_pct", 0.02)), format="%.4f")
        expense_growth_pct = st.number_input("Expense growth %/yr", value=float(assum_defaults.get("expense_growth_pct", 0.03)), format="%.4f")
    hold_years = st.number_input("Hold period (years)", value=int(assum_defaults.get("hold_years", 5)), min_value=1)


def _clean_units(df: pd.DataFrame) -> list[dict]:
    units = []
    for _, row in df.iterrows():
        if not str(row.get("label", "")).strip():
            continue
        unit = {
            "label": str(row["label"]),
            "bedrooms": float(row.get("bedrooms") or 0),
            "sqft": float(row.get("sqft") or 0),
            "is_owner_unit": bool(row.get("is_owner_unit", False)),
            "market_rent": float(row.get("market_rent") or 0),
        }
        for optional_field in ("current_rent", "tenant_name", "lease_start", "lease_end", "lease_type"):
            val = row.get(optional_field)
            if val is None or (isinstance(val, float) and math.isnan(val)) or val == "":
                continue
            unit[optional_field] = str(val) if optional_field in ("tenant_name", "lease_type") else val
        units.append(unit)
    return units


def _clean_expenses(df: pd.DataFrame) -> list[dict]:
    items = []
    for _, row in df.iterrows():
        if not str(row.get("name", "")).strip():
            continue
        items.append({
            "name": str(row["name"]),
            "annual_amount": float(row.get("annual_amount") or 0),
            "source": row.get("source") or "assumption",
        })
    return items


st.divider()
if st.button("Create Deal", type="primary"):
    deal_dict = {
        "deal_name": deal_name,
        "address": address,
        "price": price,
        "county": county,
        "property_type": property_type,
        "units": _clean_units(units_df),
        "expense_items": _clean_expenses(expenses_df),
        "financing": {
            "down_payment_pct": down_payment_pct, "interest_rate": interest_rate,
            "amortization_years": int(amortization_years), "upfront_mip_pct": upfront_mip_pct,
            "annual_mip_pct": annual_mip_pct, "closing_cost_pct": closing_cost_pct,
            "max_seller_concession_pct": max_seller_concession_pct, "rental_income_credit_pct": rental_income_credit_pct,
        },
        "assumptions": {
            "vacancy_pct": vacancy_pct, "management_pct": management_pct, "repairs_pct": repairs_pct,
            "capex_reserve_per_sqft": capex_reserve_per_sqft, "rent_growth_pct": rent_growth_pct,
            "expense_growth_pct": expense_growth_pct, "exit_cap_rate_spread": 0.005, "hold_years": int(hold_years),
        },
        "is_house_hack": is_house_hack,
        "owner_occupy_months": int(owner_occupy_months),
        "seller_concessions_amount": seller_concessions_amount,
        "down_payment_assistance_amount": down_payment_assistance_amount,
        "owner_share_of_expenses": owner_share_of_expenses,
        "peeling_paint": peeling_paint,
        "unsafe_electrical": unsafe_electrical,
        "missing_handrails": missing_handrails,
        "no_permanent_heat_source": no_permanent_heat_source,
        "separate_utilities": {"Unknown": None, "Yes": True, "No": False}[separate_utilities_choice],
    }
    if year_built:
        deal_dict["year_built"] = int(year_built)
    if comparable_rent_estimate:
        deal_dict["comparable_rent_estimate"] = comparable_rent_estimate
    if residential_sqft:
        deal_dict["residential_sqft"] = residential_sqft
    if total_building_sqft_override:
        deal_dict["total_building_sqft"] = total_building_sqft_override

    try:
        property_input = PropertyInput(**deal_dict)
    except ValidationError as e:
        st.error("Fix these before creating the deal:")
        for err in e.errors():
            st.write(f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}")
    else:
        yaml_content = yaml.safe_dump(property_input.model_dump(mode="json", exclude_none=True), sort_keys=False)
        row = create_deal(s, property_input, yaml_content, user_id=user.id)
        if row.is_house_hack:
            create_checklist_for_deal(s, row.id, "house_hack")
        else:
            create_checklist_for_deal(s, row.id, "commercial")
        st.success(f"Created '{row.deal_name}'.")
        st.session_state["selected_deal_id"] = row.id
        st.session_state["prefill"] = {}
        if st.button("Go to Deal Detail"):
            st.switch_page("pages/2_Deal_Detail.py")
