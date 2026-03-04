#!/usr/bin/env python3
"""
布林带震荡套利策略回测 (均值回归)
逻辑：价格触及下轨做多(回归中轨)，触及上轨做空(回归中轨)
⚠️ 只在震荡市使用，趋势市会亏损
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

# 布林带套利参数
PARAMS = {
    "bb_period": 20,
    "bb_stddev": 2.0,
    "entry_threshold": 1.0,      # 触及轨道阈值
    "exit_threshold": 0.3,       # 中轨附近平仓
    "max_bandwidth_pct": 0.05,   # 最大带宽5%(超过认为是趋势市)
    "min_bandwidth_pct": 0.01,   # 最小带宽1%
    "stop_loss_atr": 2.0,        # 2倍ATR止损(防止趋势延续)
}

def adx_simple(highs: list, lows: list, closes: list) -> float:
    """简化ADX估算"""
    p = 14
    if len(highs) < p + 1:
        return 20.0
    tr = [highs[0]-lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = sum(tr[-p:]) / p
    price_range = max(closes[-p:]) - min(closes[-p:])
    return min(50, (price_range / atr) * 10) if atr > 0 else 20

def backtest_bb_mean_reversion(candles: list, symbol: str) -> dict:
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    
    bb_mid, bb_upper, bb_lower = bb(c, PARAMS["bb_period"], PARAMS["bb_stddev"])
    atr_vals = atr(h, l, c)
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(30, len(c)-1):
        price = c[i]
        mid = bb_mid[i]
        upper = bb_upper[i]
        lower = bb_lower[i]
        
        # 带宽计算
        bandwidth = (upper - lower) / mid if mid > 0 else 0
        
        # 趋势过滤
        adx_val = adx_simple(h[:i+1], l[:i+1], c[:i+1])
        is_ranging = bandwidth <= PARAMS["max_bandwidth_pct"] and bandwidth >= PARAMS["min_bandwidth_pct"]
        
        # 检查平仓
        if pos:
            near_mid = abs(price - mid) / mid < PARAMS["exit_threshold"]
            stop_hit = (pos["type"] == "LONG" and price <= pos["sl"]) or (pos["type"] == "SHORT" and price >= pos["sl"])
            
            if near_mid or stop_hit:
                if pos["type"] == "LONG":
                    pnl = (price - pos["entry"]) / pos["entry"] * leverage
                else:
                    pnl = (pos["entry"] - price) / pos["entry"] * leverage
                
                capital = capital * (1 + pnl * 0.3 - 0.0007)
                trades.append({"type": pos["type"], "pnl": pnl * 0.3})
                equity.append((candles[i]["t"], capital))
                pos = None
        
        # 开新仓 (只在震荡市)
        if not pos and is_ranging and adx_val < 25:
            touch_lower = price <= lower * (1 + PARAMS["entry_threshold"] - 1)
            touch_upper = price >= upper * (1 - PARAMS["entry_threshold"] + 1)
            near_mid = abs(price - mid) / mid < PARAMS["exit_threshold"]
            
            atr_val = atr_vals[i] if atr_vals[i] > 0 else price * 0.01
            
            if touch_lower and not near_mid:
                pos = {"type": "LONG", "entry": price,
                       "sl": price - PARAMS["stop_loss_atr"] * atr_val}
            elif touch_upper and not near_mid:
                pos = {"type": "SHORT", "entry": price,
                       "sl": price + PARAMS["stop_loss_atr"] * atr_val}
    
    # 计算指标
    if not trades: return {"error": "无交易"}
    
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
    print("布林带震荡套利策略回测")
    print("⚠️  均值回归策略 - 只在震荡市有效!")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym}】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        
        result = backtest_bb_mean_reversion(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
    
    print("\n" + "="*60)
    print("⚠️  重要提醒")
    print("="*60)
    print("此策略是均值回归，与趋势策略相反:")
    print("• 大牛市中会持续亏损 (买在回调，但趋势继续上涨)")
    print("• 只适合横盘震荡市场")
    print("• 建议与趋势策略搭配使用，对冲风险")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
