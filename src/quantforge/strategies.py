"""Signals use only information available at the current close."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    name: str = "trend"
    fast: int = 20
    slow: int = 60
    lookback: int = 20
    entry_z: float = 1.5

    def __post_init__(self):
        if self.name not in {"trend", "momentum", "mean_reversion"}:
            raise ValueError("Unknown strategy")
        if any(
            isinstance(v, bool) or not isinstance(v, int) or not 2 <= v <= 1000
            for v in (self.fast, self.slow, self.lookback)
        ):
            raise ValueError("Strategy windows must be integers between 2 and 1000")
        if self.fast >= self.slow:
            raise ValueError("Fast window must be smaller than slow window")
        if not np.isfinite(self.entry_z) or not 0 < self.entry_z <= 10:
            raise ValueError("Mean reversion entry threshold must be in (0, 10]")


def target_weights(bars: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    close = bars.close
    if config.name == "trend":
        fast = close.rolling(config.fast).mean()
        slow = close.rolling(config.slow).mean()
        result = (fast > slow).astype(float)
    elif config.name == "momentum":
        result = (close.pct_change(config.lookback, fill_method=None) > 0).astype(float)
    else:
        mean = close.rolling(config.lookback).mean()
        std = close.rolling(config.lookback).std().replace(0, np.nan)
        z = (close - mean) / std
        holding = False
        values = []
        for value in z:
            if pd.isna(value):
                holding = False
            elif value < -config.entry_z:
                holding = True
            elif value >= 0:
                holding = False
            values.append(float(holding))
        result = pd.Series(values, index=bars.index)
    return result.rename("target_weight")
