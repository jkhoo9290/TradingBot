from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .config import BotConfig
from .exchange import BybitExchange
from .indicators import compute_atr_from_ohlcv
from .risk import plan_short_by_atr
from .state import BotState, load_state, save_state


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.4f}%"


def _round_qty(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step


class FundingShortBot:
    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg
        self._effective_testnet = cfg.bybit_testnet
        self.ex = BybitExchange(
            api_key=cfg.bybit_api_key,
            api_secret=cfg.bybit_api_secret,
            testnet=cfg.bybit_testnet,
        )
        try:
            self.ex.load_markets()
        except Exception as e:
            # Some environments are blocked from Bybit testnet via CloudFront geo rules.
            # Fall back to mainnet for "internal testing" (dry-run/public data) instead of crashing.
            if cfg.bybit_testnet:
                print(f"[warn] bybit testnet unreachable ({e}); falling back to mainnet endpoints")
                self._effective_testnet = False
                self.ex = BybitExchange(
                    api_key=cfg.bybit_api_key,
                    api_secret=cfg.bybit_api_secret,
                    testnet=False,
                )
                self.ex.load_markets()
            else:
                raise

    def _fetch_equity_safe(self) -> float:
        # In dry-run / no key mode, fallback to a dummy equity to allow planning/logging.
        if self.cfg.dry_run and (not self.cfg.bybit_api_key or not self.cfg.bybit_api_secret):
            return 1000.0
        return self.ex.fetch_equity_usdt()

    def _daily_circuit_breaker_check(self, equity: float, st: BotState) -> BotState:
        if st.day_start_equity <= 0:
            st.day_start_equity = equity
        dd = (equity - st.day_start_equity) / st.day_start_equity
        if dd <= -abs(self.cfg.daily_max_loss_pct):
            st.circuit_breaker = True
        return st

    def decide(self) -> tuple[Decision, dict]:
        funding = self.ex.fetch_funding(self.cfg.symbol)
        ttf = self.ex.time_to_next_funding_seconds(funding.next_funding_time_ms)
        last_price = self.ex.fetch_last_price(self.cfg.symbol)

        equity = self._fetch_equity_safe()
        st = load_state(self.cfg.state_path, equity_fallback=equity)
        st = self._daily_circuit_breaker_check(equity, st)
        save_state(self.cfg.state_path, st)

        # If can't query positions (no key), we assume flat and only log.
        pos = 0.0
        if self.cfg.bybit_api_key and self.cfg.bybit_api_secret and not self.cfg.dry_run:
            pos = self.ex.fetch_position_size(self.cfg.symbol)
        elif self.cfg.bybit_api_key and self.cfg.bybit_api_secret and self.cfg.dry_run:
            # dry-run with key still can query positions
            try:
                pos = self.ex.fetch_position_size(self.cfg.symbol)
            except Exception:
                pos = 0.0

        ctx = {
            "funding_rate": funding.funding_rate,
            "next_funding_time_ms": funding.next_funding_time_ms,
            "time_to_next_funding_s": ttf,
            "last_price": last_price,
            "equity_usdt": equity,
            "position_size": pos,
            "circuit_breaker": st.circuit_breaker,
        }

        # No new entries if circuit breaker is on
        if st.circuit_breaker:
            return Decision(action="hold", reason="daily circuit breaker active"), ctx

        # If in position (short), consider exit conditions
        if pos < 0:
            if funding.funding_rate <= self.cfg.funding_rate_exit:
                return Decision(action="exit", reason=f"funding cooled to {_fmt_pct(funding.funding_rate)}"), ctx
            return Decision(action="hold", reason="short open; waiting"), ctx

        # Flat: check entry conditions
        if funding.funding_rate < self.cfg.funding_rate_entry:
            return Decision(action="hold", reason=f"funding {_fmt_pct(funding.funding_rate)} < entry"), ctx

        if ttf is not None and ttf > self.cfg.enter_window_seconds:
            return Decision(action="hold", reason=f"too early before funding (ttf={ttf}s)"), ctx

        return Decision(action="enter_short", reason=f"funding high {_fmt_pct(funding.funding_rate)}"), ctx

    def execute_once(self) -> None:
        decision, ctx = self.decide()

        print(
            f"[status] price={ctx['last_price']:.2f}  funding={_fmt_pct(ctx['funding_rate'])}  "
            f"ttf={ctx['time_to_next_funding_s']}s  equity={ctx['equity_usdt']:.2f}  "
            f"pos={ctx['position_size']}  dry_run={self.cfg.dry_run} testnet={self._effective_testnet}"
        )
        print(f"[decision] {decision.action}: {decision.reason}")

        if decision.action == "hold":
            return

        if decision.action == "exit":
            if self.cfg.dry_run:
                print("[dry-run] would close short position (market buy reduceOnly)")
                return
            pos = float(ctx["position_size"])
            qty_to_close = abs(pos)
            if qty_to_close <= 0:
                print("[warn] exit requested but position size is 0")
                return
            self.ex.place_market_buy_to_close(self.cfg.symbol, qty_to_close)
            print("[live] close order sent")
            return

        if decision.action != "enter_short":
            return

        # Build ATR plan (public data)
        ohlcv = self.ex.fetch_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=max(200, self.cfg.atr_period + 5))
        atr_res = compute_atr_from_ohlcv(ohlcv, period=self.cfg.atr_period)
        entry_price = float(ctx["last_price"])

        plan = plan_short_by_atr(
            equity_usdt=float(ctx["equity_usdt"]),
            risk_per_trade=self.cfg.risk_per_trade,
            max_initial_margin_pct=self.cfg.max_initial_margin_pct,
            leverage=self.cfg.leverage,
            entry_price=entry_price,
            atr=atr_res.atr,
            atr_stop_mult=self.cfg.atr_stop_mult,
            tp_mult=self.cfg.tp_mult,
        )

        # Round qty to market lot step if available
        mkt = self.ex.raw.market(self.cfg.symbol)
        step = float(mkt.get("precision", {}).get("amount") or 0.0)
        # CCXT precision is decimal digits, not step. Prefer limits/lotSize if present.
        lot_step = None
        if "limits" in mkt and isinstance(mkt["limits"], dict):
            amt = mkt["limits"].get("amount", {})
            if isinstance(amt, dict):
                lot_step = amt.get("min")
        qty = plan.qty
        if lot_step is not None and isinstance(lot_step, (int, float)) and lot_step > 0:
            qty = _round_qty(qty, float(lot_step))

        print(
            f"[plan] qty={qty:.6f}  entry~{plan.entry_price:.2f}  stop={plan.stop_price:.2f}  "
            f"tp={plan.take_profit_price if plan.take_profit_price else 'off'}  "
            f"risk~{plan.risk_usdt:.2f}USDT  init_margin~{plan.initial_margin_est_usdt:.2f}USDT  "
            f"atr={atr_res.atr:.2f}"
        )

        if self.cfg.dry_run:
            print("[dry-run] would: set isolated+leverage, market sell, then place reduceOnly stop-market buy")
            return

        # Live: enforce leverage & isolated
        self.ex.set_leverage_and_margin_mode(self.cfg.symbol, self.cfg.leverage)

        # Entry
        self.ex.place_market_short(self.cfg.symbol, qty)
        print("[live] entry order sent")

        # Hard stop (must succeed, otherwise close immediately)
        try:
            self.ex.place_stop_market_buy_to_close(self.cfg.symbol, qty, plan.stop_price)
            print("[live] stop order placed")
        except Exception as e:
            print(f"[risk] failed to place stop; emergency close. err={e}")
            try:
                self.ex.place_market_buy_to_close(self.cfg.symbol, qty)
            finally:
                raise

        # Optional TP
        if plan.take_profit_price is not None:
            try:
                self.ex.place_take_profit_market_buy_to_close(self.cfg.symbol, qty, plan.take_profit_price)
                print("[live] take-profit order placed")
            except Exception as e:
                print(f"[warn] failed to place take-profit (continuing with stop only). err={e}")

    def run_forever(self) -> None:
        while True:
            try:
                self.execute_once()
            except Exception as e:
                print(f"[error] {e}")
            time.sleep(self.cfg.poll_seconds)

