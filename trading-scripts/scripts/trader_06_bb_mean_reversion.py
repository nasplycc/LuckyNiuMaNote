#!/usr/bin/env python3
"""
策略6: 布林带震荡套利交易机器人 (均值回归策略)
逻辑：价格触及下轨做多（赌回归中轨），触及上轨做空（赌回归中轨）
注意：只在震荡市使用，趋势市会亏损
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
    "trade_cooldown": 14400,
    "trade_side": "both",
    "trade_side_by_symbol": {"BTC": "short_only", "ETH": "both"},
    "maker_fee": 0.0001,
    "taker_fee": 0.00035,
    "min_profit_after_fee": 0.005,
}

# 布林带震荡套利参数
STRATEGY_PARAMS = {
    "bb_period": 20,
    "bb_stddev": 2.0,
    "entry_threshold": 1.0,     # 触及轨道的阈值（1.0 = 正好触及）
    "exit_threshold": 0.3,      # 中轨附近平仓阈值
    "max_bandwidth_pct": 0.05,  # 最大带宽5%，超过认为是趋势市
    "min_bandwidth_pct": 0.01,  # 最小带宽1%，太窄不交易
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_06_bb_mean_reversion.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("BbMeanReversionTrader")


def sma(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out = []
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
    out = []
    for idx in range(len(values)):
        start = max(0, idx - period + 1)
        window = values[start:idx+1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        out.append(variance ** 0.5)
    return out


def bollinger_bands(values: List[float], period: int, std_mult: float):
    mid = sma(values, period)
    std = rolling_std(values, period)
    upper = [m + std_mult * s for m, s in zip(mid, std)]
    lower = [m - std_mult * s for m, s in zip(mid, std)]
    return mid, upper, lower


def adx_filter(highs: List[float], lows: List[float], closes: List[float]) -> float:
    """简单ADX计算，用于过滤趋势"""
    period = 14
    if len(highs) < period + 1:
        return 20.0
    
    tr_list = []
    for i in range(len(highs)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(highs[i] - lows[i], 
                    abs(highs[i] - closes[i-1]), 
                    abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    
    atr = sum(tr_list[-period:]) / period
    price_range = max(closes[-period:]) - min(closes[-period:])
    
    # 简单的趋势强度估计
    adx_estimate = min(50, (price_range / atr) * 10) if atr > 0 else 20
    return adx_estimate


def analyze_bb_mean_reversion(closes: List[float], highs: List[float], lows: List[float]) -> Dict:
    """布林带均值回归分析"""
    p = STRATEGY_PARAMS
    
    # 计算布林带
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, p["bb_period"], p["bb_stddev"])
    
    if len(closes) < p["bb_period"]:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    mid = bb_mid[-1]
    upper = bb_upper[-1]
    lower = bb_lower[-1]
    
    # 计算带宽（作为震荡市/趋势市判断）
    bandwidth = (upper - lower) / mid if mid > 0 else 0
    
    # 趋势过滤 - ADX
    adx_val = adx_filter(highs, lows, closes)
    
    # 是否是震荡市判断
    is_ranging = bandwidth <= p["max_bandwidth_pct"] and bandwidth >= p["min_bandwidth_pct"]
    
    # 如果不是震荡市，不交易（避免趋势市被套）
    if not is_ranging:
        return {
            "action": "HOLD",
            "reason": f"not_ranging(bandwidth:{bandwidth:.3f},adx:{adx_val:.1f})",
            "is_ranging": False,
            "bandwidth": bandwidth,
        }
    
    # 偏离中轨的距离（标准化）
    deviation = (price - mid) / (upper - lower) if (upper - lower) > 0 else 0
    
    # 触及轨道检测
    touch_lower = price <= lower * (1 + p["entry_threshold"] - 1)  # 触及或突破下轨
    touch_upper = price >= upper * (1 - p["entry_threshold"] + 1)  # 触及或突破上轨
    
    # 中轨附近检测（平仓用）
    near_mid = abs(price - mid) / mid < p["exit_threshold"]
    
    # 信号生成
    # 触及下轨做多（回归中轨）
    long_signal = touch_lower and not near_mid
    # 触及上轨做空（回归中轨）
    short_signal = touch_upper and not near_mid
    
    return {
        "action": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
        "reason": f"BB_reversion(dev:{deviation:.2f},bandwidth:{bandwidth:.3f},"
                  f"touch_lower:{touch_lower},touch_upper:{touch_upper},near_mid:{near_mid})",
        "price": price,
        "bb_mid": mid,
        "bb_upper": upper,
        "bb_lower": lower,
        "deviation": deviation,
        "bandwidth": bandwidth,
        "is_ranging": is_ranging,
        "touch_lower": touch_lower,
        "touch_upper": touch_upper,
        "near_mid": near_mid,
    }


class BbMeanReversionTrader:
    def __init__(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = None
        self.last_trade_time = {}
        self._setup_exchange()
        
    def _setup_exchange(self):
        if CONFIG["api_private_key"]:
            account = Account.from_key(CONFIG["api_private_key"])
            self.exchange = Exchange(account, constants.MAINNET_API_URL, account_address=CONFIG["main_wallet"])
            
    def get_klines(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> Dict:
        """获取K线数据"""
        try:
            from datetime import datetime, timedelta
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = end_time - (limit * 60 * 60 * 1000 if timeframe == "1h" else limit * 60 * 1000)
            
            candles = self.info.candles_snapshot(symbol, timeframe, start_time, end_time)
            
            return {
                "open": [float(c["o"]) for c in candles],
                "high": [float(c["h"]) for c in candles],
                "low": [float(c["l"]) for c in candles],
                "close": [float(c["c"]) for c in candles],
                "volume": [float(c["v"]) for c in candles],
            }
        except Exception as e:
            logger.error(f"获取K线失败 {symbol}: {e}")
            return None
    
    def get_position(self, symbol: str) -> Dict:
        """获取当前持仓"""
        try:
            state = self.info.user_state(CONFIG["main_wallet"])
            for pos in state.get("assetPositions", []):
                if pos["position"]["coin"] == symbol:
                    return {
                        "size": float(pos["position"]["szi"]),
                        "entry_price": float(pos["position"]["entryPx"]),
                        "unrealized_pnl": float(pos["position"]["unrealizedPnl"]),
                    }
            return {"size": 0, "entry_price": 0, "unrealized_pnl": 0}
        except Exception as e:
            logger.error(f"获取持仓失败 {symbol}: {e}")
            return {"size": 0, "entry_price": 0, "unrealized_pnl": 0}
    
    def can_trade(self, symbol: str) -> bool:
        """检查交易冷却"""
        last_time = self.last_trade_time.get(symbol, 0)
        return time.time() - last_time > CONFIG["trade_cooldown"]
    
    def execute_trade(self, symbol: str, signal: Dict):
        """执行交易"""
        if not self.exchange:
            logger.warning(f"[模拟] {symbol} {signal['action']}: {signal['reason']}")
            return
            
        side_limit = CONFIG["trade_side_by_symbol"].get(symbol, CONFIG["trade_side"])
        
        action = signal["action"]
        if action == "LONG" and side_limit == "short_only":
            logger.info(f"{symbol} 多头信号被过滤 (仅做空)")
            return
        if action == "SHORT" and side_limit == "long_only":
            logger.info(f"{symbol} 空头信号被过滤 (仅做多)")
            return
            
        # 检查是否在震荡市
        if not signal.get("is_ranging", False):
            logger.info(f"{symbol} 非震荡市，不执行均值回归交易")
            return
            
        logger.info(f"[下单] {symbol} {action}: {signal['reason']}")
        self.last_trade_time[symbol] = time.time()
    
    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("布林带震荡套利交易机器人启动")
        logger.info("⚠️ 警告：此策略仅在震荡市有效，趋势市会亏损！")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    signal = analyze_bb_mean_reversion(
                        klines["close"],
                        klines["high"],
                        klines["low"]
                    )
                    
                    if not self.can_trade(symbol):
                        signal["action"] = "HOLD"
                        signal["reason"] += " (cooldown)"
                    
                    if signal["action"] != "HOLD":
                        self.execute_trade(symbol, signal)
                    else:
                        logger.info(f"{symbol} {signal['action']}: {signal['reason']}")
                
                logger.info(f"Sleep {CONFIG['check_interval']}s")
                time.sleep(CONFIG["check_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                time.sleep(300)


if __name__ == "__main__":
    trader = BbMeanReversionTrader()
    trader.run()
