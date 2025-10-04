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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER REFERENCES contracts(id) ON DELETE CASCADE,
                    box_name TEXT,
                    box_left INTEGER,
                    box_top INTEGER,
                    box_right INTEGER,
                    box_bottom INTEGER,
                    recognized_text TEXT,
                    confirmed_text TEXT,
                    status TEXT DEFAULT 'pending',
                    image_path TEXT,
                    reviewed_by INTEGER,
                    reviewed_by_name TEXT,
                    reviewed_at TIMESTAMP,
                    needs_training INTEGER DEFAULT 0,
                    UNIQUE(contract_id, box_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_training_words (
                    word TEXT PRIMARY KEY,
                    trained INTEGER DEFAULT 0
                )
                """
            )

    def close(self) -> None:
        self._connection.close()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> Optional[str]:
        cur = self._connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )
        row = cur.fetchone()
        if row:
            return row["value"]
        return None

    def set_setting(self, key: str, value: Optional[str]) -> None:
        with self._connection as conn:
            if value is None:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    """
                    INSERT INTO settings(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )

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

    # ------------------------------------------------------------------
    # OCR feedback and training utilities
    # ------------------------------------------------------------------

    def store_ocr_sample(
        self,
        contract_id: int,
        box_name: str,
        box: Sequence[int],
        recognized_text: str,
        image_path: Optional[str],
    ) -> None:
        if len(box) < 4:
            logging.warning(
                "Skipping OCR sample persistence for '%s' – invalid box %s",
                box_name,
                box,
            )
            return
        box_values = tuple(int(value) for value in box[:4])
        with self._connection as conn:
            conn.execute(
                """
                INSERT INTO ocr_samples(
                    contract_id,
                    box_name,
                    box_left,
                    box_top,
                    box_right,
                    box_bottom,
                    recognized_text,
                    image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, box_name) DO UPDATE SET
                    box_left = excluded.box_left,
                    box_top = excluded.box_top,
                    box_right = excluded.box_right,
                    box_bottom = excluded.box_bottom,
                    recognized_text = excluded.recognized_text,
                    image_path = excluded.image_path
                """,
                (
                    contract_id,
                    box_name,
                    box_values[0],
                    box_values[1],
                    box_values[2],
                    box_values[3],
                    recognized_text,
                    image_path,
                ),
            )

    def get_ocr_sample(self, contract_id: int, box_name: str) -> Optional[dict]:
        cur = self._connection.execute(
            """
            SELECT box_name, recognized_text, confirmed_text, status
            FROM ocr_samples
            WHERE contract_id = ? AND box_name = ?
            """,
            (contract_id, box_name),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "box_name": row["box_name"],
            "recognized_text": row["recognized_text"] or "",
            "confirmed_text": row["confirmed_text"] or "",
            "status": row["status"],
        }

    def confirm_ocr_contract(
        self, contract_id: int, reviewer_id: int, reviewer_name: str
    ) -> Sequence[Tuple[str, str]]:
        with self._connection as conn:
            conn.execute(
                """
                UPDATE ocr_samples
                SET confirmed_text = COALESCE(confirmed_text, recognized_text),
                    status = CASE
                        WHEN status = 'corrected' THEN status
                        ELSE 'confirmed'
                    END,
                    reviewed_by = ?,
                    reviewed_by_name = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    needs_training = 1
                WHERE contract_id = ?
                """,
                (reviewer_id, reviewer_name, contract_id),
            )
            cur = conn.execute(
                """
                SELECT box_name, COALESCE(confirmed_text, '') AS final_text
                FROM ocr_samples
                WHERE contract_id = ?
                """,
                (contract_id,),
            )
            rows = cur.fetchall()
        return [(row["box_name"], row["final_text"]) for row in rows]

    def correct_ocr_sample(
        self,
        contract_id: int,
        box_name: str,
        corrected_text: str,
        reviewer_id: int,
        reviewer_name: str,
    ) -> Optional[str]:
        cur = self._connection.execute(
            """
            SELECT id FROM ocr_samples WHERE contract_id = ? AND box_name = ?
            """,
            (contract_id, box_name),
        )
        row = cur.fetchone()
        if row is None:
            return None
        with self._connection as conn:
            conn.execute(
                """
                UPDATE ocr_samples
                SET confirmed_text = ?,
                    status = 'corrected',
                    reviewed_by = ?,
                    reviewed_by_name = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    needs_training = 1
                WHERE contract_id = ? AND box_name = ?
                """,
                (
                    corrected_text,
                    reviewer_id,
                    reviewer_name,
                    contract_id,
                    box_name,
                ),
            )
            cur = conn.execute(
                """
                SELECT COALESCE(confirmed_text, '') AS final_text
                FROM ocr_samples
                WHERE contract_id = ? AND box_name = ?
                """,
                (contract_id, box_name),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return row["final_text"]

    def queue_training_words(self, words: Sequence[str]) -> None:
        if not words:
            return
        with self._connection as conn:
            for word in words:
                normalized = word.strip()
                if not normalized:
                    continue
                conn.execute(
                    """
                    INSERT INTO ocr_training_words(word, trained)
                    VALUES(?, 0)
                    ON CONFLICT(word) DO UPDATE SET trained = 0
                    """,
                    (normalized,),
                )

    def consume_training_words(self) -> Sequence[str]:
        with self._connection as conn:
            cur = conn.execute(
                "SELECT word FROM ocr_training_words WHERE trained = 0"
            )
            words = [row["word"] for row in cur.fetchall()]
            if words:
                conn.executemany(
                    "UPDATE ocr_training_words SET trained = 1 WHERE word = ?",
                    [(word,) for word in words],
                )
        return words
