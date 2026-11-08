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
            raise ValueError("未知策略")
        if any(
            isinstance(v, bool) or not isinstance(v, int) or not 2 <= v <= 1000
            for v in (self.fast, self.slow, self.lookback)
        ):
            raise ValueError("策略窗口必须为 2 至 1000 的整数")
        if self.fast >= self.slow:
            raise ValueError("快速窗口必须小于慢速窗口")
        if not np.isfinite(self.entry_z) or not 0 < self.entry_z <= 10:
            raise ValueError("均值回归入场阈值必须在 (0, 10] 内")


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
