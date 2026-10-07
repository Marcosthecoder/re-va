# RE-VA — Real Estate Virtual Assistant

Decision support for finding, underwriting, and closing a first real estate
deal in the Lehigh Valley, PA — starting with an FHA house hack (buy a 2-4
unit property, live in one unit, rent the rest).

**RE-VA never contacts anyone or executes a transaction on your behalf.**
Every financial output shows its inputs and math so you can verify it
yourself. See the disclaimer at the bottom — this is not legal, tax, or
financial advice.

## What's built

**Phase 1 — underwriting engine (`underwriting/`).** Pure Python, no LLM
involved in any calculation: NOI, cap rate, DSCR, cash flow, cash-on-cash,
breakeven occupancy, a 5-year pro forma with IRR and equity multiple,
sensitivity analysis, downside/base/upside scenarios, max offer price, and
lease rollover risk — plus an FHA house-hack-specific module (full payment
including MIP, cash-to-close, live-in vs. move-out phase, lender DTI, the
FHA self-sufficiency test, loan limits, self-employed qualifying income, and
FHA property-standards red flags) and rule-based PASS/NEGOTIATE/PURSUE
verdict logic. `cli/run_deal.py` runs one deal YAML through it from the
terminal.

**Phase 2 — intake, reports (`intake/`, `reports/`, `db/`).** Paste listing
text or upload a PDF/rent-roll CSV/XLSX; Claude extracts structured fields
with a confidence flag per field, and CSV/XLSX rent rolls are parsed with
plain Python (no LLM). A one-page report (top risks, top strengths,
questions for the broker — all rule-based) exports to PDF, with an optional
Claude-written plain-English explanation of the numbers already computed.
Deals persist in SQLite via SQLAlchemy.

**Phase 3 — coach, roadmap, outreach (`coach/`, `roadmap/`, `outreach/`).**
A chat coach that explains terms using your actual deal's numbers, plus a
static quiz on NOI/cap rate/DSCR/NNN leases/due diligence. A closing
checklist (house hack by default, commercial for later deals) with
status/notes/dates tracked per deal. Draft emails to brokers, lenders, and
sellers — **drafts only, nothing is ever sent automatically.**

**Phase 4 — market data (`market/`).** Stored rent comps with an over/under
-market flag (>15% off the comp average), and a property-tax helper. No
automated county tax API is wired up — Lehigh/Northampton County don't have
one that's reliably scrapable — so it always returns a manual-entry pointer
plus a reassessment-after-sale reminder, never a guessed number.

**Dashboard (`app/`).** A Streamlit app tying all of the above together:
a pipeline view of every deal (stage, verdict, key metrics), a new-deal
flow (manual form, paste/PDF intake, or CSV/XLSX rent-roll upload), a full
deal-detail page (rent roll, pro forma, scenarios, house-hack breakdown,
rule-by-rule verdict, PDF export), the coach, the roadmap, outreach drafts,
market comps, and an investor-profile editor.

`tests/` — 162 tests. 100% line coverage on `underwriting/` (the math) plus
`db/`, `roadmap/`, `market/`, `reports/report_builder.py`,
`reports/pdf_export.py`. The few uncovered lines are the actual Anthropic/
Google API call sites, which were validated live instead of mocked.

## Setup

Requires Python 3.11+.

```bash
cd re-va
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`. The underwriting engine and CLI are pure
Python and need no API key. For document intake, plain-English
explanations, and the coach chat, add an Anthropic key:

1. Go to https://console.anthropic.com/settings/keys (requires an
   Anthropic Console account with billing/credits set up — this is a
   separate account from a regular claude.ai login).
2. Create a key scoped to a specific workspace (simplest) and paste it into
   `.env` as `ANTHROPIC_API_KEY=...`. It should look like
   `sk-ant-api03-...`.
   - If your key instead starts with `sk-ant-usr-` (a workspace-unscoped
     "user" key), also set `ANTHROPIC_WORKSPACE_ID=...` in `.env` — find
     the workspace ID in the Console's workspace settings.
3. Never commit `.env` — it's already in `.gitignore`.

Every LLM-powered feature in the dashboard checks for a configured key and
shows a plain setup message instead of crashing if one isn't present —
everything else works regardless.

Optional, Phase 4 only: set `GOOGLE_SHEETS_CREDENTIALS_PATH` in `.env` to a
Google service-account JSON key file to enable the "Export to Google
Sheets" button on a deal's report. Skip it if you don't need Sheets export.

## Running the dashboard

```bash
source .venv/bin/activate
streamlit run app/Home.py
```

Opens at http://localhost:8501. Start on **New Deal** to add your first
property (manual entry, paste a listing, or upload a rent roll), then use
**Deal Detail** for the full analysis and verdict, **Roadmap** to track
closing steps, **Outreach** for draft emails, **Market Comps** for rent
comps and the tax-lookup helper, and **Investor Profile** to edit your
cash-on-hand, income, and thresholds. Data lives in `re_va.db` (SQLite,
git-ignored) in the project root.

## Running a deal from the CLI (no dashboard, no DB)

```bash
source .venv/bin/activate
python -m cli.run_deal tests/fixtures/good_duplex.yaml
python -m cli.run_deal tests/fixtures/marginal_triplex.yaml
python -m cli.run_deal tests/fixtures/bad_fourplex.yaml
```

Each prints the full rent roll, itemized expenses (with source labels —
seller-provided, county record, or assumption), core metrics, 5-year pro
forma, scenarios, the FHA house-hack breakdown, the self-employed
qualifying-income status, and a final verdict with every rule's pass/fail
shown. Copy one of the files in `tests/fixtures/` and edit the numbers to
run your own deal this way — every field is documented inline.

Both the CLI and the dashboard read investor-level settings (cash on hand,
income, DTI thresholds, FHA loan limits) from
`config/investor_profile.yaml` — editable directly or via the Investor
Profile page. Everything in it is configurable, and any field the engine
falls back to a code default for is labeled as an assumption in the output.

## Running tests

```bash
source .venv/bin/activate
python -m pytest --cov=underwriting --cov=db --cov=roadmap --cov=market --cov=outreach --cov=reports --cov=intake --cov=llm --cov-report=term-missing
```

## Project layout

```
config/investor_profile.yaml   Investor-level settings and thresholds
underwriting/                  The math engine (Phase 1, see above)
cli/run_deal.py                CLI entry point (no DB, no dashboard)
db/                             SQLAlchemy models + repository (deals, checklists, drafts, comps, LLM call log)
llm/client.py                   Anthropic SDK wrapper; logs every call
intake/                          Listing/PDF/rent-roll parsing (Phase 2)
reports/                         Report builder, PDF export, Sheets export (Phase 2)
coach/                           Chat coach + quiz (Phase 3)
roadmap/                         Closing checklists + tracker (Phase 3)
outreach/                        Draft emails, never auto-sent (Phase 3)
market/                          Rent comps + tax-lookup helper (Phase 4)
app/                             Streamlit dashboard
tests/                           162 tests + 3 sample deal fixtures
```

## Disclaimer

RE-VA is decision support only. It is not legal, tax, or financial advice.
Verify every number with a lender, attorney, and inspector before buying
anything. It never contacts a broker, lender, or seller, and never submits
an offer or executes a transaction — every outreach draft and every number
is for you to review and act on yourself.
