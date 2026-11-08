"""Command line entry points for reproducible research and the web application."""

import argparse
import json
from pathlib import Path

from .data import demo_bars, read_csv, validate_symbol, yahoo_bars
from .engine import BacktestConfig, run_backtest
from .strategies import StrategyConfig


def main():
    parser = argparse.ArgumentParser(prog="quantforge", description="量化研究、回测与模拟交易")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本地网页和 API")
    serve.add_argument("--port", type=int, default=8000)
    demo = commands.add_parser("demo", help="用合成数据执行可复现回测")
    demo.add_argument("--output", type=Path, default=Path("reports/demo"))
    backtest = commands.add_parser("backtest", help="回测本地 CSV")
    backtest.add_argument("csv", type=Path)
    backtest.add_argument(
        "--strategy", choices=["trend", "momentum", "mean_reversion"], default="trend"
    )
    backtest.add_argument("--cash", type=float, default=100_000)
    backtest.add_argument("--output", type=Path, default=Path("reports/backtest"))
    download = commands.add_parser("download", help="下载 Yahoo 复权日线")
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
                raise ValueError("DEMO 保留用于合成行情")
            bars = yahoo_bars(symbol, args.start, args.end)
            args.output.mkdir(parents=True, exist_ok=True)
            bars.to_csv(args.output / f"{symbol}.csv")
            print(f"已保存 {len(bars)} 行至 {args.output / f'{symbol}.csv'}")
        else:
            bars = demo_bars() if args.command == "demo" else read_csv(args.csv)
            strategy = StrategyConfig(name=getattr(args, "strategy", "trend"))
            result = run_backtest(
                bars, strategy, BacktestConfig(initial_cash=getattr(args, "cash", 100_000))
            )
            result.export(args.output)
            if args.command == "demo":
                bars.to_csv(args.output / "synthetic_bars.csv")
                print("数据来源：固定随机种子的合成行情，不代表真实证券收益。")
            print(json.dumps(result.metrics, ensure_ascii=False, indent=2, allow_nan=False))
            print(f"报告目录：{args.output.resolve()}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"错误：{exc}\n")


if __name__ == "__main__":
    main()
