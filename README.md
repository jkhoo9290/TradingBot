# 资金费率做空机器人（Binance U 本位合约 / CCXT）

> 目标：资金费率 **为正且很高** 时，尝试进场做空以获取 funding；并通过“强制风控”把爆仓风险降到极低。
>
> 重要：任何策略都无法做到“绝对不会爆仓”。本项目通过 **隔离保证金 + 低杠杆 + 按止损距离算仓位 + 下单后必须成功挂止损 + 日内熔断** 等方式尽量避免极端风险（断网、插针、跳空、系统性故障仍可能导致超预期亏损）。

## 特性

- **触发条件**：资金费率（funding rate）高于阈值才允许开空
- **只做空**：默认策略只做空，不做多
- **硬风控**：
  - 隔离保证金（isolated）
  - 低杠杆（默认 3x）
  - 按“止损距离”计算仓位，单笔最大亏损固定为权益的 X%
  - 开仓后 **必须** 成功挂出 `STOP_MARKET`（reduceOnly），否则立即市价平仓
  - 日内最大亏损/最大回撤触发熔断：停止开新仓
- **默认 dry-run**：只打印拟执行动作，不会真实下单

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 配置（环境变量）

复制一份示例：

```bash
cp .env.example .env
```

然后在 `.env` 里填写：

- `BINANCE_API_KEY` / `BINANCE_API_SECRET`
- `DRY_RUN=true`（建议先保持 true）

## 运行

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python -m funding_short_bot.cli
```

## 策略逻辑（简述）

- **入场**：当 fundingRate >= `FUNDING_RATE_ENTRY` 且距离下一次结算小于 `ENTER_WINDOW_SECONDS` 时，允许开空
- **止损**：用 ATR 计算止损距离：`stop = entry + ATR * ATR_STOP_MULT`
- **仓位**：按风险预算 `equity * RISK_PER_TRADE` 计算数量：`qty = risk_usdt / (stop - entry)`
- **止盈**：默认 `TP_MULT` 倍 ATR（也可以关闭）
- **持仓管理**：可选移动止损（跟踪盈利后上移止损/保本）

## 重要提示

- 在你确认逻辑完全符合预期前，请一直保持 `DRY_RUN=true`。
- 真实交易前建议先把杠杆设为 1–3x，并把 `RISK_PER_TRADE` 设为 0.2%–1% 级别。

