"""Telegram notifier for trading runtime alerts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / ".runtime_config.json"


def _load_runtime_config() -> Dict[str, Any]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_CONFIG_PATH.read_text())
    except Exception:
        return {}


class TelegramNotifier:
    def __init__(self) -> None:
        cfg = _load_runtime_config().get("telegram", {})
        self.token = os.getenv("TG_BOT_TOKEN") or cfg.get("bot_token") or ""
        self.chat_id = os.getenv("TG_CHAT_ID") or cfg.get("chat_id") or ""
        self.enabled = bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=8,
            )
            return resp.status_code == 200
        except Exception:
            return False
