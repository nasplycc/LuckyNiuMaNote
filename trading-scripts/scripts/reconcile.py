"""Startup reconciliation between exchange state and local SQLite state."""
from __future__ import annotations

from typing import Any, Dict, List

from risk_guard import RiskGuard
from state_store import StateStore


class ReconcileResult(dict):
    pass


def reconcile_exchange_state(
    *,
    store: StateStore,
    guard: RiskGuard,
    account_state: Dict[str, Any],
    open_orders: List[Dict[str, Any]],
    enforce_safe_mode: bool = True,
) -> ReconcileResult:
    result: ReconcileResult = ReconcileResult(ok=True, issues=[])

    local_positions = {p["symbol"]: p for p in store.get_open_positions()}
    exchange_positions = {}
    for pos in account_state.get("positions", []):
        p = pos.get("position", {})
        coin = p.get("coin")
        size = float(p.get("szi", 0) or 0)
        if coin and size != 0:
            exchange_positions[coin] = p

    orders_by_coin: Dict[str, List[Dict[str, Any]]] = {}
    for order in open_orders or []:
        coin = order.get("coin")
        if not coin:
            continue
        orders_by_coin.setdefault(coin, []).append(order)

    for symbol, ex_pos in exchange_positions.items():
        local_pos = local_positions.get(symbol)
        symbol_orders = orders_by_coin.get(symbol, [])
        # Hyperliquid open_orders API doesn't return 'tpsl' field
        # So we identify protection orders by: reduceOnly=True
        reduce_only_orders = [o for o in symbol_orders if o.get("reduceOnly")]
        has_protection = len(reduce_only_orders) >= 2  # Need at least SL + TP

        if not local_pos:
            result["ok"] = False
            result["issues"].append({"type": "missing_local_position", "symbol": symbol})
        if not has_protection:
            result["ok"] = False
            result["issues"].append({"type": "missing_protection_orders", "symbol": symbol, "reduce_only_count": len(reduce_only_orders)})

    for symbol in local_positions:
        if symbol not in exchange_positions:
            result["ok"] = False
            result["issues"].append({"type": "stale_local_position", "symbol": symbol})

    known_order_ids = store.get_known_order_ids()
    for order in open_orders or []:
        oid = str(order.get("oid") or "")
        coin = order.get("coin")
        if oid and oid not in known_order_ids and coin not in exchange_positions:
            result["ok"] = False
            result["issues"].append({"type": "unknown_open_order", "symbol": coin, "order_id": oid})

    if not result["ok"]:
        if enforce_safe_mode:
            guard.enter_safe_mode("Startup reconciliation failed", {"issues": result["issues"]})
            store.record_event("CRITICAL", "reconcile_failed", "Startup reconciliation failed", {"issues": result["issues"]})
        else:
            store.record_event("WARN", "reconcile_warn", "Startup reconciliation warnings in monitor-only mode", {"issues": result["issues"]})
    else:
        # If SAFE_MODE was triggered by previous reconciliation failure, auto-clear it
        if guard.in_safe_mode() and "reconciliation" in str(guard.state.get("safe_reason", "")).lower():
            guard.exit_safe_mode()
            store.record_event("INFO", "safe_mode_exit", "SAFE_MODE auto-cleared after successful reconciliation", {})
        store.record_event("INFO", "reconcile_ok", "Startup reconciliation passed", {})

    return result
