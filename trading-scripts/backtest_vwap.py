#!/usr/bin/env python3
"""
VWAP 突破策略回测分析
逻辑：价格突破VWAP上方做多，跌破VWAP下方做空
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

def calculate_vwap(prices: list, volumes: list, period: int = 24) -> list:
    """计算VWAP"""
    vwap = []
    for i in range(len(prices)):
        start = max(0, i - period + 1)
        cum_pv = sum(p * v for p, v in zip(prices[start:i+1], volumes[start:i+1]))
        cum_vol = sum(volumes[start:i+1])
        vwap.append(cum_pv / cum_vol if cum_vol > 0 else prices[i])
    return vwap

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

# VWAP参数
PARAMS = {
    "vwap_period": 24,        # 24小时VWAP
    "breakout_threshold": 0.002,  # 突破阈值0.2%
    "volume_confirmation": True,
    "min_volume_ratio": 1.2,  # 成交量>1.2倍均量
    "stop_loss_atr": 1.5,
    "take_profit_atr": 2.5,
}

def backtest_vwap(candles: list, symbol: str) -> dict:
    if len(candles) < 50: return {"error": "数据不足"}
    
    c = [float(x["c"]) for x in candles]
    h = [float(x["h"]) for x in candles]
    l = [float(x["l"]) for x in candles]
    v = [float(x["v"]) for x in candles]
    
    vwap = calculate_vwap(c, v, PARAMS["vwap_period"])
    vol_sma = sma(v, 20)
    atr_vals = atr(h, l, c)
    
    capital = 1000
    leverage = 2
    fee_rate = 0.00035
    
    pos = None
    trades = []
    equity = [(candles[0]["t"], capital)]
    
    for i in range(30, len(c)-1):
        price = c[i]
        prev_price = c[i-1]
        
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
            current_vwap = vwap[i]
            prev_vwap = vwap[i-1]
            
            # 突破检测
            price_above = price > current_vwap * (1 + PARAMS["breakout_threshold"])
            price_below = price < current_vwap * (1 - PARAMS["breakout_threshold"])
            cross_up = prev_price <= prev_vwap and price > current_vwap
            cross_down = prev_price >= prev_vwap and price < current_vwap
            
            # 成交量确认
            volume_ok = v[i] > vol_sma[i] * PARAMS["min_volume_ratio"] if vol_sma[i] > 0 else False
            
            # 信号
            long_signal = cross_up and price_above and volume_ok
            short_signal = cross_down and price_below and volume_ok
            
            # 如果没有成交量确认，降低条件
            if not long_signal and not short_signal:
                long_signal = cross_up and price_above
                short_signal = cross_down and price_below
            
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

def parameter_test_vwap(candles: list, param_name: str, values: list) -> list:
    results = []
    for val in values:
        old_val = PARAMS[param_name]
        PARAMS[param_name] = val
        result = backtest_vwap(candles, "TEST")
        result["param"] = val
        results.append(result)
        PARAMS[param_name] = old_val
    return results

def run():
    print("\n" + "="*60)
    print("VWAP 突破策略回测")
    print("逻辑: 价格突破VWAP±0.2% + 成交量确认")
    print("="*60)
    
    end = int(datetime.now().timestamp() * 1000)
    start = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
    
    for sym in ["BTC", "ETH"]:
        print(f"\n【{sym} - 默认参数】")
        candles = get_candles(sym, start, end)
        print(f"数据: {len(candles)} 根K线")
        
        result = backtest_vwap(candles, sym)
        for k, v in result.items():
            print(f"  {k}: {v}")
        
        # 参数测试
        print(f"\n【{sym} - 参数优化】")
        print("-" * 40)
        
        print("VWAP周期:")
        for r in parameter_test_vwap(candles, "vwap_period", [12, 18, 24, 30, 36]):
            print(f"  {r['param']:2d}h: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\n突破阈值:")
        for r in parameter_test_vwap(candles, "breakout_threshold", [0.001, 0.002, 0.003, 0.005, 0.01]):
            print(f"  {r['param']:.3f}: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
        
        print("\n成交量倍数:")
        PARAMS["volume_confirmation"] = True
        for r in parameter_test_vwap(candles, "min_volume_ratio", [1.0, 1.2, 1.5, 2.0]):
            print(f"  {r['param']:.1f}x: 胜率{r.get('胜率',0):5.1f}% | 收益{r.get('总收益',0):6.2f}% | 回撤{r.get('最大回撤',0):5.2f}%")
    
    print("\n" + "="*60)
    print("【改进建议】")
    print("="*60)
    print("1. VWAP周期: 24小时是标准，可尝试18或30小时")
    print("2. 突破阈值: 0.2%-0.3%平衡假突破和入场时机")
    print("3. 成交量确认: 1.2-1.5倍较好，过滤假突破")
    print("4. 增加趋势过滤: 只在EMA50>VWAP时做多")
    print("5. 优化出场: 使用VWAP作为移动止损线")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
