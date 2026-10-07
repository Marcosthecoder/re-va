"""Lehigh and Northampton County property tax helpers.

No live public API is integrated here — PA county tax/parcel search tools
aren't consistently API-accessible, and guessing at an endpoint would risk
silently returning wrong numbers. This is a manual-entry workflow instead:
look the parcel up on the county's own assessment/tax search site, then
enter the number yourself with source="county_record" on the deal.
"""
from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_COUNTIES = ("Lehigh", "Northampton")


@dataclass
class TaxLookupGuidance:
    county: str
    status: str
    guidance: str
    reassessment_note: str


def lookup_property_tax(county: str, address: str | None = None) -> TaxLookupGuidance:
    """Always returns manual-entry guidance — there is no automated lookup.

    Search the county's own property/parcel search tool directly (e.g. search
    "<county name> PA property tax search" or "<county name> PA parcel viewer")
    for the current annual tax on the specific parcel, then add it to the deal
    as an expense_item with source="county_record".
    """
    county_label = county if county in SUPPORTED_COUNTIES else f"{county} (not Lehigh/Northampton — verify locally)"
    return TaxLookupGuidance(
        county=county_label,
        status="manual_entry_required",
        guidance=(
            f"No automated tax lookup is built for {county_label}. Search the county's own official "
            "property/parcel search tool for the current annual tax bill on this parcel"
            + (f" ({address})" if address else "")
            + ", then enter it as an expense_item with source=\"county_record\"."
        ),
        reassessment_note=reassessment_note(county),
    )


def reassessment_note(county: str) -> str:
    return (
        f"Sale price can trigger a reassessment in {county} County — the current owner's tax bill "
        "may understate what you'll actually owe after closing. Ask the broker/seller whether a "
        "reassessment has historically followed a sale here, and budget for the higher figure if unsure."
    )


def estimate_annual_tax_from_millage(assessed_value: float, millage_rate_mills: float) -> float:
    """Estimate annual tax from an assessed value and a combined millage rate.

    1 mill = $1 of tax per $1,000 of assessed value. ``millage_rate_mills`` should
    be the combined county + municipal + school district rate, entered manually
    from the county's published rate — never guessed.
    """
    if assessed_value < 0 or millage_rate_mills < 0:
        raise ValueError("assessed_value and millage_rate_mills must be non-negative")
    return assessed_value * millage_rate_mills / 1000
