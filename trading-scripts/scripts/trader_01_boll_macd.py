#!/usr/bin/env python3
"""
策略1: BOLL + MACD 共振交易机器人 V3 (稳健版)
改进：
1. BTC: MACD快周期14, ETH: 布林带周期15
2. 止损1.5ATR, 止盈2.5ATR
3. 添加跟踪止损1.0ATR保护利润
4. 回撤控制3%以内，低风险稳健运行
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
from trade_state import load_trade_times, save_trade_times

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
LOG_DIR = WORKSPACE_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 读取配置文件
def load_config():
    config_path = Path(__file__).resolve().parents[1] / "config" / ".hl_config"
    cfg = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    cfg[key] = value
    return cfg

hl_cfg = load_config()

CONFIG = {
    "main_wallet": hl_cfg.get("MAIN_WALLET", ""),
    "api_wallet": hl_cfg.get("API_WALLET", ""),
    "api_private_key": hl_cfg.get("API_PRIVATE_KEY", os.getenv("HL_API_KEY", "")),
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
}

# V3 稳健版参数
SYMBOL_PARAMS = {
    "BTC": {
        "bb_period": 20,
        "bb_stddev": 2.0,
        "macd_fast": 14,      # 优化：从12改为14
        "macd_slow": 26,
        "macd_signal": 9,
        "stop_loss_atr": 1.5,  # 止损1.5倍ATR
        "take_profit_atr": 2.5, # 止盈2.5倍ATR
        "trail_atr": 1.0,      # 跟踪止损1.0倍ATR
    },
    "ETH": {
        "bb_period": 15,       # 优化：从20改为15
        "bb_stddev": 2.0,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "stop_loss_atr": 1.5,
        "take_profit_atr": 2.5,
        "trail_atr": 1.0,
    }
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_01_boll_macd.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("BollMacdTrader")


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
    
    atr = []
    for i in range(len(tr_list)):
        if i < period - 1:
            atr.append(sum(tr_list[:i+1]) / (i+1))
        elif i == period - 1:
            atr.append(sum(tr_list[:period]) / period)
        else:
            atr.append((atr[-1] * (period-1) + tr_list[i]) / period)
    return atr


def analyze_boll_macd(symbol: str, closes: List[float], highs: List[float], lows: List[float]) -> Dict:
    """BOLL + MACD 共振分析 V3稳健版"""
    p = SYMBOL_PARAMS.get(symbol, SYMBOL_PARAMS["BTC"])
    
    # 计算指标
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, p["bb_period"], p["bb_stddev"])
    macd_line, signal_line, histogram = macd_calc(
        closes, p["macd_fast"], p["macd_slow"], p["macd_signal"]
    )
    atr_values = calculate_atr(highs, lows, closes)
    
    if len(closes) < 2:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    prev_price = closes[-2]
    
    # BOLL信号
    boll_long = price <= bb_lower[-1] * 1.01
    boll_short = price >= bb_upper[-1] * 0.99
    
    # MACD信号
    macd_long = macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]
    macd_short = macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]
    
    # 共振判断
    resonance_long = boll_long and macd_long
    resonance_short = boll_short and macd_short
    
    # 计算止损止盈
    atr = atr_values[-1] if atr_values[-1] > 0 else price * 0.01
    stop_loss = 0
    take_profit = 0
    
    if resonance_long:
        stop_loss = price - p["stop_loss_atr"] * atr
        take_profit = price + p["take_profit_atr"] * atr
    elif resonance_short:
        stop_loss = price + p["stop_loss_atr"] * atr
        take_profit = price - p["take_profit_atr"] * atr
    
    return {
        "action": "LONG" if resonance_long else "SHORT" if resonance_short else "HOLD",
        "reason": f"BOLL({'long' if boll_long else 'short' if boll_short else 'none'}),"
                  f"MACD({'golden' if macd_long else 'death' if macd_short else 'none'})",
        "price": price,
        "atr": atr,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "bb_lower": bb_lower[-1],
        "bb_upper": bb_upper[-1],
        "macd": macd_line[-1],
        "signal": signal_line[-1],
    }


class BollMacdTrader:
    def __init__(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = None
        self.last_trade_time = load_trade_times("boll_macd")
        self.positions = {}
        self._setup_exchange()
        
    def _setup_exchange(self):
        if CONFIG["api_private_key"]:
            account = Account.from_key(CONFIG["api_private_key"])
            self.exchange = Exchange(account, constants.MAINNET_API_URL, account_address=CONFIG["main_wallet"])

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

    def get_klines(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> Dict:
        try:
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = end_time - (limit * 60 * 60 * 1000)
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
    
    def check_exit(self, symbol: str, current_price: float) -> tuple:
        """检查止盈止损，返回(should_exit, exit_type, pnl_pct)"""
        if symbol not in self.positions:
            return False, None, 0
        
        pos = self.positions[symbol]
        p = SYMBOL_PARAMS.get(symbol, SYMBOL_PARAMS["BTC"])
        atr = pos.get("atr", current_price * 0.01)
        
        # 更新跟踪止损
        if pos["type"] == "LONG":
            # 价格涨了，上移止损
            new_sl = max(pos["stop_loss"], current_price - p["trail_atr"] * atr)
            if new_sl > pos["stop_loss"]:
                logger.info(f"{symbol} 跟踪止损上移: {pos['stop_loss']:.2f} -> {new_sl:.2f}")
                pos["stop_loss"] = new_sl
            
            # 检查止损
            if current_price <= pos["stop_loss"]:
                pnl_pct = (current_price - pos["entry"]) / pos["entry"]
                return True, "STOP_LOSS", pnl_pct
            
            # 检查止盈
            if current_price >= pos["take_profit"]:
                pnl_pct = (current_price - pos["entry"]) / pos["entry"]
                return True, "TAKE_PROFIT", pnl_pct
        
        else:  # SHORT
            # 价格跌了，下移止损
            new_sl = min(pos["stop_loss"], current_price + p["trail_atr"] * atr)
            if new_sl < pos["stop_loss"]:
                logger.info(f"{symbol} 跟踪止损下移: {pos['stop_loss']:.2f} -> {new_sl:.2f}")
                pos["stop_loss"] = new_sl
            
            if current_price >= pos["stop_loss"]:
                pnl_pct = (pos["entry"] - current_price) / pos["entry"]
                return True, "STOP_LOSS", pnl_pct
            
            if current_price <= pos["take_profit"]:
                pnl_pct = (pos["entry"] - current_price) / pos["entry"]
                return True, "TAKE_PROFIT", pnl_pct
        
        return False, None, 0
    
    def can_trade(self, symbol: str) -> bool:
        last_time = self.last_trade_time.get(symbol, 0)
        return time.time() - last_time > CONFIG["trade_cooldown"]
    
    def execute_exit(self, symbol: str, exit_type: str, pnl_pct: float):
        """执行平仓"""
        if symbol not in self.positions:
            return
        
        pos = self.positions[symbol]
        
        # 实盘平仓
        if self.exchange:
            try:
                # 平掉当前仓位
                is_buy = pos["type"] == "SHORT"  # 空头平仓用买单
                size = abs(pos.get("size", 0))
                if size > 0:
                    current_price = signal["price"]
                limit_price = current_price * 1.01 if is_buy else current_price * 0.99
                limit_price = round(limit_price, 1)
                result = self.exchange.order(
                    symbol, is_buy, size, limit_price, {"limit": {"tif": "Gtc"}}, reduce_only=True
                )
                logger.info(f"【实盘平仓】{symbol} 结果: {result}")
            except Exception as e:
                logger.error(f"平仓失败 {symbol}: {e}")
        
        logger.info(f"【平仓】{symbol} {pos['type']} | 原因: {exit_type} | 盈亏: {pnl_pct*100:.2f}%")
        del self.positions[symbol]
    
    def execute_entry(self, symbol: str, signal: Dict):
        """执行开仓"""
        side_limit = CONFIG["trade_side_by_symbol"].get(symbol, CONFIG["trade_side"])
        action = signal["action"]
        
        if action == "LONG" and side_limit == "short_only":
            logger.info(f"{symbol} 多头信号被过滤")
            return
        if action == "SHORT" and side_limit == "long_only":
            logger.info(f"{symbol} 空头信号被过滤")
            return
        
        # 计算仓位大小 (使用账户余额的30%)
        size = 0
        if self.exchange:
            try:
                position_value = 30.0  # 固定仓位
                # 不查询余额，使用固定仓位
                # position_value = 30.0 已设置
                size = position_value / signal["price"]
                if size * signal["price"] < CONFIG["min_order_value"]:
                    logger.warning(f"{symbol} 订单金额太小，跳过")
                    return
            except Exception as e:
                logger.error(f"获取账户信息失败: {e}")
                return
        
        # 实盘开仓
        if self.exchange and size > 0:
            try:
                is_buy = action == "LONG"
                current_price = signal["price"]
                limit_price = current_price * 1.01 if is_buy else current_price * 0.99
                limit_price = round(limit_price, 1)
                result = self.exchange.order(
                    symbol, is_buy, size, limit_price, {"limit": {"tif": "Gtc"}}
                )
                logger.info(f"【实盘开仓】{symbol} {action} 结果: {result}")
                
                # 检查订单是否真正成功
                if result.get("status") != "ok":
                    logger.error(f"开仓失败: {result}")
                    return
                
                # 检查内部statuses是否有错误
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses and len(statuses) > 0:
                    if "error" in statuses[0]:
                        logger.error(f"开仓被拒绝: {statuses[0]['error']}")
                        return
                    if "resting" not in statuses[0] and "filled" not in statuses[0]:
                        logger.error(f"开仓异常: {statuses[0]}")
                        return
                
                logger.info(f"【成功】{symbol} {action} 订单已提交")
                
            except Exception as e:
                logger.error(f"开仓失败 {symbol}: {e}")
                return
        else:
            logger.warning(f"【模拟开仓】{symbol} {action}")
            return
        
        # 记录持仓
        self.positions[symbol] = {
            "type": action,
            "entry": signal["price"],
            "size": size,
            "atr": signal["atr"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "entry_time": time.time()
        }
        
        logger.info(f"【开仓】{symbol} {action} @ {signal['price']:.2f} | 数量: {size:.4f} | "
                   f"止损: {signal['stop_loss']:.2f} | 止盈: {signal['take_profit']:.2f}")
        self.last_trade_time[symbol] = time.time()
        save_trade_times("boll_macd", self.last_trade_time)
    
    def run(self):
        logger.info("=" * 50)
        logger.info("BOLL + MACD V3 稳健版交易机器人启动")
        logger.info("策略: MACD14(BTC)/BB15(ETH) + 1.5ATR止损/2.5ATR止盈 + 跟踪止损")
        logger.info("目标: 回撤<5%, 稳健收益")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足")
                        continue
                    
                    current_price = klines["close"][-1]
                    
                    # 1. 先检查止盈止损
                    if symbol in self.positions:
                        should_exit, exit_type, pnl_pct = self.check_exit(symbol, current_price)
                        if should_exit:
                            self.execute_exit(symbol, exit_type, pnl_pct)
                            continue
                    
                    # 2. 检查是否有持仓（内存 + 链上）
                    if symbol in self.positions:
                        logger.info(f"{symbol} 持仓中: {self.positions[symbol]['type']} | "
                                   f"当前价: {current_price:.2f} | 跟踪止损: {self.positions[symbol]['stop_loss']:.2f}")
                        continue
                    
                    pos = self.get_position(symbol)
                    if pos["size"] != 0:
                        logger.info(f"{symbol} 链上已有持仓(size={pos['size']}), 跳过开仓")
                        continue
                    
                    # 3. 检查冷却
                    if not self.can_trade(symbol):
                        logger.info(f"{symbol} 冷却中...")
                        continue
                    
                    # 4. 分析信号
                    signal = analyze_boll_macd(
                        symbol, klines["close"], klines["high"], klines["low"]
                    )
                    
                    # 5. 执行开仓
                    if signal["action"] != "HOLD":
                        self.execute_entry(symbol, signal)
                    else:
                        logger.info(f"{symbol} {signal['action']}: {signal['reason']}")
                
                logger.info(f"Sleep {CONFIG['check_interval']}s")
                time.sleep(CONFIG["check_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                time.sleep(300)


if __name__ == "__main__":
    trader = BollMacdTrader()
    trader.run()
