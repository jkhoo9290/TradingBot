from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AtrResult:
    atr: float
    last_close: float


def compute_atr_from_ohlcv(ohlcv: list[list[float]], period: int) -> AtrResult:
    """
    ohlcv: list of [ms, open, high, low, close, volume]
    """
    if len(ohlcv) < period + 2:
        raise ValueError(f"Not enough OHLCV to compute ATR: have {len(ohlcv)}, need {period + 2}")

    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    atr = float(tr.rolling(window=period).mean().iloc[-1])
    last_close = float(close.iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        raise ValueError(f"ATR invalid: {atr}")
    return AtrResult(atr=atr, last_close=last_close)

