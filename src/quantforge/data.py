"""Strict daily OHLCV validation and interchangeable data sources."""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]
SYMBOL_PATTERN = r"[A-Za-z0-9^][A-Za-z0-9.^=_-]{0,19}"


def validate_symbol(symbol: str) -> str:
    if not re.fullmatch(SYMBOL_PATTERN, symbol):
        raise ValueError("代码只能包含字母、数字及 . ^ = _ -，长度不超过 20")
    return symbol.upper()


def validate_bars(frame: pd.DataFrame) -> pd.DataFrame:
    bars = frame.copy()
    bars.columns = [str(c).strip().lower() for c in bars.columns]
    if bars.columns.duplicated().any():
        raise ValueError("行情列名不能重复")
    if "date" in bars.columns:
        bars.index = pd.to_datetime(bars.pop("date"), errors="raise", utc=True)
    elif not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("行情需要 date 列或 DatetimeIndex")
    if bars.index.isna().any():
        raise ValueError("行情日期不能缺失")
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(None).normalize()
    bars.index.name = "date"
    if bars.index.duplicated().any():
        raise ValueError("日线行情不允许重复日期")
    missing = set(COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"行情缺少字段: {', '.join(sorted(missing))}")
    bars = bars[COLUMNS].sort_index().astype(float)
    if len(bars) < 2 or len(bars) > 100_000:
        raise ValueError("行情需要 2 至 100000 行")
    if not np.isfinite(bars.to_numpy()).all():
        raise ValueError("行情不能包含空值或无穷值")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("价格必须为正数")
    if (bars.volume < 0).any():
        raise ValueError("成交量不能为负数")
    if (
        (bars.high < bars[["open", "close", "low"]].max(axis=1))
        | (bars.low > bars[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("OHLC 高低价关系不合法")
    return bars


def read_csv(source: str | Path | io.StringIO) -> pd.DataFrame:
    return validate_bars(pd.read_csv(source))


def demo_bars(periods: int = 756, seed: int = 42) -> pd.DataFrame:
    """Synthetic data, never presented as a real security's history."""
    if not 2 <= periods <= 10_000:
        raise ValueError("演示行情长度应为 2 至 10000")
    rng = np.random.default_rng(seed)
    cycle = np.sin(np.arange(periods) / 65) * 0.0014
    returns = rng.normal(0.00035 + cycle, 0.012, periods)
    close = 100 * np.exp(np.cumsum(returns))
    previous = np.r_[100, close[:-1]]
    opening = previous * np.exp(rng.normal(0, 0.003, periods))
    spread = rng.uniform(0.002, 0.015, periods)
    return validate_bars(
        pd.DataFrame(
            {
                "open": opening,
                "high": np.maximum(opening, close) * (1 + spread),
                "low": np.minimum(opening, close) * (1 - spread),
                "close": close,
                "volume": rng.integers(1_000_000, 8_000_000, periods),
            },
            index=pd.bdate_range(end="2025-12-31", periods=periods),
        )
    )


def yahoo_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Adjusted OHLC; end is exclusive according to Yahoo's API."""
    import yfinance as yf

    symbol = validate_symbol(symbol)
    if pd.Timestamp(start) >= pd.Timestamp(end):
        raise ValueError("开始日期必须早于结束日期")
    bars = yf.download(
        symbol, start=start, end=end, auto_adjust=True, progress=False, threads=False, timeout=20
    )
    if bars.empty:
        raise ValueError("未取得 Yahoo 行情，请检查代码、日期和网络，或使用 CSV")
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.get_level_values(0)
    return validate_bars(bars)
