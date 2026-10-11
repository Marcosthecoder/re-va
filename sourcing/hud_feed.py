"""Free, public HUD-owned REO (foreclosure) property leads for Lehigh Valley house hunting.

Pulls from HUD's own open-data ArcGIS feed ("FHA Single Family REO Properties
For Sale"), not from hudhomestore.gov directly — hudhomestore.gov's
robots.txt disallows all automated access, so this module never requests
anything from that site. It only *constructs* a link to each property's
hudhomestore.gov page so you can check the asking price, unit count, and bid
window yourself before entering it as a deal.

The ArcGIS feed has no price, unit count, or listing-status field — just
address, case number, county-ish geocodes, and acquisition date. Treat every
result as a lead to verify, not a ready-to-underwrite deal.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import requests
from pydantic import BaseModel

HUD_REO_FEATURE_SERVER = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/SF_REO/FeatureServer/0/query"
)
HUDHOMESTORE_PROPERTY_URL = "https://www.hudhomestore.gov/propertydetails?caseNumber={case_num}"

# City -> county, for the Lehigh Valley metro (Lehigh + Northampton counties, PA).
# Not exhaustive of every township's postal city name — this is a lead list,
# not a guaranteed-complete search. Widen it (or search statewide) if you want
# a bigger net.
LEHIGH_VALLEY_CITIES: dict[str, str] = {
    "ALLENTOWN": "Lehigh", "EMMAUS": "Lehigh", "WHITEHALL": "Lehigh", "CATASAUQUA": "Lehigh",
    "COPLAY": "Lehigh", "MACUNGIE": "Lehigh", "ALBURTIS": "Lehigh", "COOPERSBURG": "Lehigh",
    "SLATINGTON": "Lehigh", "NEW TRIPOLI": "Lehigh", "OREFIELD": "Lehigh", "ZIONSVILLE": "Lehigh",
    "BREINIGSVILLE": "Lehigh", "FOGELSVILLE": "Lehigh",
    "BETHLEHEM": "Northampton", "EASTON": "Northampton", "FOUNTAIN HILL": "Northampton",
    "HELLERTOWN": "Northampton", "NAZARETH": "Northampton", "NORTHAMPTON": "Northampton",
    "BANGOR": "Northampton", "PEN ARGYL": "Northampton", "WIND GAP": "Northampton",
    "BATH": "Northampton", "FREEMANSBURG": "Northampton", "WALNUTPORT": "Northampton",
}


class HudFeedError(RuntimeError):
    """Raised when the HUD ArcGIS feed can't be reached or returns an error."""


class HudReoListing(BaseModel):
    case_num: str
    address: str
    city: str
    state: str
    zip_code: str | None = None
    county_guess: str | None = None  # "Lehigh" / "Northampton" / None if not in our city list
    date_acquired: date | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def hudhomestore_url(self) -> str:
        return HUDHOMESTORE_PROPERTY_URL.format(case_num=self.case_num)


def _parse_feature(attrs: dict) -> HudReoListing:
    acquired = None
    raw_ms = attrs.get("DATE_ACQUIRED")
    if raw_ms:
        acquired = datetime.fromtimestamp(raw_ms / 1000, tz=timezone.utc).date()

    city = (attrs.get("CITY") or "").strip()
    zip_code = attrs.get("DISPLAY_ZIP_CODE")
    return HudReoListing(
        case_num=attrs["CASE_NUM"],
        address=(attrs.get("ADDRESS") or "").strip(),
        city=city,
        state=attrs.get("STATE_CODE") or "",
        zip_code=str(zip_code) if zip_code is not None else None,
        county_guess=LEHIGH_VALLEY_CITIES.get(city.upper()),
        date_acquired=acquired,
        latitude=attrs.get("MAP_LATITUDE"),
        longitude=attrs.get("MAP_LONGITUDE"),
    )


def fetch_hud_reo(state_code: str = "PA", timeout: float = 10.0) -> list[HudReoListing]:
    """All unsold HUD-owned REO properties in the given state, from HUD's public
    open-data feed. Raises HudFeedError on a network/HTTP/parse failure."""
    params = {
        "where": f"STATE_CODE='{state_code}' AND DATE_CLOSED IS NULL",
        "outFields": "CASE_NUM,ADDRESS,CITY,STATE_CODE,DISPLAY_ZIP_CODE,DATE_ACQUIRED,MAP_LATITUDE,MAP_LONGITUDE",
        "f": "json",
        "resultRecordCount": 2000,
        "orderByFields": "DATE_ACQUIRED DESC",
    }
    try:
        resp = requests.get(HUD_REO_FEATURE_SERVER, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise HudFeedError(f"Couldn't reach HUD's property feed: {e}") from e
    except ValueError as e:
        raise HudFeedError(f"HUD's property feed returned something unexpected: {e}") from e

    if data.get("error"):
        raise HudFeedError(f"HUD's property feed returned an error: {data['error']}")

    return [_parse_feature(f["attributes"]) for f in data.get("features", [])]


def filter_lehigh_valley(listings: list[HudReoListing]) -> list[HudReoListing]:
    """Keeps only listings whose city matches the LEHIGH_VALLEY_CITIES allowlist."""
    return [listing for listing in listings if listing.county_guess is not None]
