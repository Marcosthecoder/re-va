"""Default closing checklists. House hack is the default for deal one;
commercial is here for later deals, keeping the engine strategy-agnostic."""
from __future__ import annotations

HOUSE_HACK_CHECKLIST: tuple[str, ...] = (
    "Credit and savings prep (check credit report, pay down cards, avoid new debt/large deposits)",
    "Get FHA pre-approval from 2-3 lenders and compare terms",
    "Check PHFA / Keystone Advantage Assistance eligibility",
    "Find a buyer's agent experienced with 2-4 unit multifamily",
    "Submit an offer, including seller concessions where appropriate",
    "Schedule and attend the home inspection",
    "FHA appraisal (incl. self-sufficiency test for 3-4 units, minimum property standards)",
    "Review existing leases, lease terms, and security deposits held by the seller",
    "Learn PA landlord-tenant basics (notice periods, security deposit rules, habitability)",
    "Check rental license / inspection rules for the specific city (Allentown, Bethlehem, and Easton each have their own)",
    "Clear to close: final walkthrough, closing disclosure review, wire down payment/closing funds",
    "Closing",
    "Move in within 60 days of closing (FHA owner-occupancy requirement)",
    "First 90 days as a landlord: collect rent, set up a system for maintenance requests and bookkeeping",
)

COMMERCIAL_CHECKLIST: tuple[str, ...] = (
    "Letter of Intent (LOI)",
    "Purchase and sale agreement",
    "Environmental Phase I assessment",
    "Zoning verification and use confirmation",
    "Tenant estoppel certificates",
    "Arrange commercial financing / term sheet",
    "Title search and survey",
    "Closing",
)


def checklist_for(checklist_type: str) -> list[str]:
    if checklist_type == "house_hack":
        return list(HOUSE_HACK_CHECKLIST)
    if checklist_type == "commercial":
        return list(COMMERCIAL_CHECKLIST)
    raise ValueError(f"Unknown checklist_type '{checklist_type}'. Must be 'house_hack' or 'commercial'.")
