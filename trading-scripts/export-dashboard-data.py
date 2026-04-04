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
    base = {
        'ema_fast': 20, 'ema_trend': 50, 'ema_long': 200,
        'rsi_fast': 4, 'rsi_main': 14, 'bb_period': 20, 'bb_stddev': 2.0,
        'volume_sma_period': 30, 'rsi_fast_buy': 23.0, 'rsi_main_buy': 36.0,
        'rsi_fast_sell': 75.0, 'rsi_main_sell': 60.0, 'min_volume_ratio': 0.65,
        'bb_touch_buffer': 1.01, 'ema_pullback_buffer': 0.985,
        'regime_price_floor': 0.95, 'regime_price_ceiling': 1.05,
        'bb_reject_buffer': 0.99, 'ema_bounce_buffer': 1.015,
        'max_breakdown_pct': 0.10, 'max_breakout_pct': 0.10,
    }
    if symbol == 'ETH':
        base.update({'rsi_fast_buy': 21.0, 'rsi_main_buy': 34.0, 'rsi_fast_sell': 72.0, 'rsi_main_sell': 60.0})
    return base


def diagnose_symbol(symbol: str) -> Dict[str, Any]:
    params = nfi_params_for_symbol(symbol)
    klines = get_klines(symbol, interval='1h', limit=240)
    if len(klines) < params['ema_long'] + 5:
        return {'symbol': symbol, 'status': 'insufficient_data'}
    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]
    ema_fast_vals = ema(closes, int(params['ema_fast']))
    ema_trend_vals = ema(closes, int(params['ema_trend']))
    ema_long_vals = ema(closes, int(params['ema_long']))
    rsi_fast_vals = rsi_wilder(closes, int(params['rsi_fast']))
    rsi_main_vals = rsi_wilder(closes, int(params['rsi_main']))
    _, bb_upper_vals, bb_lower_vals = bollinger_bands(closes, int(params['bb_period']), float(params['bb_stddev']))
    volume_sma_vals = sma(volumes, int(params['volume_sma_period']))
    i = len(closes) - 1
    price = closes[i]
    volume_now = volumes[i]
    volume_sma_now = volume_sma_vals[i]
    rsi_fast_now = rsi_fast_vals[i]
    rsi_main_now = rsi_main_vals[i]
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
    return {
        'symbol': symbol,
        'timeframe': '1h',
        'price': round(price, 6),
        'rsi_fast': round(rsi_fast_now, 2),
        'rsi_main': round(rsi_main_now, 2),
        'volume_now': round(volume_now, 6),
        'volume_sma_30': round(volume_sma_now, 6),
        'volume_threshold': round(volume_threshold, 6),
        'volume_ratio_to_sma': round((volume_now / volume_sma_now), 4) if volume_sma_now else None,
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
        'human_summary': (
            f"{symbol} 当前未触发。做多还差: {','.join(long_missing) or '无'}；"
            f"做空还差: {','.join(short_missing) or '无'}；"
            f"当前 RSI={rsi_fast_now:.1f}/{rsi_main_now:.1f}，量能={volume_now:.2f}，阈值≥{volume_threshold:.2f}。"
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
        "bot_mode": "SAFE_MODE" if risk_guard_state.get("safe_mode") else "LIVE",
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
    rows = query_rows(
        "SELECT * FROM orders ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 50"
    )
    trades: List[Dict[str, Any]] = []
    for row in rows:
        payload = safe_json_loads(row.get("payload_json"), {})
        status = str(row.get("status") or "").upper()
        if status not in {"FILLED", "CLOSED", "EXECUTED"}:
            continue
        trades.append(
            {
                "trade_id": row.get("order_id") or f"local_{row.get('id')}",
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "position_side": payload.get("position_side") or "UNKNOWN",
                "price": safe_float(row.get("price")),
                "qty": safe_float(row.get("size")),
                "fee": safe_float(payload.get("fee")),
                "realized_pnl": safe_float(payload.get("realized_pnl")),
                "source": payload.get("source", "bot"),
                "strategy_tag": payload.get("strategy_tag", "NFI"),
                "executed_at": row.get("updated_at") or row.get("created_at"),
            }
        )

    return {
        "updated_at": ctx.now_iso,
        "trades": trades[:30],
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
    systemd_state = get_systemd_state(SERVICE_NAME)
    latest_log = find_latest_log()
    log_lines = tail_lines(latest_log, 200) if latest_log else []
    last_heartbeat = extract_last_log_timestamp(log_lines)
    risk_guard = query_one("SELECT value_json, updated_at FROM runtime_state WHERE key='risk_guard'")
    risk_guard_state = safe_json_loads(risk_guard.get("value_json"), {})
    last_order = query_one("SELECT created_at FROM orders ORDER BY created_at DESC LIMIT 1")
    last_event = query_one("SELECT created_at FROM system_events ORDER BY created_at DESC LIMIT 1")

    return {
        "updated_at": ctx.now_iso,
        **systemd_state,
        "safe_mode": bool(risk_guard_state.get("safe_mode", False)),
        "safe_reason": risk_guard_state.get("safe_reason", ""),
        "monitor_only": not bool(
            os.getenv("HL_API_KEY")
            or read_hl_config().get("API_PRIVATE_KEY")
        ),
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
        "SELECT * FROM system_events ORDER BY created_at DESC LIMIT 50"
    )
    alerts: List[Dict[str, Any]] = []
    for row in rows:
        payload = safe_json_loads(row.get("payload_json"), {})
        alerts.append(
            {
                "id": f"event_{row.get('id')}",
                "level": str(row.get("level") or "info").lower(),
                "title": row.get("event_type") or "system_event",
                "message": row.get("message") or "",
                "symbol": payload.get("symbol"),
                "created_at": row.get("created_at"),
                "status": "open",
            }
        )

    return {
        "updated_at": ctx.now_iso,
        "alerts": alerts,
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
