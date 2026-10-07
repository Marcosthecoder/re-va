"""Tests for the pure-Python parts of intake.extractor: CSV/XLSX rent roll
parsing and column-name normalization. extract_from_text/extract_from_pdf
call Claude and aren't covered here (no network calls in unit tests)."""
from __future__ import annotations

import io

from intake.extractor import parse_rent_roll_csv, parse_rent_roll_xlsx


def test_parse_rent_roll_csv_basic_columns():
    csv_text = "Unit,Bedrooms,Sqft,Market Rent,Current Rent\nA,2,800,1200,1100\nB,1,600,900,900\n"
    rows = parse_rent_roll_csv(csv_text.encode("utf-8"))
    assert len(rows) == 2
    assert rows[0]["label"] == "A"
    assert rows[0]["bedrooms"] == 2.0
    assert rows[0]["market_rent"] == 1200.0
    assert rows[0]["current_rent"] == 1100.0


def test_parse_rent_roll_csv_handles_dollar_signs_and_commas():
    csv_text = "Unit,Market Rent\nA,\"$1,200\"\n"
    rows = parse_rent_roll_csv(csv_text.encode("utf-8"))
    assert rows[0]["market_rent"] == 1200.0


def test_parse_rent_roll_csv_ignores_unrecognized_columns():
    csv_text = "Unit,Favorite Color,Market Rent\nA,Blue,1000\n"
    rows = parse_rent_roll_csv(csv_text.encode("utf-8"))
    assert "Favorite Color" not in rows[0]
    assert "favorite_color" not in rows[0]
    assert rows[0]["market_rent"] == 1000.0


def test_parse_rent_roll_csv_skips_blank_rows():
    csv_text = "Unit,Market Rent\nA,1000\n,\n"
    rows = parse_rent_roll_csv(csv_text.encode("utf-8"))
    assert len(rows) == 1


def test_parse_rent_roll_csv_handles_bom():
    csv_text = "﻿Unit,Market Rent\nA,1000\n"
    rows = parse_rent_roll_csv(csv_text.encode("utf-8"))
    assert rows[0]["label"] == "A"


def test_parse_rent_roll_xlsx_basic(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Unit", "Bedrooms", "Market Rent", "Lease End"])
    ws.append(["A", 2, 1150, "2027-01-01"])
    path = tmp_path / "rent_roll.xlsx"
    wb.save(path)

    rows = parse_rent_roll_xlsx(path.read_bytes())
    assert len(rows) == 1
    assert rows[0]["label"] == "A"
    assert rows[0]["bedrooms"] == 2.0
    assert rows[0]["market_rent"] == 1150.0
    assert rows[0]["lease_end"] == "2027-01-01"


def test_parse_rent_roll_xlsx_empty_sheet_returns_empty_list(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    path = tmp_path / "empty.xlsx"
    wb.save(path)
    rows = parse_rent_roll_xlsx(path.read_bytes())
    assert rows == []
