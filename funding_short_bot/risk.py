from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionPlan:
    side: str  # 'sell' for short entry
    entry_price: float
    stop_price: float
    take_profit_price: float | None
    qty: float
    risk_usdt: float
    initial_margin_est_usdt: float


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def plan_short_by_atr(
    *,
    equity_usdt: float,
    risk_per_trade: float,
    max_initial_margin_pct: float,
    leverage: int,
    entry_price: float,
    atr: float,
    atr_stop_mult: float,
    tp_mult: float,
) -> PositionPlan:
    """
    - Short entry.
    - Stop above entry by ATR*mult.
    - Position size so that (stop-entry)*qty ~= risk_usdt.
    - Additionally cap initial margin to equity * max_initial_margin_pct.
    """
    if equity_usdt <= 0:
        raise ValueError("equity_usdt must be > 0")
    if leverage <= 0:
        raise ValueError("leverage must be > 0")
    if entry_price <= 0 or atr <= 0:
        raise ValueError("entry_price and atr must be > 0")

    risk_usdt = equity_usdt * clamp(risk_per_trade, 0.0, 1.0)
    stop_price = entry_price + atr * atr_stop_mult
    stop_distance = stop_price - entry_price
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0")

    qty_by_risk = risk_usdt / stop_distance  # in base coin (e.g. BTC)

    # Cap by max initial margin usage: notional/leverage <= equity * max_margin_pct
    max_margin = equity_usdt * clamp(max_initial_margin_pct, 0.0, 1.0)
    max_notional = max_margin * leverage
    qty_by_margin = max_notional / entry_price

    qty = min(qty_by_risk, qty_by_margin)
    if qty <= 0:
        raise ValueError("qty computed <= 0")

    initial_margin_est = (qty * entry_price) / leverage

    take_profit_price = None
    if tp_mult > 0:
        take_profit_price = max(0.0, entry_price - atr * tp_mult)
        if take_profit_price <= 0:
            take_profit_price = None

    return PositionPlan(
        side="sell",
        entry_price=entry_price,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        qty=qty,
        risk_usdt=risk_usdt,
        initial_margin_est_usdt=initial_margin_est,
    )

