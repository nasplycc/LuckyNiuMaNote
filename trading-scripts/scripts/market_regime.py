#!/usr/bin/env python3
"""
Market Regime Detection - Inspired by SuperTrend AI Adaptive

Detects market regime shifts (trending, ranging, volatile) and adapts
SuperTrend multiplier automatically.

Author: 马总监 💰
Date: 2026-04-10
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger("MarketRegime")


@dataclass
class RegimeResult:
    """Market regime detection result"""
    regime: str  # "trending" | "ranging" | "volatile"
    confidence: float  # 0.0 - 1.0
    supertrend_multiplier: float  # adapted multiplier
    trend_direction: str  # "up" | "down" | "neutral"
    adx_value: float
    volatility_ratio: float
    rsi_zone: str  # "oversold" | "neutral" | "overbought"


def sma(values: List[float], period: int) -> List[float]:
    """Simple Moving Average"""
    if not values:
        return []
    out: List[float] = []
    running = 0.0
    for idx, v in enumerate(values):
        running += v
        if idx >= period:
            running -= values[idx - period]
        count = period if idx >= period - 1 else (idx + 1)
        out.append(running / count)
    return out


def ema(values: List[float], period: int) -> List[float]:
    """Exponential Moving Average"""
    if not values:
        return []
    multiplier = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * multiplier + out[-1] * (1 - multiplier))
    return out


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Average True Range (Wilder's method)"""
    if len(closes) < 2:
        return [0.0] * len(closes)

    tr = [0.0] * len(closes)
    for i in range(1, len(closes)):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    out = [0.0] * len(closes)
    running = 0.0
    for i in range(1, len(closes)):
        if i <= period:
            running += tr[i]
            out[i] = running / i
        else:
            out[i] = ((out[i - 1] * (period - 1)) + tr[i]) / period
    return out


def rsi(values: List[float], period: int = 14) -> List[float]:
    """Relative Strength Index (Wilder's method)"""
    if len(values) < 2:
        return [50.0] * len(values)

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    out = [50.0] * len(values)
    if len(changes) < period:
        return out

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return out


