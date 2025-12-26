from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import ccxt


@dataclass(frozen=True)
class FundingInfo:
    funding_rate: float
    next_funding_time_ms: int | None


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


class BybitExchange:
    def __init__(self, *, api_key: str, api_secret: str, testnet: bool) -> None:
        self._ex = ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {
                    # USDT perpetual
                    "defaultType": "swap",
                    # keep unified margin behavior
                    "defaultSubType": "linear",
                    # Avoid hitting spot instruments endpoints (testnet often blocks /v5 spot)
                    "fetchMarkets": {"types": ["linear"]},
                },
            }
        )
        if testnet:
            # CCXT supports sandbox mode for Bybit
            self._ex.set_sandbox_mode(True)

    @property
    def raw(self) -> ccxt.bybit:
        return self._ex

    def load_markets(self) -> None:
        self._ex.load_markets()

    def fetch_last_price(self, symbol: str) -> float:
        t = self._ex.fetch_ticker(symbol)
        last = t.get("last")
        if last is None:
            raise RuntimeError(f"ticker.last missing for {symbol}: {t}")
        return float(last)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return self._ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_funding(self, symbol: str) -> FundingInfo:
        info: dict[str, Any] = self._ex.fetch_funding_rate(symbol)
        # unified keys: fundingRate, nextFundingTimestamp (ms)
        fr = info.get("fundingRate")
        if fr is None:
            # try raw info fallback
            fr = info.get("info", {}).get("fundingRate")
        funding_rate = float(fr)
        nft = info.get("nextFundingTimestamp")
        if nft is None:
            nft = info.get("info", {}).get("nextFundingTime")
        next_funding_time_ms = int(nft) if nft is not None else None
        return FundingInfo(funding_rate=funding_rate, next_funding_time_ms=next_funding_time_ms)

    def time_to_next_funding_seconds(self, next_funding_time_ms: int | None) -> int | None:
        if next_funding_time_ms is None:
            return None
        return max(0, int((next_funding_time_ms - _now_ms()) / 1000))

    # ---------- private account / trading ----------
    def fetch_equity_usdt(self) -> float:
        """
        Best-effort equity for USDT perpetual account.
        """
        bal = self._ex.fetch_balance()
        total = bal.get("total", {})
        # Prefer USDT total equity if present
        if isinstance(total, dict) and "USDT" in total and total["USDT"] is not None:
            return float(total["USDT"])
        # fallback: try free+used
        usdt = bal.get("USDT", {})
        if isinstance(usdt, dict):
            t = usdt.get("total")
            if t is not None:
                return float(t)
        raise RuntimeError(f"Cannot determine USDT equity from balance: keys={list(bal.keys())}")

    def set_leverage_and_margin_mode(self, symbol: str, leverage: int) -> None:
        # isolated margin
        try:
            self._ex.set_margin_mode("isolated", symbol)
        except Exception:
            # some accounts / endpoints may not support unified margin mode setting via ccxt
            pass
        try:
            self._ex.set_leverage(leverage, symbol)
        except Exception:
            pass

    def fetch_position_size(self, symbol: str) -> float:
        """
        Returns signed contracts in base units when available:
        - >0 for long, <0 for short, 0 for flat.
        """
        try:
            positions = self._ex.fetch_positions([symbol])
        except Exception:
            # fallback to risk-free: assume flat if cannot query
            return 0.0
        for p in positions or []:
            if p.get("symbol") != symbol:
                continue
            contracts = p.get("contracts")
            side = p.get("side")
            if contracts is None:
                continue
            qty = float(contracts)
            if side == "short":
                return -abs(qty)
            if side == "long":
                return abs(qty)
            # sometimes side missing but qty sign may exist
            return float(p.get("contractSize", 1)) * qty
        return 0.0

    def place_market_short(self, symbol: str, qty: float) -> dict[str, Any]:
        return self._ex.create_order(symbol, "market", "sell", qty, None, {})

    def place_market_buy_to_close(self, symbol: str, qty: float) -> dict[str, Any]:
        return self._ex.create_order(symbol, "market", "buy", qty, None, {"reduceOnly": True})

    def place_stop_market_buy_to_close(self, symbol: str, qty: float, stop_price: float) -> dict[str, Any]:
        """
        Place a stop-market to close a short.
        CCXT unified: use "stopPrice" on a market order and reduceOnly.
        """
        params = {
            "stopPrice": float(stop_price),
            "reduceOnly": True,
        }
        return self._ex.create_order(symbol, "market", "buy", qty, None, params)

    def place_take_profit_market_buy_to_close(self, symbol: str, qty: float, take_profit_price: float) -> dict[str, Any]:
        params = {
            "stopPrice": float(take_profit_price),
            "reduceOnly": True,
        }
        return self._ex.create_order(symbol, "market", "buy", qty, None, params)

