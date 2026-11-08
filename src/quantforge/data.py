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
        raise ValueError(
            "Symbols may contain only letters, digits, and . ^ = _ -, with a maximum length of 20"
        )
    return symbol.upper()


def validate_bars(frame: pd.DataFrame) -> pd.DataFrame:
    bars = frame.copy()
    bars.columns = [str(c).strip().lower() for c in bars.columns]
    if bars.columns.duplicated().any():
        raise ValueError("Market data column names must be unique")
    if "date" in bars.columns:
        bars.index = pd.to_datetime(bars.pop("date"), errors="raise", utc=True)
    elif not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("Market data requires a date column or DatetimeIndex")
    if bars.index.isna().any():
        raise ValueError("Market data dates must not be missing")
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert(None).normalize()
    bars.index.name = "date"
    if bars.index.duplicated().any():
        raise ValueError("Daily market data must not contain duplicate dates")
    missing = set(COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"Missing market data fields: {', '.join(sorted(missing))}")
    bars = bars[COLUMNS].sort_index().astype(float)
    if len(bars) < 2 or len(bars) > 100_000:
        raise ValueError("Market data must contain between 2 and 100000 rows")
    if not np.isfinite(bars.to_numpy()).all():
        raise ValueError("Market data must not contain missing or infinite values")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Prices must be positive")
    if (bars.volume < 0).any():
        raise ValueError("Volume must not be negative")
    if (
        (bars.high < bars[["open", "close", "low"]].max(axis=1))
        | (bars.low > bars[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("Invalid OHLC high/low price relationships")
    return bars


def read_csv(source: str | Path | io.StringIO) -> pd.DataFrame:
    return validate_bars(pd.read_csv(source))


def demo_bars(periods: int = 756, seed: int = 42) -> pd.DataFrame:
    """Synthetic data, never presented as a real security's history."""
    if not 2 <= periods <= 10_000:
        raise ValueError("Demo data must contain between 2 and 10000 rows")
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
        raise ValueError("Start date must be before end date")
    bars = yf.download(
        symbol, start=start, end=end, auto_adjust=True, progress=False, threads=False, timeout=20
    )
    if bars.empty:
        raise ValueError(
            "No Yahoo data received. Check the symbol, dates, and network, or import a CSV file"
        )
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.get_level_values(0)
    return validate_bars(bars)
