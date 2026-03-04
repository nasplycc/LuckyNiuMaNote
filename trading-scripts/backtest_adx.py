#!/usr/bin/env python3
"""
ADX 趋势强度过滤策略回测
逻辑：ADX>25趋势强时跟随趋势，ADX<20趋势弱时观望
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

def adx_calc(highs: list, lows: list, closes: list, p: int = 14):
    """计算ADX, +DI, -DI"""
    plus_dm, minus_dm = [], []
    for i in range(len(highs)):
        if i == 0:
            plus_dm.append(0)
            minus_dm.append(0)
        else:
            up = highs[i] - highs[i-1]
            down = lows[i-1] - lows[i]
            plus_dm.append(up if up > down and up > 0 else 0)
            minus_dm.append(down if down > up and down > 0 else 0)
    
    atr_vals = atr(highs, lows, closes, p)
    
    plus_di, minus_di, dx = [], [], []
    for i in range(len(atr_vals)):
        if atr_vals[i] > 0:
            plus_di.append(100 * plus_dm[i] / atr_vals[i])
            minus_di.append(100 * minus_dm[i] / atr_vals[i])
        else:
            plus_di.append(0)
            minus_di.append(0)
        
        if plus_di[i] + minus_di[i] > 0:
            dx.append(100 * abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i]))
        else:
            dx.append(0)
    
    adx = []
    for i in range(len(dx)):
        if i < p-1: adx.append(sum(dx[:i+1])/(i+1))
        elif i == p-1: adx.append(sum(dx[:p])/p)
        else: adx.append((adx[-1]*(p-1) + dx[i])/p)
    
    return adx, plus_di, minus_di

# ADX参数
PARAMS = {
    "adx_period": 14,
    "adx_strong": 25,    # ADX>25趋势强
    "adx_weak": 20,      # ADX<20趋势弱
    "ema_fast": 20,
    "ema_slow": 50,
    "stop_loss_atr": 2.0,
    "take_profit_atr": 3.0,
}

def backtest_adx(candles: list, symbol: str) -> dict:
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    
    adx_vals, plus_di, minus_di = adx_calc(h, l, c, PARAMS["adx_period"])
    ema_fast = ema(c, PARAMS["ema_fast"])
    ema_slow = ema(c, PARAMS["ema_slow"])
    atr_vals = atr(h, l, c)
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(30, len(c)-1):
        price = c[i]
        
        # ADX状态
        adx_strong = adx_vals[i] > PARAMS["adx_strong"]
        adx_weak = adx_vals[i] < PARAMS["adx_weak"]
        
        # DI方向
        di_bullish = plus_di[i] > minus_di[i]
        di_bearish = minus_di[i] > plus_di[i]
        
        # EMA趋势
        ema_bullish = ema_fast[i] > ema_slow[i]
        ema_bearish = ema_fast[i] < ema_slow[i]
        
        # 检查平仓
        if pos:
            if pos["type"] == "LONG":
                if price <= pos["sl"] or price >= pos["tp"] or (adx_weak and di_bearish):
                    pnl = (price - pos["entry"]) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "LONG", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
            else:
                if price >= pos["sl"] or price <= pos["tp"] or (adx_weak and di_bullish):
                    pnl = (pos["entry"] - price) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "SHORT", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
        
        # 开新仓 (只在趋势强时)
        if not pos and adx_strong:
            atr_val = atr_vals[i] if atr_vals[i] > 0 else price * 0.01
            
            if di_bullish and ema_bullish:
                pos = {"type": "LONG", "entry": price,
                       "sl": price - PARAMS["stop_loss_atr"] * atr_val,
                       "tp": price + PARAMS["take_profit_atr"] * atr_val}
            elif di_bearish and ema_bearish:
                pos = {"type": "SHORT", "entry": price,
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
    results = []
    for val in values:
        old_val = PARAMS[param_name]
        PARAMS[param_name] = val
        result = backtest_adx(candles, "TEST")
        result["param"] = val
        results.append(result)
        PARAMS[param_name] = old_val
    return results

def run():
    print("\n" + "="*60)
    print("ADX 趋势强度过滤策略回测")
    print("逻辑: ADX>25 + DI方向 + EMA趋势")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym} - 默认参数】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        
        result = backtest_adx(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
        
        # 参数测试
        print(f"\n【{sym} - 参数优化】")
        print("-" * 40)
        
        print("ADX强趋势阈值:")
        for r in parameter_test(candles, "adx_strong", [20, 22, 25, 28, 30]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\nEMA快周期:")
        for r in parameter_test(candles, "ema_fast", [10, 15, 20, 25, 30]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
    
    print("\n" + "="*60)
    print("【改进建议】")
    print("="*60)
    print("1. ADX阈值: 25标准，可尝试22-28范围")
    print("2. EMA周期: 20/50是标准组合")
    print("3. 增加: ADX上升确认趋势加强")
    print("4. 优化: 震荡市ADX<20反向交易")
    print("5. 组合: 可作为其他策略的过滤器")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
