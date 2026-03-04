#!/usr/bin/env python3
"""
BOLL + MACD 共振策略 V2 回测 (优化版)
改进：
1. BTC: MACD快周期14, 止损1.5ATR, 止盈2.5ATR
2. ETH: 布林带周期15
3. 增加ADX趋势过滤
4. 增加成交量确认
"""

import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import requests

# Hyperliquid API
HL_API = "https://api.hyperliquid.xyz/info"

def hl_request(body: dict) -> dict:
    try:
        resp = requests.post(HL_API, json=body, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"API错误: {e}")
        return {}

def get_historical_candles(symbol: str, start_time: int, end_time: int) -> List[dict]:
    try:
        candles = hl_request({
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "interval": "1h"
            }
        })
        return candles if isinstance(candles, list) else []
    except Exception as e:
        print(f"获取数据失败 {symbol}: {e}")
        return []

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
    return macd_line, signal_line

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

def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    if len(highs) < period * 2:
        return [20.0] * len(highs)
    
    plus_dm, minus_dm = [], []
    for i in range(len(highs)):
        if i == 0:
            plus_dm.append(0)
            minus_dm.append(0)
        else:
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
    
    atr = calculate_atr(highs, lows, closes, period)
    
    plus_di, minus_di, dx = [], [], []
    for i in range(len(atr)):
        if atr[i] > 0:
            plus_di.append(100 * plus_dm[i] / atr[i])
            minus_di.append(100 * minus_dm[i] / atr[i])
        else:
            plus_di.append(0)
            minus_di.append(0)
        
        if plus_di[i] + minus_di[i] > 0:
            dx.append(100 * abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i]))
        else:
            dx.append(0)
    
    adx = []
    for i in range(len(dx)):
        if i < period - 1:
            adx.append(sum(dx[:i+1]) / (i+1))
        elif i == period - 1:
            adx.append(sum(dx[:period]) / period)
        else:
            adx.append((adx[-1] * (period-1) + dx[i]) / period)
    return adx

# 优化后的参数
SYMBOL_PARAMS = {
    "BTC": {
        "bb_period": 20,
        "bb_stddev": 2.0,
        "macd_fast": 14,  # 优化：14
        "macd_slow": 26,
        "macd_signal": 9,
        "adx_threshold": 25,
        "volume_mult": 1.2,
        "stop_loss_atr": 1.5,  # 优化：1.5
        "take_profit_atr": 2.5,  # 优化：2.5
    },
    "ETH": {
        "bb_period": 15,  # 优化：15
        "bb_stddev": 2.0,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "adx_threshold": 25,
        "volume_mult": 1.2,
        "stop_loss_atr": 1.5,
        "take_profit_atr": 2.5,
    }
}

def generate_signals_v2(candles: List[dict], symbol: str) -> List[dict]:
    """生成V2交易信号"""
    p = SYMBOL_PARAMS[symbol]
    
    if len(candles) < 50:
        return []
    
    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]
    volumes = [float(c["v"]) for c in candles]
    
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, p["bb_period"], p["bb_stddev"])
    macd_line, signal_line = macd_calc(closes, p["macd_fast"], p["macd_slow"], p["macd_signal"])
    adx_values = calculate_adx(highs, lows, closes)
    volume_sma = sma(volumes, 20)
    atr_values = calculate_atr(highs, lows, closes)
    bandwidths = [(u - l) / m if m > 0 else 0 for u, l, m in zip(bb_upper, bb_lower, bb_mid)]
    
    signals = []
    position = None
    
    for i in range(max(p["bb_period"], p["macd_slow"]) + 10, len(closes)):
        price = closes[i]
        
        # 检查是否需要平仓
        if position:
            pnl_pct = 0
            if position["type"] == "LONG":
                pnl_pct = (price - position["entry"]) / position["entry"]
                if price <= position["stop_loss"] or price >= position["take_profit"]:
                    signals.append({
                        "index": i, "time": candles[i]["t"], "type": "CLOSE_LONG",
                        "price": price, "pnl_pct": pnl_pct, "reason": "stop/tp"
                    })
                    position = None
            else:  # SHORT
                pnl_pct = (position["entry"] - price) / position["entry"]
                if price >= position["stop_loss"] or price <= position["take_profit"]:
                    signals.append({
                        "index": i, "time": candles[i]["t"], "type": "CLOSE_SHORT",
                        "price": price, "pnl_pct": pnl_pct, "reason": "stop/tp"
                    })
                    position = None
        
        # 生成新信号
        boll_long = price <= bb_lower[i] * 1.01
        boll_short = price >= bb_upper[i] * 0.99
        macd_long = macd_line[i] > signal_line[i] and macd_line[i-1] <= signal_line[i-1]
        macd_short = macd_line[i] < signal_line[i] and macd_line[i-1] >= signal_line[i-1]
        bandwidth_expanding = bandwidths[i] > bandwidths[i-1] * 1.02 if i > 0 else False
        adx_strong = adx_values[i] > p["adx_threshold"]
        volume_confirmed = volumes[i] > volume_sma[i] * p["volume_mult"] if volume_sma[i] > 0 else False
        
        # V2: 增加ADX和成交量过滤
        long_signal = boll_long and macd_long and bandwidth_expanding and adx_strong and volume_confirmed
        short_signal = boll_short and macd_short and bandwidth_expanding and adx_strong and volume_confirmed
        
        # 如果无强ADX，降级条件
        if not long_signal and not short_signal:
            long_signal = boll_long and macd_long and bandwidth_expanding
            short_signal = boll_short and macd_short and bandwidth_expanding
        
        if long_signal and not position:
            atr = atr_values[i] if atr_values[i] > 0 else price * 0.01
            position = {
                "type": "LONG", "entry": price,
                "stop_loss": price - p["stop_loss_atr"] * atr,
                "take_profit": price + p["take_profit_atr"] * atr,
            }
            signals.append({
                "index": i, "time": candles[i]["t"], "type": "OPEN_LONG",
                "price": price, "atr": atr, "adx": adx_values[i]
            })
        elif short_signal and not position:
            atr = atr_values[i] if atr_values[i] > 0 else price * 0.01
            position = {
                "type": "SHORT", "entry": price,
                "stop_loss": price + p["stop_loss_atr"] * atr,
                "take_profit": price - p["take_profit_atr"] * atr,
            }
            signals.append({
                "index": i, "time": candles[i]["t"], "type": "OPEN_SHORT",
                "price": price, "atr": atr, "adx": adx_values[i]
            })
    
    return signals

