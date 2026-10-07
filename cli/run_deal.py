"""CLI entry point for Phase 1: run one deal YAML through the underwriting engine
and print a full, hand-checkable report. No LLM calls happen anywhere in this path.

Usage:
    python -m cli.run_deal tests/fixtures/good_duplex.yaml
    python -m cli.run_deal path/to/deal.yaml --profile config/investor_profile.yaml
"""
from __future__ import annotations

import argparse
import sys

from underwriting import engine, house_hack, self_employed, verdict
from underwriting.models import load_deal
from underwriting.pipeline import analyze_deal
from underwriting.profile import load_investor_profile

DISCLAIMER = (
    "DECISION SUPPORT ONLY. Not legal, tax, or financial advice. Verify every number "
    "with a lender, attorney, and inspector before buying. This tool never contacts "
    "anyone or executes a transaction on your behalf."
)


def money(x: float) -> str:
    return f"${x:,.0f}"


def pct(x: float) -> str:
    if x == float("inf"):
        return "inf"
    return f"{x:.1%}"


def rule(char: str = "-", width: int = 78) -> str:
    return char * width


def print_header(title: str) -> None:
    print()
    print(rule("="))
    print(title)
    print(rule("="))


def print_rent_roll(core: engine.CoreMetrics) -> None:
    rr = core.rent_roll
    print_header("RENT ROLL")
    print(f"Gross potential rent (market):   {money(rr.gross_potential_rent_monthly_market)}/mo  ({money(rr.gross_potential_rent_annual_market)}/yr)")
    print(f"Gross potential rent (in-place): {money(rr.gross_potential_rent_monthly_in_place)}/mo  ({money(rr.gross_potential_rent_annual_in_place)}/yr)")


def print_expenses(core: engine.CoreMetrics) -> None:
    print_header("OPERATING EXPENSES (annual, market-based)")
    for item in core.operating_expenses.items:
        print(f"  {item.name:<28} {money(item.annual_amount):>12}   [{item.source}]")
    print(f"  {'TOTAL':<28} {money(core.operating_expenses.total_annual):>12}")


def print_core_metrics(core: engine.CoreMetrics) -> None:
    print_header("CORE METRICS (fully rented at market)")
    print(f"NOI (market):              {money(core.noi_annual)}/yr")
    print(f"NOI (in-place):            {money(core.noi_annual_in_place)}/yr")
    print(f"Cap rate (market):         {pct(core.cap_rate_market)}")
    print(f"Cap rate (in-place):       {pct(core.cap_rate_in_place)}")
    ds = core.debt_service
    print(f"Loan amount:               {money(ds.loan_amount)}  (incl. financed upfront MIP {money(ds.financed_upfront_mip)})")
    print(f"Monthly P&I:               {money(ds.monthly_principal_interest)}")
    print(f"Monthly MIP:               {money(ds.monthly_mip)}")
    print(f"DSCR:                      {core.dscr:.2f}")
    print(f"Cash flow before tax:      {money(core.cash_flow_before_tax_monthly)}/mo  ({money(core.cash_flow_before_tax_annual)}/yr)")
    print(f"Total cash required:       {money(core.total_cash_required)}")
    print(f"Cash-on-cash return:       {pct(core.cash_on_cash_return)}")
    print(f"Breakeven occupancy:       {pct(core.breakeven_occupancy)}")


def print_pro_forma(pf: engine.ProForma) -> None:
    print_header("5-YEAR PRO FORMA")
    print(f"{'Year':<6}{'GPR':>12}{'EGI':>12}{'OpEx':>12}{'NOI':>12}{'CF before tax':>16}{'Loan balance':>14}")
    for y in pf.years:
        print(
            f"{y.year:<6}{money(y.gross_potential_rent):>12}{money(y.effective_gross_income):>12}"
            f"{money(y.operating_expenses):>12}{money(y.noi):>12}{money(y.cash_flow_before_tax):>16}{money(y.loan_balance_end_of_year):>14}"
        )
    ex = pf.exit
    print()
    print(f"Exit NOI (forward year):  {money(ex.exit_noi_forward)}")
    print(f"Exit cap rate:            {pct(ex.exit_cap_rate)}")
    print(f"Exit value:               {money(ex.exit_value)}")
    print(f"Selling costs:            {money(ex.selling_costs)}")
    print(f"Loan balance at exit:     {money(ex.loan_balance_at_exit)}")
    print(f"Net sale proceeds:        {money(ex.net_sale_proceeds)}")
    print(f"IRR:                      {'n/a' if pf.irr is None else pct(pf.irr)}")
    print(f"Equity multiple:          {pf.equity_multiple:.2f}x")


