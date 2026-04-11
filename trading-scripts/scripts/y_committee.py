#!/usr/bin/env python3
"""
Y(4.0) Voting Committee - 8-Component Multi-Layer Decision System

Inspired by TradingView Y(4.0) strategy by nudaez
Adapted for Hyperliquid futures trading

Core concept: 8 indicators vote together, not individually.
- Each component scores 0-3 points
- Minimum N/8 components must be active
- Total score must exceed threshold
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger("YCommittee")


@dataclass
class ComponentScore:
    """单个组件评分"""
    name: str
    score: int  # 0-3
    active: bool
    reason: str


@dataclass
class CommitteeVote:
    """委员会投票结果"""
    total_score: int
    max_score: int  # 24
    active_count: int
    total_components: int  # 8
    passed: bool
    direction: str  # "LONG" or "SHORT"
    components: List[ComponentScore]
    volume_multiplier: float
    final_score: float


def calculate_rsi_score(rsi_value: float, rsi_oversold: float = 30, rsi_overbought: float = 70) -> ComponentScore:
    """
    RSI Component Scoring (0-3 points)
    
    Scoring:
    - 0: Neutral zone (30-70)
    - 1: Mild extreme (25-30 or 70-75)
    - 2: Moderate extreme (20-25 or 75-80)
    - 3: Deep extreme (<20 or >80)
    """
    if rsi_value < 20:
        return ComponentScore("RSI", 3, True, f"深度超卖 ({rsi_value:.1f} < 20)")
    elif rsi_value < 25:
        return ComponentScore("RSI", 2, True, f"中度超卖 ({rsi_value:.1f} < 25)")
    elif rsi_value < 30:
        return ComponentScore("RSI", 1, True, f"轻度超卖 ({rsi_value:.1f} < 30)")
    elif rsi_value > 80:
        return ComponentScore("RSI", 3, True, f"深度超买 ({rsi_value:.1f} > 80)")
    elif rsi_value > 75:
        return ComponentScore("RSI", 2, True, f"中度超买 ({rsi_value:.1f} > 75)")
    elif rsi_value > 70:
        return ComponentScore("RSI", 1, True, f"轻度超买 ({rsi_value:.1f} > 70)")
    else:
        return ComponentScore("RSI", 0, False, f"中性区域 ({rsi_value:.1f})")


def calculate_stoch_score(stoch_k: float, stoch_d: float, prev_k: float, prev_d: float) -> ComponentScore:
    """
    Stochastic Component Scoring (0-3 points)
    
    Scoring:
    - 0: Neutral zone (20-80)
    - 1: Zone + mild cross (K/D交叉进入极端区)
    - 2: Zone + moderate cross + direction
    - 3: Deep zone + strong cross
    """
    # 判断是否在极端区域
    oversold_zone = stoch_k < 20
    overbought_zone = stoch_k > 80
    
    # 判断交叉
    bullish_cross = stoch_k > stoch_d and prev_k <= prev_d  # K上穿D
    bearish_cross = stoch_k < stoch_d and prev_k >= prev_d  # K下穿D
    
    if oversold_zone and bullish_cross:
        return ComponentScore("Stoch", 3, True, f"超卖区金叉 (K={stoch_k:.1f}, D={stoch_d:.1f})")
    elif oversold_zone:
        return ComponentScore("Stoch", 2, True, f"超卖区 (K={stoch_k:.1f} < 20)")
    elif overbought_zone and bearish_cross:
        return ComponentScore("Stoch", 3, True, f"超买区死叉 (K={stoch_k:.1f}, D={stoch_d:.1f})")
    elif overbought_zone:
        return ComponentScore("Stoch", 2, True, f"超买区 (K={stoch_k:.1f} > 80)")
    elif bullish_cross and stoch_k < 30:
        return ComponentScore("Stoch", 1, True, f"低位金叉 (K={stoch_k:.1f})")
    elif bearish_cross and stoch_k > 70:
        return ComponentScore("Stoch", 1, True, f"高位死叉 (K={stoch_k:.1f})")
    else:
        return ComponentScore("Stoch", 0, False, f"中性 (K={stoch_k:.1f}, D={stoch_d:.1f})")


def calculate_bb_score(price: float, bb_upper: float, bb_lower: float, bb_mid: float) -> ComponentScore:
    """
    Bollinger Bands Component Scoring (0-3 points)
    
    Scoring:
    - 0: Inside bands
    - 1: Touching lower/upper band
    - 2: Outside band by small margin
    - 3: Significantly outside band
    """
    bb_width = bb_upper - bb_lower
    
    # 价格相对位置
    lower_distance = (price - bb_lower) / bb_width if bb_width > 0 else 0
    upper_distance = (bb_upper - price) / bb_width if bb_width > 0 else 0
    
    if price < bb_lower * 0.98:  # 显著跌破下轨
        return ComponentScore("BB", 3, True, f"显著跌破下轨 (价格={price:.2f}, 下轨={bb_lower:.2f})")
    elif price < bb_lower:  # 跌破下轨
        return ComponentScore("BB", 2, True, f"跌破下轨 (价格={price:.2f})")
    elif price <= bb_lower * 1.01:  # 触及下轨
        return ComponentScore("BB", 1, True, f"触及下轨 (价格={price:.2f})")
    elif price > bb_upper * 1.02:  # 显著突破上轨
        return ComponentScore("BB", 3, True, f"显著突破上轨 (价格={price:.2f}, 上轨={bb_upper:.2f})")
    elif price > bb_upper:  # 突破上轨
        return ComponentScore("BB", 2, True, f"突破上轨 (价格={price:.2f})")
    elif price >= bb_upper * 0.99:  # 触及上轨
        return ComponentScore("BB", 1, True, f"触及上轨 (价格={price:.2f})")
    else:
        return ComponentScore("BB", 0, False, f"布林带内 (价格={price:.2f})")


def calculate_cci_score(cci_value: float) -> ComponentScore:
    """
    CCI (Commodity Channel Index) Scoring (0-3 points)
    
    Scoring:
    - 0: Neutral (-100 to +100)
    - 1: Mild extreme (-100 to -150 or +100 to +150)
    - 2: Moderate extreme (-150 to -200 or +150 to +200)
    - 3: Deep extreme (<-200 or >+200)
    """
    if cci_value < -200:
        return ComponentScore("CCI", 3, True, f"深度超卖 (CCI={cci_value:.1f} < -200)")
    elif cci_value < -150:
        return ComponentScore("CCI", 2, True, f"中度超卖 (CCI={cci_value:.1f} < -150)")
    elif cci_value < -100:
        return ComponentScore("CCI", 1, True, f"轻度超卖 (CCI={cci_value:.1f} < -100)")
    elif cci_value > 200:
        return ComponentScore("CCI", 3, True, f"深度超买 (CCI={cci_value:.1f} > +200)")
    elif cci_value > 150:
        return ComponentScore("CCI", 2, True, f"中度超买 (CCI={cci_value:.1f} > +150)")
    elif cci_value > 100:
        return ComponentScore("CCI", 1, True, f"轻度超买 (CCI={cci_value:.1f} > +100)")
    else:
        return ComponentScore("CCI", 0, False, f"中性区域 (CCI={cci_value:.1f})")


def calculate_williams_r_score(wr_value: float) -> ComponentScore:
    """
    Williams %R Scoring (0-3 points)
    
    Williams %R range: 0 to -100
    - 0 to -20: Overbought
    - -80 to -100: Oversold
    
    Scoring:
    - 0: Neutral (-20 to -80)
    - 1: Mild oversold/overbought
    - 2: Moderate extreme
    - 3: Deep extreme
    """
    # Williams %R 通常显示为负值
    # -80以下为超卖，-20以上为超买
    
    if wr_value < -90:
        return ComponentScore("Williams%R", 3, True, f"深度超卖 (WR={wr_value:.1f} < -90)")
    elif wr_value < -85:
        return ComponentScore("Williams%R", 2, True, f"中度超卖 (WR={wr_value:.1f} < -85)")
    elif wr_value < -80:
        return ComponentScore("Williams%R", 1, True, f"轻度超卖 (WR={wr_value:.1f} < -80)")
    elif wr_value > -10:
        return ComponentScore("Williams%R", 3, True, f"深度超买 (WR={wr_value:.1f} > -10)")
    elif wr_value > -15:
        return ComponentScore("Williams%R", 2, True, f"中度超买 (WR={wr_value:.1f} > -15)")
    elif wr_value > -20:
        return ComponentScore("Williams%R", 1, True, f"轻度超买 (WR={wr_value:.1f} > -20)")
    else:
        return ComponentScore("Williams%R", 0, False, f"中性区域 (WR={wr_value:.1f})")


def calculate_mfi_score(mfi_value: float) -> ComponentScore:
    """
    MFI (Money Flow Index) Scoring (0-3 points)
    
    MFI range: 0 to 100
    Similar to RSI but includes volume
    
    Scoring:
    - 0: Neutral (20-80)
    - 1: Mild extreme
    - 2: Moderate extreme
    - 3: Deep extreme
    """
    if mfi_value < 10:
        return ComponentScore("MFI", 3, True, f"深度资金流出 (MFI={mfi_value:.1f} < 10)")
    elif mfi_value < 20:
        return ComponentScore("MFI", 2, True, f"中度资金流出 (MFI={mfi_value:.1f} < 20)")
    elif mfi_value < 30:
        return ComponentScore("MFI", 1, True, f"轻度资金流出 (MFI={mfi_value:.1f} < 30)")
    elif mfi_value > 90:
        return ComponentScore("MFI", 3, True, f"深度资金流入 (MFI={mfi_value:.1f} > 90)")
    elif mfi_value > 80:
        return ComponentScore("MFI", 2, True, f"中度资金流入 (MFI={mfi_value:.1f} > 80)")
    elif mfi_value > 70:
        return ComponentScore("MFI", 1, True, f"轻度资金流入 (MFI={mfi_value:.1f} > 70)")
    else:
        return ComponentScore("MFI", 0, False, f"中性资金流 (MFI={mfi_value:.1f})")


def calculate_adx_score(adx_value: float, plus_di: float, minus_di: float) -> ComponentScore:
    """
    ADX/DI Scoring (0-3 points)
    
    Scoring:
    - 0: No trend (ADX < 20)
    - 1: Weak trend + direction
    - 2: Moderate trend + direction
    - 3: Strong trend + direction change
    """
    direction = "BULLISH" if plus_di > minus_di else "BEARISH"
    
    if adx_value > 40:
        return ComponentScore("ADX/DI", 3, True, f"强趋势 ({direction}, ADX={adx_value:.1f} > 40)")
    elif adx_value > 25:
        return ComponentScore("ADX/DI", 2, True, f"中等趋势 ({direction}, ADX={adx_value:.1f} > 25)")
    elif adx_value > 20:
        return ComponentScore("ADX/DI", 1, True, f"弱趋势 ({direction}, ADX={adx_value:.1f} > 20)")
    else:
        return ComponentScore("ADX/DI", 0, False, f"无明确趋势 (ADX={adx_value:.1f} < 20)")


def calculate_divergence_score(prices: List[float], rsi_values: List[float], lookback: int = 14) -> ComponentScore:
    """
    Divergence Scoring (0-3 points)
    
    Divergence detection:
    - Bullish divergence: Price makes lower low, RSI makes higher low
    - Bearish divergence: Price makes higher high, RSI makes lower high
    
    Scoring:
    - 0: No divergence
    - 1: Weak divergence (small difference)
    - 2: Moderate divergence
    - 3: Strong divergence (significant difference)
    """
    if len(prices) < lookback or len(rsi_values) < lookback:
        return ComponentScore("Divergence", 0, False, "数据不足")
    
    # 取最近lookback周期
    recent_prices = prices[-lookback:]
    recent_rsi = rsi_values[-lookback:]
    
    # 找价格低点和高点
    price_low_idx = min(range(len(recent_prices)), key=lambda i: recent_prices[i])
    price_high_idx = max(range(len(recent_prices)), key=lambda i: recent_prices[i])
    
    # 找RSI低点和高点
    rsi_low_idx = min(range(len(recent_rsi)), key=lambda i: recent_rsi[i])
    rsi_high_idx = max(range(len(recent_rsi)), key=lambda i: recent_rsi[i])
    
    # 检测背离
    bullish_div = price_low_idx > rsi_low_idx  # 价格新低，RSI未新低
    bearish_div = price_high_idx > rsi_high_idx  # 价格新高，RSI未新高
    
    if bullish_div:
        # 价格底部和RSI底部的时间差
        divergence_strength = abs(recent_prices[price_low_idx] - min(recent_prices)) + \
                             abs(recent_rsi[rsi_low_idx] - min(recent_rsi))
        if divergence_strength > 10:
            return ComponentScore("Divergence", 3, True, f"强看涨背离 (价格底≠RSI底)")
        elif divergence_strength > 5:
            return ComponentScore("Divergence", 2, True, f"中等看涨背离")
        else:
            return ComponentScore("Divergence", 1, True, f"弱看涨背离")
    elif bearish_div:
        divergence_strength = abs(recent_prices[price_high_idx] - max(recent_prices)) + \
                             abs(recent_rsi[rsi_high_idx] - max(recent_rsi))
        if divergence_strength > 10:
            return ComponentScore("Divergence", 3, True, f"强看跌背离 (价格顶≠RSI顶)")
        elif divergence_strength > 5:
            return ComponentScore("Divergence", 2, True, f"中等看跌背离")
        else:
            return ComponentScore("Divergence", 1, True, f"弱看跌背离")
    else:
        return ComponentScore("Divergence", 0, False, "无背离")


def y_committee_vote(
    rsi_fast: float,
    stoch_k: float,
    stoch_d: float,
    prev_stoch_k: float,
    prev_stoch_d: float,
    price: float,
    bb_upper: float,
    bb_lower: float,
    bb_mid: float,
    cci: float,
    williams_r: float,
    mfi: float,
    adx: float,
    plus_di: float,
    minus_di: float,
    prices_history: List[float],
    rsi_history: List[float],
    volume_ratio: float = 1.0,
    min_active_components: int = 5,  # 至少5/8组件激活
    min_total_score: int = 10,  # 总分至少10
) -> CommitteeVote:
    """
    Y(4.0) 委员会投票
    
    Args:
        各种指标值
        volume_ratio: 成交量比率（相对于SMA）
        min_active_components: 最少激活组件数
        min_total_score: 最少总分
    
    Returns:
        CommitteeVote: 投票结果
    """
    # 计算各组件得分
    components = [
        calculate_rsi_score(rsi_fast),
        calculate_stoch_score(stoch_k, stoch_d, prev_stoch_k, prev_stoch_d),
        calculate_bb_score(price, bb_upper, bb_lower, bb_mid),
        calculate_cci_score(cci),
        calculate_williams_r_score(williams_r),
        calculate_mfi_score(mfi),
        calculate_adx_score(adx, plus_di, minus_di),
        calculate_divergence_score(prices_history, rsi_history),
    ]
    
    # 统计得分
    total_score = sum(c.score for c in components)
    active_count = sum(1 for c in components if c.active)
    
    # 判断方向（基于RSI和Stoch的领先性）
    oversold_count = sum(1 for c in components if c.active and c.score > 0 and 
                         ("超卖" in c.reason or "oversold" in c.reason.lower() or "跌破" in c.reason))
    overbought_count = sum(1 for c in components if c.active and c.score > 0 and 
                           ("超买" in c.reason or "overbought" in c.reason.lower() or "突破" in c.reason))
    
    direction = "LONG" if oversold_count > overbought_count else "SHORT" if overbought_count > oversold_count else "NEUTRAL"
    
    # Layer 2: 成交量倍数
    volume_multiplier = 1.0
    if volume_ratio > 1.5:
        volume_multiplier = 1.3
    elif volume_ratio > 1.2:
        volume_multiplier = 1.15
    elif volume_ratio > 1.0:
        volume_multiplier = 1.05
    
    # 最终得分
    final_score = total_score * volume_multiplier
    
    # 是否通过
    passed = (active_count >= min_active_components and final_score >= min_total_score and direction != "NEUTRAL")
    
    logger.info(
        f"Y(4.0) 投票: 激活={active_count}/8, 总分={total_score}, 最终={final_score:.1f}, "
        f"方向={direction}, 通过={passed}, 成交量倍数={volume_multiplier:.2f}"
    )
    
    return CommitteeVote(
        total_score=total_score,
        max_score=24,
        active_count=active_count,
        total_components=8,
        passed=passed,
        direction=direction,
        components=components,
        volume_multiplier=volume_multiplier,
        final_score=final_score,
    )


def format_committee_report(vote: CommitteeVote) -> str:
    """格式化委员会投票报告"""
    lines = [
        f"=== Y(4.0) 委员会投票报告 ===",
        f"总分: {vote.total_score}/{vote.max_score} (最终: {vote.final_score:.1f})",
        f"激活组件: {vote.active_count}/{vote.total_components}",
        f"方向: {vote.direction}",
        f"成交量倍数: {vote.volume_multiplier:.2f}",
        f"结论: {'✅ 通过' if vote.passed else '❌ 未通过'}",
        "",
        "组件详情:",
    ]
    
    for c in vote.components:
        status = "✓" if c.active else "○"
        lines.append(f"  {status} {c.name}: {c.score}分 - {c.reason}")
    
    return "\n".join(lines)