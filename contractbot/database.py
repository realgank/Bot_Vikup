"""SQLite persistence utilities for ContractBot."""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .parsing import ContractItem


class Database:
    """Encapsulate the SQLite schema and business operations."""

    def __init__(self, path: Path):
        self.path = path
        self._connection_lock = threading.Lock()
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        logging.info("Ensuring database schema")
        with self._connection as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id INTEGER UNIQUE,
                    display_name TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    game_nick TEXT UNIQUE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    system TEXT,
                    player_name TEXT,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    buyback_percent REAL,
                    est_total REAL,
                    bisk_credited REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER REFERENCES contracts(id) ON DELETE CASCADE,
                    item_name TEXT,
                    qty REAL,
                    est_value REAL,
                    UNIQUE(contract_id, item_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    system TEXT,
                    item_name TEXT,
                    qty REAL,
                    PRIMARY KEY(system, item_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payouts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    amount REAL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            for column in ("buyback_percent", "est_total", "bisk_credited"):
                try:
                    conn.execute(f"SELECT {column} FROM contracts LIMIT 1")
                except sqlite3.OperationalError:
                    conn.execute(
                        f"ALTER TABLE contracts ADD COLUMN {column} REAL"
                    )

    def close(self) -> None:
        self._connection.close()

    # ------------------------------------------------------------------
    # User / character utilities
    # ------------------------------------------------------------------

    def get_or_create_user(self, discord_id: int, display_name: str) -> int:
        with self._connection as conn:
            cur = conn.execute(
                "SELECT id FROM users WHERE discord_id = ?",
                (discord_id,),
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO users(discord_id, display_name) VALUES (?, ?)",
                (discord_id, display_name),
            )
            return int(cur.lastrowid)

    def link_character(self, user_id: int, game_nick: str) -> None:
        with self._connection as conn:
            cur = conn.execute(
                "SELECT id FROM characters WHERE game_nick = ?",
                (game_nick,),
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE characters SET user_id = ? WHERE id = ?",
                    (user_id, row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO characters(user_id, game_nick) VALUES (?, ?)",
                    (user_id, game_nick),
                )
            conn.execute(
                "UPDATE contracts SET user_id = ? WHERE player_name = ? AND user_id IS NULL",
                (user_id, game_nick),
            )

    def get_user_by_character(self, game_nick: str) -> Optional[int]:
        cur = self._connection.execute(
            "SELECT user_id FROM characters WHERE game_nick = ?",
            (game_nick,),
        )
        row = cur.fetchone()
        if row and row["user_id"] is not None:
            return int(row["user_id"])
        return None

    def calculate_balance(self, user_id: int) -> float:
        cur = self._connection.execute(
            "SELECT COALESCE(SUM(bisk_credited), 0) AS total FROM contracts WHERE user_id = ?",
            (user_id,),
        )
        contracts_total = float(cur.fetchone()["total"])
        cur = self._connection.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payouts WHERE user_id = ?",
            (user_id,),
        )
        payouts_total = float(cur.fetchone()["total"])
        return contracts_total - payouts_total

    # ------------------------------------------------------------------
    # Contract persistence
    # ------------------------------------------------------------------

    def record_contract(
        self,
        system: str,
        player_name: str,
        buyback_percent: float,
        items: Sequence[ContractItem],
        user_id: Optional[int],
    ) -> Tuple[int, float, float]:
        est_total = sum(item.est_value for item in items)
        bisk_credited = est_total * (buyback_percent / 100.0)
        logging.info(
            "Recording contract for player '%s' (system: %s) – est_total=%.2f, bisk=%.2f",
            player_name,
            system,
            est_total,
            bisk_credited,
        )
        with self._connection as conn:
            cur = conn.execute(
                """
                INSERT INTO contracts(system, player_name, user_id, buyback_percent, est_total, bisk_credited)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (system, player_name, user_id, buyback_percent, est_total, bisk_credited),
            )
            contract_id = int(cur.lastrowid)
            for item in items:
                conn.execute(
                    """
                    INSERT INTO contract_items(contract_id, item_name, qty, est_value)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(contract_id, item_name) DO UPDATE SET
                        qty = excluded.qty,
                        est_value = excluded.est_value
                    """,
                    (contract_id, item.item_name, item.quantity, item.est_value),
                )
                conn.execute(
                    """
                    INSERT INTO inventory(system, item_name, qty)
                    VALUES (?, ?, ?)
                    ON CONFLICT(system, item_name) DO UPDATE SET
                        qty = qty + excluded.qty
                    """,
                    (system, item.item_name, item.quantity),
                )
        return contract_id, est_total, bisk_credited