def backtest_v2(candles: List[dict], signals: List[dict], symbol: str) -> dict:
    """V2回测"""
    if not signals:
        return {"error": "无信号"}
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for sig in signals:
        if "CLOSE" in sig["type"]:
            pnl_amount = 0
            if trades:
                last_trade = trades[-1]
                if last_trade.get("open"):
                    entry = last_trade["entry"]
                    exit_p = sig["price"]
                    size = last_trade["size"]
                    
                    if last_trade["type"] == "LONG":
                        pnl_pct = (exit_p - entry) / entry * leverage
                    else:
                        pnl_pct = (entry - exit_p) / entry * leverage
                    
                    pnl_amount = size * pnl_pct
                    fee = size * fee_rate * 2
                    capital += pnl_amount - fee
                    
                    trades[-1].update({
                        "close": True, "exit": exit_p, "pnl_pct": pnl_pct,
                        "pnl_amount": pnl_amount - fee, "exit_time": sig["time"]
                    })
                    equity.append((sig["time"], capital))
        else:
            size = capital * 0.3 * leverage
            trades.append({
                "type": "LONG" if "LONG" in sig["type"] else "SHORT",
                "entry": sig["price"], "size": size,
                "open": True, "entry_time": sig["time"],
                "adx": sig.get("adx", 0)
            })
    
    # 计算指标
    closed_trades = [t for t in trades if t.get("close")]
    if not closed_trades:
        return {"error": "无完成交易"}
    
    winning = [t for t in closed_trades if t["pnl_amount"] > 0]
    win_rate = len(winning) / len(closed_trades) * 100
    total_return = (capital - 1000) / 1000 * 100
    
    profit_factor = sum(t["pnl_amount"] for t in winning) / abs(sum(t["pnl_amount"] for t in closed_trades if t["pnl_amount"] <= 0)) if sum(t["pnl_amount"] for t in closed_trades if t["pnl_amount"] <= 0) != 0 else float('inf')
    
    # 最大回撤
    max_dd = 0
    peak = 1000
    for _, eq in equity:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return {
        "total_trades": len(closed_trades),
        "win_rate": round(win_rate, 2),
        "total_return": round(total_return, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "final_capital": round(capital, 2),
    }

def run_backtest_v2(symbol: str, months: int = 6):
    print(f"\n{'='*60}")
    print(f"BOLL + MACD V2 回测 - {symbol}")
    print(f"优化: MACD14(BTC)/BB15(ETH) + ADX + 成交量")
    print(f"{'='*60}\n")
    
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=30*months)).timestamp() * 1000)
    
    print(f"获取历史数据...")
    candles = get_historical_candles(symbol, start_time, end_time)
    print(f"获取到 {len(candles)} 根K线\n")
    
    print("生成V2信号...")
    signals = generate_signals_v2(candles, symbol)
    print(f"信号数量: {len(signals)}\n")
    
    print("【V2 回测结果】")
    print("-" * 40)
    result = backtest_v2(candles, signals, symbol)
    
    for k, v in result.items():
        print(f"{k}: {v}")
    
    print(f"\n{'='*60}\n")
    return result

if __name__ == "__main__":
    # V1 vs V2 对比
    print("\n" + "="*60)
    print("V1 vs V2 对比回测")
    print("="*60)
    
    run_backtest_v2("BTC", 6)
    run_backtest_v2("ETH", 6)
