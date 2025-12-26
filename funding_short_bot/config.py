from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _get_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else raw


@dataclass(frozen=True)
class BotConfig:
    # Exchange (Bybit)
    bybit_api_key: str
    bybit_api_secret: str
    bybit_testnet: bool

    # Safety
    dry_run: bool

    # Market
    symbol: str
    timeframe: str
    leverage: int

    # Funding strategy
    funding_rate_entry: float
    funding_rate_exit: float
    enter_window_seconds: int

    # Risk
    risk_per_trade: float
    max_initial_margin_pct: float
    daily_max_loss_pct: float

    # ATR / Stops
    atr_period: int
    atr_stop_mult: float
    tp_mult: float
    enable_trail: bool
    trail_after_r_mult: float
    trail_stop_r_mult: float

    # Loop
    poll_seconds: int

    # State
    state_path: str

    # Offline mode (no network)
    offline_mode: bool


def load_config() -> BotConfig:
    return BotConfig(
        bybit_api_key=_get_str("BYBIT_API_KEY", ""),
        bybit_api_secret=_get_str("BYBIT_API_SECRET", ""),
        bybit_testnet=_get_bool("BYBIT_TESTNET", True),
        dry_run=_get_bool("DRY_RUN", True),
        symbol=_get_str("SYMBOL", "BTC/USDT:USDT"),
        timeframe=_get_str("TIMEFRAME", "5m"),
        leverage=_get_int("LEVERAGE", 3),
        funding_rate_entry=_get_float("FUNDING_RATE_ENTRY", 0.0005),
        funding_rate_exit=_get_float("FUNDING_RATE_EXIT", 0.0002),
        enter_window_seconds=_get_int("ENTER_WINDOW_SECONDS", 1800),
        risk_per_trade=_get_float("RISK_PER_TRADE", 0.005),
        max_initial_margin_pct=_get_float("MAX_INITIAL_MARGIN_PCT", 0.25),
        daily_max_loss_pct=_get_float("DAILY_MAX_LOSS_PCT", 0.03),
        atr_period=_get_int("ATR_PERIOD", 14),
        atr_stop_mult=_get_float("ATR_STOP_MULT", 2.0),
        tp_mult=_get_float("TP_MULT", 3.0),
        enable_trail=_get_bool("ENABLE_TRAIL", True),
        trail_after_r_mult=_get_float("TRAIL_AFTER_R_MULT", 1.0),
        trail_stop_r_mult=_get_float("TRAIL_STOP_R_MULT", 0.5),
        poll_seconds=_get_int("POLL_SECONDS", 15),
        state_path=_get_str("STATE_PATH", "./bot_state.json"),
        offline_mode=_get_bool("OFFLINE_MODE", False),
    )

