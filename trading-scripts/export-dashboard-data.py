#!/usr/bin/env python3
"""
Export LuckyNiuMa dashboard data into JSON files for web / mini-program consumption.

Outputs:
- data-export/meta.json
- data-export/overview.json
- data-export/positions.json
- data-export/trades.json
- data-export/orders.json
- data-export/performance.json
- data-export/bot_status.json
- data-export/alerts.json
- data-export/signal_diagnostics.json

Design goals:
- Read-only export layer
- Works directly on NAS without extra server dependencies
- Reuses existing Hyperliquid + SQLite + log sources when available
- Degrades gracefully when some sources are missing
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
WORKSPACE_ROOT = REPO_ROOT.parent
STATE_DB = PROJECT_ROOT / "state" / "trader_state.db"
LOG_DIR = REPO_ROOT / "logs"
OUTPUT_DIR = REPO_ROOT / "data-export"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / ".runtime_config.json"
GENERATED_DATA_PATH = REPO_ROOT / "frontend" / "public" / "generated-data.json"
HL_API = "https://api.hyperliquid.xyz/info"
DEFAULT_WALLET = "0xfFd91a584cf6419b92E58245898D2A9281c628eb"
SERVICE_NAME = os.getenv("LUCKYNIUMA_SERVICE_NAME", "luckyniuma-trader.service")


@dataclass
class ExportContext:
    now_iso: str
    wallet: str
    account_state: Dict[str, Any]
    spot_state: Dict[str, Any]
    prices: Dict[str, float]
    db_available: bool


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def safe_json_loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def read_runtime_config() -> Dict[str, Any]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_CONFIG_PATH.read_text())
    except Exception:
        return {}


def read_hl_config() -> Dict[str, str]:
    path = PROJECT_ROOT / 'config' / '.hl_config'
    if not path.exists():
        return {}
    data: Dict[str, str] = {}
    try:
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            data[k.strip()] = v.strip()
    except Exception:
        return {}
    return data


def read_generated_data() -> Dict[str, Any]:
    if not GENERATED_DATA_PATH.exists():
        return {}
    try:
        return json.loads(GENERATED_DATA_PATH.read_text())
    except Exception:
        return {}


def resolve_wallet(runtime_cfg: Dict[str, Any], generated_data: Dict[str, Any]) -> str:
    env_wallet = os.getenv("LUCKYNIUMA_WALLET")
    if env_wallet:
        return env_wallet

    hl_cfg = read_hl_config()
    main_wallet = hl_cfg.get("MAIN_WALLET") or runtime_cfg.get("main_wallet")
    if main_wallet:
        return main_wallet

    verification = generated_data.get("VERIFICATION", {})
    wallet = verification.get("tradingAccount")
    if wallet:
        return wallet

    return DEFAULT_WALLET


def hl_request(body: Dict[str, Any]) -> Any:
    resp = requests.post(HL_API, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_hyperliquid_user_fills(ctx_wallet: str | None = None) -> List[Dict[str, Any]]:
    wallet = ctx_wallet
    if not wallet:
        runtime_cfg = read_runtime_config()
        generated_data = read_generated_data()
        wallet = resolve_wallet(runtime_cfg, generated_data)
    if not wallet:
        return []
    try:
        data = hl_request({"type": "userFills", "user": wallet})
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_prices() -> Dict[str, float]:
    try:
        mids = hl_request({"type": "allMids"})
    except Exception:
        return {}

    prices: Dict[str, float] = {}
    for key, value in mids.items():
        try:
            prices[key] = float(value)
        except Exception:
            continue
    return prices


def get_account_state(wallet: str) -> Dict[str, Any]:
    try:
        state = hl_request({"type": "clearinghouseState", "user": wallet})
    except Exception:
        return {}

    return state if isinstance(state, dict) else {}


def get_spot_state(wallet: str) -> Dict[str, Any]:
    try:
        state = hl_request({"type": "spotClearinghouseState", "user": wallet})
    except Exception:
        return {}

    return state if isinstance(state, dict) else {}


def db_connect() -> Optional[sqlite3.Connection]:
    if not STATE_DB.exists():
        return None
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def query_rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = db_connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> Dict[str, Any]:
    conn = db_connect()
    if conn is None:
        return {}
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}
    finally:
        conn.close()


def get_git_version() -> str:
    app_version = (os.getenv("APP_VERSION") or "").strip()
    if app_version:
        return app_version
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except Exception:
        return "unknown"


def translate_alert_title(event_type: str) -> str:
    mapping = {
        "safe_mode": "风控保护",
        "safe_mode_exit": "风控解除",
        "failure": "运行失败",
        "api_timeout": "接口超时",
        "cycle_exception": "策略循环异常",
        "system_event": "系统事件",
        "startup": "启动检查",
        "reconcile_ok": "状态对账正常",
        "reconcile_failed": "状态对账失败",
    }
    return mapping.get(event_type, event_type)


def translate_alert_message(message: str) -> str:
    if not message:
        return ""
    translated = message
    replacements = [
        ("Exited SAFE_MODE", "已退出风控保护模式"),
        ("SAFE_MODE", "风控保护模式"),
        ("system startup completed", "系统启动完成"),
        ("startup completed", "启动完成"),
        ("Reconcile OK", "状态对账正常"),
        ("reconcile ok", "状态对账正常"),
        ("reconcile failed", "状态对账失败"),
        ("api timeout", "接口请求超时"),
        ("cycle exception", "策略循环异常"),
        ("telegram notifier disabled", "Telegram 通知未启用"),
        ("missing bot token or chat_id", "缺少机器人 Token 或 Chat ID"),
        ("process healthy", "进程运行正常"),
    ]
    for src, dst in replacements:
        translated = translated.replace(src, dst)
    return translated


def get_systemd_state(service_name: str) -> Dict[str, Any]:
    result = {
        "service_name": service_name,
        "service_status": "unknown",
        "process_healthy": False,
    }
    try:
        active = subprocess.check_output(
            ["systemctl", "is-active", service_name],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        result["service_status"] = active
        result["process_healthy"] = active == "active"
    except Exception:
        return result
    return result


def tail_lines(path: Path, limit: int = 200) -> List[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(errors="ignore").splitlines()
        return lines[-limit:]
    except Exception:
        return []


def find_latest_log() -> Optional[Path]:
    candidates = [LOG_DIR / "trader_nfi.log", LOG_DIR / "trader-nfi-nohup.log"]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def extract_last_log_timestamp(lines: List[str]) -> Optional[str]:
    for line in reversed(lines):
        if len(line) >= 19:
            prefix = line[:19]
            try:
                dt = datetime.strptime(prefix, "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=datetime.now().astimezone().tzinfo).isoformat(timespec="seconds")
            except Exception:
                continue
    return None


def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    out = [values[0]]
    for price in values[1:]:
        out.append(price * multiplier + out[-1] * (1 - multiplier))
    return out


def sma(values: List[float], period: int) -> List[float]:
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


def rolling_std(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    out: List[float] = []
    for idx in range(len(values)):
        start = max(0, idx - period + 1)
        window = values[start : idx + 1]
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


def rsi_wilder(values: List[float], period: int) -> List[float]:
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


def get_klines(symbol: str, interval: str = '1h', limit: int = 240) -> List[Dict[str, float]]:
    try:
        payload = hl_request({"type": "candleSnapshot", "req": {"coin": symbol, "interval": interval, "startTime": 0}})
        rows = payload if isinstance(payload, list) else []
        out = []
        for c in rows[-limit:]:
            out.append({
                'open': safe_float(c.get('o')),
                'high': safe_float(c.get('h')),
                'low': safe_float(c.get('l')),
                'close': safe_float(c.get('c')),
                'volume': safe_float(c.get('v')),
                'time': c.get('t'),
            })
        return out
    except Exception:
        return []


def nfi_params_for_symbol(symbol: str) -> Dict[str, Any]:
    # BTC 双向交易策略参数
    base = {
        'ema_fast': 20, 'ema_trend': 50, 'ema_long': 200,
        'rsi_fast': 4, 'rsi_main': 14, 'bb_period': 20, 'bb_stddev': 2.0,
        'volume_sma_period': 30,
        # BTC 做多阈值（已放宽）
        'rsi_fast_buy': 38.0, 'rsi_main_buy': 50.0,
        # BTC 做空阈值（已放宽）
        'rsi_fast_sell': 58.0, 'rsi_main_sell': 48.0,
        # BTC 成交量要求
        'min_volume_ratio': 0.25,
        'bb_touch_buffer': 1.04, 'ema_pullback_buffer': 0.98,
        'regime_price_floor': 0.92, 'regime_price_ceiling': 1.08,
        'bb_reject_buffer': 0.96, 'ema_bounce_buffer': 1.04,
        'max_breakdown_pct': 0.15, 'max_breakout_pct': 0.15,
    }
    if symbol == 'ETH':
        # ETH 更宽松的阈值
        base.update({'rsi_fast_buy': 32.0, 'rsi_main_buy': 46.0, 'rsi_fast_sell': 62.0, 'rsi_main_sell': 50.0, 'min_volume_ratio': 0.18})
    return base


def stochastic(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[float], List[float]]:
    """Stochastic K and D calculation"""
    k_vals = []
    for i in range(len(closes)):
        if i < period - 1:
            k_vals.append(50.0)
            continue
        highest = max(highs[i - period + 1:i + 1])
        lowest = min(lows[i - period + 1:i + 1])
        if highest == lowest:
            k_vals.append(50.0)
        else:
            k_vals.append(100.0 * (closes[i] - lowest) / (highest - lowest))
    # D is SMA of K
    d_vals = sma(k_vals, 3)
    return k_vals, d_vals


def cci(highs: List[float], lows: List[float], closes: List[float], period: int = 20) -> List[float]:
    """CCI (Commodity Channel Index) calculation"""
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    tp_sma = sma(tp, period)
    tp_std = rolling_std(tp, period)
    cci_vals = []
    for i in range(len(tp)):
        if tp_std[i] == 0:
            cci_vals.append(0.0)
        else:
            cci_vals.append((tp[i] - tp_sma[i]) / (0.015 * tp_std[i]))
    return cci_vals


def williams_r(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Williams %R calculation"""
    wr_vals = []
    for i in range(len(closes)):
        if i < period - 1:
            wr_vals.append(-50.0)
            continue
        highest = max(highs[i - period + 1:i + 1])
        lowest = min(lows[i - period + 1:i + 1])
        if highest == lowest:
            wr_vals.append(-50.0)
        else:
            wr_vals.append(-100.0 * (highest - closes[i]) / (highest - lowest))
    return wr_vals


