"""Long-only, next-open backtesting with explicit friction and risk constraints."""

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import validate_bars
from .strategies import StrategyConfig, target_weights


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000
    commission_bps: float = 5
    slippage_bps: float = 5
    max_position: float = 0.95
    target_volatility: float = 0.15
    volatility_window: int = 20
    max_drawdown: float = 0.20
    rebalance_threshold: float = 0.02

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not np.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.initial_cash <= 0:
            raise ValueError("Initial cash must be greater than zero")
        if not 0 <= self.commission_bps <= 100 or not 0 <= self.slippage_bps <= 100:
            raise ValueError("Commission and slippage must be between 0 and 100 basis points")
        if not 0 < self.max_position <= 1:
            raise ValueError("Maximum position must be in (0, 1]")
        if not 0 <= self.target_volatility <= 3:
            raise ValueError("Target volatility must be in [0, 3]; 0 disables volatility scaling")
        if not isinstance(self.volatility_window, int) or not 2 <= self.volatility_window <= 1000:
            raise ValueError("Volatility window must be an integer between 2 and 1000")
        if not 0 < self.max_drawdown <= 1:
            raise ValueError("Maximum drawdown must be in (0, 1]")
        if not 0 <= self.rebalance_threshold < 1:
            raise ValueError("Rebalance threshold must be in [0, 1)")


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict
    config: dict

    def payload(self) -> dict:
        equity = self.equity.reset_index()
        equity["date"] = equity["date"].dt.strftime("%Y-%m-%d")
        return {
            "metrics": self.metrics,
            "equity": equity.to_dict("records"),
            "trades": self.trades.to_dict("records"),
            "config": self.config,
        }

    def export(self, directory: str | Path) -> None:
        import json

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.equity.to_csv(directory / "equity.csv")
        self.trades.to_csv(directory / "trades.csv", index=False)
        (directory / "report.json").write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )


def run_backtest(
    bars: pd.DataFrame, strategy: StrategyConfig | None = None, config: BacktestConfig | None = None
) -> BacktestResult:
    bars = validate_bars(bars)
    strategy = strategy or StrategyConfig()
    config = config or BacktestConfig()
    signal = target_weights(bars, strategy)
    if config.target_volatility:
        vol = bars.close.pct_change(fill_method=None).rolling(
            config.volatility_window
        ).std() * np.sqrt(252)
        scale = (config.target_volatility / vol.replace(0, np.nan)).clip(upper=1)
        # A flat trailing market permits the position cap; an incomplete window does not.
        scale = scale.mask(vol == 0, 1).fillna(0)
        signal = signal * scale
    targets = (signal * config.max_position).shift(1).fillna(0)
    cash, quantity, cost_basis = config.initial_cash, 0.0, 0.0
    peak = config.initial_cash
    halted = False
    halt_date = None
    commission = config.commission_bps / 10_000
    slippage = config.slippage_bps / 10_000
    rows, trades = [], []
    for date, row in bars.iterrows():
        opening, close = float(row.open), float(row.close)
        equity_open = cash + quantity * opening
        target = 0.0 if halted else float(targets.loc[date])
        weight = quantity * opening / equity_open if equity_open > 0 else 0.0
        # Friction-aware sizing targets the post-fill portfolio weight, with no leverage.
        delta = 0.0
        if abs(target - weight) >= config.rebalance_threshold or (target == 0 and quantity > 0):
            if target > weight:
                friction = (1 + slippage) * (1 + commission) - 1
                delta = (target * equity_open - quantity * opening) / (
                    opening * (1 + target * friction)
                )
            elif target < weight:
                friction = 1 - (1 - slippage) * (1 - commission)
                delta = (target * equity_open - quantity * opening) / (
                    opening * (1 - target * friction)
                )
        if abs(delta) > 1e-10:
            side = "buy" if delta > 0 else "sell"
            price = opening * (1 + slippage if delta > 0 else 1 - slippage)
            if side == "buy":
                size = min(delta, cash / (price * (1 + commission)))
            else:
                size = min(-delta, quantity)
            fee = size * price * commission
            realized = None
            if side == "buy":
                cost_basis = (cost_basis * quantity + size * price + fee) / (quantity + size)
                cash -= size * price + fee
                quantity += size
            else:
                realized = size * (price - cost_basis) - fee
                cash += size * price - fee
                quantity -= size
                if quantity < 1e-10:
                    quantity, cost_basis = 0.0, 0.0
            cash = max(cash, 0.0)
            trades.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "side": side,
                    "quantity": size,
                    "price": price,
                    "fee": fee,
                    "slippage_cost": size * abs(price - opening),
                    "realized_pnl": realized,
                    "reason": "drawdown_stop" if halted else "rebalance",
                }
            )
        equity = cash + quantity * close
        peak = max(peak, equity)
        drawdown = equity / peak - 1
        if not halted and drawdown <= -config.max_drawdown:
            halted, halt_date = True, date.strftime("%Y-%m-%d")
        rows.append(
            {
                "date": date,
                "equity": equity,
                "cash": cash,
                "quantity": quantity,
                "close": close,
                "exposure": quantity * close / equity if equity else 0,
                "drawdown": drawdown,
                "halted": halted,
            }
        )
    curve = pd.DataFrame(rows).set_index("date")
    curve["benchmark"] = config.initial_cash * bars.close / bars.close.iloc[0]
    daily = curve.equity.pct_change(fill_method=None).dropna()
    total_return = curve.equity.iloc[-1] / config.initial_cash - 1
    annual_vol = float(daily.std(ddof=0) * np.sqrt(252))
    sells = [t["realized_pnl"] for t in trades if t["side"] == "sell"]
    metrics = {
        "initial_cash": config.initial_cash,
        "final_equity": float(curve.equity.iloc[-1]),
        "total_return": float(total_return),
        "annualized_return": float((1 + total_return) ** (252 / max(len(daily), 1)) - 1),
        "annualized_volatility": annual_vol,
        "sharpe_ratio": float(daily.mean() * 252 / annual_vol) if annual_vol > 1e-12 else 0.0,
        "max_drawdown": float(-curve.drawdown.min()),
        "benchmark_return": float(curve.benchmark.iloc[-1] / config.initial_cash - 1),
        "trade_count": len(trades),
        "sell_count": len(sells),
        "sell_win_rate": sum(pnl > 0 for pnl in sells) / len(sells) if sells else None,
        "total_fees": float(sum(t["fee"] for t in trades)),
        "total_slippage": float(sum(t["slippage_cost"] for t in trades)),
        "average_exposure": float(curve.exposure.mean()),
        "halt_date": halt_date,
        "bars": len(bars),
    }
    # Object dtype retains None for unrealized buy fills, ensuring strict JSON output.
    fills = pd.DataFrame(
        trades,
        columns=[
            "date",
            "side",
            "quantity",
            "price",
            "fee",
            "slippage_cost",
            "realized_pnl",
            "reason",
        ],
        dtype=object,
    )
    return BacktestResult(
        curve, fills, metrics, {"strategy": asdict(strategy), "execution": asdict(config)}
    )
