"""Risk guard with SAFE_MODE persistence and counters."""
from __future__ import annotations

from typing import Any, Dict

from state_store import StateStore


class RiskGuard:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.state = self.store.get_runtime_value(
            "risk_guard",
            {
                "safe_mode": False,
                "safe_reason": "",
                "consecutive_failures": 0,
                "api_timeouts": 0,
            },
        )

    def _save(self) -> None:
        self.store.set_runtime_value("risk_guard", self.state)

    def in_safe_mode(self) -> bool:
        return bool(self.state.get("safe_mode"))

    def enter_safe_mode(self, reason: str, payload: Dict[str, Any] | None = None) -> None:
        self.state["safe_mode"] = True
        self.state["safe_reason"] = reason
        self._save()
        self.store.record_event("CRITICAL", "safe_mode", reason, payload or {})

    def exit_safe_mode(self) -> None:
        self.state["safe_mode"] = False
        self.state["safe_reason"] = ""
        self._save()
        self.store.record_event("INFO", "safe_mode_exit", "Exited SAFE_MODE", {})

    def record_success(self) -> None:
        self.state["consecutive_failures"] = 0
        self.state["api_timeouts"] = 0
        self._save()

    def record_failure(self, reason: str, payload: Dict[str, Any] | None = None, threshold: int = 3) -> bool:
        self.state["consecutive_failures"] = int(self.state.get("consecutive_failures", 0)) + 1
        self._save()
        self.store.record_event("ERROR", "failure", reason, payload or {})
        if self.state["consecutive_failures"] >= threshold:
            self.enter_safe_mode(f"Consecutive failures >= {threshold}: {reason}", payload)
            return True
        return False

    def record_api_timeout(self, payload: Dict[str, Any] | None = None, threshold: int = 5) -> bool:
        self.state["api_timeouts"] = int(self.state.get("api_timeouts", 0)) + 1
        self._save()
        self.store.record_event("ERROR", "api_timeout", "API timeout", payload or {})
        if self.state["api_timeouts"] >= threshold:
            self.enter_safe_mode(f"API timeouts >= {threshold}", payload)
            return True
        return False