def mfi(highs: List[float], lows: List[float], closes: List[float], volumes: List[float], period: int = 14) -> List[float]:
    """MFI (Money Flow Index) calculation"""
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    mf = [t * v for t, v in zip(tp, volumes)]
    mfi_vals = [50.0] * len(closes)
    if len(closes) < period:
        return mfi_vals
    for i in range(period, len(closes)):
        pos_flow = 0.0
        neg_flow = 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos_flow += mf[j]
            elif tp[j] < tp[j - 1]:
                neg_flow += mf[j]
        if neg_flow == 0:
            mfi_vals[i] = 100.0
        else:
            mf_ratio = pos_flow / neg_flow
            mfi_vals[i] = 100.0 - (100.0 / (1.0 + mf_ratio))
    return mfi_vals


def adx_di(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[float], List[float], List[float]]:
    """ADX, +DI, -DI calculation"""
    plus_dm = [0.0] * len(closes)
    minus_dm = [0.0] * len(closes)
    tr = [0.0] * len(closes)
    
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    
    # Smoothed values using Wilder smoothing
    atr_vals = [tr[0]]
    plus_di_vals = [0.0]
    minus_di_vals = [0.0]
    
    # First period: simple sum
    atr_vals.extend([sum(tr[1:period]) / period] * (period - 1))
    plus_di_smooth = sum(plus_dm[1:period]) / period
    minus_di_smooth = sum(minus_dm[1:period]) / period
    plus_di_vals.extend([100.0 * plus_di_smooth / atr_vals[-1] if atr_vals[-1] else 0.0] * (period - 1))
    minus_di_vals.extend([100.0 * minus_di_smooth / atr_vals[-1] if atr_vals[-1] else 0.0] * (period - 1))
    
    # Wilder smoothing for rest
    for i in range(period, len(closes)):
        atr_vals.append((atr_vals[-1] * (period - 1) + tr[i]) / period)
        plus_di_smooth = (plus_di_smooth * (period - 1) + plus_dm[i]) / period
        minus_di_smooth = (minus_di_smooth * (period - 1) + minus_dm[i]) / period
        plus_di_vals.append(100.0 * plus_di_smooth / atr_vals[i] if atr_vals[i] else 0.0)
        minus_di_vals.append(100.0 * minus_di_smooth / atr_vals[i] if atr_vals[i] else 0.0)
    
    # DX and ADX
    dx_vals = []
    for i in range(len(plus_di_vals)):
        di_sum = plus_di_vals[i] + minus_di_vals[i]
        if di_sum == 0:
            dx_vals.append(0.0)
        else:
            dx_vals.append(100.0 * abs(plus_di_vals[i] - minus_di_vals[i]) / di_sum)
    
    # ADX = smoothed DX
    adx_vals = [0.0] * len(dx_vals)
    if len(dx_vals) > period * 2:
        adx_vals[period * 2 - 1] = sum(dx_vals[period:period * 2]) / period
        for i in range(period * 2, len(dx_vals)):
            adx_vals[i] = (adx_vals[i - 1] * (period - 1) + dx_vals[i]) / period
    
    return adx_vals, plus_di_vals, minus_di_vals


