"""Command line entry points for reproducible research and the web application."""

import argparse
import json
from pathlib import Path

from .data import demo_bars, read_csv, validate_symbol, yahoo_bars
from .engine import BacktestConfig, run_backtest
from .strategies import StrategyConfig


def main():
    parser = argparse.ArgumentParser(
        prog="quantforge", description="Quantitative research, backtesting, and paper trading"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the local dashboard and API")
    serve.add_argument("--port", type=int, default=8000)
    demo = commands.add_parser("demo", help="Run a reproducible backtest with synthetic data")
    demo.add_argument("--output", type=Path, default=Path("reports/demo"))
    backtest = commands.add_parser("backtest", help="Backtest a local CSV file")
    backtest.add_argument("csv", type=Path)
    backtest.add_argument(
        "--strategy", choices=["trend", "momentum", "mean_reversion"], default="trend"
    )
    backtest.add_argument("--cash", type=float, default=100_000)
    backtest.add_argument("--output", type=Path, default=Path("reports/backtest"))
    download = commands.add_parser("download", help="Download adjusted daily bars from Yahoo")
    download.add_argument("symbol")
    download.add_argument("--start", default="2020-01-01")
    download.add_argument("--end", default="2025-12-31")
    download.add_argument("--output", type=Path, default=Path("data/datasets"))
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            uvicorn.run("quantforge.api:create_app", factory=True, host="127.0.0.1", port=args.port)
        elif args.command == "download":
            symbol = validate_symbol(args.symbol)
            if symbol == "DEMO":
                raise ValueError("DEMO is reserved for synthetic data")
            bars = yahoo_bars(symbol, args.start, args.end)
            args.output.mkdir(parents=True, exist_ok=True)
            bars.to_csv(args.output / f"{symbol}.csv")
            print(f"Saved {len(bars)} rows to {args.output / f'{symbol}.csv'}")
        else:
            bars = demo_bars() if args.command == "demo" else read_csv(args.csv)
            strategy = StrategyConfig(name=getattr(args, "strategy", "trend"))
            result = run_backtest(
                bars, strategy, BacktestConfig(initial_cash=getattr(args, "cash", 100_000))
            )
            result.export(args.output)
            if args.command == "demo":
                bars.to_csv(args.output / "synthetic_bars.csv")
                print(
                    "Data source: synthetic market data with a fixed random seed, not actual security returns."
                )
            print(json.dumps(result.metrics, ensure_ascii=False, indent=2, allow_nan=False))
            print(f"Report directory: {args.output.resolve()}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
