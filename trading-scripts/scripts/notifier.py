"""Telegram notifier for trading runtime alerts."""
from __future__ import annotations

import json
import logging
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / ".runtime_config.json"
logger = logging.getLogger("NFITrader")


@contextmanager
def _force_ipv4_resolution():
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


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
            logger.warning("telegram notifier disabled: missing bot token or chat_id")
            return False
        try:
            with _force_ipv4_resolution():
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text},
                    timeout=12,
                )
            if resp.status_code != 200:
                logger.error("telegram send failed: status=%s body=%s", resp.status_code, resp.text)
                return False
            logger.info("telegram alert sent")
            return True
        except Exception as exc:
            logger.error("telegram send exception: %s", exc)
            return False
