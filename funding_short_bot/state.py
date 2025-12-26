from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_date_str(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(ts or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


@dataclass
class BotState:
    day: str
    day_start_equity: float
    circuit_breaker: bool

    @staticmethod
    def fresh(equity: float) -> "BotState":
        return BotState(day=_utc_date_str(), day_start_equity=equity, circuit_breaker=False)


def load_state(path: str, equity_fallback: float) -> BotState:
    if not os.path.exists(path):
        return BotState.fresh(equity_fallback)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        st = BotState(
            day=str(raw.get("day", _utc_date_str())),
            day_start_equity=float(raw.get("day_start_equity", equity_fallback)),
            circuit_breaker=bool(raw.get("circuit_breaker", False)),
        )
        # new day reset
        today = _utc_date_str()
        if st.day != today:
            return BotState.fresh(equity_fallback)
        return st
    except Exception:
        return BotState.fresh(equity_fallback)


def save_state(path: str, state: BotState) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "day": state.day,
                "day_start_equity": state.day_start_equity,
                "circuit_breaker": state.circuit_breaker,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(tmp, path)

