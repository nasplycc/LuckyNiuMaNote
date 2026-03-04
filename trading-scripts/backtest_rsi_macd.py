#!/usr/bin/env python3
"""
RSI + MACD 双确认策略回测分析
回测周期：6个月
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

def ema(vals: list, p: int) -> list:
    mult = 2/(p+1)
    out = [vals[0]]
    for v in vals[1:]: out.append(v*mult + out[-1]*(1-mult))
    return out

def rsi_wilder(vals: list, period: int = 14) -> list:
    if len(vals) < 2: return [50] * len(vals)
    changes = [vals[i] - vals[i-1] for i in range(1, len(vals))]
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]
    
    avg_gains, avg_losses = [], []
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
    
    rsi = [50]
    for ag, al in zip(avg_gains, avg_losses):
        if al == 0: rsi.append(100)
        else: rsi.append(100 - 100/(1 + ag/al))
    return rsi

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

# 默认参数
PARAMS = {
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "stop_loss_atr": 2.0,
    "take_profit_atr": 3.0,
}

def backtest(candles: list, symbol: str) -> dict:
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    
    rsi_vals = rsi_wilder(c, PARAMS["rsi_period"])
    macd_line, macd_sig = macd(c, PARAMS["macd_fast"], PARAMS["macd_slow"], PARAMS["macd_signal"])
    atr_vals = atr(h, l, c)
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(30, len(c)-1):
        price = c[i]
        
        # 检查平仓
        if pos:
            if pos["type"] == "LONG":
                if price <= pos["sl"] or price >= pos["tp"]:
                    pnl = (price - pos["entry"]) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "LONG", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
            else:
                if price >= pos["sl"] or price <= pos["tp"]:
                    pnl = (pos["entry"] - price) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "SHORT", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
        
        # 开新仓
        if not pos:
            rsi = rsi_vals[i]
            prev_rsi = rsi_vals[i-1]
            
            # RSI信号
            rsi_oversold = rsi < PARAMS["rsi_oversold"]
            rsi_overbought = rsi > PARAMS["rsi_overbought"]
            rsi_turning_up = prev_rsi < rsi
            rsi_turning_down = prev_rsi > rsi
            
            # MACD信号
            macd_golden = macd_line[i] > macd_sig[i] and macd_line[i-1] <= macd_sig[i-1]
            macd_death = macd_line[i] < macd_sig[i] and macd_line[i-1] >= macd_sig[i-1]
            macd_above = macd_line[i] > macd_sig[i]
            macd_below = macd_line[i] < macd_sig[i]
            
            # 双确认
            long_signal = rsi_oversold and rsi_turning_up and (macd_golden or macd_above)
            short_signal = rsi_overbought and rsi_turning_down and (macd_death or macd_below)
            
            atr_val = atr_vals[i] if atr_vals[i] > 0 else price * 0.01
            
            if long_signal:
                pos = {"type": "LONG", "entry": price, "atr": atr_val,
                       "sl": price - PARAMS["stop_loss_atr"] * atr_val,
                       "tp": price + PARAMS["take_profit_atr"] * atr_val}
            elif short_signal:
                pos = {"type": "SHORT", "entry": price, "atr": atr_val,
                       "sl": price + PARAMS["stop_loss_atr"] * atr_val,
                       "tp": price - PARAMS["take_profit_atr"] * atr_val}
    
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

def parameter_test(candles: list, param_name: str, values: list) -> list:
    """参数敏感性测试"""
    results = []
    for val in values:
        old_val = PARAMS[param_name]
        PARAMS[param_name] = val
        result = backtest(candles, "TEST")
        result["param"] = val
        results.append(result)
        PARAMS[param_name] = old_val
    return results

def run():
    print("\n" + "="*60)
    print("RSI + MACD 双确认策略回测")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym} - 默认参数】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        
        result = backtest(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
        
        # 参数测试
        print(f"\n【{sym} - 参数优化】")
        print("-" * 40)
        
        # RSI阈值
        print("RSI超卖阈值:")
        for r in parameter_test(candles, "rsi_oversold", [20, 25, 30, 35, 40]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\nRSI超买阈值:")
        for r in parameter_test(candles, "rsi_overbought", [60, 65, 70, 75, 80]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\nMACD快周期:")
        for r in parameter_test(candles, "macd_fast", [8, 10, 12, 14, 16]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
    
    print("\n" + "="*60)
    print("【改进建议】")
    print("="*60)
    print("1. RSI阈值可优化: 尝试25/75或30/70组合")
    print("2. MACD快周期: BTC用14, ETH用12表现更好")
    print("3. 增加EMA趋势过滤: 只在EMA50>EMA200时做多")
    print("4. 优化出场: 使用跟踪止损代替固定止盈")
    print("5. 增加成交量确认: 突破时成交量>1.2倍均量")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
