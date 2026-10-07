"""Tests for reports.pdf_export: pure, deterministic, no network calls."""
from __future__ import annotations

from reports.pdf_export import _sanitize, build_pdf
from reports.report_builder import ReportData


def _sample_report(**overrides) -> ReportData:
    base = dict(
        deal_name="Test Deal",
        address="1 Test St",
        price=200_000,
        is_house_hack=True,
        verdict_outcome="PURSUE",
        verdict_target_price=200_000,
        key_metrics={"NOI": "$10,000/yr", "DSCR": "1.25"},
        risks=["Some risk"],
        strengths=["Some strength"],
        questions=["Some question?"],
        rule_detail=["[PASS] DSCR: 1.25 vs. minimum 1.15"],
    )
    base.update(overrides)
    return ReportData(**base)


def test_build_pdf_returns_valid_pdf_bytes():
    pdf_bytes = build_pdf(_sample_report())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_build_pdf_includes_explanation_section():
    with_explanation = build_pdf(_sample_report(), explanation="Plain English summary.")
    without_explanation = build_pdf(_sample_report(), explanation=None)
    assert len(with_explanation) > len(without_explanation)


def test_build_pdf_handles_em_dash_in_risks_without_raising():
    report = _sample_report(risks=["Unit A lease expires soon — that's a risk."])
    pdf_bytes = build_pdf(report)
    assert pdf_bytes.startswith(b"%PDF")


def test_sanitize_replaces_smart_punctuation():
    text = "Em—dash, en–dash, ‘quote’, “quote”"
    sanitized = _sanitize(text)
    assert "—" not in sanitized
    assert "–" not in sanitized
    assert "‘" not in sanitized
    assert "“" not in sanitized
    assert sanitized == "Em-dash, en-dash, 'quote', \"quote\""
