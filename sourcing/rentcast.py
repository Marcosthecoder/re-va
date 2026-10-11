"""RentCast active for-sale listings search (optional — needs a free API key).

RentCast's free "Developer" plan gives 50 requests/month, no credit card.
Get a key at https://app.rentcast.io/app/api and put it in .env (or the
deployed app's Secrets) as RENTCAST_API_KEY. Unlike the HUD feed, this hits
RentCast's own documented REST API with your key — not scraping anything.

Price filtering is done client-side after the fetch rather than relying on
RentCast's documented-but-unconfirmed range query syntax for `price`, to
avoid silently sending a malformed filter.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel

import requests

load_dotenv()

RENTCAST_BASE_URL = "https://api.rentcast.io/v1"
MULTI_FAMILY_2_4_UNIT = "Multi-Family"  # RentCast's single property-type value covering duplex/triplex/fourplex


class RentCastNotConfigured(RuntimeError):
    """Raised when RENTCAST_API_KEY isn't set."""


class RentCastError(RuntimeError):
    """Raised on a network failure, an invalid key, or a RentCast API error response."""


class RentCastListing(BaseModel):
    id: str | None = None
    formatted_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    county: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_type: str | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    square_footage: float | None = None
    year_built: int | None = None
    status: str | None = None
    price: float | None = None
    listed_date: str | None = None
    days_on_market: int | None = None
    mls_name: str | None = None
    mls_number: str | None = None


def is_configured() -> bool:
    return bool(os.environ.get("RENTCAST_API_KEY"))


def _parse_listing(raw: dict) -> RentCastListing:
    return RentCastListing(
        id=raw.get("id"),
        formatted_address=raw.get("formattedAddress"),
        city=raw.get("city"),
        state=raw.get("state"),
        zip_code=raw.get("zipCode"),
        county=raw.get("county"),
        latitude=raw.get("latitude"),
        longitude=raw.get("longitude"),
        property_type=raw.get("propertyType"),
        bedrooms=raw.get("bedrooms"),
        bathrooms=raw.get("bathrooms"),
        square_footage=raw.get("squareFootage"),
        year_built=raw.get("yearBuilt"),
        status=raw.get("status"),
        price=raw.get("price"),
        listed_date=raw.get("listedDate"),
        days_on_market=raw.get("daysOnMarket"),
        mls_name=raw.get("mlsName"),
        mls_number=raw.get("mlsNumber"),
    )


def search_sale_listings(
    city: str | None = None,
    state: str = "PA",
    zip_code: str | None = None,
    property_type: str = MULTI_FAMILY_2_4_UNIT,
    min_price: float | None = None,
    max_price: float | None = None,
    status: str = "Active",
    limit: int = 50,
    timeout: float = 10.0,
) -> list[RentCastListing]:
    """Active for-sale listings matching the given filters.

    Raises RentCastNotConfigured if no API key is set, RentCastError on a
    network/HTTP/auth failure. min_price/max_price are applied client-side
    after the fetch.
    """
    api_key = os.environ.get("RENTCAST_API_KEY")
    if not api_key:
        raise RentCastNotConfigured(
            "RENTCAST_API_KEY is not set. Get a free key (50 requests/month, no card needed) at "
            "https://app.rentcast.io/app/api and add it to .env."
        )

    params: dict[str, str | int] = {"state": state, "propertyType": property_type, "status": status, "limit": limit}
    if city:
        params["city"] = city
    if zip_code:
        params["zipCode"] = zip_code

    try:
        resp = requests.get(
            f"{RENTCAST_BASE_URL}/listings/sale",
            params=params,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise RentCastError(f"Couldn't reach RentCast: {e}") from e

    if resp.status_code in (401, 403):
        raise RentCastError("RentCast rejected the API key — check RENTCAST_API_KEY in .env.")
    if resp.status_code == 429:
        raise RentCastError("RentCast rate limit hit (free tier is 50 requests/month). Try again next month.")
    try:
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RentCastError(f"RentCast returned an error: {e}") from e
    except ValueError as e:
        raise RentCastError(f"RentCast returned something unexpected: {e}") from e

    listings = [_parse_listing(raw) for raw in data]

    if min_price is not None:
        listings = [listing for listing in listings if listing.price is None or listing.price >= min_price]
    if max_price is not None:
        listings = [listing for listing in listings if listing.price is None or listing.price <= max_price]

    return listings