def print_scenarios(scenarios: dict[str, engine.ScenarioResult]) -> None:
    print_header("SCENARIOS")
    print(f"{'Scenario':<10}{'NOI':>12}{'CF/mo':>10}{'CoC':>10}{'IRR':>10}")
    for name in ("downside", "base", "upside"):
        s = scenarios[name]
        irr_str = "n/a" if s.pro_forma.irr is None else pct(s.pro_forma.irr)
        print(f"{name:<10}{money(s.core.noi_annual):>12}{money(s.core.cash_flow_before_tax_monthly):>10}{pct(s.core.cash_on_cash_return):>10}{irr_str:>10}")


def print_lease_rollover(flags: list[engine.LeaseRolloverFlag]) -> None:
    print_header("LEASE ROLLOVER RISK (<=24 months)")
    if not flags:
        print("None.")
        return
    for f in flags:
        print(f"  {f.unit_label}: expires {f.lease_end} ({f.months_to_expiry} months), {pct(f.income_share_pct)} of market GPR")


def print_rules(v: verdict.Verdict) -> None:
    for r in v.rules:
        mark = "PASS" if r.passed else "FAIL"
        print(f"  [{mark}] {r.name}: {r.detail}")


def print_verdict(v: verdict.Verdict) -> None:
    print_header(f"VERDICT: {v.outcome}")
    print_rules(v)
    print()
    if v.target_price is not None:
        print(f"Target/offer price: {money(v.target_price)}")
    print(v.summary)


