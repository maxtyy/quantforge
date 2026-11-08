import json

import numpy as np
import pandas as pd
import pytest

from quantforge.data import demo_bars, validate_bars
from quantforge.engine import BacktestConfig, run_backtest
from quantforge.strategies import StrategyConfig, target_weights


def bars_from_prices(prices, openings=None):
    close = np.array(prices, dtype=float)
    opening = close if openings is None else np.array(openings, dtype=float)
    return pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, close),
            "low": np.minimum(opening, close),
            "close": close,
            "volume": 1000,
        },
        index=pd.bdate_range("2024-01-01", periods=len(close)),
    )


def execution(**kwargs):
    return BacktestConfig(
        **{
            "commission_bps": 0,
            "slippage_bps": 0,
            "target_volatility": 0,
            "max_position": 1,
            "rebalance_threshold": 0,
            "max_drawdown": 1,
            **kwargs,
        }
    )


def test_signal_is_executed_at_next_open():
    bars = bars_from_prices([10, 11, 12, 20, 21], [10, 10, 11, 15, 20])
    result = run_backtest(bars, StrategyConfig(fast=2, slow=3), execution())
    assert result.trades.iloc[0].date == "2024-01-04"
    assert result.trades.iloc[0].price == 15
    assert result.equity.iloc[2].quantity == 0
    assert result.metrics["final_equity"] == pytest.approx(100_000 / 15 * 21)


@pytest.mark.parametrize("name", ["trend", "momentum", "mean_reversion"])
def test_future_data_cannot_change_past_signals_or_fills(name):
    bars = demo_bars(300)
    changed = bars.copy()
    changed.loc[changed.index[200] :, ["open", "high", "low", "close"]] *= 3
    strategy = StrategyConfig(name=name)
    pd.testing.assert_series_equal(
        target_weights(bars, strategy).iloc[:200], target_weights(changed, strategy).iloc[:200]
    )
    first = run_backtest(bars, strategy)
    second = run_backtest(changed, strategy)
    pd.testing.assert_frame_equal(first.equity.iloc[:200], second.equity.iloc[:200])


def test_fees_slippage_and_cash_accounting():
    bars = bars_from_prices([10, 11, 12, 12])
    result = run_backtest(
        bars, StrategyConfig(fast=2, slow=3), execution(commission_bps=10, slippage_bps=20)
    )
    trade = result.trades.iloc[0]
    expected_price = 12 * 1.002
    expected_size = 100_000 / (expected_price * 1.001)
    assert trade.price == pytest.approx(expected_price)
    assert trade.quantity == pytest.approx(expected_size)
    assert result.equity.iloc[-1].cash == pytest.approx(0, abs=1e-8)
    assert result.metrics["final_equity"] == pytest.approx(expected_size * 12)
    assert result.metrics["total_fees"] + result.metrics["total_slippage"] == pytest.approx(
        100_000 - result.metrics["final_equity"]
    )


def test_drawdown_liquidates_next_open_and_never_reenters():
    bars = bars_from_prices([10, 11, 12, 15, 9, 8, 20, 30], [10, 11, 12, 12, 15, 7, 8, 20])
    result = run_backtest(bars, StrategyConfig(fast=2, slow=3), execution(max_drawdown=0.2))
    assert result.metrics["halt_date"] == "2024-01-05"
    stop = result.trades[result.trades.reason == "drawdown_stop"].iloc[0]
    assert stop.date == "2024-01-08"
    assert stop.price == 7
    assert result.equity.iloc[5:].quantity.eq(0).all()
    assert result.metrics["max_drawdown"] > 0.2  # Gaps can exceed the configured trigger.


def test_flat_data_no_trades_finite_metrics(tmp_path):
    result = run_backtest(bars_from_prices([10] * 80))
    assert result.metrics["trade_count"] == 0
    assert result.metrics["sharpe_ratio"] == 0
    assert result.metrics["sell_win_rate"] is None
    result.export(tmp_path)
    json.loads((tmp_path / "report.json").read_text())


def test_long_only_and_equity_identity():
    result = run_backtest(demo_bars())
    curve = result.equity
    assert curve.cash.min() >= 0
    assert curve.quantity.min() >= 0
    np.testing.assert_allclose(curve.equity, curve.cash + curve.quantity * curve.close)
    json.dumps(result.payload(), allow_nan=False)


@pytest.mark.parametrize("mutation", ["duplicate", "nan", "invalid_ohlc", "negative_volume"])
def test_invalid_data_is_rejected(mutation):
    bars = demo_bars(5)
    if mutation == "duplicate":
        bars = pd.concat([bars, bars.iloc[:1]])
    elif mutation == "nan":
        bars.iloc[0, 0] = np.nan
    elif mutation == "invalid_ohlc":
        bars.iloc[0, 1] = 1
    else:
        bars.iloc[0, 4] = -1
    with pytest.raises(ValueError):
        validate_bars(bars)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_cash": 0},
        {"commission_bps": -1},
        {"slippage_bps": float("nan")},
        {"max_position": 2},
    ],
)
def test_invalid_execution_config(kwargs):
    with pytest.raises(ValueError):
        BacktestConfig(**kwargs)
