#!/usr/bin/env python3
"""
NostalgiaForInfinity-inspired Hyperliquid auto trader.

This is the active standalone trading script.

Notes:
- This is an adaptation of NFI concepts to Hyperliquid futures flow.
- It is NOT a byte-for-byte port of the original Freqtrade strategy.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import requests
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
LOG_DIR = WORKSPACE_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "main_wallet": "",
    "api_wallet": "",
    "api_private_key": os.getenv("HL_API_KEY", ""),
    "symbols": ["BTC", "ETH"],
    "timeframe": "1h",
    "max_leverage": 3,
    "default_leverage": 2,
    "max_position_usd": 294,
    "min_order_value": 10,
    "check_interval": 60,
    "trade_cooldown": 14400,  # 4h，对齐收益最优组合的冷却设置
    "trade_side": "both",  # both / long_only / short_only（全局默认）
    "trade_side_by_symbol": {"BTC": "short_only", "ETH": "both"},  # 按币种覆盖
    "maker_fee": 0.0001,
    "taker_fee": 0.00035,
    "min_profit_after_fee": 0.005,
}

# NFI-style parameters (default + optional per-symbol overrides)
NFI_DEFAULTS = {
    "ema_fast": 20,
    "ema_trend": 50,
    "ema_long": 200,
    "rsi_fast": 4,
    "rsi_main": 14,
    "atr_period": 14,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "volume_sma_period": 30,
    "rsi_fast_buy": 23.0,
    "rsi_main_buy": 36.0,
    "bb_touch_buffer": 1.01,
    "ema_pullback_buffer": 0.985,
    "regime_price_floor": 0.95,
    "max_breakdown_pct": 0.10,
    "enable_short": True,
    "rsi_fast_sell": 79.0,
    "rsi_main_sell": 62.0,
    "bb_reject_buffer": 0.99,
    "ema_bounce_buffer": 1.015,
    "regime_price_ceiling": 1.05,
    "max_breakout_pct": 0.10,
    "min_volume_ratio": 0.65,
    "stop_loss_atr_mult": 2.4,
    "take_profit_atr_mult": 4.0,
}

NFI_SYMBOL_OVERRIDES = {
    "ETH": {
        "rsi_fast_buy": 21.0,
        "rsi_main_buy": 34.0,
        "rsi_fast_sell": 75.0,
        "rsi_main_sell": 62.0,
        "stop_loss_atr_mult": 2.8,
        "take_profit_atr_mult": 2.8,
    }
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_nfi.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("NFITrader")


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * multiplier + out[-1] * (1 - multiplier))
    return out


def sma(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out: List[float] = []
    running = 0.0
    for idx, v in enumerate(values):
        running += v
        if idx >= period:
            running -= values[idx - period]
        count = period if idx >= period - 1 else (idx + 1)
        out.append(running / count)
    return out


def rolling_std(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out: List[float] = []
    for idx in range(len(values)):
        start = max(0, idx - period + 1)
        window = values[start : idx + 1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        out.append(variance ** 0.5)
    return out


def bollinger_bands(values: List[float], period: int, std_mult: float) -> Tuple[List[float], List[float], List[float]]:
    mid = sma(values, period)
    std = rolling_std(values, period)
    upper = [m + std_mult * s for m, s in zip(mid, std)]
    lower = [m - std_mult * s for m, s in zip(mid, std)]
    return mid, upper, lower


def rsi_wilder(values: List[float], period: int) -> List[float]:
    if len(values) < 2:
        return [50.0] * len(values)

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    out = [50.0] * len(values)
    if len(changes) < period:
        return out

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return out


def atr_wilder(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    if len(closes) < 2:
        return [0.0] * len(closes)

    tr = [0.0] * len(closes)
    for i in range(1, len(closes)):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    out = [0.0] * len(closes)
    running = 0.0
    for i in range(1, len(closes)):
        if i <= period:
            running += tr[i]
            out[i] = running / i
        else:
            out[i] = ((out[i - 1] * (period - 1)) + tr[i]) / period
    return out


def load_hl_config() -> None:
    config_path = PROJECT_ROOT / "config" / ".hl_config"
    if not config_path.exists():
        return

    mapping = {
        "MAIN_WALLET": "main_wallet",
        "API_WALLET": "api_wallet",
        "API_PRIVATE_KEY": "api_private_key",
    }

    for raw in config_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in mapping and v:
            CONFIG[mapping[k]] = v

    if os.getenv("HL_API_KEY"):
        CONFIG["api_private_key"] = os.getenv("HL_API_KEY", "")


class NostalgiaForInfinityTrader:
    def __init__(self) -> None:
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.account = None
        self.exchange = None
        key = (CONFIG.get("api_private_key") or "").strip()
        if key:
            self.account = Account.from_key(key)
            self.exchange = Exchange(
                self.account,
                constants.MAINNET_API_URL,
                account_address=CONFIG["main_wallet"],
            )
        else:
            logger.warning(
                "API_PRIVATE_KEY 未配置：仅拉取行情与信号日志，不会向 Hyperliquid 下单"
            )
        self.last_loss_time = None
        self.peak_balance = 0.0

    def _get_nfi_params(self, symbol: str) -> Dict[str, float]:
        params = dict(NFI_DEFAULTS)
        params.update(NFI_SYMBOL_OVERRIDES.get(symbol.upper(), {}))
        return params

    def _calc_position_size(self, confidence: float) -> float:
        max_size = CONFIG["max_position_usd"]
        size = round(max_size * confidence, 2)
        return size if size >= CONFIG["min_order_value"] else 0.0

    def _check_profit_after_fees(self, position_size: float, entry_price: float, take_profit: float) -> Dict:
        taker_fee = CONFIG["taker_fee"]
        min_profit = CONFIG["min_profit_after_fee"]

        price_change_pct = abs(take_profit - entry_price) / entry_price
        gross_profit = position_size * price_change_pct
        open_fee = position_size * taker_fee
        close_fee = position_size * (1 + price_change_pct) * taker_fee
        total_fees = open_fee + close_fee
        net_profit = gross_profit - total_fees
        net_profit_pct = net_profit / position_size if position_size > 0 else 0.0

        if net_profit_pct < min_profit:
            return {
                "valid": False,
                "gross_profit": gross_profit,
                "total_fees": total_fees,
                "net_profit": net_profit,
                "net_profit_pct": net_profit_pct * 100,
                "reason": (
                    f"net {net_profit_pct * 100:.2f}% < min {min_profit * 100:.2f}% after fee"
                ),
            }

        return {
            "valid": True,
            "gross_profit": gross_profit,
            "total_fees": total_fees,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct * 100,
            "reason": "net profit after fee is acceptable",
        }

    def _calc_confidence_long(
        self,
        price: float,
        bb_lower: float,
        ema_trend_v: float,
        ema_long_v: float,
        rsi_fast_v: float,
        rsi_main_v: float,
        volume_v: float,
        volume_sma_v: float,
    ) -> float:
        confidence = 0.45

        if price <= bb_lower:
            confidence += 0.15
        if ema_trend_v > ema_long_v:
            confidence += 0.10
        if rsi_main_v <= 33:
            confidence += 0.10
        if rsi_fast_v <= 18:
            confidence += 0.10
        if volume_sma_v > 0 and volume_v >= volume_sma_v:
            confidence += 0.10

        return min(confidence, 1.0)

    def _calc_confidence_short(
        self,
        price: float,
        bb_upper: float,
        ema_trend_v: float,
        ema_long_v: float,
        rsi_fast_v: float,
        rsi_main_v: float,
        volume_v: float,
        volume_sma_v: float,
    ) -> float:
        confidence = 0.45

        if price >= bb_upper:
            confidence += 0.15
        if ema_trend_v < ema_long_v:
            confidence += 0.10
        if rsi_main_v >= 67:
            confidence += 0.10
        if rsi_fast_v >= 82:
            confidence += 0.10
        if volume_sma_v > 0 and volume_v >= volume_sma_v:
            confidence += 0.10

        return min(confidence, 1.0)

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 260) -> List[Dict]:
        try:
            url = "https://api.hyperliquid.xyz/info"
            end_time = int(time.time() * 1000)
            hours = max(limit, 100)
            start_time = end_time - (hours * 60 * 60 * 1000)

            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": end_time,
                },
            }

            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                return []

            data = resp.json()
            candles = []
            for c in data:
                candles.append(
                    {
                        "timestamp": c["t"],
                        "open": float(c["o"]),
                        "high": float(c["h"]),
                        "low": float(c["l"]),
                        "close": float(c["c"]),
                        "volume": float(c["v"]),
                    }
                )
            return candles
        except Exception as exc:
            logger.error("failed to fetch klines %s: %s", symbol, exc)
            return []

    def analyze_symbol(self, symbol: str) -> Dict:
        params = self._get_nfi_params(symbol)
        lookback = int(max(params["ema_long"] + 40, 260))
        klines = self.get_klines(symbol, interval=CONFIG["timeframe"], limit=lookback)

        if len(klines) < params["ema_long"] + 5:
            return {"action": "HOLD", "reason": f"{symbol} not enough candles"}

        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        volumes = [k["volume"] for k in klines]

        ema_fast = ema(closes, int(params["ema_fast"]))
        ema_trend = ema(closes, int(params["ema_trend"]))
        ema_long = ema(closes, int(params["ema_long"]))
        rsi_fast = rsi_wilder(closes, int(params["rsi_fast"]))
        rsi_main = rsi_wilder(closes, int(params["rsi_main"]))
        atr_vals = atr_wilder(highs, lows, closes, int(params["atr_period"]))
        _, bb_upper, bb_lower = bollinger_bands(closes, int(params["bb_period"]), float(params["bb_stddev"]))
        volume_sma = sma(volumes, int(params["volume_sma_period"]))

        i = len(closes) - 1
        price = closes[i]
        atr_now = atr_vals[i]
        if atr_now <= 0:
            return {"action": "HOLD", "reason": f"{symbol} ATR is zero"}

        short_enabled = bool(params.get("enable_short", True))
        by_symbol = CONFIG.get("trade_side_by_symbol") or {}
        trade_side = str(by_symbol.get(symbol, CONFIG.get("trade_side", "both"))).lower()
        allow_long = trade_side in {"both", "long_only", "long"}
        allow_short = trade_side in {"both", "short_only", "short"}
        regime_ok = (
            ema_trend[i] > ema_long[i]
            and price > ema_long[i] * float(params["regime_price_floor"])
        )
        pullback_ok = (
            price <= bb_lower[i] * float(params["bb_touch_buffer"])
            or price <= ema_fast[i] * float(params["ema_pullback_buffer"])
        )
        rsi_ok = (
            rsi_fast[i] <= float(params["rsi_fast_buy"])
            and rsi_main[i] <= float(params["rsi_main_buy"])
        )
        volume_ok = volume_sma[i] > 0 and volumes[i] >= volume_sma[i] * float(params["min_volume_ratio"])
        not_breakdown = price >= ema_long[i] * (1.0 - float(params["max_breakdown_pct"]))
        stabilizing = closes[i] >= closes[i - 1] or rsi_fast[i] > rsi_fast[i - 1]

        long_ok = allow_long and regime_ok and pullback_ok and rsi_ok and volume_ok and not_breakdown and stabilizing

        regime_short = (
            ema_trend[i] < ema_long[i]
            and price < ema_long[i] * float(params["regime_price_ceiling"])
        )
        pullback_short = (
            price >= bb_upper[i] * float(params["bb_reject_buffer"])
            or price >= ema_fast[i] * float(params["ema_bounce_buffer"])
        )
        rsi_short = (
            rsi_fast[i] >= float(params["rsi_fast_sell"])
            and rsi_main[i] >= float(params["rsi_main_sell"])
        )
        not_breakout = price <= ema_long[i] * (1.0 + float(params["max_breakout_pct"]))
        stabilizing_short = closes[i] <= closes[i - 1] or rsi_fast[i] < rsi_fast[i - 1]
        short_ok = (
            allow_short
            and short_enabled
            and regime_short
            and pullback_short
            and rsi_short
            and volume_ok
            and not_breakout
            and stabilizing_short
        )

        if not (long_ok or short_ok):
            reasons = []
            if not regime_ok and not regime_short:
                reasons.append("regime")
            if not pullback_ok and not pullback_short:
                reasons.append("pullback")
            if not rsi_ok and not rsi_short:
                reasons.append("rsi")
            if not volume_ok:
                reasons.append("volume")
            if not not_breakdown and not not_breakout:
                reasons.append("breakout")
            if not stabilizing and not stabilizing_short:
                reasons.append("stabilizing")
            return {"action": "HOLD", "reason": f"{symbol} no-entry ({','.join(reasons)})"}

        side = "LONG"
        if long_ok and short_ok:
            long_score = (
                max(0.0, float(params["rsi_fast_buy"]) - rsi_fast[i])
                + max(0.0, float(params["rsi_main_buy"]) - rsi_main[i])
                + max(0.0, (bb_lower[i] - price) / price * 100)
            )
            short_score = (
                max(0.0, rsi_fast[i] - float(params["rsi_fast_sell"]))
                + max(0.0, rsi_main[i] - float(params["rsi_main_sell"]))
                + max(0.0, (price - bb_upper[i]) / price * 100)
            )
            side = "SHORT" if short_score > long_score else "LONG"
        elif short_ok:
            side = "SHORT"

        if side == "LONG":
            confidence = self._calc_confidence_long(
                price,
                bb_lower[i],
                ema_trend[i],
                ema_long[i],
                rsi_fast[i],
                rsi_main[i],
                volumes[i],
                volume_sma[i],
            )
        else:
            confidence = self._calc_confidence_short(
                price,
                bb_upper[i],
                ema_trend[i],
                ema_long[i],
                rsi_fast[i],
                rsi_main[i],
                volumes[i],
                volume_sma[i],
            )
        position_size = self._calc_position_size(confidence)
        if position_size < CONFIG["min_order_value"]:
            return {"action": "HOLD", "reason": f"{symbol} position too small"}

        if side == "LONG":
            stop_loss = price - atr_now * float(params["stop_loss_atr_mult"])
            take_profit = price + atr_now * float(params["take_profit_atr_mult"])
            action = "BUY"
        else:
            stop_loss = price + atr_now * float(params["stop_loss_atr_mult"])
            take_profit = price - atr_now * float(params["take_profit_atr_mult"])
            action = "SELL"
        fee_check = self._check_profit_after_fees(position_size, price, take_profit)
        if not fee_check["valid"]:
            return {"action": "HOLD", "reason": f"{symbol} {fee_check['reason']}"}

        return {
            "action": action,
            "symbol": symbol,
            "confidence": confidence,
            "size": position_size,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": atr_now,
            "fees": fee_check,
            "reason": (
                f"{symbol} NFI {side} entry, RSI({rsi_fast[i]:.1f}/{rsi_main[i]:.1f}), "
                f"SL={params['stop_loss_atr_mult']}xATR TP={params['take_profit_atr_mult']}xATR"
            ),
        }

    def get_account_state(self) -> Dict:
        try:
            state = self.info.user_state(CONFIG["main_wallet"])
            margin = state.get("marginSummary", {})
            return {
                "account_value": float(margin.get("accountValue", 0)),
                "withdrawable": float(state.get("withdrawable", 0)),
                "positions": state.get("assetPositions", []),
            }
        except Exception as exc:
            logger.error("failed to get account state: %s", exc)
            return {"account_value": 0.0, "withdrawable": 0.0, "positions": []}

    def get_open_orders(self) -> List[Dict]:
        try:
            return self.info.open_orders(CONFIG["main_wallet"])
        except Exception as exc:
            logger.error("failed to get open orders: %s", exc)
            return []

    def cancel_all_orders(self, symbol: str) -> None:
        if not self.exchange:
            return
        try:
            for order in self.get_open_orders():
                if order.get("coin") == symbol:
                    self.exchange.cancel(symbol, order.get("oid"))
        except Exception as exc:
            logger.error("failed to cancel orders %s: %s", symbol, exc)

    def has_position(self, symbol: str) -> bool:
        account = self.get_account_state()
        for pos in account.get("positions", []):
            p = pos.get("position", {})
            if p.get("coin") == symbol and float(p.get("szi", 0)) != 0:
                return True
        return False

    def place_order(self, symbol: str, is_buy: bool, size: float, price: float, reduce_only: bool = False) -> Dict:
        if not self.exchange:
            logger.info("monitor-only mode, skip order %s", symbol)
            return {"status": "skipped", "message": "no signing key"}
        try:
            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                price,
                {"limit": {"tif": "Gtc"}},
                reduce_only=reduce_only,
            )
            logger.info("order result: %s", result)
            return result
        except Exception as exc:
            logger.error("failed to place order: %s", exc)
            return {"status": "error", "message": str(exc)}

    def can_trade(self) -> bool:
        if self.last_loss_time:
            if datetime.now() - self.last_loss_time < timedelta(seconds=CONFIG["trade_cooldown"]):
                logger.info("cooldown active, skip")
                return False

        account = self.get_account_state()
        current_value = account["account_value"]
        if self.peak_balance == 0:
            self.peak_balance = current_value
        if current_value > self.peak_balance:
            self.peak_balance = current_value

        if self.peak_balance > 0:
            drawdown = (self.peak_balance - current_value) / self.peak_balance
            if drawdown >= 0.20:
                logger.warning("drawdown %.2f%% >= 20%%, stop trading", drawdown * 100)
                return False
        return True

    def log_trade(self, signal: Dict, result: Dict) -> None:
        log_entry = {
            "time": datetime.now().isoformat(),
            "signal": signal,
            "result": result,
        }
        log_file = LOG_DIR / "trades_nfi.jsonl"
        with log_file.open("a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def run_cycle(self) -> None:
        logger.info("=" * 50)
        logger.info("start NFI cycle")

        if not self.can_trade():
            logger.info("risk guard blocked this cycle")
            return

        for symbol in CONFIG["symbols"]:
            if self.has_position(symbol):
                logger.info("%s already has position, skip", symbol)
                continue

            signal = self.analyze_symbol(symbol)
            if signal["action"] == "HOLD":
                logger.info("%s", signal["reason"])
                continue

            if signal["size"] < CONFIG["min_order_value"]:
                logger.info("%s position too small %.2f, skip", symbol, signal["size"])
                continue

            logger.info("NFI signal %s: %s", symbol, signal["reason"])
            logger.info("  confidence: %.1f%%", signal["confidence"] * 100)
            logger.info("  position: $%.2f", signal["size"])
            logger.info("  entry: $%.2f", signal["entry_price"])
            logger.info("  stop: $%.2f", signal["stop_loss"])
            logger.info("  take profit: $%.2f", signal["take_profit"])

            fee = signal.get("fees", {})
            if fee:
                logger.info(
                    "  net: $%.2f (%.2f%%) fee: $%.2f",
                    fee.get("net_profit", 0.0),
                    fee.get("net_profit_pct", 0.0),
                    fee.get("total_fees", 0.0),
                )

            self.cancel_all_orders(symbol)
            is_buy = signal["action"] == "BUY"
            result = self.place_order(
                symbol,
                is_buy,
                signal["size"] / signal["entry_price"],
                signal["entry_price"],
            )
            self.log_trade(signal, result)

            if result.get("status") == "ok":
                logger.info("%s order submitted", symbol)
            else:
                logger.error("%s order failed: %s", symbol, result)

    def run(self) -> None:
        logger.info("NostalgiaForInfinity-inspired trader started")
        logger.info("symbols: %s", CONFIG["symbols"])
        logger.info("timeframe: %s", CONFIG["timeframe"])
        by_symbol = CONFIG.get("trade_side_by_symbol") or {}
        for symbol in CONFIG["symbols"]:
            ts = by_symbol.get(symbol, CONFIG.get("trade_side", "both"))
            logger.info("trade_side %s: %s", symbol, ts)
        for symbol in CONFIG["symbols"]:
            p = self._get_nfi_params(symbol)
            logger.info(
                "%s params: ema(%s/%s/%s), rsi(%s/%s<=%.1f/%.1f), bb(%s,%.1f), sl/tp(%.1f/%.1f)xATR",
                symbol,
                int(p["ema_fast"]),
                int(p["ema_trend"]),
                int(p["ema_long"]),
                int(p["rsi_fast"]),
                int(p["rsi_main"]),
                float(p["rsi_fast_buy"]),
                float(p["rsi_main_buy"]),
                int(p["bb_period"]),
                float(p["bb_stddev"]),
                float(p["stop_loss_atr_mult"]),
                float(p["take_profit_atr_mult"]),
            )

        while True:
            try:
                self.run_cycle()
            except Exception as exc:
                logger.error("cycle exception: %s", exc, exc_info=True)

            logger.info("sleep %ss", CONFIG["check_interval"])
            time.sleep(CONFIG["check_interval"])


def main() -> None:
    load_hl_config()
    if not CONFIG["main_wallet"]:
        logger.error("MAIN_WALLET missing in trading-scripts/config/.hl_config")
        raise SystemExit(1)
    if not CONFIG["api_private_key"]:
        logger.warning(
            "API_PRIVATE_KEY 缺失：将启动 NFI 进程但仅记录信号；补齐密钥后重启 auto-trader 即可恢复实盘"
        )

    trader = NostalgiaForInfinityTrader()
    trader.run()


if __name__ == "__main__":
    main()
