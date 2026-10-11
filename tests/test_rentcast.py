"""Tests for sourcing.rentcast. No real network calls — requests.get is mocked."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from sourcing.rentcast import (
    RentCastError,
    RentCastNotConfigured,
    is_configured,
    search_sale_listings,
)

RAW_LISTING = {
    "id": "abc123",
    "formattedAddress": "123 Main St, Allentown, PA 18101",
    "city": "Allentown",
    "state": "PA",
    "zipCode": "18101",
    "county": "Lehigh",
    "latitude": 40.6,
    "longitude": -75.47,
    "propertyType": "Multi-Family",
    "bedrooms": 4,
    "bathrooms": 2,
    "squareFootage": 2400,
    "yearBuilt": 1920,
    "status": "Active",
    "price": 275000,
    "listedDate": "2026-09-01",
    "daysOnMarket": 15,
    "mlsName": "LVAR",
    "mlsNumber": "PA123456",
}


def _mock_response(json_body, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


def test_is_configured(monkeypatch):
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)
    assert is_configured() is False
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    assert is_configured() is True


def test_search_raises_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)
    with pytest.raises(RentCastNotConfigured, match="RENTCAST_API_KEY"):
        search_sale_listings(city="Allentown")


def test_search_parses_listings(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    with patch("sourcing.rentcast.requests.get", return_value=_mock_response([RAW_LISTING])) as mock_get:
        listings = search_sale_listings(city="Allentown", state="PA")

    assert len(listings) == 1
    listing = listings[0]
    assert listing.formatted_address == "123 Main St, Allentown, PA 18101"
    assert listing.price == 275000
    assert listing.property_type == "Multi-Family"

    call = mock_get.call_args
    assert call.kwargs["headers"]["X-Api-Key"] == "fake-key"
    assert call.kwargs["params"]["city"] == "Allentown"
    assert call.kwargs["params"]["propertyType"] == "Multi-Family"


def test_search_applies_client_side_price_filter(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    cheap = {**RAW_LISTING, "id": "cheap", "price": 100000}
    expensive = {**RAW_LISTING, "id": "expensive", "price": 900000}
    with patch("sourcing.rentcast.requests.get", return_value=_mock_response([cheap, expensive, RAW_LISTING])):
        listings = search_sale_listings(city="Allentown", min_price=200000, max_price=500000)

    assert [listing.id for listing in listings] == ["abc123"]


def test_search_raises_on_invalid_key(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "bad-key")
    with patch("sourcing.rentcast.requests.get", return_value=_mock_response({}, status_code=401)):
        with pytest.raises(RentCastError, match="rejected"):
            search_sale_listings(city="Allentown")


def test_search_raises_on_server_error(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    resp = Mock()
    resp.status_code = 500
    resp.raise_for_status.side_effect = requests.HTTPError("500 error")
    with patch("sourcing.rentcast.requests.get", return_value=resp):
        with pytest.raises(RentCastError, match="returned an error"):
            search_sale_listings(city="Allentown")


def test_search_raises_on_rate_limit(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    with patch("sourcing.rentcast.requests.get", return_value=_mock_response({}, status_code=429)):
        with pytest.raises(RentCastError, match="rate limit"):
            search_sale_listings(city="Allentown")


def test_search_raises_on_network_error(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    with patch("sourcing.rentcast.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(RentCastError, match="Couldn't reach"):
            search_sale_listings(city="Allentown")


def test_search_raises_on_unparseable_response(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    resp = Mock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")
    with patch("sourcing.rentcast.requests.get", return_value=resp):
        with pytest.raises(RentCastError, match="unexpected"):
            search_sale_listings(city="Allentown")


def test_search_passes_zip_code_param(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "fake-key")
    with patch("sourcing.rentcast.requests.get", return_value=_mock_response([])) as mock_get:
        search_sale_listings(zip_code="18101")

    assert mock_get.call_args.kwargs["params"]["zipCode"] == "18101"
