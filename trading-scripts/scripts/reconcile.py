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

    for symbol, _ex_pos in exchange_positions.items():
        local_pos = local_positions.get(symbol)
        symbol_orders = orders_by_coin.get(symbol, [])
        trigger_orders = [
            o for o in symbol_orders
            if str(o.get("orderType", "")).lower().find("trigger") >= 0
            or o.get("triggerCondition")
            or str(o.get("origType", "")).lower().find("trigger") >= 0
        ]
        has_trigger = len(trigger_orders) > 0
        has_stop = any(
            str(o.get("tpsl", "")).lower() == "sl" or str(o.get("orderType", "")).lower().find("sl") >= 0
            for o in trigger_orders
        )
        has_tp = any(
            str(o.get("tpsl", "")).lower() == "tp" or str(o.get("orderType", "")).lower().find("tp") >= 0
            for o in trigger_orders
        )

        if not local_pos:
            result["ok"] = False
            result["issues"].append({"type": "missing_local_position", "symbol": symbol})
        if not has_trigger:
            result["ok"] = False
            result["issues"].append({"type": "missing_protection_order", "symbol": symbol})
        if has_trigger and not has_stop:
            result["ok"] = False
            result["issues"].append({"type": "missing_stop_loss", "symbol": symbol})
        if has_trigger and not has_tp:
            result["ok"] = False
            result["issues"].append({"type": "missing_take_profit", "symbol": symbol})

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
