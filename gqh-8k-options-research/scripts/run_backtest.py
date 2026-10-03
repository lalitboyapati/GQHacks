#!/usr/bin/env python
"""Run the options backtest over a saved event set.

Examples
--------
    python scripts/run_backtest.py                        # all strategies
    python scripts/run_backtest.py --hold 5 --hold 10 --hold 21
    python scripts/run_backtest.py --strategies exec_put,stock_short
    python scripts/run_backtest.py --max-cap 10e9 --no-earnings-confound
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.backtest import BacktestConfig, run_backtest, trades_frame
from eightk.config import Settings
from eightk.edgar import Filing
from eightk.events import EventRecord
from eightk.massive_src import MassiveClient
from eightk.options_book import CostModel
from eightk.report import format_report, summarize
from eightk.strategies import StrategyConfig, default_strategies


def _rebuild_events(path: Path) -> list[EventRecord]:
    """Reconstruct event records from a saved JSON event file.

    Only the fields the strategies actually read are restored, which keeps
    the event file a stable, human-readable contract rather than a pickle of
    internal objects.
    """
    from eightk.classify import EfficiencyPlan, ExecChange
    from eightk.novelty import NoveltyAssessment

    rows = json.loads(path.read_text())
    records: list[EventRecord] = []
    for row in rows:
        filing = Filing.from_dict(row)

        exec_change = None
        if row.get("exec_top_role") is not None or row.get("exec_is_departure") is not None:
            exec_change = ExecChange(
                is_departure=bool(row.get("exec_is_departure")),
                is_appointment=bool(row.get("exec_is_appointment")),
                roles=tuple(row.get("exec_roles") or ()),
                top_role=row.get("exec_top_role"),
                person=row.get("exec_person"),
                abrupt=bool(row.get("exec_abrupt")),
                successor_named=bool(row.get("exec_successor_named")),
                interim_successor=bool(row.get("exec_interim_successor")),
                disagreement=bool(row.get("exec_disagreement")),
                for_cause=bool(row.get("exec_for_cause")),
                retirement=bool(row.get("exec_retirement")),
                comp_only=bool(row.get("exec_comp_only")),
                severity=float(row.get("exec_severity") or 0.0),
            )

        plan = None
        if row.get("plan_is_plan"):
            plan = EfficiencyPlan(
                is_plan=True,
                charge_usd=row.get("plan_charge_usd"),
                savings_usd=row.get("plan_savings_usd"),
                savings_horizon_years=row.get("plan_savings_horizon_years"),
                headcount=row.get("plan_headcount"),
                headcount_pct=row.get("plan_headcount_pct"),
                cash_charge=bool(row.get("plan_cash_charge")),
                cost_front_loaded=bool(row.get("plan_cost_front_loaded")),
                payback_years=row.get("plan_payback_years"),
            )

        novelty = None
        if row.get("novelty_score") is not None:
            novelty = NoveltyAssessment(
                score=float(row["novelty_score"]),
                is_repeat=bool(row.get("is_repeat")),
                self_reported_repeat=bool(row.get("self_reported_repeat")),
                fresh_markers=bool(row.get("fresh_markers")),
                pointer_only=bool(row.get("pointer_only")),
                report_lag_days=int(row.get("report_lag_days") or 0),
                prior_news_count=int(row.get("prior_news_count") or 0),
                max_prior_similarity=float(row.get("max_prior_similarity") or 0.0),
                hours_since_first_mention=row.get("hours_since_first_mention"),
                body_chars=int(row.get("body_chars") or 0),
                matched_headline=row.get("matched_headline"),
            )

        records.append(EventRecord(
            filing=filing,
            exec_change=exec_change,
            plan=plan,
            novelty=novelty,
            market_cap=row.get("market_cap"),
            company_name=row.get("company_name"),
            sic_description=row.get("sic_description"),
            text_chars=int(row.get("text_chars") or 0),
            event_types=tuple(row.get("event_types") or ()),
        ))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--events", default=None, help="Path to the events JSON")
    parser.add_argument("--hold", action="append", type=int, default=None,
                        help="Holding period in sessions; repeat to sweep")
    parser.add_argument("--strategies", default=None,
                        help="Comma-separated strategy names (default: all)")
    parser.add_argument("--notional", type=float, default=10_000.0,
                        help="Underlying notional per trade, for comparability")
    parser.add_argument("--max-cap", type=float, default=20e9,
                        help="Market-cap ceiling for 'smaller company'")
    parser.add_argument("--min-severity", type=float, default=0.35,
                        help="Minimum executive-change severity to trade")
    parser.add_argument("--spread-pct", type=float, default=0.04,
                        help="Half-spread as a share of option premium, each way")
    parser.add_argument("--include-earnings-confound", action="store_true",
                        help="Include filings that also carry an earnings release")
    parser.add_argument("--min-dte", type=int, default=21)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument("--out-prefix", default=None, help="Where to write result CSVs")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("run_backtest")

    settings = Settings.from_env()
    settings.ensure_dirs()

    events_path = Path(args.events) if args.events else settings.events_dir / "events.json"
    if not events_path.exists():
        print(f"No event file at {events_path}. Run scripts/fetch_events.py first.")
        return 1

    events = _rebuild_events(events_path)
    log.info("loaded %d events from %s", len(events), events_path)

    if not settings.has_massive:
        print("MASSIVE_API_KEY is required for prices and option chains. "
              "Add it to .env and re-run.")
        return 1
    massive = MassiveClient(settings.massive_api_key, settings.cache_dir,
                            offline=settings.offline)

    strategy_config = StrategyConfig(
        min_days_to_expiry=args.min_dte,
        max_days_to_expiry=args.max_dte,
        min_severity=args.min_severity,
        max_market_cap=args.max_cap,
        exclude_earnings_confounded=not args.include_earnings_confound,
    )
    strategies = default_strategies(strategy_config)
    if args.strategies:
        wanted = {name.strip() for name in args.strategies.split(",") if name.strip()}
        strategies = [s for s in strategies if s.name in wanted]
        if not strategies:
            print(f"No strategies matched {sorted(wanted)}")
            return 1

    holds = args.hold or [5, 10, 21]
    import pandas as pd
    all_frames = []

    for hold in holds:
        config = BacktestConfig(
            hold_sessions=hold,
            target_notional=args.notional,
            cost_model=CostModel(spread_pct_of_premium=args.spread_pct),
            strategy_config=strategy_config,
        )
        log.info("=== holding period: %d sessions ===", hold)
        trades = run_backtest(events, strategies, massive=massive, config=config)
        if not trades:
            log.warning("no trades at hold=%d", hold)
            continue
        frame = trades_frame(trades)
        frame["hold"] = hold
        all_frames.append(frame)

        print()
        print(format_report(frame))

    if not all_frames:
        print("No trades were simulated at any holding period.")
        return 1

    combined = pd.concat(all_frames, ignore_index=True)
    prefix = Path(args.out_prefix) if args.out_prefix else settings.results_dir / "backtest"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    trades_csv = prefix.with_name(prefix.name + "_trades.csv")
    summary_csv = prefix.with_name(prefix.name + "_summary.csv")
    combined.to_csv(trades_csv, index=False)

    summaries = []
    for hold, group in combined.groupby("hold"):
        table = summarize(group)
        table["hold"] = hold
        summaries.append(table)
    pd.concat(summaries, ignore_index=True).to_csv(summary_csv, index=False)

    print(f"\nWrote {len(combined)} trades to {trades_csv}")
    print(f"Wrote per-strategy summary to {summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
