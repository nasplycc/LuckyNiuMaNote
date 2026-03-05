#!/usr/bin/env python3
"""
策略5: ADX 趋势强度过滤交易机器人
逻辑：ADX衡量趋势强度，趋势强时跟随趋势，趋势弱时观望或反向
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
    "trade_cooldown": 14400,  # 默认值，实际按 COIN_PARAMS 中的 cooldown 覆盖
    "trade_side": "both",
    "trade_side_by_symbol": {"BTC": "short_only", "ETH": "both"},
    "maker_fee": 0.0001,
    "taker_fee": 0.00035,
    "min_profit_after_fee": 0.005,
}

# ADX 参数 (回测优化: 3月+6月跨时段验证，按币种独立优化)
STRATEGY_PARAMS = {
    "adx_strong_trend": 25,
    "adx_weak_trend": 20,
}

COIN_PARAMS = {
    "BTC": {"ema_fast": 8, "ema_slow": 50, "cooldown": 3600},    # 1h冷却: 3月+16.82% 6月+37.51% 评分28.08
    "ETH": {"ema_fast": 25, "ema_slow": 30, "cooldown": 14400},  # 4h冷却: 3月+34.41% 6月+44.46% 评分41.81
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader_05_adx.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("AdxTrader")


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int):
    """计算ADX, +DI, -DI"""
    if len(highs) < period + 1:
        return [20.0] * len(highs), [20.0] * len(highs), [20.0] * len(highs)
    
    # True Range
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
    
    # Wilder平滑
    atr = []
    plus_di = []
    minus_di = []
    dx = []
    adx = []
    
    for i in range(len(tr_list)):
        if i < period - 1:
            atr.append(sum(tr_list[:i+1]) / (i+1))
            plus_di.append(sum(plus_dm[:i+1]) / (i+1))
            minus_di.append(sum(minus_dm[:i+1]) / (i+1))
        elif i == period - 1:
            atr.append(sum(tr_list[:period]) / period)
            plus_di.append(sum(plus_dm[:period]) / period)
            minus_di.append(sum(minus_dm[:period]) / period)
        else:
            atr.append((atr[-1] * (period-1) + tr_list[i]) / period)
            plus_di.append((plus_di[-1] * (period-1) + plus_dm[i]) / period)
            minus_di.append((minus_di[-1] * (period-1) + minus_dm[i]) / period)
        
        # 计算DI
        if atr[i] > 0:
            pdi = 100 * plus_di[i] / atr[i]
            mdi = 100 * minus_di[i] / atr[i]
        else:
            pdi = 0
            mdi = 0
        
        # 计算DX
        if pdi + mdi > 0:
            dx_val = 100 * abs(pdi - mdi) / (pdi + mdi)
        else:
            dx_val = 0
        
        dx.append(dx_val)
        
        # 计算ADX (DX的平滑)
        if i < period * 2 - 2:
            adx.append(sum(dx[:i+1]) / (i+1))
        elif i == period * 2 - 2:
            adx.append(sum(dx[-period:]) / period)
        else:
            adx.append((adx[-1] * (period-1) + dx_val) / period)
    
    return adx, plus_di, minus_di


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    mult = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * mult + out[-1] * (1 - mult))
    return out


def analyze_adx_trend(symbol: str, highs: List[float], lows: List[float], closes: List[float]) -> Dict:
    """ADX趋势强度过滤分析 (按币种独立双EMA + ADX过滤)"""
    p = STRATEGY_PARAMS
    cp = COIN_PARAMS.get(symbol, {"ema_fast": 25, "ema_slow": 30})
    adx_period = 10
    
    adx, plus_di, minus_di = calculate_adx(highs, lows, closes, adx_period)
    
    ema_fast_vals = ema(closes, cp["ema_fast"])
    ema_slow_vals = ema(closes, cp["ema_slow"])
    
    if len(closes) < 30:
        return {"action": "HOLD", "reason": "insufficient_data"}
    
    price = closes[-1]
    current_adx = adx[-1]
    current_plus_di = plus_di[-1]
    current_minus_di = minus_di[-1]
    
    strong_trend = current_adx > p["adx_strong_trend"]
    weak_trend = current_adx < p["adx_weak_trend"]
    
    di_bullish = current_plus_di > current_minus_di
    di_bearish = current_minus_di > current_plus_di
    
    ema_bullish = ema_fast_vals[-1] > ema_slow_vals[-1]
    ema_bearish = ema_fast_vals[-1] < ema_slow_vals[-1]
    
    long_signal = strong_trend and di_bullish and ema_bullish
    short_signal = strong_trend and di_bearish and ema_bearish
    
    return {
        "action": "LONG" if long_signal else "SHORT" if short_signal else "HOLD",
        "reason": f"ADX({current_adx:.1f},{'strong' if strong_trend else 'weak' if weak_trend else 'medium'}),"
                  f"+DI({current_plus_di:.1f}),-DI({current_minus_di:.1f}),"
                  f"EMA{cp['ema_fast']}/{cp['ema_slow']}({'bull' if ema_bullish else 'bear'})",
        "price": price,
        "adx": current_adx,
        "plus_di": current_plus_di,
        "minus_di": current_minus_di,
        "strong_trend": strong_trend,
        "weak_trend": weak_trend,
        "di_bullish": di_bullish,
        "di_bearish": di_bearish,
    }


class AdxTrader:
    def __init__(self):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = None
        self.last_trade_time = load_trade_times("adx")
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
        cooldown = COIN_PARAMS.get(symbol, {}).get("cooldown", CONFIG["trade_cooldown"])
        return time.time() - last_time > cooldown
    
    def execute_trade(self, symbol: str, signal: Dict):
        """执行交易"""
        side_limit = CONFIG["trade_side_by_symbol"].get(symbol, CONFIG["trade_side"])
        
        action = signal["action"]
        if action == "LONG" and side_limit == "short_only":
            logger.info(f"{symbol} 多头信号被过滤 (仅做空)")
            return
        if action == "SHORT" and side_limit == "long_only":
            logger.info(f"{symbol} 空头信号被过滤 (仅做多)")
            return
        
        if self.exchange:
            try:
                self.exchange.update_leverage(CONFIG["default_leverage"], symbol, is_cross=True)
                position_value = 30.0
                current_price = signal["price"]
                # 计算数量并舍入到正确精度（BTC 5位，ETH 4位）
                raw_size = position_value / current_price
                sz_decimals = 5 if symbol == "BTC" else 4
                size = float(f"{raw_size:.{sz_decimals}f}")
                
                # 确保最小订单金额
                if size * current_price < CONFIG["min_order_value"]:
                    logger.warning(f"{symbol} 订单金额太小({size * current_price:.2f}<{CONFIG['min_order_value']}), 跳过")
                    return
                
                is_buy = action == "LONG"
                # 使用限价单，价格为当前价的1%偏离（确保快速成交）
                limit_price = current_price * 1.01 if is_buy else current_price * 0.99
                limit_price = float(f"{limit_price:.1f}")  # 保留1位小数
                
                logger.info(f"【准备下单】{symbol} {action} 数量:{size} 价格:{limit_price}")
                
                result = self.exchange.order(
                    symbol, is_buy, size, limit_price, {"limit": {"tif": "Gtc"}}
                )
                logger.info(f"【实盘】{symbol} {action} 结果:{result}")
                
                # 检查订单是否真正成功（不仅外层status，还要检查内部statuses）
                if result.get("status") != "ok":
                    logger.error(f"下单失败: {result}")
                    return
                
                # 检查内部statuses是否有错误
                statuses = result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses and len(statuses) > 0:
                    if "error" in statuses[0]:
                        logger.error(f"下单被拒绝: {statuses[0]['error']}")
                        return
                    if "resting" not in statuses[0] and "filled" not in statuses[0]:
                        logger.error(f"下单异常: {statuses[0]}")
                        return
                
                logger.info(f"【成功】{symbol} {action} 订单已提交")
                
            except Exception as e:
                logger.error(f"下单失败 {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return
        else:
            logger.warning(f"【模拟】{symbol} {action}: {signal['reason']}")
            return
        
        self.last_trade_time[symbol] = time.time()
        save_trade_times("adx", self.last_trade_time)
    
    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("ADX 趋势强度过滤交易机器人启动")
        logger.info("=" * 50)
        
        while True:
            try:
                for symbol in CONFIG["symbols"]:
                    klines = self.get_klines(symbol, CONFIG["timeframe"])
                    if not klines or len(klines["close"]) < 50:
                        logger.warning(f"{symbol} 数据不足，跳过")
                        continue
                    
                    signal = analyze_adx_trend(
                        symbol,
                        klines["high"],
                        klines["low"],
                        klines["close"]
                    )
                    
                    if not self.can_trade(symbol):
                        signal["action"] = "HOLD"
                        signal["reason"] += " (cooldown)"
                    
                    if signal["action"] != "HOLD":
                        pos = self.get_position(symbol)
                        if pos["size"] != 0:
                            logger.info(f"{symbol} 已有持仓(size={pos['size']}), 跳过开仓")
                            continue
                        self.execute_trade(symbol, signal)
                    else:
                        logger.info(f"{symbol} {signal['action']}: {signal['reason']}")
                
                logger.info(f"Sleep {CONFIG['check_interval']}s")
                time.sleep(CONFIG["check_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                time.sleep(300)


if __name__ == "__main__":
    trader = AdxTrader()
    trader.run()
