"""SQLite state store for trader runtime state."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STATE_DIR / "trader_state.db"


class StateStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL,
                    reason TEXT,
                    snapshot_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_id TEXT,
                    client_id TEXT,
                    price REAL,
                    size REAL,
                    status TEXT,
                    payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    side TEXT,
                    entry_price REAL,
                    size REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT NOT NULL,
                    source_order_id TEXT,
                    opened_at DATETIME,
                    closed_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    meta_json TEXT
                );

                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def record_signal(self, symbol: str, action: str, confidence: float | None, reason: str, snapshot: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO signals(symbol, action, confidence, reason, snapshot_json) VALUES(?,?,?,?,?)",
                (symbol, action, confidence, reason, json.dumps(snapshot, ensure_ascii=False)),
            )

    def record_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        order_id: str | None,
        client_id: str | None,
        price: float | None,
        size: float | None,
        status: str,
        payload: Dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO orders(symbol, order_type, side, order_id, client_id, price, size, status, payload_json)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    symbol,
                    order_type,
                    side,
                    order_id,
                    client_id,
                    price,
                    size,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def update_order_status(self, order_id: str, status: str, payload: Dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE orders SET status=?, payload_json=COALESCE(?, payload_json), updated_at=CURRENT_TIMESTAMP WHERE order_id=?",
                (status, json.dumps(payload, ensure_ascii=False) if payload is not None else None, order_id),
            )

    def upsert_position(
        self,
        symbol: str,
        side: str | None,
        entry_price: float | None,
        size: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        status: str,
        source_order_id: str | None = None,
        opened_at: str | None = None,
        closed_at: str | None = None,
        meta: Dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO positions(symbol, side, entry_price, size, stop_loss, take_profit, status, source_order_id, opened_at, closed_at, meta_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET
                  side=excluded.side,
                  entry_price=excluded.entry_price,
                  size=excluded.size,
                  stop_loss=excluded.stop_loss,
                  take_profit=excluded.take_profit,
                  status=excluded.status,
                  source_order_id=excluded.source_order_id,
                  opened_at=COALESCE(excluded.opened_at, positions.opened_at),
                  closed_at=excluded.closed_at,
                  meta_json=excluded.meta_json,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    symbol,
                    side,
                    entry_price,
                    size,
                    stop_loss,
                    take_profit,
                    status,
                    source_order_id,
                    opened_at,
                    closed_at,
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )

    def get_open_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE symbol=? AND status IN ('OPEN','RISK','UNPROTECTED') ORDER BY updated_at DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return dict(row) if row else None

    def get_open_positions(self) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status IN ('OPEN','RISK','UNPROTECTED') ORDER BY symbol"
            ).fetchall()
            return [dict(r) for r in rows]

    def record_event(self, level: str, event_type: str, message: str, payload: Dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO system_events(level, event_type, message, payload_json) VALUES(?,?,?,?)",
                (level, event_type, message, json.dumps(payload or {}, ensure_ascii=False)),
            )

    def set_runtime_value(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runtime_state(key, value_json) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def get_runtime_value(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value_json FROM runtime_state WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row[0])
            except Exception:
                return default

    def get_known_order_ids(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT order_id FROM orders WHERE order_id IS NOT NULL AND order_id != ''").fetchall()
            return {r[0] for r in rows if r[0]}

    def close_position(self, symbol: str, closed_at: str | None = None, meta: Dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE positions SET status='CLOSED', closed_at=COALESCE(?, CURRENT_TIMESTAMP), meta_json=?, updated_at=CURRENT_TIMESTAMP WHERE symbol=?",
                (closed_at, json.dumps(meta or {}, ensure_ascii=False), symbol),
            )

    def get_orders_for_symbol(self, symbol: str, order_type: str | None = None) -> list[Dict[str, Any]]:
        with self.connect() as conn:
            if order_type:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE symbol=? AND order_type=? ORDER BY created_at DESC",
                    (symbol, order_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE symbol=? ORDER BY created_at DESC",
                    (symbol,),
                ).fetchall()
            return [dict(r) for r in rows]
