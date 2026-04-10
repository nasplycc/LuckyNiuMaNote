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
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from notifier import TelegramNotifier
from reconcile import reconcile_exchange_state
from risk_guard import RiskGuard
from state_store import StateStore
from market_regime import (
    detect_market_regime,
    adapt_supertrend_multiplier,
    score_trend_flip,
    detect_supertrend,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
LOG_DIR = WORKSPACE_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / ".runtime_config.json"

CONFIG = {
    "main_wallet": "",
    "api_wallet": "",
    "api_private_key": os.getenv("HL_API_KEY", ""),
    "trader_mode": (os.getenv("TRADER_MODE", "monitor") or "monitor").strip().lower(),
    "symbols": ["BTC", "ETH"],
    "timeframe": "1h",
    "max_leverage": 3,
    "default_leverage": 2,
    "max_position_usd": 294,
    "min_order_value": 10,
    "check_interval": 60,
    "trade_cooldown": 14400,
    "trade_side": "both",
    "trade_side_by_symbol": {"BTC": "short_only", "ETH": "both"},
    "maker_fee": 0.0001,
    "taker_fee": 0.00035,
    "min_profit_after_fee": 0.005,
    "max_consecutive_failures": 3,
    "max_api_timeouts": 5,
    "safe_mode_on_protection_failure": True,
    "auto_exit_safe_mode_on_api_recovery": True,
    "entry_fill_timeout_sec": 20,
    "entry_fill_poll_interval_sec": 2,
}

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
    # === RSI 阈值下调：更容易触发信号 ===
    "rsi_fast_buy": 28.0,  # 原 23.0 → 28.0 (更容易超卖触发)
    "rsi_main_buy": 42.0,  # 原 36.0 → 42.0 (更容易超卖触发)
    "rsi_fast_sell": 70.0,  # 原 75.0 → 70.0 (更容易超买触发)
    "rsi_main_sell": 55.0,  # 原 60.0 → 55.0 (更容易超买触发)
    # === 放宽布林带和价格条件 ===
    "bb_touch_buffer": 1.02,  # 原 1.01 → 1.02 (更容易触及)
    "ema_pullback_buffer": 0.99,  # 原 0.985 → 0.99 (更容易回踩)
    "bb_reject_buffer": 0.98,  # 原 0.99 → 0.98 (更容易触及上轨)
    "ema_bounce_buffer": 1.02,  # 原 1.015 → 1.02 (更容易反弹)
    # === 放宽趋势和破位条件 ===
    "regime_price_floor": 0.92,  # 原 0.95 → 0.92 (允许更深度回踩)
    "regime_price_ceiling": 1.08,  # 原 1.05 → 1.08 (允许更高反弹)
    "max_breakdown_pct": 0.15,  # 原 0.10 → 0.15 (允许更大破位)
    "max_breakout_pct": 0.15,  # 原 0.10 → 0.15 (允许更大突破)
    # === 降低成交量要求 ===
    "min_volume_ratio": 0.35,  # 原 0.45 → 0.35 (更低成交量门槛)
    # === 止损止盈调整：更激进 ===
    "stop_loss_atr_mult": 2.0,  # 原 2.4 → 2.0 (更紧止损，更快出场)
    "take_profit_atr_mult": 3.0,  # 原 4.0 → 3.0 (更容易止盈)
    # === SuperTrend 参数：更敏感 ===
    "supertrend_period": 10,
    "supertrend_base_multiplier": 2.5,  # 原 3.0 → 2.5 (更敏感)
    "min_trend_flip_score": 45,  # 原 55 → 45 (更容易触发翻转信号)
    # === 其他 ===
    "enable_short": True,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "volume_sma_period": 30,
}

# Regime-adaptive stop loss/take profit multipliers - 更激进
REGIME_SL_TP_ADJUSTMENTS = {
    "trending": {"sl_mult": 0.75, "tp_mult": 1.0},   # 更紧止损 (0.85→0.75), 止盈不放大
    "ranging": {"sl_mult": 0.9, "tp_mult": 0.85},    # 止损收紧 (1.1→0.9), 止盈更容易 (0.9→0.85)
    "volatile": {"sl_mult": 1.0, "tp_mult": 0.7},    # 快速出场 (1.3→1.0), 止盈更保守 (0.8→0.7)
}

