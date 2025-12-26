from __future__ import annotations

import argparse
import os

from .bot import FundingShortBot
from .config import load_config
from .offline import offline_plan_preview, round6


def main() -> None:
    p = argparse.ArgumentParser(description="Bybit funding-rate short bot (testnet friendly)")
    p.add_argument("--once", action="store_true", help="run one decision cycle and exit")
    p.add_argument("--live", action="store_true", help="override DRY_RUN=false for this run")
    p.add_argument("--offline-demo", action="store_true", help="no network; generate a synthetic high-funding tick and print plan")
    args = p.parse_args()

    if args.live:
        os.environ["DRY_RUN"] = "false"

    cfg = load_config()

    if args.offline_demo or cfg.offline_mode:
        preview = offline_plan_preview(
            equity_usdt=1000.0,
            leverage=cfg.leverage,
            risk_per_trade=cfg.risk_per_trade,
            max_initial_margin_pct=cfg.max_initial_margin_pct,
            atr_period=cfg.atr_period,
            atr_stop_mult=cfg.atr_stop_mult,
            tp_mult=cfg.tp_mult,
        )
        tp = preview["tp"]
        tp_str = f"{tp:.2f}" if tp is not None else "off"
        print(
            "[offline-demo] "
            f"price={preview['price']:.2f} funding={preview['funding_rate']*100:.4f}% "
            f"next_funding_in={preview['next_funding_in_s']}s atr={preview['atr']:.2f}"
        )
        print(
            "[offline-demo] "
            f"qty={round6(preview['qty'])} stop={preview['stop']:.2f} "
            f"tp={tp_str} "
            f"risk≈{preview['risk_usdt']:.2f}USDT init_margin≈{preview['init_margin_est_usdt']:.2f}USDT"
        )
        return

    bot = FundingShortBot(cfg)

    if args.once:
        bot.execute_once()
    else:
        bot.run_forever()


if __name__ == "__main__":
    main()

