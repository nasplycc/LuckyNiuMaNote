#!/usr/bin/env python3
"""
策略3: VWAP 突破交易机器人
逻辑：价格突破VWAP上方做多，跌破VWAP下方做空
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

# VWAP 参数
STRATEGY_PARAMS = {
    "vwap_period": 24,  # 24小时VWAP
    "breakout_threshold": 0.002,  # 突破阈值 0.2%
    "volume_confirmation": True,  # 需要成交量确认
    "min_volume_ratio": 1.2,  # 成交量需大于均量1.2倍
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_03_vwap.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("VwapTrader")


def calculate_vwap(prices: List[float], volumes: List[float], period: int) -> List[float]:
    """计算VWAP"""
    if len(prices) != len(volumes) or len(prices) < period:
        return []
    
    vwap = []
    for i in range(len(prices)):
        start = max(0, i - period + 1)
        cum_pv = sum(p * v for p, v in zip(prices[start:i+1], volumes[start:i+1]))
        cum_vol = sum(volumes[start:i+1])
        vwap.append(cum_pv / cum_vol if cum_vol > 0 else prices[i])
    return vwap


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


def analyze_vwap_breakout(closes: List[float], volumes: List[float]) -> Dict:
    """VWAP突破分析"""
    p = STRATEGY_PARAMS
    
    # 计算VWAP
    vwap = calculate_vwap(closes, volumes, p["vwap_period"])
    
    # 计算成交量均线
    vol_sma = sma(volumes, p["vwap_period"])
    
    if len(closes) < 2 or len(vwap) < 2:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    prev_price = closes[-2]
    current_vwap = vwap[-1]
    prev_vwap = vwap[-2]
    
    # 突破检测
    price_above_vwap = price > current_vwap * (1 + p["breakout_threshold"])
    price_below_vwap = price < current_vwap * (1 - p["breakout_threshold"])
    
    # 突破方向变化检测
    cross_up = prev_price <= prev_vwap and price > current_vwap
    cross_down = prev_price >= prev_vwap and price < current_vwap
    
    # 成交量确认
    volume_confirmed = False
    if len(vol_sma) > 0 and vol_sma[-1] > 0:
        volume_ratio = volumes[-1] / vol_sma[-1]
        volume_confirmed = volume_ratio >= p["min_volume_ratio"]
    
    # 信号生成
    long_signal = cross_up and price_above_vwap
    short_signal = cross_down and price_below_vwap
    
    # 如果需要成交量确认
    if p["volume_confirmation"]:
        long_signal = long_signal and volume_confirmed
        short_signal = short_signal and volume_confirmed
    
    return {
        "action": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
        "reason": f"VWAP({current_vwap:.2f}),price({price:.2f}),"
                  f"cross:{'up' if cross_up else 'down' if cross_down else 'none'},"
                  f"vol_confirmed:{volume_confirmed}",
        "price": price,
        "vwap": current_vwap,
        "deviation": (price - current_vwap) / current_vwap,
        "cross_up": cross_up,
        "cross_down": cross_down,
        "volume_confirmed": volume_confirmed,
    }


class VwapTrader:
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
        logger.info("VWAP 突破交易机器人启动")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    signal = analyze_vwap_breakout(
                        klines["close"], 
                        klines["volume"]
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
    trader = VwapTrader()
    trader.run()
