#!/usr/bin/env python3
"""
SuperTrend 趋势跟随策略回测分析
逻辑：ATR + 移动平均线，价格在SuperTrend线上方做多，下方做空
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

def atr(highs: list, lows: list, closes: list, p: int = 10):
    """计算ATR"""
    tr = [highs[0]-lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    out = []
    for i in range(len(tr)):
        if i < p-1: out.append(sum(tr[:i+1])/(i+1))
        elif i == p-1: out.append(sum(tr[:p])/p)
        else: out.append((out[-1]*(p-1) + tr[i])/p)
    return out

def supertrend(highs: list, lows: list, closes: list, period: int = 10, multiplier: float = 3.0):
    """计算SuperTrend"""
    atr_vals = atr(highs, lows, closes, period)
    
    # 基础上下轨
    basic_upper = []
    basic_lower = []
    for i in range(len(closes)):
        avg_price = (highs[i] + lows[i]) / 2
        basic_upper.append(avg_price + multiplier * atr_vals[i])
        basic_lower.append(avg_price - multiplier * atr_vals[i])
    
    # 最终上下轨和趋势
    final_upper = [basic_upper[0]]
    final_lower = [basic_lower[0]]
    trend = [1]  # 1 = 多头, -1 = 空头
    
    for i in range(1, len(closes)):
        prev_close = closes[i-1]
        
        # 上轨
        if basic_upper[i] < final_upper[i-1] or prev_close > final_upper[i-1]:
            final_upper.append(basic_upper[i])
        else:
            final_upper.append(final_upper[i-1])
        
        # 下轨
        if basic_lower[i] > final_lower[i-1] or prev_close < final_lower[i-1]:
            final_lower.append(basic_lower[i])
        else:
            final_lower.append(final_lower[i-1])
        
        # 趋势判断
        if closes[i] > final_upper[i-1]:
            trend.append(1)
        elif closes[i] < final_lower[i-1]:
            trend.append(-1)
        else:
            trend.append(trend[i-1])
    
    # SuperTrend线
    st = [final_lower[i] if trend[i] == 1 else final_upper[i] for i in range(len(trend))]
    
    return st, trend, final_upper, final_lower

# SuperTrend参数
PARAMS = {
    "atr_period": 10,
    "atr_multiplier": 3.0,
    "stop_loss_pct": 0.02,  # 2%止损
}

def backtest_supertrend(candles: list, symbol: str) -> dict:
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    
    st, trend, upper, lower = supertrend(h, l, c, PARAMS["atr_period"], PARAMS["atr_multiplier"])
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(20, len(c)-1):
        price = c[i]
        
        # 检查平仓
        if pos:
            if pos["type"] == "LONG":
                # 趋势转空或止损
                if trend[i] == -1 or price <= pos["sl"]:
                    pnl = (price - pos["entry"]) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "LONG", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
            else:
                # 趋势转多或止损
                if trend[i] == 1 or price >= pos["sl"]:
                    pnl = (pos["entry"] - price) / pos["entry"] * leverage
                    capital = capital * (1 + pnl * 0.3 - 0.0007)
                    trades.append({"type": "SHORT", "pnl": pnl * 0.3})
                    equity.append((candles[i]["t"], capital))
                    pos = None
        
        # 开新仓 (趋势反转)
        if not pos:
            if trend[i] == 1 and trend[i-1] == -1:  # 空头转多头
                pos = {
                    "type": "LONG", 
                    "entry": price,
                    "sl": price * (1 - PARAMS["stop_loss_pct"])
                }
            elif trend[i] == -1 and trend[i-1] == 1:  # 多头转空头
                pos = {
                    "type": "SHORT", 
                    "entry": price,
                    "sl": price * (1 + PARAMS["stop_loss_pct"])
                }
    
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
        result = backtest_supertrend(candles, "TEST")
        result["param"] = val
        results.append(result)
        PARAMS[param_name] = old_val
    return results

def run():
    print("\n" + "="*60)
    print("SuperTrend 趋势跟随策略回测")
    print("逻辑: ATR×3 + 10周期, 趋势反转时入场")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym} - 默认参数】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        
        result = backtest_supertrend(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
        
        # 参数测试
        print(f"\n【{sym} - 参数优化】")
        print("-" * 40)
        
        print("ATR周期:")
        for r in parameter_test(candles, "atr_period", [7, 10, 14, 21]):
            print(f"  {r['param']:2d}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\nATR乘数:")
        for r in parameter_test(candles, "atr_multiplier", [2.0, 2.5, 3.0, 3.5, 4.0]):
            print(f"  {r['param']:.1f}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\n止损比例:")
        for r in parameter_test(candles, "stop_loss_pct", [0.01, 0.02, 0.03, 0.05]):
            print(f"  {r['param']:.2f}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
    
    print("\n" + "="*60)
    print("【改进建议】")
    print("="*60)
    print("1. ATR周期: 10-14天适合1小时K线")
    print("2. ATR乘数: 3.0是标准，可尝试2.5或3.5")
    print("3. 止损: 2%-3%防止假突破")
    print("4. 增加过滤: 只在ADX>20时跟随趋势")
    print("5. 多时间框架: 4H确认趋势，1H入场")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