def run(deal_path: str, profile_path: str) -> int:
    deal = load_deal(deal_path)
    profile = load_investor_profile(profile_path)
    bundle = analyze_deal(deal, profile)
    thresholds, analysis = bundle.thresholds, bundle.analysis

    print_header(f"DEAL: {analysis.deal_name}")
    print(f"{deal.address} | {deal.county} County | {deal.property_type} | {deal.unit_count} units")
    print(f"Asking price: {money(analysis.price)}")

    print_rent_roll(analysis.core)
    print_expenses(analysis.core)
    print_core_metrics(analysis.core)
    print_lease_rollover(analysis.lease_rollover_flags)
    print_pro_forma(analysis.pro_forma)
    print_scenarios(analysis.scenarios)

    print_header("MAX OFFER PRICE (core thresholds only)")
    print(money(analysis.max_offer_price))

    if deal.is_house_hack:
        hh = bundle.hh_bundle
        payment = house_hack.full_monthly_payment(deal)
        cash_close, live_in, dti = hh.cash_close, hh.live_in, hh.dti
        self_suff, loan_limit, mixed_use = hh.self_sufficiency, hh.loan_limit, hh.mixed_use
        standards_flags = hh.standards_flags
        max_price_hh = hh.max_offer_price_house_hack

        print_header("FHA HOUSE HACK: FULL MONTHLY PAYMENT")
        print(f"P&I:         {money(payment.principal_interest)}")
        print(f"Property tax:{money(payment.property_tax):>12}")
        print(f"Insurance:   {money(payment.insurance)}")
        print(f"MIP:         {money(payment.mip)}")
        print(f"TOTAL:       {money(payment.total)}")

        print_header("CASH TO CLOSE")
        print(f"Down payment:          {money(cash_close.down_payment)}")
        print(f"Closing costs:         {money(cash_close.closing_costs)}")
        print(f"Seller concessions:    -{money(cash_close.seller_concessions)}")
        print(f"Down payment assist.:  -{money(cash_close.down_payment_assistance)}")
        print(f"TOTAL REQUIRED:        {money(cash_close.total_cash_required)}")
        print(f"Cash on hand:          {money(cash_close.cash_on_hand)}")
        print(f"Gap:                   {money(max(cash_close.cash_gap, 0))} {'(SHORT)' if not cash_close.covered else '(covered)'}")

        print_header("LIVE-IN PHASE: NET MONTHLY HOUSING COST")
        print(f"Full payment:                {money(live_in.full_monthly_payment)}")
        print(f"Owner's share of expenses:   +{money(live_in.owner_share_of_expenses)}")
        print(f"Other units' rent:            {money(live_in.other_units_rent_monthly)}")
        print(f"  less vacancy+repairs:      -{money(live_in.vacancy_and_repair_adjustment)}")
        print(f"  net rent credited:          {money(live_in.net_rent_from_others)}")
        print(f"NET MONTHLY HOUSING COST:     {money(live_in.net_monthly_housing_cost)}")
        if live_in.comparable_rent_estimate is not None:
            print(f"Comparable apartment rent:    {money(live_in.comparable_rent_estimate)}")
            print(f"Monthly savings vs. renting:  {money(live_in.monthly_savings_vs_comparable)}")
        else:
            print("Comparable apartment rent:    not provided (set comparable_rent_estimate in the deal YAML)")

        print_header("LENDER QUALIFICATION: DTI")
        print(f"Effective monthly income (incl. {pct(deal.financing.rental_income_credit_pct)} of other units' rent): {money(dti.effective_monthly_income)}")
        print(f"Front DTI: {pct(dti.front_dti)} (max {pct(dti.max_front_dti)}) -> {'PASS' if dti.front_pass else 'FAIL'}")
        print(f"Back DTI:  {pct(dti.back_dti)} (max {pct(dti.max_back_dti)}) -> {'PASS' if dti.back_pass else 'FAIL'}")

        print_header("FHA SELF-SUFFICIENCY TEST (3-4 unit)")
        if self_suff.applicable:
            print(f"75% of total market rent: {money(self_suff.seventy_five_pct_of_rent)}/mo")
            print(f"Full monthly payment:     {money(self_suff.full_monthly_payment)}/mo")
            print(f"Gap:                      {money(self_suff.gap)}  -> {'PASS' if self_suff.passed else 'FAIL'}")
        else:
            print(f"Not applicable ({deal.unit_count} units).")

        print_header("FHA LOAN LIMIT")
        if loan_limit.status == "unknown_verify_hud":
            print(f"Loan amount {money(loan_limit.loan_amount)} — county limit for {deal.unit_count} unit(s) not set in profile. VERIFY on HUD lookup.")
        else:
            print(f"Loan amount {money(loan_limit.loan_amount)} vs. limit {money(loan_limit.limit)} -> {loan_limit.status.upper()}")

        print_header("MIXED-USE CHECK")
        if mixed_use.applicable:
            print(f"Residential share: {pct(mixed_use.residential_pct)} -> {'PASS' if mixed_use.passed else 'FAIL'}")
        else:
            print("Not applicable (not a mixed-use deal).")

        print_header("PROPERTY STANDARDS FLAGS")
        if not standards_flags:
            print("None flagged.")
        for f in standards_flags:
            print(f"  [{f.severity.upper()}] {f.code}: {f.description}")

        print_header("MAX OFFER PRICE (house hack, all constraints)")
        print(money(max_price_hh))

    final_verdict = bundle.verdict

    if profile.investor.ownership_pct is None or profile.investor.ownership_pct >= 0.25:
        print_header("SELF-EMPLOYED QUALIFYING INCOME")
        se = self_employed.self_employed_qualifying_income(
            ownership_pct=profile.investor.ownership_pct,
            years_of_tax_returns=profile.investor.years_of_tax_returns_with_this_income,
            yearly_net_incomes=[],
        )
        if se.calculable:
            print(f"Qualifying monthly income: {money(se.qualifying_monthly_income)}")
        else:
            print(f"Not yet calculable: {se.years_available} of {se.years_required} required years of returns on file.")
            print(f"Projected mortgage-ready date: {se.mortgage_ready_date} ({se.months_until_ready} months away)")
        for n in se.notes:
            print(f"  NOTE: {n}")
        print("Checklist:")
        for item in se.checklist:
            print(f"  - {item}")

    print_verdict(final_verdict)

    print()
    print(rule("#"))
    print(DISCLAIMER)
    print(rule("#"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one deal YAML through the RE-VA underwriting engine.")
    parser.add_argument("deal", help="Path to a deal YAML file")
    parser.add_argument("--profile", default="config/investor_profile.yaml", help="Path to investor_profile.yaml")
    args = parser.parse_args(argv)
    return run(args.deal, args.profile)


if __name__ == "__main__":
    sys.exit(main())
