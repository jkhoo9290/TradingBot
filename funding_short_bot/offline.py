from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from .indicators import compute_atr_from_ohlcv
from .risk import plan_short_by_atr


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class OfflineTick:
    ohlcv: list[list[float]]  # [ms, o, h, l, c, v]
    last_price: float
    funding_rate: float
    next_funding_time_ms: int | None


def generate_demo_tick(symbol: str, timeframe: str, *, atr_period: int) -> OfflineTick:
    """
    Generates synthetic OHLCV + a "high funding" situation for internal testing
    when Bybit endpoints are unreachable from the current environment.
    """
    # Build a random walk around 100_000
    start = 100_000.0
    bars = max(200, atr_period + 5)
    ts0 = _now_ms() - bars * 60_000
    price = start
    ohlcv: list[list[float]] = []
    for i in range(bars):
        o = price
        delta = random.uniform(-120.0, 120.0)
        c = max(1.0, o + delta)
        h = max(o, c) + random.uniform(0.0, 60.0)
        l = min(o, c) - random.uniform(0.0, 60.0)
        v = random.uniform(10.0, 50.0)
        ohlcv.append([ts0 + i * 60_000, o, h, l, c, v])
        price = c

    last_price = float(ohlcv[-1][4])
    # Simulate high positive funding (0.08%) with funding in 10 minutes
    funding_rate = 0.0008
    next_funding_time_ms = _now_ms() + 10 * 60_000
    return OfflineTick(
        ohlcv=ohlcv,
        last_price=last_price,
        funding_rate=funding_rate,
        next_funding_time_ms=next_funding_time_ms,
    )


def offline_plan_preview(
    *,
    equity_usdt: float,
    leverage: int,
    risk_per_trade: float,
    max_initial_margin_pct: float,
    atr_period: int,
    atr_stop_mult: float,
    tp_mult: float,
) -> dict:
    tick = generate_demo_tick("BTC/USDT:USDT", "5m", atr_period=atr_period)
    atr_res = compute_atr_from_ohlcv(tick.ohlcv, period=atr_period)
    plan = plan_short_by_atr(
        equity_usdt=equity_usdt,
        risk_per_trade=risk_per_trade,
        max_initial_margin_pct=max_initial_margin_pct,
        leverage=leverage,
        entry_price=tick.last_price,
        atr=atr_res.atr,
        atr_stop_mult=atr_stop_mult,
        tp_mult=tp_mult,
    )
    return {
        "price": tick.last_price,
        "funding_rate": tick.funding_rate,
        "next_funding_in_s": max(0, int((tick.next_funding_time_ms - _now_ms()) / 1000)),
        "atr": atr_res.atr,
        "qty": plan.qty,
        "stop": plan.stop_price,
        "tp": plan.take_profit_price,
        "risk_usdt": plan.risk_usdt,
        "init_margin_est_usdt": plan.initial_margin_est_usdt,
        "liquidation_note": "demo only; real liquidation depends on Bybit maintenance margin + mark price",
    }


def round6(x: float) -> float:
    return math.floor(x * 1e6) / 1e6

