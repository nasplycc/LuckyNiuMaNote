#!/usr/bin/env python3
"""
策略4: SuperTrend 趋势跟随交易机器人
逻辑：ATR + 移动平均线，价格在SuperTrend线上方做多，下方做空
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

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

# SuperTrend 参数 (优化版: ATR乘数4.0)
STRATEGY_PARAMS = {
    "atr_period": 10,
    "atr_multiplier": 4.0,  # 优化：从3.0改为4.0，过滤假信号
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_04_supertrend.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("SuperTrendTrader")


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    """计算ATR (Average True Range)"""
    if len(highs) < 2 or len(lows) < 2 or len(closes) < 2:
        return [0.0] * len(closes)
    
    tr_list = []
    for i in range(len(highs)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i-1])
            tr3 = abs(lows[i] - closes[i-1])
            tr = max(tr1, tr2, tr3)
        tr_list.append(tr)
    
    # Wilder平滑
    atr = []
    for i in range(len(tr_list)):
        if i < period - 1:
            atr.append(sum(tr_list[:i+1]) / (i+1))
        elif i == period - 1:
            atr.append(sum(tr_list[:period]) / period)
        else:
            atr.append((atr[-1] * (period-1) + tr_list[i]) / period)
    
    return atr


def calculate_supertrend(highs: List[float], lows: List[float], closes: List[float], 
                         atr_period: int, atr_mult: float):
    """计算SuperTrend"""
    atr = calculate_atr(highs, lows, closes, atr_period)
    
    # 基础上下轨
    basic_upper = []
    basic_lower = []
    for i in range(len(closes)):
        avg_price = (highs[i] + lows[i]) / 2
        basic_upper.append(avg_price + atr_mult * atr[i])
        basic_lower.append(avg_price - atr_mult * atr[i])
    
    # 最终上下轨和趋势方向
    final_upper = [basic_upper[0]]
    final_lower = [basic_lower[0]]
    trend = [1]  # 1 = 多头, -1 = 空头
    
    for i in range(1, len(closes)):
        prev_close = closes[i-1]
        
        # 上轨
        if basic_upper[i] < final_upper[i-1] or prev_close > final_upper[i-1]:
            final_upper.append(basic_upper[i])
        else:
            final_upper.append(final_upper[i-1])
        
        # 下轨
        if basic_lower[i] > final_lower[i-1] or prev_close < final_lower[i-1]:
            final_lower.append(basic_lower[i])
        else:
            final_lower.append(final_lower[i-1])
        
        # 趋势判断
        if closes[i] > final_upper[i-1]:
            trend.append(1)
        elif closes[i] < final_lower[i-1]:
            trend.append(-1)
        else:
            trend.append(trend[i-1])
    
    # SuperTrend线
    supertrend = []
    for i in range(len(trend)):
        if trend[i] == 1:
            supertrend.append(final_lower[i])
        else:
            supertrend.append(final_upper[i])
    
    return supertrend, trend, final_upper, final_lower


def analyze_supertrend(highs: List[float], lows: List[float], closes: List[float]) -> Dict:
    """SuperTrend趋势跟随分析"""
    p = STRATEGY_PARAMS
    
    supertrend, trend, upper_band, lower_band = calculate_supertrend(
        highs, lows, closes, p["atr_period"], p["atr_multiplier"]
    )
    
    if len(closes) < 2:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    prev_price = closes[-2]
    current_trend = trend[-1]
    prev_trend = trend[-2] if len(trend) > 1 else current_trend
    
    # 趋势反转检测
    trend_flip_long = prev_trend == -1 and current_trend == 1  # 空头转多头
    trend_flip_short = prev_trend == 1 and current_trend == -1  # 多头转空头
    
    # 信号生成
    long_signal = trend_flip_long
    short_signal = trend_flip_short
    
    return {
        "action": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
        "reason": f"SuperTrend({current_trend},{'flip_long' if trend_flip_long else 'flip_short' if trend_flip_short else 'hold'}),"
                  f"price({price:.2f}),st({supertrend[-1]:.2f})",
        "price": price,
        "supertrend": supertrend[-1],
        "trend": current_trend,
        "trend_flip_long": trend_flip_long,
        "trend_flip_short": trend_flip_short,
        "upper_band": upper_band[-1],
        "lower_band": lower_band[-1],
    }


class SuperTrendTrader:
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
            
        logger.info(f"[下单] {symbol} {action}: {signal['reason']}")
        self.last_trade_time[symbol] = time.time()
    
    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("SuperTrend 趋势跟随交易机器人启动")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    signal = analyze_supertrend(
                        klines["high"],
                        klines["low"],
                        klines["close"]
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
    trader = SuperTrendTrader()
    trader.run()
