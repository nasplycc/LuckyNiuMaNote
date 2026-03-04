#!/usr/bin/env python3
"""
策略1: BOLL + MACD 共振交易机器人 (优化版)
改进：
1. BTC: MACD快周期14, 止损1.5ATR, 止盈2.5ATR
2. ETH: 布林带周期15
3. 增加ADX趋势过滤(>25)
4. 增加成交量确认(>1.2倍均量)
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

# 按币种优化的参数
SYMBOL_PARAMS = {
    "BTC": {
        "bb_period": 20,
        "bb_stddev": 2.0,
        "macd_fast": 14,  # 优化：从12改为14
        "macd_slow": 26,
        "macd_signal": 9,
        "min_bandwidth_expansion": 1.02,
        "adx_threshold": 25,  # ADX趋势强度阈值
        "volume_multiplier": 1.2,  # 成交量倍数
        "stop_loss_atr": 1.5,  # 优化：从2.0改为1.5
        "take_profit_atr": 2.5,  # 优化：从3.0改为2.5
    },
    "ETH": {
        "bb_period": 15,  # 优化：从20改为15
        "bb_stddev": 2.0,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "min_bandwidth_expansion": 1.02,
        "adx_threshold": 25,
        "volume_multiplier": 1.2,
        "stop_loss_atr": 1.5,
        "take_profit_atr": 2.5,
    }
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_01_boll_macd_v2.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("BollMacdTraderV2")


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


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """计算ATR"""
    if len(highs) < 2:
        return [0.0] * len(highs)
    
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


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """计算ADX趋势强度"""
    if len(highs) < period * 2:
        return [20.0] * len(highs)
    
    # +DM, -DM
    plus_dm = []
    minus_dm = []
    for i in range(len(highs)):
        if i == 0:
            plus_dm.append(0)
            minus_dm.append(0)
        else:
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)
            
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)
    
    # 计算ATR
    atr = calculate_atr(highs, lows, closes, period)
    
    # +DI, -DI
    plus_di = []
    minus_di = []
    for i in range(len(atr)):
        if atr[i] > 0:
            plus_di.append(100 * plus_dm[i] / atr[i])
            minus_di.append(100 * minus_dm[i] / atr[i])
        else:
            plus_di.append(0)
            minus_di.append(0)
    
    # DX
    dx = []
    for i in range(len(plus_di)):
        if plus_di[i] + minus_di[i] > 0:
            dx.append(100 * abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i]))
        else:
            dx.append(0)
    
    # ADX
    adx = []
    for i in range(len(dx)):
        if i < period - 1:
            adx.append(sum(dx[:i+1]) / (i+1))
        elif i == period - 1:
            adx.append(sum(dx[:period]) / period)
        else:
            adx.append((adx[-1] * (period-1) + dx[i]) / period)
    
    return adx


def analyze_boll_macd_v2(symbol: str, closes: List[float], highs: List[float], 
                         lows: List[float], volumes: List[float]) -> Dict:
    """优化版BOLL + MACD共振分析"""
    p = SYMBOL_PARAMS.get(symbol, SYMBOL_PARAMS["BTC"])
    
    # 计算布林带
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, p["bb_period"], p["bb_stddev"])
    
    # 计算带宽
    bandwidths = [(u - l) / m if m > 0 else 0 for u, l, m in zip(bb_upper, bb_lower, bb_mid)]
    
    # 计算MACD
    macd_line, signal_line, histogram = macd_calc(
        closes, p["macd_fast"], p["macd_slow"], p["macd_signal"]
    )
    
    # 计算ADX趋势强度
    adx_values = calculate_adx(highs, lows, closes)
    
    # 计算成交量均值
    volume_sma = sma(volumes, 20)
    
    # 计算ATR用于止损
    atr_values = calculate_atr(highs, lows, closes)
    
    if len(closes) < 50:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    prev_price = closes[-2]
    
    # BOLL信号
    boll_long = price <= bb_lower[-1] * 1.01
    boll_short = price >= bb_upper[-1] * 0.99
    
    # 带宽扩张检测
    bandwidth_expanding = False
    if len(bandwidths) >= 3:
        bandwidth_expanding = bandwidths[-1] > bandwidths[-2] * p["min_bandwidth_expansion"]
    
    # MACD信号
    macd_long = macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]
    macd_short = macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]
    
    # ADX趋势强度过滤
    adx_strong = adx_values[-1] > p["adx_threshold"]
    
    # 成交量确认
    volume_confirmed = False
    if len(volume_sma) > 0 and volume_sma[-1] > 0:
        volume_confirmed = volumes[-1] > volume_sma[-1] * p["volume_multiplier"]
    
    # 止损止盈价位
    atr = atr_values[-1] if atr_values[-1] > 0 else price * 0.01
    stop_loss_long = price - p["stop_loss_atr"] * atr
    take_profit_long = price + p["take_profit_atr"] * atr
    stop_loss_short = price + p["stop_loss_atr"] * atr
    take_profit_short = price - p["take_profit_atr"] * atr
    
    # 共振判断（添加ADX和成交量过滤）
    resonance_long = boll_long and macd_long and bandwidth_expanding and adx_strong and volume_confirmed
    resonance_short = boll_short and macd_short and bandwidth_expanding and adx_strong and volume_confirmed
    
    # 如果没有强ADX，只要求带宽扩张（降低门槛）
    if not resonance_long and not resonance_short:
        resonance_long = boll_long and macd_long and bandwidth_expanding
        resonance_short = boll_short and macd_short and bandwidth_expanding
    
    return {
        "action": "LONG" if resonance_long else "SHORT" if resonance_short else "HOLD",
        "reason": f"BOLL({'touch_lower' if boll_long else 'touch_upper' if boll_short else 'none'}),"
                  f"MACD({'golden' if macd_long else 'death' if macd_short else 'none'}),"
                  f"BB_exp:{bandwidth_expanding},ADX:{adx_values[-1]:.1f}({'' if adx_strong else 'weak'}),"
                  f"Vol:{'' if volume_confirmed else 'no_conf'}",
        "boll_long": boll_long,
        "boll_short": boll_short,
        "macd_long": macd_long,
        "macd_short": macd_short,
        "bandwidth_expanding": bandwidth_expanding,
        "adx": adx_values[-1],
        "adx_strong": adx_strong,
        "volume_confirmed": volume_confirmed,
        "price": price,
        "bb_lower": bb_lower[-1],
        "bb_upper": bb_upper[-1],
        "macd": macd_line[-1],
        "signal": signal_line[-1],
        "stop_loss": stop_loss_long if resonance_long else stop_loss_short if resonance_short else 0,
        "take_profit": take_profit_long if resonance_long else take_profit_short if resonance_short else 0,
    }


class BollMacdTraderV2:
    def __init__(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = None
        self.last_trade_time = {}
        self.positions = {}  # 跟踪持仓
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
    
    def check_exit_conditions(self, symbol: str, current_price: float, signal: Dict) -> bool:
        """检查是否需要平仓（止损/止盈）"""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        stop_loss = pos.get("stop_loss", 0)
        take_profit = pos.get("take_profit", 0)
        
        if pos["type"] == "LONG":
            if current_price <= stop_loss:
                logger.info(f"{symbol} 触发止损: {current_price} <= {stop_loss}")
                return True
            if current_price >= take_profit:
                logger.info(f"{symbol} 触发止盈: {current_price} >= {take_profit}")
                return True
        else:  # SHORT
            if current_price >= stop_loss:
                logger.info(f"{symbol} 触发止损: {current_price} >= {stop_loss}")
                return True
            if current_price <= take_profit:
                logger.info(f"{symbol} 触发止盈: {current_price} <= {take_profit}")
                return True
        
        return False
    
    def can_trade(self, symbol: str) -> bool:
        """检查交易冷却"""
        last_time = self.last_trade_time.get(symbol, 0)
        return time.time() - last_time > CONFIG["trade_cooldown"]
    
    def execute_trade(self, symbol: str, signal: Dict):
        """执行交易"""
        if not self.exchange:
            logger.warning(f"[模拟] {symbol} {signal['action']}: {signal['reason']}")
            # 模拟持仓跟踪
            if signal['action'] != "HOLD":
                self.positions[symbol] = {
                    "type": signal['action'],
                    "entry": signal['price'],
                    "stop_loss": signal['stop_loss'],
                    "take_profit": signal['take_profit'],
                    "time": time.time()
                }
                self.last_trade_time[symbol] = time.time()
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
        
        # 记录持仓
        if action != "HOLD":
            self.positions[symbol] = {
                "type": action,
                "entry": signal['price'],
                "stop_loss": signal['stop_loss'],
                "take_profit": signal['take_profit'],
                "time": time.time()
            }
            self.last_trade_time[symbol] = time.time()
    
    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("BOLL + MACD 共振交易机器人V2启动")
        logger.info("优化: MACD快周期14, 布林带15(ETH), ADX过滤, 成交量确认")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    # 获取数据
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    current_price = klines["close"][-1]
                    
                    # 检查是否需要平仓
                    if self.check_exit_conditions(symbol, current_price, {}):
                        logger.info(f"{symbol} 执行平仓")
                        if symbol in self.positions:
                            del self.positions[symbol]
                        continue
                    
                    # 分析信号
                    signal = analyze_boll_macd_v2(
                        symbol,
                        klines["close"], 
                        klines["high"], 
                        klines["low"],
                        klines["volume"]
                    )
                    
                    # 检查冷却
                    if not self.can_trade(symbol):
                        signal["action"] = "HOLD"
                        signal["reason"] += " (cooldown)"
                    
                    # 执行交易
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
    trader = BollMacdTraderV2()
    trader.run()