def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Average Directional Index"""
    if len(closes) < period + 1:
        return [0.0] * len(closes)

    plus_dm = [0.0] * len(closes)
    minus_dm = [0.0] * len(closes)
    tr = [0.0] * len(closes)

    for i in range(1, len(closes)):
        high_move = highs[i] - highs[i - 1]
        low_move = lows[i - 1] - lows[i]

        if high_move > low_move and high_move > 0:
            plus_dm[i] = high_move
        if low_move > high_move and low_move > 0:
            minus_dm[i] = low_move

        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    plus_di = [0.0] * len(closes)
    minus_di = [0.0] * len(closes)

    for i in range(period, len(closes)):
        sum_plus_dm = sum(plus_dm[i - period + 1:i + 1])
        sum_minus_dm = sum(minus_dm[i - period + 1:i + 1])
        sum_tr = sum(tr[i - period + 1:i + 1])

        if sum_tr > 0:
            plus_di[i] = (sum_plus_dm / sum_tr) * 100
            minus_di[i] = (sum_minus_dm / sum_tr) * 100

    dx = [0.0] * len(closes)
    for i in range(period, len(closes)):
        di_sum = plus_di[i] + minus_di[i]
        if di_sum > 0:
            dx[i] = abs(plus_di[i] - minus_di[i]) / di_sum * 100

    adx_vals = sma(dx, period)
    return adx_vals


def detect_supertrend(highs: List[float], lows: List[float], closes: List[float], multiplier: float = 3.0, period: int = 10) -> Tuple[List[float], List[int]]:
    """
    Calculate SuperTrend values and direction.
    Returns: (supertrend_values, directions) where direction is 1=up, -1=down
    """
    atr_vals = atr(highs, lows, closes, period)
    if len(atr_vals) < 2:
        return [], []

    basic_upper = []
    basic_lower = []
    for i in range(len(closes)):
        if atr_vals[i] > 0:
            basic_upper.append((highs[i] + lows[i]) / 2 + multiplier * atr_vals[i])
            basic_lower.append((highs[i] + lows[i]) / 2 - multiplier * atr_vals[i])
        else:
            basic_upper.append(0)
            basic_lower.append(0)

    final_upper = [0.0] * len(closes)
    final_lower = [0.0] * len(closes)
    supertrend = [0.0] * len(closes)
    direction = [0] * len(closes)

    for i in range(1, len(closes)):
        if basic_upper[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if basic_lower[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if direction[i - 1] == 1:
            if closes[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            if closes[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    return supertrend, direction


def detect_market_regime(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    volumes: List[float],
    adx_period: int = 14,
    atr_period: int = 14,
    rsi_period: int = 14,
    lookback_ranging: int = 20,
) -> RegimeResult:
    """
    Detect market regime using multiple factors:
    1. ADX - trend strength
    2. ATR ratio - volatility
    3. RSI zone - momentum
    4. Price vs EMA - trend direction
    5. Bollinger Band width - squeeze/expansion

    Returns regime: "trending" | "ranging" | "volatile"
    """
    if len(closes) < adx_period + 10:
        return RegimeResult(
            regime="ranging",
            confidence=0.5,
            supertrend_multiplier=3.0,
            trend_direction="neutral",
            adx_value=0,
            volatility_ratio=1.0,
            rsi_zone="neutral"
        )

    # Calculate indicators
    adx_vals = adx(highs, lows, closes, adx_period)
    atr_vals = atr(highs, lows, closes, atr_period)
    rsi_vals = rsi(closes, rsi_period)
    ema_fast = ema(closes, 20)
    ema_slow = ema(closes, 50)

    # Current values
    adx_now = adx_vals[-1]
    atr_now = atr_vals[-1]
    rsi_now = rsi_vals[-1]
    price = closes[-1]

    # ADX-based trend strength
    # ADX > 25 = strong trend, ADX < 20 = ranging
    if adx_now > 25:
        trend_strength = "strong"
    elif adx_now > 20:
        trend_strength = "moderate"
    else:
        trend_strength = "weak"

    # Volatility ratio (current ATR vs average ATR)
    atr_avg = sum(atr_vals[-lookback_ranging:]) / lookback_ranging if len(atr_vals) >= lookback_ranging else atr_now
    volatility_ratio = atr_now / atr_avg if atr_avg > 0 else 1.0

    # RSI zone
    if rsi_now < 30:
        rsi_zone = "oversold"
    elif rsi_now > 70:
        rsi_zone = "overbought"
    else:
        rsi_zone = "neutral"

    # Trend direction (EMA crossover + price position)
    if ema_fast[-1] > ema_slow[-1] and price > ema_slow[-1]:
        trend_direction = "up"
    elif ema_fast[-1] < ema_slow[-1] and price < ema_slow[-1]:
        trend_direction = "down"
    else:
        trend_direction = "neutral"

    # Determine regime
    # Volatile: high ATR ratio (> 1.5) regardless of ADX
    if volatility_ratio > 1.5:
        regime = "volatile"
        confidence = min((volatility_ratio - 1.5) / 1.0 + 0.5, 1.0)
        supertrend_multiplier = 4.0  # Wide bands to avoid whipsaws

    # Trending: ADX > 20 + clear trend direction
    elif trend_strength in ("strong", "moderate") and trend_direction != "neutral":
        regime = "trending"
        confidence = min(adx_now / 50.0 + 0.3, 1.0)
        supertrend_multiplier = 2.0  # Tight bands to follow trend

    # Ranging: low ADX + neutral trend
    else:
        regime = "ranging"
        confidence = max(1.0 - adx_now / 30.0, 0.5)
        supertrend_multiplier = 3.5  # Medium bands

    logger.info(
        "Regime detected: %s (confidence=%.2f, ADX=%.1f, VolRatio=%.2f, RSI=%.1f, Trend=%s, ST_Mult=%.1f)",
        regime, confidence, adx_now, volatility_ratio, rsi_now, trend_direction, supertrend_multiplier
    )

    return RegimeResult(
        regime=regime,
        confidence=confidence,
        supertrend_multiplier=supertrend_multiplier,
        trend_direction=trend_direction,
        adx_value=adx_now,
        volatility_ratio=volatility_ratio,
        rsi_zone=rsi_zone
    )


def adapt_supertrend_multiplier(regime: str, base_multiplier: float = 3.0) -> float:
    """
    Adapt SuperTrend multiplier based on regime.

    Trending: tighten (2.0)
    Ranging: widen (3.5)
    Volatile: widest (4.0)
    """
    if regime == "trending":
        return 2.0
    elif regime == "ranging":
        return 3.5
    elif regime == "volatile":
        return 4.0
    else:
        return base_multiplier


def score_trend_flip(
    regime_result: RegimeResult,
    volume_ratio: float,
    price_change_pct: float,
    bb_width_pct: float,
    atr_change_pct: float,
) -> float:
    """
    Score a SuperTrend trend flip (0-100).

    Factors:
    1. Regime quality (trending regimes score highest)
    2. Volume surge (conviction)
    3. Price momentum
    4. Bollinger Band width (squeeze release)
    5. ATR change (volatility expansion)

    Returns: score 0-100
    """
    score = 0.0

    # Factor 1: Regime quality (max 30 points)
    if regime_result.regime == "trending":
        score += 30 * regime_result.confidence
    elif regime_result.regime == "ranging":
        score += 10  # Penalize ranging
    else:  # volatile
        score += 15

    # Factor 2: Volume surge (max 20 points)
    if volume_ratio > 1.5:
        score += 20
    elif volume_ratio > 1.2:
        score += 15
    elif volume_ratio > 1.0:
        score += 10
    else:
        score += 5

    # Factor 3: Price momentum (max 20 points)
    if abs(price_change_pct) > 3.0:
        score += 20
    elif abs(price_change_pct) > 2.0:
        score += 15
    elif abs(price_change_pct) > 1.0:
        score += 10
    else:
        score += 5

    # Factor 4: BB width - squeeze release (max 15 points)
    if bb_width_pct > 10:
        score += 15
    elif bb_width_pct > 5:
        score += 10
    else:
        score += 5

    # Factor 5: ATR change - volatility expansion (max 15 points)
    if atr_change_pct > 20:
        score += 15
    elif atr_change_pct > 10:
        score += 10
    else:
        score += 5

    return min(score, 100.0)