def diagnose_symbol(symbol: str) -> Dict[str, Any]:
    params = nfi_params_for_symbol(symbol)
    klines = get_klines(symbol, interval='1h', limit=240)
    if len(klines) < params['ema_long'] + 5:
        return {'symbol': symbol, 'status': 'insufficient_data'}
    closes = [k['close'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]
    ema_fast_vals = ema(closes, int(params['ema_fast']))
    ema_trend_vals = ema(closes, int(params['ema_trend']))
    ema_long_vals = ema(closes, int(params['ema_long']))
    rsi_fast_vals = rsi_wilder(closes, int(params['rsi_fast']))
    rsi_main_vals = rsi_wilder(closes, int(params['rsi_main']))
    bb_mid_vals, bb_upper_vals, bb_lower_vals = bollinger_bands(closes, int(params['bb_period']), float(params['bb_stddev']))
    volume_sma_vals = sma(volumes, int(params['volume_sma_period']))
    
    # Y(4.0) 委员会指标计算
    stoch_k_vals, stoch_d_vals = stochastic(highs, lows, closes, 14)
    cci_vals = cci(highs, lows, closes, 20)
    wr_vals = williams_r(highs, lows, closes, 14)
    mfi_vals = mfi(highs, lows, closes, volumes, 14)
    adx_vals, plus_di_vals, minus_di_vals = adx_di(highs, lows, closes, 14)
    
    i = len(closes) - 1
    price = closes[i]
    volume_now = volumes[i]
    volume_sma_now = volume_sma_vals[i]
    rsi_fast_now = rsi_fast_vals[i]
    rsi_main_now = rsi_main_vals[i]
    
    # Y(4.0) 委员会各组件当前值
    stoch_k_now = stoch_k_vals[i]
    stoch_d_now = stoch_d_vals[i]
    prev_stoch_k = stoch_k_vals[i - 1] if i > 0 else stoch_k_now
    prev_stoch_d = stoch_d_vals[i - 1] if i > 0 else stoch_d_now
    bb_upper_now = bb_upper_vals[i]
    bb_lower_now = bb_lower_vals[i]
    bb_mid_now = bb_mid_vals[i]
    cci_now = cci_vals[i]
    wr_now = wr_vals[i]
    mfi_now = mfi_vals[i]
    adx_now = adx_vals[i]
    plus_di_now = plus_di_vals[i]
    minus_di_now = minus_di_vals[i]
    volume_ratio = volume_now / volume_sma_now if volume_sma_now else 1.0
    
    # NFI 基础判定
    regime_long = ema_trend_vals[i] > ema_long_vals[i] and price > ema_long_vals[i] * float(params['regime_price_floor'])
    pullback_long = price <= bb_lower_vals[i] * float(params['bb_touch_buffer']) or price <= ema_fast_vals[i] * float(params['ema_pullback_buffer'])
    rsi_long = rsi_fast_now <= float(params['rsi_fast_buy']) and rsi_main_now <= float(params['rsi_main_buy'])
    volume_ok = volume_sma_now > 0 and volume_now >= volume_sma_now * float(params['min_volume_ratio'])
    stabilizing_long = closes[i] >= closes[i - 1] or rsi_fast_vals[i] > rsi_fast_vals[i - 1]
    regime_short = ema_trend_vals[i] < ema_long_vals[i] and price < ema_long_vals[i] * float(params['regime_price_ceiling'])
    pullback_short = price >= bb_upper_vals[i] * float(params['bb_reject_buffer']) or price >= ema_fast_vals[i] * float(params['ema_bounce_buffer'])
    rsi_short = rsi_fast_now >= float(params['rsi_fast_sell']) and rsi_main_now >= float(params['rsi_main_sell'])
    stabilizing_short = closes[i] <= closes[i - 1] or rsi_fast_vals[i] < rsi_fast_vals[i - 1]
    long_missing = []
    short_missing = []
    if not regime_long: long_missing.append('regime')
    if not pullback_long: long_missing.append('pullback')
    if not rsi_long: long_missing.append('rsi')
    if not volume_ok: long_missing.append('volume')
    if not stabilizing_long: long_missing.append('stabilizing')
    if not regime_short: short_missing.append('regime')
    if not pullback_short: short_missing.append('pullback')
    if not rsi_short: short_missing.append('rsi')
    if not volume_ok: short_missing.append('volume')
    if not stabilizing_short: short_missing.append('stabilizing')
    volume_threshold = volume_sma_now * float(params['min_volume_ratio']) if volume_sma_now > 0 else 0.0
    
    # 构建 Y(4.0) 委员会各组件评分详情
    y_components = []
    
    # RSI 组件
    if rsi_fast_now < 20:
        y_components.append({'name': 'RSI', 'score': 3, 'active': True, 'reason': f'深度超卖 ({rsi_fast_now:.1f} < 20)', 'direction': 'LONG'})
    elif rsi_fast_now < 25:
        y_components.append({'name': 'RSI', 'score': 2, 'active': True, 'reason': f'中度超卖 ({rsi_fast_now:.1f} < 25)', 'direction': 'LONG'})
    elif rsi_fast_now < 30:
        y_components.append({'name': 'RSI', 'score': 1, 'active': True, 'reason': f'轻度超卖 ({rsi_fast_now:.1f} < 30)', 'direction': 'LONG'})
    elif rsi_fast_now > 80:
        y_components.append({'name': 'RSI', 'score': 3, 'active': True, 'reason': f'深度超买 ({rsi_fast_now:.1f} > 80)', 'direction': 'SHORT'})
    elif rsi_fast_now > 75:
        y_components.append({'name': 'RSI', 'score': 2, 'active': True, 'reason': f'中度超买 ({rsi_fast_now:.1f} > 75)', 'direction': 'SHORT'})
    elif rsi_fast_now > 70:
        y_components.append({'name': 'RSI', 'score': 1, 'active': True, 'reason': f'轻度超买 ({rsi_fast_now:.1f} > 70)', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'RSI', 'score': 0, 'active': False, 'reason': f'中性区域 ({rsi_fast_now:.1f})', 'direction': 'NEUTRAL'})
    
    # Stoch 组件
    stoch_bullish_cross = stoch_k_now > stoch_d_now and prev_stoch_k <= prev_stoch_d
    stoch_bearish_cross = stoch_k_now < stoch_d_now and prev_stoch_k >= prev_stoch_d
    if stoch_k_now < 20 and stoch_bullish_cross:
        y_components.append({'name': 'Stoch', 'score': 3, 'active': True, 'reason': f'超卖区金叉 (K={stoch_k_now:.1f}, D={stoch_d_now:.1f})', 'direction': 'LONG'})
    elif stoch_k_now < 20:
        y_components.append({'name': 'Stoch', 'score': 2, 'active': True, 'reason': f'超卖区 (K={stoch_k_now:.1f} < 20)', 'direction': 'LONG'})
    elif stoch_k_now > 80 and stoch_bearish_cross:
        y_components.append({'name': 'Stoch', 'score': 3, 'active': True, 'reason': f'超买区死叉 (K={stoch_k_now:.1f}, D={stoch_d_now:.1f})', 'direction': 'SHORT'})
    elif stoch_k_now > 80:
        y_components.append({'name': 'Stoch', 'score': 2, 'active': True, 'reason': f'超买区 (K={stoch_k_now:.1f} > 80)', 'direction': 'SHORT'})
    elif stoch_bullish_cross and stoch_k_now < 30:
        y_components.append({'name': 'Stoch', 'score': 1, 'active': True, 'reason': f'低位金叉 (K={stoch_k_now:.1f})', 'direction': 'LONG'})
    elif stoch_bearish_cross and stoch_k_now > 70:
        y_components.append({'name': 'Stoch', 'score': 1, 'active': True, 'reason': f'高位死叉 (K={stoch_k_now:.1f})', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'Stoch', 'score': 0, 'active': False, 'reason': f'中性 (K={stoch_k_now:.1f}, D={stoch_d_now:.1f})', 'direction': 'NEUTRAL'})
    
    # BB 组件
    if price < bb_lower_now * 0.98:
        y_components.append({'name': 'BB', 'score': 3, 'active': True, 'reason': f'显著跌破下轨', 'direction': 'LONG'})
    elif price < bb_lower_now:
        y_components.append({'name': 'BB', 'score': 2, 'active': True, 'reason': f'跌破下轨', 'direction': 'LONG'})
    elif price <= bb_lower_now * 1.01:
        y_components.append({'name': 'BB', 'score': 1, 'active': True, 'reason': f'触及下轨', 'direction': 'LONG'})
    elif price > bb_upper_now * 1.02:
        y_components.append({'name': 'BB', 'score': 3, 'active': True, 'reason': f'显著突破上轨', 'direction': 'SHORT'})
    elif price > bb_upper_now:
        y_components.append({'name': 'BB', 'score': 2, 'active': True, 'reason': f'突破上轨', 'direction': 'SHORT'})
    elif price >= bb_upper_now * 0.99:
        y_components.append({'name': 'BB', 'score': 1, 'active': True, 'reason': f'触及上轨', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'BB', 'score': 0, 'active': False, 'reason': f'布林带内', 'direction': 'NEUTRAL'})
    
    # CCI 组件
    if cci_now < -200:
        y_components.append({'name': 'CCI', 'score': 3, 'active': True, 'reason': f'深度超卖 (CCI={cci_now:.1f})', 'direction': 'LONG'})
    elif cci_now < -150:
        y_components.append({'name': 'CCI', 'score': 2, 'active': True, 'reason': f'中度超卖 (CCI={cci_now:.1f})', 'direction': 'LONG'})
    elif cci_now < -100:
        y_components.append({'name': 'CCI', 'score': 1, 'active': True, 'reason': f'轻度超卖 (CCI={cci_now:.1f})', 'direction': 'LONG'})
    elif cci_now > 200:
        y_components.append({'name': 'CCI', 'score': 3, 'active': True, 'reason': f'深度超买 (CCI={cci_now:.1f})', 'direction': 'SHORT'})
    elif cci_now > 150:
        y_components.append({'name': 'CCI', 'score': 2, 'active': True, 'reason': f'中度超买 (CCI={cci_now:.1f})', 'direction': 'SHORT'})
    elif cci_now > 100:
        y_components.append({'name': 'CCI', 'score': 1, 'active': True, 'reason': f'轻度超买 (CCI={cci_now:.1f})', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'CCI', 'score': 0, 'active': False, 'reason': f'中性区域 (CCI={cci_now:.1f})', 'direction': 'NEUTRAL'})
    
    # Williams %R 组件
    if wr_now < -90:
        y_components.append({'name': 'Williams%R', 'score': 3, 'active': True, 'reason': f'深度超卖 (WR={wr_now:.1f})', 'direction': 'LONG'})
    elif wr_now < -85:
        y_components.append({'name': 'Williams%R', 'score': 2, 'active': True, 'reason': f'中度超卖 (WR={wr_now:.1f})', 'direction': 'LONG'})
    elif wr_now < -80:
        y_components.append({'name': 'Williams%R', 'score': 1, 'active': True, 'reason': f'轻度超卖 (WR={wr_now:.1f})', 'direction': 'LONG'})
    elif wr_now > -10:
        y_components.append({'name': 'Williams%R', 'score': 3, 'active': True, 'reason': f'深度超买 (WR={wr_now:.1f})', 'direction': 'SHORT'})
    elif wr_now > -15:
        y_components.append({'name': 'Williams%R', 'score': 2, 'active': True, 'reason': f'中度超买 (WR={wr_now:.1f})', 'direction': 'SHORT'})
    elif wr_now > -20:
        y_components.append({'name': 'Williams%R', 'score': 1, 'active': True, 'reason': f'轻度超买 (WR={wr_now:.1f})', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'Williams%R', 'score': 0, 'active': False, 'reason': f'中性区域 (WR={wr_now:.1f})', 'direction': 'NEUTRAL'})
    
    # MFI 组件
    if mfi_now < 10:
        y_components.append({'name': 'MFI', 'score': 3, 'active': True, 'reason': f'深度资金流出 (MFI={mfi_now:.1f})', 'direction': 'LONG'})
    elif mfi_now < 20:
        y_components.append({'name': 'MFI', 'score': 2, 'active': True, 'reason': f'中度资金流出 (MFI={mfi_now:.1f})', 'direction': 'LONG'})
    elif mfi_now < 30:
        y_components.append({'name': 'MFI', 'score': 1, 'active': True, 'reason': f'轻度资金流出 (MFI={mfi_now:.1f})', 'direction': 'LONG'})
    elif mfi_now > 90:
        y_components.append({'name': 'MFI', 'score': 3, 'active': True, 'reason': f'深度资金流入 (MFI={mfi_now:.1f})', 'direction': 'SHORT'})
    elif mfi_now > 80:
        y_components.append({'name': 'MFI', 'score': 2, 'active': True, 'reason': f'中度资金流入 (MFI={mfi_now:.1f})', 'direction': 'SHORT'})
    elif mfi_now > 70:
        y_components.append({'name': 'MFI', 'score': 1, 'active': True, 'reason': f'轻度资金流入 (MFI={mfi_now:.1f})', 'direction': 'SHORT'})
    else:
        y_components.append({'name': 'MFI', 'score': 0, 'active': False, 'reason': f'中性资金流 (MFI={mfi_now:.1f})', 'direction': 'NEUTRAL'})
    
    # ADX/DI 组件
    adx_direction = 'BULLISH' if plus_di_now > minus_di_now else 'BEARISH'
    if adx_now > 40:
        y_components.append({'name': 'ADX/DI', 'score': 3, 'active': True, 'reason': f'强趋势 ({adx_direction}, ADX={adx_now:.1f})', 'direction': adx_direction})
    elif adx_now > 25:
        y_components.append({'name': 'ADX/DI', 'score': 2, 'active': True, 'reason': f'中等趋势 ({adx_direction}, ADX={adx_now:.1f})', 'direction': adx_direction})
    elif adx_now > 20:
        y_components.append({'name': 'ADX/DI', 'score': 1, 'active': True, 'reason': f'弱趋势 ({adx_direction}, ADX={adx_now:.1f})', 'direction': adx_direction})
    else:
        y_components.append({'name': 'ADX/DI', 'score': 0, 'active': False, 'reason': f'无明确趋势 (ADX={adx_now:.1f})', 'direction': 'NEUTRAL'})
    
    # Divergence 组件（简化版：基于RSI和价格对比）
    lookback = 14
    if len(closes) >= lookback and len(rsi_fast_vals) >= lookback:
        recent_prices = closes[-lookback:]
        recent_rsi = rsi_fast_vals[-lookback:]
        price_low_idx = min(range(len(recent_prices)), key=lambda idx: recent_prices[idx])
        rsi_low_idx = min(range(len(recent_rsi)), key=lambda idx: recent_rsi[idx])
        price_high_idx = max(range(len(recent_prices)), key=lambda idx: recent_prices[idx])
        rsi_high_idx = max(range(len(recent_rsi)), key=lambda idx: recent_rsi[idx])
        bullish_div = price_low_idx > rsi_low_idx  # 价格新低，RSI未新低
        bearish_div = price_high_idx > rsi_high_idx  # 价格新高，RSI未新高
        if bullish_div:
            y_components.append({'name': 'Divergence', 'score': 2, 'active': True, 'reason': f'看涨背离 (价格底≠RSI底)', 'direction': 'LONG'})
        elif bearish_div:
            y_components.append({'name': 'Divergence', 'score': 2, 'active': True, 'reason': f'看跌背离 (价格顶≠RSI顶)', 'direction': 'SHORT'})
        else:
            y_components.append({'name': 'Divergence', 'score': 0, 'active': False, 'reason': f'无背离', 'direction': 'NEUTRAL'})
    else:
        y_components.append({'name': 'Divergence', 'score': 0, 'active': False, 'reason': '数据不足', 'direction': 'NEUTRAL'})
    
    # 计算 Y 委员会总分和判定
    y_total_score = sum(c['score'] for c in y_components)
    y_active_count = sum(1 for c in y_components if c['active'])
    y_long_signals = sum(1 for c in y_components if c['active'] and c['direction'] == 'LONG')
    y_short_signals = sum(1 for c in y_components if c['active'] and c['direction'] == 'SHORT')
    y_direction = 'LONG' if y_long_signals > y_short_signals else 'SHORT' if y_short_signals > y_long_signals else 'NEUTRAL'
    
    # 成交量倍数
    y_volume_multiplier = 1.0
    if volume_ratio > 1.5:
        y_volume_multiplier = 1.3
    elif volume_ratio > 1.2:
        y_volume_multiplier = 1.15
    elif volume_ratio > 1.0:
        y_volume_multiplier = 1.05
    y_final_score = y_total_score * y_volume_multiplier
    
    # Y 委员会通过条件：至少5/8组件激活 + 总分≥10 + 有明确方向
    y_passed = y_active_count >= 5 and y_final_score >= 10 and y_direction != 'NEUTRAL'
    
    # market_score 计算（综合评分 0-100）
    regime_score = 25 if regime_long or regime_short else 0
    adx_score = 20 if adx_now > 25 else 10 if adx_now > 20 else 0
    volume_score = 25 if volume_ok else 15 if volume_ratio > 0.8 else 0
    volatility_score = 15 if abs(cci_now) > 100 else 10 if abs(cci_now) > 50 else 0
    rsi_zone_score = 15 if rsi_fast_now < 30 or rsi_fast_now > 70 else 0
    market_score = min(100, regime_score + adx_score + volume_score + volatility_score + rsi_zone_score)
    
    return {
        'symbol': symbol,
        'timeframe': '1h',
        'price': round(price, 6),
        'rsi_fast': round(rsi_fast_now, 2),
        'rsi_main': round(rsi_main_now, 2),
        'stoch_k': round(stoch_k_now, 2),
        'stoch_d': round(stoch_d_now, 2),
        'cci': round(cci_now, 2),
        'williams_r': round(wr_now, 2),
        'mfi': round(mfi_now, 2),
        'adx': round(adx_now, 2),
        'plus_di': round(plus_di_now, 2),
        'minus_di': round(minus_di_now, 2),
        'volume_now': round(volume_now, 6),
        'volume_sma_30': round(volume_sma_now, 6),
        'volume_threshold': round(volume_threshold, 6),
        'volume_ratio_to_sma': round(volume_ratio, 4) if volume_sma_now else None,
        'thresholds': {
            'long': {'rsi_fast_max': params['rsi_fast_buy'], 'rsi_main_max': params['rsi_main_buy']},
            'short': {'rsi_fast_min': params['rsi_fast_sell'], 'rsi_main_min': params['rsi_main_sell']},
            'volume_min_ratio_to_sma': params['min_volume_ratio'],
        },
        'distance_to_long_rsi': {
            'rsi_fast': round(rsi_fast_now - float(params['rsi_fast_buy']), 2),
            'rsi_main': round(rsi_main_now - float(params['rsi_main_buy']), 2),
        },
        'distance_to_short_rsi': {
            'rsi_fast': round(float(params['rsi_fast_sell']) - rsi_fast_now, 2),
            'rsi_main': round(float(params['rsi_main_sell']) - rsi_main_now, 2),
        },
        'distance_to_volume_threshold': round(volume_threshold - volume_now, 6),
        'long_setup': {'ready': len(long_missing) == 0, 'missing': long_missing},
        'short_setup': {'ready': len(short_missing) == 0, 'missing': short_missing},
        'y_committee': {
            'components': y_components,
            'total_score': y_total_score,
            'max_score': 24,
            'final_score': round(y_final_score, 2),
            'active_count': y_active_count,
            'passed': y_passed,
            'direction': y_direction,
            'volume_multiplier': round(y_volume_multiplier, 2),
            'long_signals': y_long_signals,
            'short_signals': y_short_signals,
            'summary': f"激活 {y_active_count}/8，总分 {y_total_score}/24（最终 {y_final_score:.1f}），方向 {y_direction}，{'✅ 通过' if y_passed else '❌ 未通过'}"
        },
        'market_score': market_score,
        'human_summary': (
            f"{symbol} NFI: 做多还差 {','.join(long_missing) or '无'}；做空还差 {','.join(short_missing) or '无'}；"
            + f"Y(4.0): 激活{y_active_count}/8，{y_total_score}分，{'通过' if y_passed else '未通过'}"
        )
    }


def build_signal_diagnostics(ctx: ExportContext) -> Dict[str, Any]:
    symbols = ['BTC', 'ETH']
    diagnostics = [diagnose_symbol(symbol) for symbol in symbols]
    return {
        'updated_at': ctx.now_iso,
        'strategy_name': 'nostalgia_for_infinity',
        'diagnostics': diagnostics,
    }


def build_meta(ctx: ExportContext) -> Dict[str, Any]:
    return {
        "project": "LuckyNiuMaNote",
        "env": os.getenv("LUCKYNIUMA_ENV", "production"),
        "exchange": "Hyperliquid",
        "timezone": datetime.now().astimezone().tzname(),
        "data_version": "v1",
        "generated_at": ctx.now_iso,
        "wallet": ctx.wallet,
        "git_version": get_git_version(),
    }


def build_overview(ctx: ExportContext) -> Dict[str, Any]:
    margin = ctx.account_state.get("marginSummary", {}) if ctx.account_state else {}
    account_value = safe_float(margin.get("accountValue"))
    total_ntl = safe_float(margin.get("totalNtlPos"))
    total_raw_usd = safe_float(margin.get("totalRawUsd"))
    withdrawable = safe_float(ctx.account_state.get("withdrawable"))
    asset_positions = ctx.account_state.get("assetPositions", []) if ctx.account_state else []
    spot_balances = ctx.spot_state.get("balances", []) if ctx.spot_state else []
    spot_usdc = 0.0
    for bal in spot_balances:
        if bal.get("coin") == "USDC":
            spot_usdc = safe_float(bal.get("total"))
            break

    open_orders_count = len(
        query_rows(
            "SELECT id FROM orders WHERE status IN ('OPEN', 'NEW', 'PLACED', 'TRIGGERED', 'RESTING')"
        )
    )

    risk_guard = query_one("SELECT value_json, updated_at FROM runtime_state WHERE key='risk_guard'")
    risk_guard_state = safe_json_loads(risk_guard.get("value_json"), {})

    return {
        "account_name": "Hyperliquid Main",
        "equity": account_value,
        "available_balance": withdrawable,
        "margin_used": max(total_ntl, total_raw_usd),
        "unrealized_pnl": sum(
            safe_float(pos.get("position", {}).get("unrealizedPnl")) for pos in asset_positions
        ),
        "spot_usdc": spot_usdc,
        "spot_balances": spot_balances,
        "perp_equity": account_value,
        "perp_available_balance": withdrawable,
        "perp_margin_used": max(total_ntl, total_raw_usd),
        "realized_pnl_today": 0.0,
        "daily_return_pct": 0.0,
        "total_return_pct": 0.0,
        "open_positions_count": len(asset_positions),
        "open_orders_count": open_orders_count,
        "bot_mode": "SAFE_MODE" if risk_guard_state.get("safe_mode") else ("MONITOR_ONLY" if os.getenv("TRADER_MODE", "monitor").lower() != "live" else "LIVE"),
        "strategy_name": "nostalgia_for_infinity",
        "updated_at": ctx.now_iso,
    }


def build_positions(ctx: ExportContext) -> Dict[str, Any]:
    positions: List[Dict[str, Any]] = []
    for item in ctx.account_state.get("assetPositions", []) if ctx.account_state else []:
        pos = item.get("position", {})
        size = safe_float(pos.get("szi"))
        side = "LONG" if size > 0 else "SHORT" if size < 0 else "FLAT"
        symbol = pos.get("coin") or "UNKNOWN"
        entry_price = safe_float(pos.get("entryPx"))
        mark_price = safe_float(pos.get("markPx"), ctx.prices.get(symbol, 0.0))
        unrealized_pnl = safe_float(pos.get("unrealizedPnl"))
        notional = abs(size) * mark_price if mark_price else 0.0
        pnl_pct = (unrealized_pnl / notional * 100.0) if notional else 0.0
        leverage = safe_float(pos.get("leverage", {}).get("value"))
        margin_mode = pos.get("leverage", {}).get("type") or "unknown"

        local_pos = query_one(
            "SELECT * FROM positions WHERE symbol=? ORDER BY updated_at DESC LIMIT 1",
            (symbol,),
        )
        meta = safe_json_loads(local_pos.get("meta_json"), {}) if local_pos else {}

        positions.append(
            {
                "symbol": symbol,
                "side": side,
                "size": abs(size),
                "entry_price": entry_price,
                "mark_price": mark_price,
                "liquidation_price": safe_float(pos.get("liquidationPx"), 0.0) or None,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": pnl_pct,
                "leverage": leverage,
                "margin_mode": margin_mode,
                "opened_at": local_pos.get("opened_at") if local_pos else None,
                "strategy_tag": meta.get("strategy_tag", "NFI"),
                "status": local_pos.get("status") if local_pos else "OPEN",
                "stop_loss": local_pos.get("stop_loss") if local_pos else None,
                "take_profit": local_pos.get("take_profit") if local_pos else None,
            }
        )

    return {
        "updated_at": ctx.now_iso,
        "positions": positions,
    }


def build_trades(ctx: ExportContext) -> Dict[str, Any]:
    fills = fetch_hyperliquid_user_fills(ctx.wallet)
    trades: List[Dict[str, Any]] = []

    for fill in fills:
        direction = str(fill.get("dir") or "")
        direction_upper = direction.upper()
        if "OPEN" in direction_upper:
            action = "开仓"
        elif "CLOSE" in direction_upper:
            action = "平仓"
        else:
            action = "成交"

        if "LONG" in direction_upper:
            position_side = "LONG"
        elif "SHORT" in direction_upper:
            position_side = "SHORT"
        else:
            position_side = "UNKNOWN"

        side_code = str(fill.get("side") or "").upper()
        side = "BUY" if side_code == "B" else "SELL" if side_code == "A" else side_code
        timestamp_ms = fill.get("time")
        timestamp = None
        try:
            if timestamp_ms is not None:
                timestamp = datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        except Exception:
            timestamp = None

        trades.append(
            {
                "trade_id": str(fill.get("tid") or fill.get("oid") or fill.get("hash") or ""),
                "symbol": fill.get("coin"),
                "action": action,
                "side": side,
                "position_side": position_side,
                "price": safe_float(fill.get("px"), default=None),
                "qty": safe_float(fill.get("sz"), default=None),
                "fee": safe_float(fill.get("fee"), default=None),
                "realized_pnl": safe_float(fill.get("closedPnl"), default=0.0),
                "source": "hyperliquid_fill",
                "strategy_tag": "NFI",
                "timestamp": timestamp,
                "raw_direction": direction,
                "hash": fill.get("hash"),
                "start_position": safe_float(fill.get("startPosition"), default=None),
            }
        )

    if not trades:
        order_rows = query_rows(
            "SELECT * FROM orders ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 100"
        )
        for row in order_rows:
            payload = safe_json_loads(row.get("payload_json"), {})
            status = str(row.get("status") or "").upper()
            payload_status = str(payload.get("status") or "").upper()
            response = payload.get("response") or {}
            data = response.get("data") or {}
            statuses = data.get("statuses") or []
            filled = None
            if statuses and isinstance(statuses, list):
                first = statuses[0] or {}
                filled = first.get("filled") if isinstance(first, dict) else None
            is_executed = bool(filled) or status in {"FILLED", "CLOSED", "EXECUTED", "OK"} or payload_status in {"FILLED", "CLOSED", "EXECUTED", "OK"}
            if not is_executed:
                continue
            trades.append(
                {
                    "trade_id": row.get("order_id") or f"local_{row.get('id')}",
                    "symbol": row.get("symbol"),
                    "action": "成交",
                    "side": row.get("side"),
                    "position_side": payload.get("position_side") or "UNKNOWN",
                    "price": safe_float(((filled or {}).get("avgPx") if isinstance(filled, dict) else None) or row.get("price"), default=None),
                    "qty": safe_float(((filled or {}).get("totalSz") if isinstance(filled, dict) else None) or row.get("size"), default=None),
                    "fee": safe_float(payload.get("fee"), default=None),
                    "realized_pnl": safe_float(payload.get("realized_pnl"), default=0.0),
                    "source": payload.get("source", "bot"),
                    "strategy_tag": payload.get("strategy_tag", "NFI"),
                    "timestamp": row.get("updated_at") or row.get("created_at"),
                }
            )

    trades.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return {
        "updated_at": ctx.now_iso,
        "trades": trades[:100],
    }


def build_orders(ctx: ExportContext) -> Dict[str, Any]:
    rows = query_rows(
        "SELECT * FROM orders ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 100"
    )
    orders: List[Dict[str, Any]] = []
    for row in rows:
        payload = safe_json_loads(row.get("payload_json"), {})
        orders.append(
            {
                "order_id": row.get("order_id") or f"local_{row.get('id')}",
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "type": row.get("order_type"),
                "price": safe_float(row.get("price")),
                "qty": safe_float(row.get("size")),
                "filled_qty": safe_float(payload.get("filled_qty")),
                "status": row.get("status"),
                "reduce_only": bool(payload.get("reduce_only", False)),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {
        "updated_at": ctx.now_iso,
        "orders": orders[:50],
    }


def build_performance(ctx: ExportContext) -> Dict[str, Any]:
    generated = read_generated_data()
    stats = generated.get("STATS", {})
    equity = safe_float(ctx.account_state.get("marginSummary", {}).get("accountValue"))
    initial_capital = safe_float(stats.get("balance"), 98.0)
    total_return_pct = ((equity - initial_capital) / initial_capital * 100.0) if initial_capital else 0.0

    return {
        "updated_at": ctx.now_iso,
        "summary": {
            "today_pnl": 0.0,
            "7d_pnl": 0.0,
            "30d_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": total_return_pct,
        },
        "equity_curve": [
            {
                "ts": ctx.now_iso,
                "equity": equity,
            }
        ],
        "notes": [
            "performance.json 初版仅输出当前权益快照",
            "后续可接入历史权益表或定时快照，补齐资金曲线 / 胜率 / 回撤",
        ],
    }


def build_bot_status(ctx: ExportContext) -> Dict[str, Any]:
    docker_hint = bool(os.getenv("LUCKYNIUMA_WALLET") or os.getenv("TRADER_MODE") or os.getenv("HL_API_KEY"))
    systemd_state = get_systemd_state(SERVICE_NAME)
    latest_log = find_latest_log()
    log_lines = tail_lines(latest_log, 200) if latest_log else []
    last_heartbeat = extract_last_log_timestamp(log_lines)
    risk_guard = query_one("SELECT value_json, updated_at FROM runtime_state WHERE key='risk_guard'")
    risk_guard_state = safe_json_loads(risk_guard.get("value_json"), {})
    last_order = query_one("SELECT created_at FROM orders ORDER BY created_at DESC LIMIT 1")
    last_event = query_one("SELECT created_at FROM system_events ORDER BY created_at DESC LIMIT 1")
    safe_mode = bool(risk_guard_state.get("safe_mode", False))
    safe_reason = risk_guard_state.get("safe_reason", "")
    safe_mode_updated_at = risk_guard.get("updated_at")
    trader_mode = (os.getenv("TRADER_MODE", "monitor") or "monitor").strip().lower()
    api_key_present = bool((os.getenv("HL_API_KEY") or "").strip() or read_hl_config().get("API_PRIVATE_KEY"))
    if docker_hint and systemd_state.get("service_status") == "unknown":
        service_status = "running" if last_heartbeat else "starting"
        process_healthy = bool(last_heartbeat)
    else:
        service_status = systemd_state.get("service_status")
        process_healthy = bool(systemd_state.get("process_healthy"))

    return {
        "updated_at": ctx.now_iso,
        **systemd_state,
        "service_status": service_status,
        "process_healthy": process_healthy,
        "safe_mode": safe_mode,
        "safe_reason": safe_reason,
        "safe_mode_updated_at": safe_mode_updated_at,
        "trader_mode": trader_mode,
        "monitor_only": (trader_mode != "live") or (not api_key_present),
        "last_heartbeat_at": last_heartbeat,
        "last_trade_at": last_order.get("created_at"),
        "last_reconcile_at": last_event.get("created_at"),
        "sqlite_ok": ctx.db_available,
        "telegram_alert_ok": True,
        "protection_order_ok": True,
        "version": get_git_version(),
        "latest_log_file": str(latest_log) if latest_log else None,
    }


def build_alerts(ctx: ExportContext) -> Dict[str, Any]:
    rows = query_rows(
        "SELECT * FROM system_events ORDER BY created_at DESC LIMIT 200"
    )
    alerts: List[Dict[str, Any]] = []
    seen = set()
    severity_rank = {"critical": 0, "error": 1, "warn": 2, "info": 3}
    status_rank = {"open": 2, "stale": 1, "resolved": 0}
    risk_guard = query_one("SELECT value_json, updated_at FROM runtime_state WHERE key='risk_guard'")
    risk_guard_state = safe_json_loads(risk_guard.get("value_json"), {})
    current_safe_mode = bool(risk_guard_state.get("safe_mode", False))
    current_safe_reason = str(risk_guard_state.get("safe_reason") or "")

    for row in rows:
        payload = safe_json_loads(row.get("payload_json"), {})
        level = str(row.get("level") or "info").lower()
        event_type = row.get("event_type") or "system_event"
        message = row.get("message") or ""
        symbol = payload.get("symbol")
        dedupe_key = (level, event_type, message, symbol)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        status = "resolved"
        if event_type == "safe_mode":
            status = "open" if current_safe_mode and message == current_safe_reason else "resolved"
        elif event_type in {"failure", "api_timeout", "cycle_exception"}:
            status = "open" if current_safe_mode and current_safe_reason and message and message in current_safe_reason else "stale"

        alerts.append(
            {
                "id": f"event_{row.get('id')}",
                "level": level,
                "title": event_type,
                "title_zh": translate_alert_title(str(event_type)),
                "message": message,
                "message_zh": translate_alert_message(str(message)),
                "symbol": symbol,
                "created_at": row.get("created_at"),
                "status": status,
            }
        )

    alerts.sort(
        key=lambda item: (
            status_rank.get(item.get("status") or "resolved", 0),
            -severity_rank.get(item["level"], 9),
            item.get("created_at") or "",
        ),
        reverse=True,
    )

    return {
        "updated_at": ctx.now_iso,
        "alerts": alerts[:20],
    }


def write_json(name: str, payload: Dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    runtime_cfg = read_runtime_config()
    generated = read_generated_data()
    wallet = resolve_wallet(runtime_cfg, generated)
    prices = get_prices()
    account_state = get_account_state(wallet)
    spot_state = get_spot_state(wallet)
    ctx = ExportContext(
        now_iso=now_iso(),
        wallet=wallet,
        account_state=account_state,
        spot_state=spot_state,
        prices=prices,
        db_available=STATE_DB.exists(),
    )

    write_json("meta.json", build_meta(ctx))
    write_json("overview.json", build_overview(ctx))
    write_json("positions.json", build_positions(ctx))
    write_json("trades.json", build_trades(ctx))
    write_json("orders.json", build_orders(ctx))
    write_json("performance.json", build_performance(ctx))
    write_json("bot_status.json", build_bot_status(ctx))
    write_json("alerts.json", build_alerts(ctx))
    write_json("signal_diagnostics.json", build_signal_diagnostics(ctx))

    print(f"[{ctx.now_iso}] Exported dashboard JSON to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
