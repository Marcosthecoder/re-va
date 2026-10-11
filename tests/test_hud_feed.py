"""Tests for sourcing.hud_feed. No real network calls — requests.get is mocked."""
from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from sourcing.hud_feed import (
    HudFeedError,
    fetch_hud_reo,
    filter_lehigh_valley,
)

ALLENTOWN_FEATURE = {
    "attributes": {
        "CASE_NUM": "441-123456",
        "ADDRESS": "123 MAIN ST   ",
        "CITY": "ALLENTOWN",
        "STATE_CODE": "PA",
        "DISPLAY_ZIP_CODE": 18101,
        "DATE_ACQUIRED": 1716163200000,  # 2024-05-20T00:00:00Z
        "MAP_LATITUDE": 40.6,
        "MAP_LONGITUDE": -75.47,
    }
}

OTHER_CITY_FEATURE = {
    "attributes": {
        "CASE_NUM": "441-999999",
        "ADDRESS": "9 SOME RD",
        "CITY": "HONESDALE",
        "STATE_CODE": "PA",
        "DISPLAY_ZIP_CODE": 18431,
        "DATE_ACQUIRED": None,
        "MAP_LATITUDE": 41.5,
        "MAP_LONGITUDE": -75.2,
    }
}


def _mock_response(json_body, status_ok=True):
    resp = Mock()
    resp.json.return_value = json_body
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.HTTPError("500 error")
    return resp


def test_fetch_hud_reo_parses_features():
    body = {"features": [ALLENTOWN_FEATURE, OTHER_CITY_FEATURE]}
    with patch("sourcing.hud_feed.requests.get", return_value=_mock_response(body)) as mock_get:
        listings = fetch_hud_reo(state_code="PA")

    assert len(listings) == 2
    allentown = listings[0]
    assert allentown.case_num == "441-123456"
    assert allentown.address == "123 MAIN ST"
    assert allentown.city == "ALLENTOWN"
    assert allentown.zip_code == "18101"
    assert allentown.date_acquired == date(2024, 5, 20)
    assert allentown.county_guess == "Lehigh"
    assert allentown.hudhomestore_url == "https://www.hudhomestore.gov/propertydetails?caseNumber=441-123456"

    other = listings[1]
    assert other.county_guess is None
    assert other.date_acquired is None

    params = mock_get.call_args.kwargs["params"]
    assert "STATE_CODE='PA'" in params["where"]


def test_fetch_hud_reo_raises_on_network_error():
    with patch("sourcing.hud_feed.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(HudFeedError, match="Couldn't reach"):
            fetch_hud_reo()


def test_fetch_hud_reo_raises_on_http_error():
    with patch("sourcing.hud_feed.requests.get", return_value=_mock_response({}, status_ok=False)):
        with pytest.raises(HudFeedError):
            fetch_hud_reo()


def test_fetch_hud_reo_raises_on_feed_error_payload():
    body = {"error": {"code": 400, "message": "bad request"}}
    with patch("sourcing.hud_feed.requests.get", return_value=_mock_response(body)):
        with pytest.raises(HudFeedError, match="bad request"):
            fetch_hud_reo()


def test_fetch_hud_reo_raises_on_unparseable_response():
    resp = Mock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")
    with patch("sourcing.hud_feed.requests.get", return_value=resp):
        with pytest.raises(HudFeedError, match="unexpected"):
            fetch_hud_reo()


def test_fetch_hud_reo_empty_features():
    with patch("sourcing.hud_feed.requests.get", return_value=_mock_response({"features": []})):
        assert fetch_hud_reo() == []


def test_filter_lehigh_valley_keeps_only_known_cities():
    body = {"features": [ALLENTOWN_FEATURE, OTHER_CITY_FEATURE]}
    with patch("sourcing.hud_feed.requests.get", return_value=_mock_response(body)):
        listings = fetch_hud_reo()

    filtered = filter_lehigh_valley(listings)
    assert len(filtered) == 1
    assert filtered[0].city == "ALLENTOWN"
