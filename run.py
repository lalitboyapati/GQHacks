"""GQHacks multi-track backtest runner.

Examples:
    python run.py --track item_202_results_ops
    python run.py --track item_202_results_ops DDOG,RBLX --count 1200
    python run.py --track disclosure_advantage --engine event
    python run.py --example dual_ma AAPL
    python run.py --example portfolio AAPL,MSFT,GOOG
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import runpy
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
INFRA_ROOT = HERE / "infrastructure"
TRACKS_DIR = HERE / "tracks"
BACKTEST_DIR = INFRA_ROOT / "backtest"

if str(INFRA_ROOT) not in sys.path:
    sys.path.insert(0, str(INFRA_ROOT))

from dotenv import load_dotenv

# Shared credentials / defaults
env_path = BACKTEST_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


def _list_tracks() -> list[str]:
    if not TRACKS_DIR.exists():
        return []
    return sorted(
        p.name
        for p in TRACKS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_") and (p / "strategy.py").exists()
    )


def _track_engine(track: str) -> str | None:
    """Read ENGINE from a track's strategy.py without importing STRATEGY_CLASS."""
    path = TRACKS_DIR / track / "strategy.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"gqh_track_meta_{track}", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    engine = getattr(mod, "ENGINE", None)
    return str(engine).strip().lower() if engine else None


def _run_event_track(track: str, argv_rest: list[str]) -> None:
    script = TRACKS_DIR / track / "scripts" / "run_backtest.py"
    if not script.exists():
        raise SystemExit(
            f"Track '{track}' uses the event engine but has no scripts/run_backtest.py"
        )
    os.environ["GQH_TRACK"] = track
    track_env = TRACKS_DIR / track / ".env"
    if track_env.exists():
        load_dotenv(track_env, override=True)
    # Mimic ``python scripts/run_backtest.py …``
    sys.argv = [str(script), *argv_rest]
    runpy.run_path(str(script), run_name="__main__")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a shared backtest for a research track or demo strategy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--track",
        default=None,
        help=f"Research track under tracks/ (available: {', '.join(_list_tracks()) or 'none yet'})",
    )
    parser.add_argument(
        "--example",
        default=None,
        help="Demo strategy under infrastructure/examples/strategies (e.g. dual_ma, portfolio)",
    )
    parser.add_argument("symbol", nargs="?", default=None, help="Ticker symbol(s), e.g. AAPL or AAPL,MSFT")
    parser.add_argument("-t", "--timespan", default=None, help="Timespan (D, M1, M5, ...)")
    parser.add_argument("-c", "--count", type=int, default=None, help="Number of bars to fetch")
    parser.add_argument("-p", "--params", default=None, help="Strategy params override (key=value,...)")
    parser.add_argument(
        "-e",
        "--engine",
        choices=["backtrader", "event"],
        default=None,
        help="backtrader (Webull BT) or event (eightk event-study). Inferred from track STRATEGY when omitted.",
    )
    parser.add_argument("--viz", choices=["lwc", "plotly"], default="lwc", help="Backtrader report visualizer")
    parser.add_argument("--fromdate", default=None)
    parser.add_argument("--todate", default=None)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--list-tracks", action="store_true", help="List research tracks and exit")
    args, unknown = parser.parse_known_args()

    if args.list_tracks:
        for name in _list_tracks():
            overview = TRACKS_DIR / name / "STRATEGY.md"
            engine = _track_engine(name) or "backtrader"
            print(f"- {name}  [{engine}]" + (f"  ({overview})" if overview.exists() else ""))
        return

    if args.track and args.example:
        raise SystemExit("Use either --track or --example, not both")

    # Optional track-local .env overrides shared infra .env
    if args.track:
        track_env = TRACKS_DIR / args.track / ".env"
        if track_env.exists():
            load_dotenv(track_env, override=True)
        os.environ["GQH_TRACK"] = args.track
        os.environ.pop("WEBULL_STRATEGY", None)
    elif args.example:
        os.environ.pop("GQH_TRACK", None)
        os.environ["WEBULL_STRATEGY"] = args.example
    elif not os.environ.get("GQH_TRACK") and not os.environ.get("WEBULL_STRATEGY"):
        default_track = "item_202_results_ops"
        if (TRACKS_DIR / default_track / "strategy.py").exists():
            os.environ["GQH_TRACK"] = default_track
            args.track = default_track
        else:
            os.environ["WEBULL_STRATEGY"] = "dual_ma"

    engine = args.engine
    if engine is None and args.track:
        engine = _track_engine(args.track)
    if engine is None:
        engine = "backtrader"

    if engine == "event":
        if not args.track:
            raise SystemExit("--engine event requires --track")
        _run_event_track(args.track, unknown)
        return
    if unknown:
        raise SystemExit(f"Unrecognized arguments for backtrader engine: {unknown}")

    if args.symbol:
        os.environ["WEBULL_SYMBOLS"] = args.symbol
    if args.timespan:
        os.environ["WEBULL_TIMESPAN"] = args.timespan
    if args.count:
        os.environ["WEBULL_COUNT"] = str(args.count)
    if args.params:
        os.environ["WEBULL_STRATEGY_PARAMS"] = args.params
    if args.fromdate:
        os.environ["WEBULL_FROMDATE"] = args.fromdate
    if args.todate:
        os.environ["WEBULL_TODATE"] = args.todate
    os.environ["WEBULL_VISUALIZE_ENGINE"] = args.viz

    report_file = BACKTEST_DIR / f"backtest_report_{os.environ.get('WEBULL_VISUALIZE_ENGINE', 'lwc')}.html"
    os.environ["WEBULL_VISUALIZE_OUTPUT"] = str(report_file)

    from backtest.main import setup_logging, run_backtest

    setup_logging()
    run_backtest()

    if not args.no_open and report_file.exists():
        print(f"\n[Browser] Opening interactive report: {report_file}")
        webbrowser.open(f"file:///{report_file.resolve().as_posix()}")


if __name__ == "__main__":
    main()
