#!/usr/bin/env python3
"""
BOLL + MACD 共振策略回测分析
回测周期：6个月
目标：评估策略表现，找出参数优化空间
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import requests
import math

# 配置
CONFIG = {
    "symbols": ["BTC", "ETH"],
    "timeframe": "1h",
    "initial_capital": 1000,  # 初始资金1000 USDC
    "leverage": 2,  # 2倍杠杆
    "position_size_pct": 0.3,  # 每次投入30%资金
    "fee_rate": 0.00035,  # 手续费0.035%
    "slippage": 0.001,  # 滑点0.1%
}

# 策略参数（默认）
DEFAULT_PARAMS = {
    "bb_period": 20,
    "bb_stddev": 2.0,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "min_bandwidth_expansion": 1.02,
    "stop_loss_atr": 2.0,  # 止损：2倍ATR
    "take_profit_atr": 3.0,  # 止盈：3倍ATR
}

# Hyperliquid API
HL_API = "https://api.hyperliquid.xyz/info"

def hl_request(body: dict) -> dict:
    """调用Hyperliquid API"""
    try:
        resp = requests.post(HL_API, json=body, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"API错误: {e}")
        return {}

def get_historical_candles(symbol: str, timeframe: str, start_time: int, end_time: int) -> List[dict]:
    """获取历史K线数据"""
    try:
        candles = hl_request({
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "interval": timeframe
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

def generate_signals(candles: List[dict], params: dict) -> List[dict]:
    """生成交易信号"""
    if len(candles) < 50:
        return []
    
    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]
    
    # 计算指标
    bb_mid, bb_upper, bb_lower = bollinger_bands(
        closes, params["bb_period"], params["bb_stddev"]
    )
    
    macd_line, signal_line, histogram = macd_calc(
        closes, params["macd_fast"], params["macd_slow"], params["macd_signal"]
    )
    
    atr = calculate_atr(highs, lows, closes)
    
    # 计算带宽
    bandwidths = []
    for i in range(len(closes)):
        if bb_mid[i] > 0:
            bandwidths.append((bb_upper[i] - bb_lower[i]) / bb_mid[i])
        else:
            bandwidths.append(0)
    
    signals = []
    for i in range(max(params["bb_period"], params["macd_slow"]) + 10, len(closes)):
        price = closes[i]
        prev_price = closes[i-1]
        
        # BOLL信号
        boll_long = price <= bb_lower[i] * 1.01
        boll_short = price >= bb_upper[i] * 0.99
        
        # 带宽扩张
        bandwidth_expanding = False
        if i >= 3:
            bandwidth_expanding = bandwidths[i] > bandwidths[i-1] * params["min_bandwidth_expansion"]
        
        # MACD信号
        macd_long = macd_line[i] > signal_line[i] and macd_line[i-1] <= signal_line[i-1]
        macd_short = macd_line[i] < signal_line[i] and macd_line[i-1] >= signal_line[i-1]
        
        # 共振判断
        signal_type = None
        if boll_long and macd_long and bandwidth_expanding:
            signal_type = "LONG"
        elif boll_short and macd_short and bandwidth_expanding:
            signal_type = "SHORT"
        
        if signal_type:
            signals.append({
                "index": i,
                "time": candles[i]["t"],
                "type": signal_type,
                "price": price,
                "atr": atr[i],
                "bb_lower": bb_lower[i],
                "bb_upper": bb_upper[i],
                "macd": macd_line[i],
                "signal": signal_line[i],
            })
    
    return signals

def backtest(candles: List[dict], signals: List[dict], params: dict) -> dict:
    """执行回测"""
    if not signals or not candles:
        return {"error": "无数据"}
    
    closes = [float(c["c"]) for c in candles]
    highs = [float(c["h"]) for c in candles]
    lows = [float(c["l"]) for c in candles]
    atr_values = calculate_atr(highs, lows, closes)
    
    capital = CONFIG["initial_capital"]
    position = None  # 当前持仓
    trades = []  # 交易记录
    equity_curve = [(candles[0]["t"], capital)]  # 权益曲线
    
    for signal in signals:
        idx = signal["index"]
        entry_price = signal["price"] * (1 + CONFIG["slippage"]) if signal["type"] == "LONG" else signal["price"] * (1 - CONFIG["slippage"])
        atr = signal["atr"] if signal["atr"] > 0 else entry_price * 0.01
        
        # 如果已有持仓，先平仓
        if position:
            exit_price = closes[idx] * (1 - CONFIG["slippage"]) if position["type"] == "LONG" else closes[idx] * (1 + CONFIG["slippage"])
            
            # 计算盈亏
            if position["type"] == "LONG":
                pnl_pct = (exit_price - position["entry"]) / position["entry"]
            else:
                pnl_pct = (position["entry"] - exit_price) / position["entry"]
            
            pnl_pct *= CONFIG["leverage"]
            pnl_amount = position["size"] * pnl_pct
            fee = position["size"] * CONFIG["fee_rate"] * 2  # 开平仓手续费
            
            capital += pnl_amount - fee
            
            trades.append({
                "type": position["type"],
                "entry_time": position["time"],
                "exit_time": candles[idx]["t"],
                "entry_price": position["entry"],
                "exit_price": exit_price,
                "pnl_pct": pnl_pct,
                "pnl_amount": pnl_amount - fee,
                "exit_reason": "signal_flip"
            })
            
            equity_curve.append((candles[idx]["t"], capital))
        
        # 开新仓
        position_size = capital * CONFIG["position_size_pct"] * CONFIG["leverage"]
        
        # 设置止损止盈
        if signal["type"] == "LONG":
            stop_loss = entry_price - params["stop_loss_atr"] * atr
            take_profit = entry_price + params["take_profit_atr"] * atr
        else:
            stop_loss = entry_price + params["stop_loss_atr"] * atr
            take_profit = entry_price - params["take_profit_atr"] * atr
        
        position = {
            "type": signal["type"],
            "entry": entry_price,
            "size": position_size,
            "time": candles[idx]["t"],
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_idx": idx
        }
    
    # 最后如果有持仓，强制平仓
    if position:
        last_idx = len(closes) - 1
        exit_price = closes[last_idx] * (1 - CONFIG["slippage"]) if position["type"] == "LONG" else closes[last_idx] * (1 + CONFIG["slippage"])
        
        if position["type"] == "LONG":
            pnl_pct = (exit_price - position["entry"]) / position["entry"]
        else:
            pnl_pct = (position["entry"] - exit_price) / position["entry"]
        
        pnl_pct *= CONFIG["leverage"]
        pnl_amount = position["size"] * pnl_pct
        fee = position["size"] * CONFIG["fee_rate"] * 2
        
        capital += pnl_amount - fee
        
        trades.append({
            "type": position["type"],
            "entry_time": position["time"],
            "exit_time": candles[last_idx]["t"],
            "entry_price": position["entry"],
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
            "pnl_amount": pnl_amount - fee,
            "exit_reason": "end_of_data"
        })
    
    # 计算回测指标
    return calculate_metrics(trades, equity_curve, capital)

def calculate_metrics(trades: List[dict], equity_curve: List[tuple], final_capital: float) -> dict:
    """计算回测指标"""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "total_return": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
        }
    
    # 基本统计
    total_trades = len(trades)
    winning_trades = [t for t in trades if t["pnl_amount"] > 0]
    losing_trades = [t for t in trades if t["pnl_amount"] <= 0]
    
    win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
    
    total_profit = sum(t["pnl_amount"] for t in winning_trades)
    total_loss = abs(sum(t["pnl_amount"] for t in losing_trades))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    total_return = (final_capital - CONFIG["initial_capital"]) / CONFIG["initial_capital"] * 100
    
    # 最大回撤
    max_drawdown = 0
    peak = CONFIG["initial_capital"]
    for _, equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # 夏普比率 (简化计算)
    if len(equity_curve) > 1:
        returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i][1] - equity_curve[i-1][1]) / equity_curve[i-1][1]
            returns.append(ret)
        
        if returns:
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_return = math.sqrt(variance)
            sharpe_ratio = (avg_return / std_return) * math.sqrt(365 * 24) if std_return > 0 else 0  # 年化
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0
    
    return {
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": round(win_rate, 2),
        "total_return": round(total_return, 2),
        "total_profit": round(total_profit, 2),
        "total_loss": round(total_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "final_capital": round(final_capital, 2),
        "trades": trades[:10],  # 只保留前10笔交易详情
    }

def parameter_sensitivity_analysis(candles: List[dict], param_name: str, param_values: List[float], base_params: dict) -> List[dict]:
    """参数敏感性分析"""
    results = []
    for val in param_values:
        test_params = base_params.copy()
        test_params[param_name] = val
        
        signals = generate_signals(candles, test_params)
        result = backtest(candles, signals, test_params)
        result["param_name"] = param_name
        result["param_value"] = val
        results.append(result)
    
    return results

def run_backtest(symbol: str = "BTC", months: int = 6):
    """运行完整回测"""
    print(f"\n{'='*60}")
    print(f"BOLL + MACD 共振策略回测 - {symbol}")
    print(f"回测周期: {months}个月")
    print(f"{'='*60}\n")
    
    # 获取历史数据 (6个月)
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=30*months)).timestamp() * 1000)
    
    print(f"获取 {symbol} 历史数据...")
    candles = get_historical_candles(symbol, "1h", start_time, end_time)
    
    if len(candles) < 100:
        print(f"数据不足: 只获取到 {len(candles)} 根K线")
        return
    
    print(f"获取到 {len(candles)} 根1小时K线")
    print(f"时间范围: {datetime.fromtimestamp(candles[0]['t']/1000)} ~ {datetime.fromtimestamp(candles[-1]['t']/1000)}\n")
    
    # 1. 默认参数回测
    print("【1】默认参数回测")
    print("-" * 40)
    signals = generate_signals(candles, DEFAULT_PARAMS)
    print(f"生成信号数量: {len(signals)}")
    
    result = backtest(candles, signals, DEFAULT_PARAMS)
    print(f"总交易次数: {result['total_trades']}")
    print(f"胜率: {result['win_rate']}%")
    print(f"总收益率: {result['total_return']}%")
    print(f"盈亏比: {result['profit_factor']}")
    print(f"最大回撤: {result['max_drawdown']}%")
    print(f"夏普比率: {result['sharpe_ratio']}")
    print(f"最终资金: {result['final_capital']} USDC\n")
    
    # 2. 参数敏感性分析
    print("【2】参数敏感性分析")
    print("-" * 40)
    
    # 布林带周期
    print("\n布林带周期 (bb_period):")
    bb_period_results = parameter_sensitivity_analysis(candles, "bb_period", [10, 15, 20, 25, 30], DEFAULT_PARAMS)
    for r in bb_period_results:
        print(f"  {r['param_value']:2d}: 胜率{r['win_rate']:5.1f}% | 收益{r['total_return']:6.2f}% | 回撤{r['max_drawdown']:5.2f}%")
    
    # MACD快周期
    print("\nMACD快周期 (macd_fast):")
    macd_fast_results = parameter_sensitivity_analysis(candles, "macd_fast", [8, 10, 12, 14, 16], DEFAULT_PARAMS)
    for r in macd_fast_results:
        print(f"  {r['param_value']:2d}: 胜率{r['win_rate']:5.1f}% | 收益{r['total_return']:6.2f}% | 回撤{r['max_drawdown']:5.2f}%")
    
    # 止损倍数
    print("\n止损ATR倍数 (stop_loss_atr):")
    sl_results = parameter_sensitivity_analysis(candles, "stop_loss_atr", [1.0, 1.5, 2.0, 2.5, 3.0], DEFAULT_PARAMS)
    for r in sl_results:
        print(f"  {r['param_value']:.1f}: 胜率{r['win_rate']:5.1f}% | 收益{r['total_return']:6.2f}% | 回撤{r['max_drawdown']:5.2f}%")
    
    # 止盈倍数
    print("\n止盈ATR倍数 (take_profit_atr):")
    tp_results = parameter_sensitivity_analysis(candles, "take_profit_atr", [2.0, 2.5, 3.0, 3.5, 4.0], DEFAULT_PARAMS)
    for r in tp_results:
        print(f"  {r['param_value']:.1f}: 胜率{r['win_rate']:5.1f}% | 收益{r['total_return']:6.2f}% | 回撤{r['max_drawdown']:5.2f}%")
    
    # 3. 改进建议
    print("\n【3】策略改进建议")
    print("-" * 40)
    
    suggestions = []
    
    if result['win_rate'] < 40:
        suggestions.append("• 胜率偏低，建议增加趋势过滤器(如ADX>25)")
    
    if result['max_drawdown'] > 30:
        suggestions.append("• 最大回撤过大，建议收紧止损或降低仓位")
    
    if result['profit_factor'] < 1.5:
        suggestions.append("• 盈亏比不理想，建议优化止盈止损比例")
    
    if result['sharpe_ratio'] < 1:
        suggestions.append("• 夏普比率偏低，建议增加波动率过滤器")
    
    # 找出最优参数组合
    best_bb = max(bb_period_results, key=lambda x: x['total_return'])
    best_sl = max(sl_results, key=lambda x: x['total_return'])
    best_tp = max(tp_results, key=lambda x: x['total_return'])
    
    suggestions.append(f"\n• 建议参数组合:")
    suggestions.append(f"  - 布林带周期: {best_bb['param_value']} (收益{best_bb['total_return']}%)")
    suggestions.append(f"  - 止损倍数: {best_sl['param_value']} (收益{best_sl['total_return']}%)")
    suggestions.append(f"  - 止盈倍数: {best_tp['param_value']} (收益{best_tp['total_return']}%)")
    
    suggestions.append(f"\n• 其他优化方向:")
    suggestions.append(f"  - 增加成交量确认 (VWAP突破 + 成交量>均值)")
    suggestions.append(f"  - 增加时间过滤器 (避开高波动时段)")
    suggestions.append(f"  - 加入波动率过滤器 (ATR percentile)")
    suggestions.append(f"  - 考虑多时间框架确认 (4H趋势 + 1H入场)")
    
    for s in suggestions:
        print(s)
    
    print(f"\n{'='*60}\n")
    
    return result

if __name__ == "__main__":
    # 回测BTC
    run_backtest("BTC", 6)
    
    # 回测ETH
    run_backtest("ETH", 6)
