"""Optional Google Sheets export. Only runs if GOOGLE_SHEETS_CREDENTIALS_PATH
is set in .env to a Google service-account JSON key file. Creates a new
spreadsheet (shared with no one by default — the service account owns it)
with live metric rows, and returns its URL.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from reports.report_builder import ReportData

load_dotenv()


class SheetsNotConfigured(RuntimeError):
    """Raised when GOOGLE_SHEETS_CREDENTIALS_PATH isn't set or doesn't point to a real file."""


def is_configured() -> bool:
    path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
    return bool(path) and os.path.isfile(path)


def export_to_sheet(report: ReportData, share_with_email: str | None = None) -> str:
    """Creates a Google Sheet with this deal's report and returns its URL.

    If ``share_with_email`` is given, grants that address edit access (the
    service account otherwise owns the sheet and no one else can open it).
    """
    if not is_configured():
        raise SheetsNotConfigured(
            "Set GOOGLE_SHEETS_CREDENTIALS_PATH in .env to a Google service account JSON key file "
            "to enable Sheets export. See README.md for setup steps."
        )

    import gspread  # imported lazily; only needed for this one optional feature

    path = os.environ["GOOGLE_SHEETS_CREDENTIALS_PATH"]
    client = gspread.service_account(filename=path)
    sheet = client.create(f"RE-VA: {report.deal_name}")
    ws = sheet.sheet1
    ws.update_title("Summary")

    rows = [
        ["Deal", report.deal_name],
        ["Address", report.address],
        ["Verdict", report.verdict_outcome],
        ["Target price", report.verdict_target_price or ""],
        [],
        ["Metric", "Value"],
        *[[k, v] for k, v in report.key_metrics.items()],
        [],
        ["Top risks"],
        *[[r] for r in report.risks],
        [],
        ["Top strengths"],
        *[[s] for s in report.strengths],
        [],
        ["Questions for broker/seller"],
        *[[q] for q in report.questions],
    ]
    ws.update(rows, "A1")

    if share_with_email:
        sheet.share(share_with_email, perm_type="user", role="writer")

    return sheet.url
