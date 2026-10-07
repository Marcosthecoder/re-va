"""Tests for the pure/config-detection parts of reports.sheets_export.
export_to_sheet itself makes real Google API calls and isn't covered here."""
from __future__ import annotations

import pytest

from reports.report_builder import ReportData
from reports.sheets_export import SheetsNotConfigured, export_to_sheet, is_configured


def test_is_configured_false_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_PATH", raising=False)
    assert is_configured() is False


def test_is_configured_false_when_path_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_PATH", str(tmp_path / "missing.json"))
    assert is_configured() is False


def test_is_configured_true_when_file_exists(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_PATH", str(creds))
    assert is_configured() is True


def test_export_raises_not_configured_without_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_PATH", raising=False)
    report = ReportData(
        deal_name="Test", address="1 Test St", price=100_000, is_house_hack=False,
        verdict_outcome="PURSUE", verdict_target_price=100_000, key_metrics={},
        risks=[], strengths=[], questions=[],
    )
    with pytest.raises(SheetsNotConfigured):
        export_to_sheet(report)
