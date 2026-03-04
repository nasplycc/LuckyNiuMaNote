#!/usr/bin/env python3
"""
BOLL + MACD V3 回测 - 平衡版
优化：保留最优参数，放宽ADX过滤，重点优化出场
"""

import json
import math
from datetime import datetime, timedelta
from typing import Dict, List
import requests

HL_API = "https://api.hyperliquid.xyz/info"

def hl_request(body: dict) -> dict:
    try:
        resp = requests.post(HL_API, json=body, timeout=30)
        return resp.json()
    except:
        return {}

def get_candles(symbol: str, start: int, end: int) -> list:
    try:
        return hl_request({
            "type": "candleSnapshot",
            "req": {"coin": symbol, "startTime": start, "endTime": end, "interval": "1h"}
        }) or []
    except:
        return []

def sma(vals: list, p: int) -> list:
    out, running = [], 0
    for i, v in enumerate(vals):
        running += v
        if i >= p: running -= vals[i-p]
        out.append(running / min(i+1, p))
    return out

def std(vals: list, p: int) -> list:
    out = []
    for i in range(len(vals)):
        window = vals[max(0,i-p+1):i+1]
        m = sum(window)/len(window)
        out.append(math.sqrt(sum((x-m)**2 for x in window)/len(window)))
    return out

def bb(vals: list, p: int, m: float):
    mid = sma(vals, p)
    s = std(vals, p)
    return mid, [a+m*b for a,b in zip(mid,s)], [a-m*b for a,b in zip(mid,s)]

def ema(vals: list, p: int) -> list:
    mult = 2/(p+1)
    out = [vals[0]]
    for v in vals[1:]: out.append(v*mult + out[-1]*(1-mult))
    return out

def macd(vals: list, f: int, s: int, sig: int):
    ef, es = ema(vals, f), ema(vals, s)
    line = [a-b for a,b in zip(ef, es)]
    signal = ema(line, sig)
    return line, signal

def atr(highs: list, lows: list, closes: list, p: int = 14):
    tr = [highs[0]-lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    out = []
    for i in range(len(tr)):
        if i < p-1: out.append(sum(tr[:i+1])/(i+1))
        elif i == p-1: out.append(sum(tr[:p])/p)
        else: out.append((out[-1]*(p-1) + tr[i])/p)
    return out

# V3参数 - 平衡版，不过度过滤
PARAMS = {
    "BTC": {"bb_p": 20, "bb_s": 2.0, "macd_f": 14, "macd_s": 26, "macd_sig": 9,
            "sl_atr": 1.5, "tp_atr": 2.5, "trail_atr": 1.0},
    "ETH": {"bb_p": 15, "bb_s": 2.0, "macd_f": 12, "macd_s": 26, "macd_sig": 9,
            "sl_atr": 1.5, "tp_atr": 2.5, "trail_atr": 1.0}
}

def backtest_v3(candles: list, symbol: str) -> dict:
    p = PARAMS[symbol]
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    
    bb_m, bb_u, bb_l = bb(c, p["bb_p"], p["bb_s"])
    macd_line, macd_sig = macd(c, p["macd_f"], p["macd_s"], p["macd_sig"])
    atr_vals = atr(h, l, c)
    
    capital = 1000
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(30, len(c)-1):
        price = c[i]
        
        # 检查平仓
        if pos:
            # 跟踪止损
            if pos["type"] == "LONG":
                new_sl = max(pos["sl"], price - p["trail_atr"] * pos["atr"])
                pos["sl"] = new_sl
                if price <= pos["sl"] or price >= pos["tp"]:
                    pnl = (price - pos["entry"]) / pos["entry"] * 2
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "LONG", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
            else:
                new_sl = min(pos["sl"], price + p["trail_atr"] * pos["atr"])
                pos["sl"] = new_sl
                if price >= pos["sl"] or price <= pos["tp"]:
                    pnl = (pos["entry"] - price) / pos["entry"] * 2
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "SHORT", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
        
        # 开新仓
        if not pos:
            boll_long = price <= bb_l[i] * 1.01
            boll_short = price >= bb_u[i] * 0.99
            macd_long = macd_line[i] > macd_sig[i] and macd_line[i-1] <= macd_sig[i-1]
            macd_short = macd_line[i] < macd_sig[i] and macd_line[i-1] >= macd_sig[i-1]
            
            atr_val = atr_vals[i] if atr_vals[i] > 0 else price * 0.01
            
            if boll_long and macd_long:
                pos = {"type": "LONG", "entry": price, "atr": atr_val,
                       "sl": price - p["sl_atr"] * atr_val,
                       "tp": price + p["tp_atr"] * atr_val}
            elif boll_short and macd_short:
                pos = {"type": "SHORT", "entry": price, "atr": atr_val,
                       "sl": price + p["sl_atr"] * atr_val,
                       "tp": price - p["tp_atr"] * atr_val}
    
    # 计算指标
    if not trades:
        return {"error": "无交易"}
    
    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins)/len(trades)*100
    total_ret = (capital-1000)/1000*100
    
    max_dd = 0
    peak = 1000
    for _, eq in equity:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak-eq)/peak*100)
    
    profit_f = sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0)) if sum(t["pnl"] for t in trades if t["pnl"] <= 0) != 0 else 999
    
    return {
        "交易次数": len(trades),
        "胜率": round(win_rate, 1),
        "总收益": round(total_ret, 2),
        "盈亏比": round(profit_f, 2),
        "最大回撤": round(max_dd, 2),
        "最终资金": round(capital, 2)
    }

def run():
    print("\n" + "="*60)
    print("BOLL + MACD V3 回测 - 平衡版")
    print("改进: 最优参数 + 跟踪止损，无ADX/成交量过滤")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym}】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        result = backtest_v3(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
    
    print("\n" + "="*60)
    print("对比 V1:")
    print("  BTC: 49.2%收益, 40.9%胜率, 2.19盈亏比, 24.84%回撤")
    print("  ETH: 21.1%收益, 42.9%胜率, 1.53盈亏比, 31.03%回撤")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
