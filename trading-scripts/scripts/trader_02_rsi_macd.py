#!/usr/bin/env python3
"""
策略2: RSI + MACD 双确认交易机器人
逻辑：RSI判断超买超卖，MACD确认趋势方向
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

# RSI + MACD 参数
STRATEGY_PARAMS = {
    "rsi_period": 14,
    "rsi_oversold": 30,  # RSI < 30 超卖
    "rsi_overbought": 70,  # RSI > 70 超买
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_02_rsi_macd.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("RsiMacdTrader")


def rsi_wilder(values: List[float], period: int) -> List[float]:
    """Wilder RSI计算"""
    if len(values) < 2:
        return [50.0] * len(values)
    
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]
    
    avg_gains = []
    avg_losses = []
    
    for i in range(len(gains)):
        if i < period - 1:
            avg_gains.append(sum(gains[:i+1]) / (i+1))
            avg_losses.append(sum(losses[:i+1]) / (i+1))
        elif i == period - 1:
            avg_gains.append(sum(gains[:period]) / period)
            avg_losses.append(sum(losses[:period]) / period)
        else:
            avg_gains.append((avg_gains[-1] * (period-1) + gains[i]) / period)
            avg_losses.append((avg_losses[-1] * (period-1) + losses[i]) / period)
    
    rsi = []
    for ag, al in zip(avg_gains, avg_losses):
        if al == 0:
            rsi.append(100.0)
        else:
            rs = ag / al
            rsi.append(100.0 - (100.0 / (1 + rs)))
    
    return [50.0] + rsi


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    mult = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * mult + out[-1] * (1 - mult))
    return out


def macd_calc(values: List[float], fast: int, slow: int, signal: int):
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def analyze_rsi_macd(closes: List[float]) -> Dict:
    """RSI + MACD 双确认分析"""
    p = STRATEGY_PARAMS
    
    # 计算RSI
    rsi_values = rsi_wilder(closes, p["rsi_period"])
    
    # 计算MACD
    macd_line, signal_line, histogram = macd_calc(
        closes, p["macd_fast"], p["macd_slow"], p["macd_signal"]
    )
    
    if len(closes) < 2:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    current_rsi = rsi_values[-1]
    prev_rsi = rsi_values[-2] if len(rsi_values) > 1 else current_rsi
    
    # RSI 信号
    rsi_oversold = current_rsi < p["rsi_oversold"]  # 超卖，可能反弹
    rsi_overbought = current_rsi > p["rsi_overbought"]  # 超买，可能回调
    rsi_turning_up = prev_rsi < current_rsi  # RSI上升
    rsi_turning_down = prev_rsi > current_rsi  # RSI下降
    
    # MACD 信号
    macd_golden = macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]  # 金叉
    macd_death = macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]  # 死叉
    macd_above = macd_line[-1] > signal_line[-1]  # MACD在信号线上方
    macd_below = macd_line[-1] < signal_line[-1]  # MACD在信号线下方
    
    # 双确认逻辑
    # 做多：RSI超卖且开始回升 + MACD金叉或在上方
    long_signal = rsi_oversold and rsi_turning_up and (macd_golden or macd_above)
    
    # 做空：RSI超买且开始下降 + MACD死叉或在下方
    short_signal = rsi_overbought and rsi_turning_down and (macd_death or macd_below)
    
    return {
        "action": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
        "reason": f"RSI({current_rsi:.1f},oversold:{rsi_oversold},overbought:{rsi_overbought},turning:{'up' if rsi_turning_up else 'down'}),"
                  f"MACD({'golden' if macd_golden else 'death' if macd_death else 'hold'})",
        "rsi": current_rsi,
        "rsi_oversold": rsi_oversold,
        "rsi_overbought": rsi_overbought,
        "macd_golden": macd_golden,
        "macd_death": macd_death,
        "price": closes[-1],
    }


class RsiMacdTrader:
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
        logger.info("RSI + MACD 双确认交易机器人启动")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    signal = analyze_rsi_macd(klines["close"])
                    
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
    trader = RsiMacdTrader()
    trader.run()