NFI_SYMBOL_OVERRIDES = {
    "ETH": {
        # ETH 波动更大，但也要降低门槛
        "rsi_fast_buy": 26.0,  # 比 BTC 略低，但仍比原来宽松
        "rsi_main_buy": 40.0,
        "rsi_fast_sell": 68.0,
        "rsi_main_sell": 53.0,
        "min_volume_ratio": 0.30,  # ETH 成交量要求更低
        "stop_loss_atr_mult": 2.2,  # 原 2.8 → 2.2 (更紧)
        "take_profit_atr_mult": 2.8,  # 原 2.8 → 2.8 (保持，ETH 波动大)
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


def load_runtime_config() -> None:
    if not RUNTIME_CONFIG_PATH.exists():
        return
    try:
        data = json.loads(RUNTIME_CONFIG_PATH.read_text())
    except Exception as exc:
        logger.warning("failed to load runtime config: %s", exc)
        return

    risk_cfg = data.get("risk", {})
    if "max_consecutive_failures" in risk_cfg:
        CONFIG["max_consecutive_failures"] = int(risk_cfg["max_consecutive_failures"])
    if "max_api_timeouts" in risk_cfg:
        CONFIG["max_api_timeouts"] = int(risk_cfg["max_api_timeouts"])
    if "safe_mode_on_protection_failure" in risk_cfg:
        CONFIG["safe_mode_on_protection_failure"] = bool(risk_cfg["safe_mode_on_protection_failure"])
    if "auto_exit_safe_mode_on_api_recovery" in risk_cfg:
        CONFIG["auto_exit_safe_mode_on_api_recovery"] = bool(risk_cfg["auto_exit_safe_mode_on_api_recovery"])
    if "entry_fill_timeout_sec" in risk_cfg:
        CONFIG["entry_fill_timeout_sec"] = int(risk_cfg["entry_fill_timeout_sec"])
    if "entry_fill_poll_interval_sec" in risk_cfg:
        CONFIG["entry_fill_poll_interval_sec"] = int(risk_cfg["entry_fill_poll_interval_sec"])


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
        self.store = StateStore()
        self.notifier = TelegramNotifier()
        self.guard = RiskGuard(self.store)
        self._size_decimals_cache: Dict[str, int] = {}
        mode = str(CONFIG.get("trader_mode") or "monitor").strip().lower()
        key = (CONFIG.get("api_private_key") or "").strip()
        if mode == "live":
            if key:
                self.account = Account.from_key(key)
                self.exchange = Exchange(
                    self.account,
                    constants.MAINNET_API_URL,
                    account_address=CONFIG["main_wallet"],
                )
            else:
                logger.warning("TRADER_MODE=live 但 API_PRIVATE_KEY 未配置：回退为 monitor-only，不会向 Hyperliquid 下单")
        else:
            if key:
                logger.info("TRADER_MODE=%s：即使检测到 API_PRIVATE_KEY，也不会下单", mode)
            logger.warning("API_PRIVATE_KEY 未配置：仅拉取行情与信号日志，不会向 Hyperliquid 下单")
        self.last_loss_time = None
        self.peak_balance = 0.0

    def notify(self, message: str) -> None:
        try:
            self.notifier.send(message)
        except Exception:
            pass

    def _retry_call(self, label: str, fn, retries: int = 2, delay_sec: float = 1.2):
        last_exc = None
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                logger.warning("%s attempt %s/%s failed: %s", label, attempt + 1, retries + 1, exc)
                time.sleep(delay_sec)
        raise last_exc

    def _extract_order_id(self, result: Dict) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        for key in ("response", "data"):
            payload = result.get(key)
            if isinstance(payload, dict):
                statuses = payload.get("data", {}).get("statuses") if isinstance(payload.get("data"), dict) else payload.get("statuses")
                if isinstance(statuses, list):
                    for item in statuses:
                        if isinstance(item, dict):
                            resting = item.get("resting") or {}
                            filled = item.get("filled") or {}
                            oid = resting.get("oid") or filled.get("oid")
                            if oid is not None:
                                return str(oid)
        oid = result.get("oid")
        return str(oid) if oid is not None else None

    def _get_size_decimals(self, symbol: str) -> int:
        cached = self._size_decimals_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            meta = self.info.meta()
            universe = meta.get("universe", []) if isinstance(meta, dict) else []
            for item in universe:
                if str(item.get("name") or "").upper() == symbol.upper():
                    decimals = int(item.get("szDecimals", 0) or 0)
                    self._size_decimals_cache[symbol] = decimals
                    return decimals
        except Exception as exc:
            logger.warning("failed to fetch szDecimals for %s: %s", symbol, exc)
        fallback = 3 if symbol.upper() == "BTC" else 2 if symbol.upper() == "ETH" else 3
        self._size_decimals_cache[symbol] = fallback
        return fallback

    def _normalize_order_size(self, symbol: str, size: float) -> float:
        decimals = self._get_size_decimals(symbol)
        quant = Decimal("1").scaleb(-decimals)
        normalized = Decimal(str(size)).quantize(quant, rounding=ROUND_DOWN)
        normalized_f = float(normalized)
        logger.info(
            "%s order size normalized: raw=%s normalized=%s szDecimals=%s",
            symbol,
            size,
            normalized_f,
            decimals,
        )
        return normalized_f

    def _normalize_trigger_price(self, symbol: str, trigger_price: float) -> float:
        decimals = max(0, 6 - self._get_size_decimals(symbol))
        quant = Decimal("1").scaleb(-decimals)
        normalized = Decimal(str(trigger_price)).quantize(quant, rounding=ROUND_HALF_UP)
        normalized_f = float(normalized)
        logger.info(
            "%s trigger price normalized: raw=%s normalized=%s priceDecimals=%s",
            symbol,
            trigger_price,
            normalized_f,
            decimals,
        )
        return normalized_f

    def _build_position_tpsl_order(self, symbol: str, is_buy: bool, size: float, trigger_price: float, kind: str) -> Dict:
        # Use SDK's own price formatting to ensure valid tick size
        limit_px = self.exchange._slippage_price(symbol, is_buy, Exchange.DEFAULT_SLIPPAGE, trigger_price)
        logger.info(
            "%s %s order prepared: trigger=%s limit_px=%s size=%s side=%s",
            symbol,
            kind,
            trigger_price,
            limit_px,
            size,
            "BUY" if is_buy else "SELL",
        )
        return {
            "coin": symbol,
            "is_buy": is_buy,
            "sz": size,
            "limit_px": limit_px,
            "order_type": {"trigger": {"triggerPx": trigger_price, "isMarket": True, "tpsl": kind}},
            "reduce_only": True,
        }

    def place_position_tpsl(self, symbol: str, is_buy: bool, size: float, stop_price: float, take_profit_price: float) -> Dict:
        if not self.exchange:
            return {"status": "skipped", "message": "no signing key"}
        try:
            orders = [
                self._build_position_tpsl_order(symbol, is_buy, size, stop_price, "sl"),
                self._build_position_tpsl_order(symbol, is_buy, size, take_profit_price, "tp"),
            ]
            result = self.exchange.bulk_orders(orders, grouping="positionTpsl")
            logger.info("positionTpsl order result: %s", result)
            self.guard.record_success()
            return result
        except requests.Timeout as exc:
            logger.error("failed to place positionTpsl orders: %s", exc)
            self.guard.record_api_timeout({"op": "place_position_tpsl", "symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_api_timeouts", 5)))
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            logger.error("failed to place positionTpsl orders: %s", exc)
            self.guard.record_failure("place_position_tpsl failed", {"symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3)))
            return {"status": "error", "message": str(exc)}

    def get_position_detail(self, symbol: str) -> Optional[Dict]:
        account = self.get_account_state()
        for pos in account.get("positions", []):
            p = pos.get("position", {})
            if p.get("coin") == symbol and float(p.get("szi", 0) or 0) != 0:
                return p
        return None

    def get_local_position_meta(self, symbol: str) -> Dict:
        row = self.store.get_open_position(symbol)
        if not row:
            return {}
        try:
            return json.loads(row.get("meta_json") or "{}")
        except Exception:
            return {}

    def wait_for_entry_fill(self, symbol: str, expected_side: str, expected_size: float) -> Optional[Dict]:
        deadline = time.time() + int(CONFIG.get("entry_fill_timeout_sec", 20))
        poll_interval = max(1, int(CONFIG.get("entry_fill_poll_interval_sec", 2)))
        while time.time() < deadline:
            pos = self.get_position_detail(symbol)
            if pos:
                live_size = float(pos.get("szi", 0) or 0)
                if expected_side == "BUY" and live_size > 0:
                    return pos
                if expected_side == "SELL" and live_size < 0:
                    return pos
            time.sleep(poll_interval)
        self.guard.enter_safe_mode(
            f"{symbol} entry fill confirmation timed out",
            {"symbol": symbol, "expected_side": expected_side, "expected_size": expected_size},
        )
        self.notify(f"🛑 {symbol} 开仓后未在规定时间内确认成交，系统进入 SAFE_MODE")
        return None

    def place_trigger_order(self, symbol: str, is_buy: bool, size: float, trigger_price: float, kind: str) -> Dict:
        if not self.exchange:
            return {"status": "skipped", "message": "no signing key"}
        normalized_trigger_price = self._normalize_trigger_price(symbol, trigger_price)
        try:
            result = self.exchange.order(
                symbol,
                is_buy,
                size,
                0.0,
                {"trigger": {"triggerPx": normalized_trigger_price, "isMarket": True, "tpsl": kind}},
                reduce_only=True,
            )
            logger.info("trigger order result: %s", result)
            self.guard.record_success()
            return result
        except requests.Timeout as exc:
            logger.error("failed to place trigger order: %s", exc)
            self.guard.record_api_timeout({"op": "place_trigger_order", "symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_api_timeouts", 5)))
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            logger.error("failed to place trigger order: %s", exc)
            self.guard.record_failure("place_trigger_order failed", {"symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3)))
            return {"status": "error", "message": str(exc)}

    def ensure_protection_orders(self, symbol: str, signal: Dict, confirmed_pos: Optional[Dict] = None) -> bool:
        pos = confirmed_pos or self.get_position_detail(symbol)
        if not pos:
            self.guard.enter_safe_mode(f"{symbol} entry submitted but no live position found for protection setup", {"symbol": symbol})
            self.store.upsert_position(symbol, None, None, None, signal.get("stop_loss"), signal.get("take_profit"), "UNPROTECTED")
            self.notify(f"🛑 {symbol} 下单后未检测到持仓，已进入 SAFE_MODE")
            return False

        size = abs(float(pos.get("szi", 0) or 0))
        if size <= 0:
            self.guard.enter_safe_mode(f"{symbol} invalid position size for protection setup", {"symbol": symbol, "position": pos})
            self.notify(f"🛑 {symbol} 持仓数量异常，已进入 SAFE_MODE")
            return False

        is_long = float(pos.get("szi", 0) or 0) > 0
        close_side = not is_long

        grouped_result = self.place_position_tpsl(
            symbol,
            close_side,
            size,
            float(signal["stop_loss"]),
            float(signal["take_profit"]),
        )
        statuses = []
        if isinstance(grouped_result, dict):
            response = grouped_result.get("response", {})
            data = response.get("data", {}) if isinstance(response, dict) else {}
            statuses = data.get("statuses", []) if isinstance(data, dict) else []

        stop_status = statuses[0] if len(statuses) > 0 and isinstance(statuses[0], dict) else {}
        tp_status = statuses[1] if len(statuses) > 1 and isinstance(statuses[1], dict) else {}
        stop_oid = str((stop_status.get("resting") or {}).get("oid") or (stop_status.get("filled") or {}).get("oid") or "") or None
        tp_oid = str((tp_status.get("resting") or {}).get("oid") or (tp_status.get("filled") or {}).get("oid") or "") or None
        stop_ok = bool(stop_oid)
        tp_ok = bool(tp_oid)
        self.store.record_order(symbol, "SL", "BUY" if close_side else "SELL", stop_oid, None, float(signal["stop_loss"]), size, "submitted" if stop_ok else "error", stop_status or grouped_result)
        self.store.record_order(symbol, "TP", "BUY" if close_side else "SELL", tp_oid, None, float(signal["take_profit"]), size, "submitted" if tp_ok else "error", tp_status or grouped_result)

        meta = {
            "grouped_result": grouped_result,
            "stop_order_id": stop_oid,
            "tp_order_id": tp_oid,
        }
        if not stop_ok or not tp_ok:
            self.store.upsert_position(
                symbol,
                "LONG" if is_long else "SHORT",
                float(pos.get("entryPx") or signal.get("entry_price") or 0),
                size,
                float(signal["stop_loss"]),
                float(signal.get("take_profit") or 0),
                "UNPROTECTED",
                meta=meta,
            )
            if bool(CONFIG.get("safe_mode_on_protection_failure", True)):
                self.guard.enter_safe_mode(f"{symbol} protection order placement failed", {"symbol": symbol, "stop_ok": stop_ok, "tp_ok": tp_ok, "meta": meta})
                self.notify(f"🛑 {symbol} 保护单挂单失败（SL:{stop_ok} TP:{tp_ok}），系统进入 SAFE_MODE")
            return False

        self.store.upsert_position(
            symbol,
            "LONG" if is_long else "SHORT",
            float(pos.get("entryPx") or signal.get("entry_price") or 0),
            size,
            float(signal["stop_loss"]),
            float(signal.get("take_profit") or 0),
            "OPEN",
            source_order_id=None,
            opened_at=datetime.now().isoformat(),
            meta=meta,
        )
        self.notify(f"✅ {symbol} 已开仓并挂保护单，方向 {'LONG' if is_long else 'SHORT'}，止损 {float(signal['stop_loss']):.4f}，止盈 {float(signal['take_profit']):.4f}")
        return True

    def refresh_position_states(self) -> None:
        account = self.get_account_state()
        live_symbols = set()
        for pos in account.get("positions", []):
            p = pos.get("position", {})
            symbol = p.get("coin")
            if symbol and float(p.get("szi", 0) or 0) != 0:
                live_symbols.add(symbol)

        for local_pos in self.store.get_open_positions():
            symbol = local_pos["symbol"]
            if symbol not in live_symbols:
                self.store.close_position(symbol, meta={"closed_by": "refresh_position_states", "closed_at_check": datetime.now().isoformat()})
                self.notify(f"✅ {symbol} 本地状态已标记为 CLOSED（检测到交易所已无持仓）")

    def attempt_repair_protection(self) -> None:
        open_orders = self.get_open_orders()
        account = self.get_account_state()
        orders_by_coin: Dict[str, List[Dict]] = {}
        for order in open_orders or []:
            coin = order.get("coin")
            if coin:
                orders_by_coin.setdefault(coin, []).append(order)

        repaired_any = False
        for pos in self.store.get_open_positions():
            symbol = pos["symbol"]
            live_pos = None
            for item in account.get("positions", []):
                p = item.get("position", {})
                if p.get("coin") == symbol and float(p.get("szi", 0) or 0) != 0:
                    live_pos = p
                    break
            if not live_pos:
                continue

            symbol_orders = orders_by_coin.get(symbol, [])
            trigger_orders = [o for o in symbol_orders if str(o.get("orderType", "")).lower().find("trigger") >= 0 or o.get("triggerCondition") or str(o.get("origType", "")).lower().find("trigger") >= 0]
            has_stop = any(str(o.get("tpsl", "")).lower() == "sl" or str(o.get("orderType", "")).lower().find("sl") >= 0 for o in trigger_orders)
            has_tp = any(str(o.get("tpsl", "")).lower() == "tp" or str(o.get("orderType", "")).lower().find("tp") >= 0 for o in trigger_orders)
            if has_stop and has_tp:
                continue

            signal = {
                "entry_price": float(pos.get("entry_price") or live_pos.get("entryPx") or 0),
                "stop_loss": float(pos.get("stop_loss") or 0),
                "take_profit": float(pos.get("take_profit") or 0),
            }
            if signal["stop_loss"] <= 0 or signal["take_profit"] <= 0:
                self.guard.enter_safe_mode(f"{symbol} protection missing and local SL/TP unavailable", {"symbol": symbol})
                self.notify(f"🛑 {symbol} 检测到保护单缺失且本地没有有效 SL/TP，进入 SAFE_MODE")
                continue

            if self.ensure_protection_orders(symbol, signal, confirmed_pos=live_pos):
                repaired_any = True
                self.store.record_event("WARN", "protection_repaired", f"Repaired protection orders for {symbol}", {"symbol": symbol})
                self.notify(f"🛠️ {symbol} 已自动补挂保护单")
            else:
                return

        if repaired_any and self.guard.in_safe_mode():
            self.guard.exit_safe_mode()
            self.notify("✅ 保护单自动修复完成，已退出 SAFE_MODE")

    def startup_reconcile(self) -> bool:
        account = self.get_account_state()
        open_orders = self.get_open_orders()
        enforce_safe_mode = self.exchange is not None
        result = reconcile_exchange_state(
            store=self.store,
            guard=self.guard,
            account_state=account,
            open_orders=open_orders,
            enforce_safe_mode=enforce_safe_mode,
        )
        if result.get("ok"):
            self.notify("✅ NFI trader 启动对账通过，允许进入运行状态")
            return True

        if not enforce_safe_mode:
            logger.warning("startup reconciliation produced warnings in monitor-only mode: %s", result.get("issues"))
            self.notify(f"⚠️ NFI trader 启动对账存在告警（monitor-only，不拦截运行）：{result.get('issues')}")
            return True

        self.notify(f"🛑 NFI trader 启动对账失败，进入 SAFE_MODE：{result.get('issues')}")
        self.attempt_repair_protection()
        account_after = self.get_account_state()
        orders_after = self.get_open_orders()
        result_after = reconcile_exchange_state(
            store=self.store,
            guard=self.guard,
            account_state=account_after,
            open_orders=orders_after,
            enforce_safe_mode=True,
        )
        if result_after.get("ok"):
            self.guard.exit_safe_mode()
            self.notify("✅ 启动后自动修复保护单成功，已退出 SAFE_MODE")
            return True
        return False

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
                "reason": f"net {net_profit_pct * 100:.2f}% < min {min_profit * 100:.2f}% after fee",
            }

        return {
            "valid": True,
            "gross_profit": gross_profit,
            "total_fees": total_fees,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct * 100,
            "reason": "net profit after fee is acceptable",
        }

    def _calc_confidence_long(self, price: float, bb_lower: float, ema_trend_v: float, ema_long_v: float, rsi_fast_v: float, rsi_main_v: float, volume_v: float, volume_sma_v: float) -> float:
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

    def _calc_confidence_short(self, price: float, bb_upper: float, ema_trend_v: float, ema_long_v: float, rsi_fast_v: float, rsi_main_v: float, volume_v: float, volume_sma_v: float) -> float:
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

        # ===== SuperTrend AI Adaptive: Market Regime Detection =====
        regime_result = detect_market_regime(closes, highs, lows, volumes)
        adapted_st_mult = adapt_supertrend_multiplier(regime_result.regime)
        
        # Calculate SuperTrend and detect trend flip
        st_values, st_direction = detect_supertrend(
            highs, lows, closes, multiplier=adapted_st_mult, period=int(params.get("supertrend_period", 10))
        )
        
        # Detect trend flip (direction changed from previous bar)
        supertrend_flip = False
        flip_direction = None
        if len(st_direction) >= 2 and i >= 1:
            if st_direction[i] != st_direction[i-1] and st_direction[i] != 0:
                supertrend_flip = True
                flip_direction = "bullish" if st_direction[i] == 1 else "bearish"
        
        # Calculate Bollinger Band width for squeeze detection
        bb_width = (bb_upper[i] - bb_lower[i]) / bb_lower[i] * 100 if bb_lower[i] > 0 else 0
        
        # Calculate volume ratio and price change for trend flip scoring
        volume_ratio = volumes[i] / volume_sma[i] if volume_sma[i] > 0 else 1.0
        price_change_pct = (closes[i] - closes[i-1]) / closes[i-1] * 100 if i > 0 and closes[i-1] > 0 else 0
        atr_change_pct = (atr_now - atr_vals[i-1]) / atr_vals[i-1] * 100 if i > 0 and atr_vals[i-1] > 0 else 0
        
        # Score the trend flip (if flipped)
        flip_score = 0.0
        if supertrend_flip:
            flip_score = score_trend_flip(
                regime_result,
                volume_ratio,
                abs(price_change_pct),
                bb_width,
                abs(atr_change_pct)
            )
        
        logger.info(
            "%s Regime=%s, ST_mult=%.1f, BB_width=%.2f%%, Vol_ratio=%.2f, Flip=%s (%s), Score=%.0f",
            symbol, regime_result.regime, adapted_st_mult, bb_width, volume_ratio,
            "YES" if supertrend_flip else "NO", flip_direction or "-", flip_score if supertrend_flip else 0
        )

        short_enabled = bool(params.get("enable_short", True))
        by_symbol = CONFIG.get("trade_side_by_symbol") or {}
        trade_side = str(by_symbol.get(symbol, CONFIG.get("trade_side", "both"))).lower()
        allow_long = trade_side in {"both", "long_only", "long"}
        allow_short = trade_side in {"both", "short_only", "short"}

        regime_ok = ema_trend[i] > ema_long[i] and price > ema_long[i] * float(params["regime_price_floor"])
        pullback_ok = price <= bb_lower[i] * float(params["bb_touch_buffer"]) or price <= ema_fast[i] * float(params["ema_pullback_buffer"])
        rsi_ok = rsi_fast[i] <= float(params["rsi_fast_buy"]) and rsi_main[i] <= float(params["rsi_main_buy"])
        volume_ok = volume_sma[i] > 0 and volumes[i] >= volume_sma[i] * float(params["min_volume_ratio"])
        not_breakdown = price >= ema_long[i] * (1.0 - float(params["max_breakdown_pct"]))
        stabilizing = closes[i] >= closes[i - 1] or rsi_fast[i] > rsi_fast[i - 1]
        long_ok = allow_long and regime_ok and pullback_ok and rsi_ok and volume_ok and not_breakdown and stabilizing

        regime_short = ema_trend[i] < ema_long[i] and price < ema_long[i] * float(params["regime_price_ceiling"])
        pullback_short = price >= bb_upper[i] * float(params["bb_reject_buffer"]) or price >= ema_fast[i] * float(params["ema_bounce_buffer"])
        rsi_short = rsi_fast[i] >= float(params["rsi_fast_sell"]) and rsi_main[i] >= float(params["rsi_main_sell"])
        not_breakout = price <= ema_long[i] * (1.0 + float(params["max_breakout_pct"]))
        stabilizing_short = closes[i] <= closes[i - 1] or rsi_fast[i] < rsi_fast[i - 1]
        short_ok = allow_short and short_enabled and regime_short and pullback_short and rsi_short and volume_ok and not_breakout and stabilizing_short

        # ===== SuperTrend Flip as Independent Entry Signal =====
        # Even if NFI conditions are not met, a high-score SuperTrend flip can trigger entry
        min_flip_score = float(params.get("min_trend_flip_score", 55))
        
        if supertrend_flip and flip_score >= min_flip_score:
            # SuperTrend flip detected with sufficient score - consider as independent signal
            flip_side = "LONG" if flip_direction == "bullish" else "SHORT"
            
            # Additional filters for flip-based entry
            flip_valid = True
            flip_reasons = []
            
            # Filter 1: Regime should not be highly volatile (too risky)
            if regime_result.regime == "volatile" and regime_result.confidence > 0.8:
                flip_valid = False
                flip_reasons.append("too_volatile")
            
            # Filter 2: Volume - 降低要求 (原 0.8 → 0.6)
            if volume_ratio < 0.6:
                flip_valid = False
                flip_reasons.append("low_volume")
            
            # Filter 3: Price change - 降低要求 (原 0.5% → 0.3%)
            if abs(price_change_pct) < 0.3:
                flip_valid = False
                flip_reasons.append("weak_momentum")
            
            if flip_valid:
                # Calculate position size based on flip score
                flip_confidence = 0.5 + (flip_score / 100.0) * 0.3  # 0.5 to 0.8 based on score
                position_size = self._calc_position_size(flip_confidence)
                
                if position_size >= CONFIG["min_order_value"]:
                    # Use regime-adaptive SL/TP
                    regime_adjustment = REGIME_SL_TP_ADJUSTMENTS.get(regime_result.regime, {"sl_mult": 1.0, "tp_mult": 1.0})
                    sl_mult = float(params["stop_loss_atr_mult"]) * regime_adjustment["sl_mult"]
                    tp_mult = float(params["take_profit_atr_mult"]) * regime_adjustment["tp_mult"]
                    
                    if flip_side == "LONG":
                        stop_loss = price - atr_now * sl_mult
                        take_profit = price + atr_now * tp_mult
                        action = "BUY"
                    else:
                        stop_loss = price + atr_now * sl_mult
                        take_profit = price - atr_now * tp_mult
                        action = "SELL"
                    
                    fee_check = self._check_profit_after_fees(position_size, price, take_profit)
                    if fee_check["valid"]:
                        logger.info(
                            "%s SuperTrend flip entry: side=%s, score=%.0f, confidence=%.2f, size=%.2f",
                            symbol, flip_side, flip_score, flip_confidence, position_size
                        )
                        return {
                            "action": action,
                            "symbol": symbol,
                            "confidence": flip_confidence,
                            "size": position_size,
                            "entry_price": price,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "atr": atr_now,
                            "fees": fee_check,
                            "regime": regime_result.regime,
                            "regime_confidence": regime_result.confidence,
                            "supertrend_multiplier": adapted_st_mult,
                            "market_score": market_score,
                            "flip_score": flip_score,
                            "signal_type": "supertrend_flip",
                            "reason": f"{symbol} SuperTrend {flip_side} flip, Score={flip_score:.0f}, Regime={regime_result.regime}, SL={sl_mult:.2f}xATR TP={tp_mult:.2f}xATR",
                        }
            
            logger.info(
                "%s SuperTrend flip rejected: score=%.0f, valid=%s, reasons=%s",
                symbol, flip_score, flip_valid, ','.join(flip_reasons) if flip_reasons else 'filters_passed_but_size_too_small'
            )
        
        # ===== Original NFI Entry Logic =====
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
            long_score = max(0.0, float(params["rsi_fast_buy"]) - rsi_fast[i]) + max(0.0, float(params["rsi_main_buy"]) - rsi_main[i]) + max(0.0, (bb_lower[i] - price) / price * 100)
            short_score = max(0.0, rsi_fast[i] - float(params["rsi_fast_sell"])) + max(0.0, rsi_main[i] - float(params["rsi_main_sell"])) + max(0.0, (price - bb_upper[i]) / price * 100)
            side = "SHORT" if short_score > long_score else "LONG"
        elif short_ok:
            side = "SHORT"

        # Calculate base NFI confidence
        base_confidence = self._calc_confidence_long(price, bb_lower[i], ema_trend[i], ema_long[i], rsi_fast[i], rsi_main[i], volumes[i], volume_sma[i]) if side == "LONG" else self._calc_confidence_short(price, bb_upper[i], ema_trend[i], ema_long[i], rsi_fast[i], rsi_main[i], volumes[i], volume_sma[i])
        
        # ===== Enhance confidence with market regime and SuperTrend flip =====
        confidence = base_confidence
        
        # Bonus 1: Market regime quality (up to +0.15)
        if regime_result.regime == "trending":
            confidence += 0.15 * regime_result.confidence
        elif regime_result.regime == "volatile":
            confidence += 0.05  # Small bonus for volatile (opportunity but risky)
        # Ranging: no bonus
        
        # Bonus 2: SuperTrend flip with high score (up to +0.20)
        if supertrend_flip and flip_score >= float(params.get("min_trend_flip_score", 55)):
            # Check if flip direction aligns with NFI signal
            if (side == "LONG" and flip_direction == "bullish") or (side == "SHORT" and flip_direction == "bearish"):
                flip_bonus = 0.10 + (flip_score / 100.0) * 0.10  # 0.10 to 0.20 based on score
                confidence += flip_bonus
                logger.info(
                    "%s SuperTrend flip bonus: +% .3f (score=%.0f, aligned=%s)",
                    symbol, flip_bonus, flip_score, flip_direction
                )
        
        # Bonus 3: High market score - 降低门槛 (原 70/60 → 60/50)
        if market_score >= 60:
            confidence += 0.10
        elif market_score >= 50:
            confidence += 0.05
        
        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)
        
        logger.info(
            "%s Confidence: base=%.2f -> final=%.2f (regime=%s, flip=%s, market_score=%.0f)",
            symbol, base_confidence, confidence, regime_result.regime,
            "YES" if supertrend_flip else "NO", market_score
        )
        position_size = self._calc_position_size(confidence)
        if position_size < CONFIG["min_order_value"]:
            return {"action": "HOLD", "reason": f"{symbol} position too small"}

        # Apply regime-adaptive stop loss and take profit
        regime_adjustment = REGIME_SL_TP_ADJUSTMENTS.get(regime_result.regime, {"sl_mult": 1.0, "tp_mult": 1.0})
        sl_mult = float(params["stop_loss_atr_mult"]) * regime_adjustment["sl_mult"]
        tp_mult = float(params["take_profit_atr_mult"]) * regime_adjustment["tp_mult"]
        
        logger.info(
            "%s Regime adjustment: %s -> SL_mult=%.2f (base %.2f x adj %.2f), TP_mult=%.2f (base %.2f x adj %.2f)",
            symbol, regime_result.regime, sl_mult, float(params["stop_loss_atr_mult"]), regime_adjustment["sl_mult"],
            tp_mult, float(params["take_profit_atr_mult"]), regime_adjustment["tp_mult"]
        )
        
        if side == "LONG":
            stop_loss = price - atr_now * sl_mult
            take_profit = price + atr_now * tp_mult
            action = "BUY"
        else:
            stop_loss = price + atr_now * sl_mult
            take_profit = price - atr_now * tp_mult
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
            "regime": regime_result.regime,
            "regime_confidence": regime_result.confidence,
            "supertrend_multiplier": adapted_st_mult,
            "market_score": market_score,
            "reason": f"{symbol} NFI {side} entry, RSI({rsi_fast[i]:.1f}/{rsi_main[i]:.1f}), Regime={regime_result.regime}, SL={sl_mult:.2f}xATR TP={tp_mult:.2f}xATR, Score={market_score:.0f}",
        }

    def get_account_state(self) -> Dict:
        try:
            state = self._retry_call(
                "get_account_state",
                lambda: self.info.user_state(CONFIG["main_wallet"]),
                retries=2,
                delay_sec=1.2,
            )
            margin = state.get("marginSummary", {})
            self.guard.record_success()
            return {
                "account_value": float(margin.get("accountValue", 0)),
                "withdrawable": float(state.get("withdrawable", 0)),
                "positions": state.get("assetPositions", []),
            }
        except requests.Timeout as exc:
            logger.error("failed to get account state after retries: %s", exc)
            self.guard.record_api_timeout({"op": "user_state", "error": str(exc)}, threshold=int(CONFIG.get("max_api_timeouts", 5)))
            return {"account_value": 0.0, "withdrawable": 0.0, "positions": []}
        except Exception as exc:
            logger.error("failed to get account state after retries: %s", exc)
            triggered = self.guard.record_failure("get_account_state failed", {"error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3)))
            if triggered:
                self.notify(f"🛑 获取账户状态连续失败，系统进入 SAFE_MODE\n错误: {exc}")
            else:
                logger.warning("suppressed single account-state alert after internal retries: %s", exc)
            return {"account_value": 0.0, "withdrawable": 0.0, "positions": []}

    def get_open_orders(self) -> List[Dict]:
        try:
            orders = self._retry_call(
                "get_open_orders(frontend)",
                lambda: self.info.frontend_open_orders(CONFIG["main_wallet"]),
                retries=1,
                delay_sec=0.8,
            )
            self.guard.record_success()
            return orders
        except Exception:
            try:
                orders = self._retry_call(
                    "get_open_orders(legacy)",
                    lambda: self.info.open_orders(CONFIG["main_wallet"]),
                    retries=1,
                    delay_sec=0.8,
                )
                self.guard.record_success()
                return orders
            except requests.Timeout as exc:
                logger.error("failed to get open orders after retries: %s", exc)
                self.guard.record_api_timeout({"op": "open_orders", "error": str(exc)}, threshold=int(CONFIG.get("max_api_timeouts", 5)))
                return []
            except Exception as exc:
                logger.error("failed to get open orders after retries: %s", exc)
                triggered = self.guard.record_failure("get_open_orders failed", {"error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3)))
                if triggered:
                    self.notify(f"🛑 获取挂单状态连续失败，系统进入 SAFE_MODE\n错误: {exc}")
                else:
                    logger.warning("suppressed single open-orders alert after internal retries: %s", exc)
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
            result = self.exchange.order(symbol, is_buy, size, price, {"limit": {"tif": "Gtc"}}, reduce_only=reduce_only)
            logger.info("order result: %s", result)
            self.guard.record_success()
            return result
        except requests.Timeout as exc:
            logger.error("failed to place order: %s", exc)
            self.guard.record_api_timeout({"op": "place_order", "symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_api_timeouts", 5)))
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            logger.error("failed to place order: %s", exc)
            self.guard.record_failure("place_order failed", {"symbol": symbol, "error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3)))
            return {"status": "error", "message": str(exc)}

    def _safe_mode_can_auto_recover(self) -> bool:
        reason = str(self.guard.state.get("safe_reason") or "").lower()
        if not bool(CONFIG.get("auto_exit_safe_mode_on_api_recovery", True)):
            return False
        recoverable_markers = (
            "get_account_state failed",
            "get_open_orders failed",
            "api timeouts >=",
            "cycle exception",
        )
        return any(marker in reason for marker in recoverable_markers)

    def _protection_safe_mode_can_auto_clear(self) -> bool:
        reason = str(self.guard.state.get("safe_reason") or "").lower()
        protection_markers = (
            "protection order placement failed",
            "protection missing",
            "protection setup",
        )
        return any(marker in reason for marker in protection_markers)

    def _recover_from_protection_safe_mode_if_possible(self) -> bool:
        if not self.guard.in_safe_mode() or not self._protection_safe_mode_can_auto_clear():
            return False
        try:
            account = self.get_account_state()
            open_orders = self.get_open_orders()
        except Exception:
            return False

        live_positions = []
        for item in account.get("positions", []):
            p = item.get("position", {})
            if float(p.get("szi", 0) or 0) != 0:
                live_positions.append(p)

        orders_by_coin: Dict[str, List[Dict]] = {}
        for order in open_orders or []:
            coin = order.get("coin")
            if coin:
                orders_by_coin.setdefault(coin, []).append(order)

        # If there are no live positions, the old protection-failure SAFE_MODE is stale and can be cleared.
        if not live_positions:
            self.guard.exit_safe_mode()
            self.notify("✅ 当前已无实际持仓，已自动清除残留的保护单 SAFE_MODE，恢复正常交易检查。")
            return True

        # If there are live positions, only clear SAFE_MODE when every live position already has both TP and SL.
        for p in live_positions:
            symbol = p.get("coin")
            symbol_orders = orders_by_coin.get(symbol, [])
            trigger_orders = [
                o for o in symbol_orders
                if str(o.get("orderType", "")).lower().find("trigger") >= 0
                or o.get("triggerCondition")
                or str(o.get("origType", "")).lower().find("trigger") >= 0
            ]
            has_stop = any(str(o.get("tpsl", "")).lower() == "sl" or str(o.get("orderType", "")).lower().find("sl") >= 0 for o in trigger_orders)
            has_tp = any(str(o.get("tpsl", "")).lower() == "tp" or str(o.get("orderType", "")).lower().find("tp") >= 0 for o in trigger_orders)
            if not (has_stop and has_tp):
                return False

        self.guard.exit_safe_mode()
        self.notify("✅ 当前持仓保护单已齐全，已自动退出残留 SAFE_MODE，恢复正常交易检查。")
        return True

    def _recover_from_api_safe_mode_if_possible(self) -> bool:
        if not self.guard.in_safe_mode() or not self._safe_mode_can_auto_recover():
            return False
        try:
            self.get_account_state()
            self.get_open_orders()
        except Exception:
            return False
        self.guard.exit_safe_mode()
        self.notify("✅ Hyperliquid API 已恢复连通，系统已自动退出 SAFE_MODE，并恢复正常交易检查；当前若仍未开仓，表示只是策略条件尚未满足。")
        return True

    def can_trade(self) -> bool:
        if self.guard.in_safe_mode():
            if self._recover_from_api_safe_mode_if_possible():
                logger.info("SAFE_MODE auto-cleared after API recovery")
            elif self._recover_from_protection_safe_mode_if_possible():
                logger.info("SAFE_MODE auto-cleared after protection-state reconciliation")
            else:
                logger.warning("SAFE_MODE active: %s", self.guard.state.get("safe_reason"))
                return False
        if self.last_loss_time and datetime.now() - self.last_loss_time < timedelta(seconds=CONFIG["trade_cooldown"]):
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
                self.guard.enter_safe_mode("drawdown >= 20%", {"drawdown": drawdown})
                self.notify(f"🛑 账户回撤达到 {drawdown * 100:.2f}%，系统进入 SAFE_MODE")
                return False
        return True

    def log_trade(self, signal: Dict, result: Dict) -> None:
        log_entry = {"time": datetime.now().isoformat(), "signal": signal, "result": result}
        log_file = LOG_DIR / "trades_nfi.jsonl"
        with log_file.open("a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def run_cycle(self) -> None:
        logger.info("=" * 50)
        logger.info("start NFI cycle")
        self.refresh_position_states()
        if not self.can_trade():
            logger.info("risk guard blocked this cycle")
            return

        for symbol in CONFIG["symbols"]:
            if self.has_position(symbol):
                logger.info("%s already has position, skip", symbol)
                continue

            signal = self.analyze_symbol(symbol)
            self.store.record_signal(symbol, signal.get("action", "HOLD"), signal.get("confidence"), signal.get("reason", ""), signal)
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
                logger.info("  net: $%.2f (%.2f%%) fee: $%.2f", fee.get("net_profit", 0.0), fee.get("net_profit_pct", 0.0), fee.get("total_fees", 0.0))

            if not self.exchange:
                logger.info("monitor-only signal for %s", symbol)
                continue

            self.cancel_all_orders(symbol)
            is_buy = signal["action"] == "BUY"
            raw_order_size = signal["size"] / signal["entry_price"]
            order_size = self._normalize_order_size(symbol, raw_order_size)
            if order_size <= 0:
                logger.error("%s normalized order size is zero, raw=%s", symbol, raw_order_size)
                self.store.record_event("ERROR", "entry_size_zero_after_rounding", f"{symbol} order size rounded to zero", {"symbol": symbol, "raw_order_size": raw_order_size})
                continue
            client_id = str(uuid.uuid4())
            result = self.place_order(symbol, is_buy, order_size, signal["entry_price"])
            self.log_trade(signal, result)
            order_id = self._extract_order_id(result)
            self.store.record_order(symbol, "ENTRY", "BUY" if is_buy else "SELL", order_id, client_id, signal["entry_price"], order_size, result.get("status", "unknown"), result)

            if result.get("status") == "ok" or order_id is not None:
                logger.info("%s order submitted", symbol)
                self.notify(f"📈 {symbol} 发出 {'BUY' if is_buy else 'SELL'} 开仓单，入场价 {signal['entry_price']:.4f}")
                confirmed_pos = self.wait_for_entry_fill(symbol, signal["action"], order_size)
                if not confirmed_pos:
                    return
                if not self.ensure_protection_orders(symbol, signal, confirmed_pos=confirmed_pos):
                    logger.error("%s protection setup failed", symbol)
                    return
            else:
                logger.error("%s order failed: %s", symbol, result)
                if self.guard.record_failure("entry order failed", {"symbol": symbol, "result": result}, threshold=int(CONFIG.get("max_consecutive_failures", 3))):
                    self.notify(f"🛑 {symbol} 连续下单失败，系统进入 SAFE_MODE")

    def run(self) -> None:
        logger.info("NostalgiaForInfinity-inspired trader started")
        self.store.record_event("INFO", "startup", "NFI trader started", {"symbols": CONFIG["symbols"]})
        self.notify(f"🚀 NFI trader 启动，模式: {'LIVE' if self.exchange else 'MONITOR_ONLY'}")
        logger.info("symbols: %s", CONFIG["symbols"])
        logger.info("timeframe: %s", CONFIG["timeframe"])
        by_symbol = CONFIG.get("trade_side_by_symbol") or {}
        for symbol in CONFIG["symbols"]:
            ts = by_symbol.get(symbol, CONFIG.get("trade_side", "both"))
            logger.info("trade_side %s: %s", symbol, ts)
        for symbol in CONFIG["symbols"]:
            p = self._get_nfi_params(symbol)
            logger.info("%s params: ema(%s/%s/%s), rsi(%s/%s<=%.1f/%.1f), bb(%s,%.1f), sl/tp(%.1f/%.1f)xATR", symbol, int(p["ema_fast"]), int(p["ema_trend"]), int(p["ema_long"]), int(p["rsi_fast"]), int(p["rsi_main"]), float(p["rsi_fast_buy"]), float(p["rsi_main_buy"]), int(p["bb_period"]), float(p["bb_stddev"]), float(p["stop_loss_atr_mult"]), float(p["take_profit_atr_mult"]))

        self.startup_reconcile()

        while True:
            try:
                self.run_cycle()
            except Exception as exc:
                logger.error("cycle exception: %s", exc, exc_info=True)
                self.store.record_event("ERROR", "cycle_exception", str(exc), {})
                if self.guard.record_failure("cycle exception", {"error": str(exc)}, threshold=int(CONFIG.get("max_consecutive_failures", 3))):
                    self.notify(f"🛑 NFI trader 出现连续异常，已进入 SAFE_MODE: {exc}")
            logger.info("sleep %ss", CONFIG["check_interval"])
            time.sleep(CONFIG["check_interval"])


def main() -> None:
    load_hl_config()
    load_runtime_config()
    CONFIG["trader_mode"] = (os.getenv("TRADER_MODE", CONFIG.get("trader_mode", "monitor")) or "monitor").strip().lower()
    if CONFIG["trader_mode"] not in {"monitor", "live"}:
        logger.warning("Unknown TRADER_MODE=%s, fallback to monitor", CONFIG["trader_mode"])
        CONFIG["trader_mode"] = "monitor"
    if not CONFIG["main_wallet"]:
        env_wallet = (os.getenv("LUCKYNIUMA_WALLET") or "").strip()
        if env_wallet:
            CONFIG["main_wallet"] = env_wallet
            logger.info("MAIN_WALLET not found in .hl_config, using LUCKYNIUMA_WALLET from environment")
    if not CONFIG["main_wallet"]:
        logger.warning(
            "MAIN_WALLET missing: trader will not start live/monitor loop. "
            "Set trading-scripts/config/.hl_config or LUCKYNIUMA_WALLET to enable trader startup."
        )
        return
    if CONFIG["trader_mode"] == "live" and not CONFIG["api_private_key"]:
        logger.warning("TRADER_MODE=live 但 API_PRIVATE_KEY 缺失：回退为 monitor-only")
        CONFIG["trader_mode"] = "monitor"
    elif not CONFIG["api_private_key"]:
        logger.warning("API_PRIVATE_KEY 缺失：将启动 NFI 进程但仅记录信号；补齐密钥后重启 auto-trader 即可恢复实盘")

    trader = NostalgiaForInfinityTrader()
    trader.run()


if __name__ == "__main__":
    main()
