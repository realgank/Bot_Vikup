"""Automation loop that processes contracts."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from .adb import ADBClient
from .buyback import BuybackManager
from .config import Config
from .database import Database
from .notifications import ContractNotification
from .ocr import OcrEngine
from .parsing import CompositionParser, extract_nick, extract_system


class ContractProcessor:
    def __init__(
        self,
        adb: ADBClient,
        ocr: OcrEngine,
        db: Database,
        parser: CompositionParser,
        buyback_manager: BuybackManager,
        config: Config,
        notification_callback: Optional[Any] = None,
    ) -> None:
        self.adb = adb
        self.ocr = ocr
        self.db = db
        self.parser = parser
        self.buyback_manager = buyback_manager
        self.config = config
        self.notification_callback = notification_callback
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        logging.info("Starting contract processing loop")
        poll_interval = self.config.poll_interval_sec
        cooldown = self.config.cooldown_after_contract_sec
        while not self._stop_event.is_set():
            try:
                self._process_cycle(poll_interval, cooldown)
            except Exception:
                logging.exception("Unexpected error in contract processing loop")
                time.sleep(poll_interval)

    def _process_cycle(self, poll_interval: float, cooldown: float) -> None:
        self.adb.execute_steps(self.config.ui.get("open_contracts_steps", []))
        screenshot = self.adb.screencap()
        if screenshot is None:
            logging.error("Failed to obtain screenshot – skipping cycle")
            return
        has_contract = self.ocr.extract_any_text(
            screenshot,
            "contracts_marker",
            self.config.ocr_boxes,
        )
        if not has_contract:
            logging.info("No contract detected; closing window and sleeping")
            self.adb.execute_steps(
                self.config.ui.get("close_contracts_window", [])
            )
            time.sleep(poll_interval)
            return

        logging.info("Contract marker detected – processing first contract")
        self.adb.execute_steps(self.config.ui.get("first_contract_tap", []))

        system_text = self.ocr.extract_text(
            screenshot, "system", self.config.ocr_boxes
        )
        player_text = self.ocr.extract_text(
            screenshot, "player_name", self.config.ocr_boxes
        )
        game_time_text = self.ocr.extract_text(
            screenshot, "game_time", self.config.ocr_boxes
        )
        logging.info(
            "OCR extracted system='%s', player='%s', time='%s'",
            system_text,
            player_text,
            game_time_text,
        )

        system_name = extract_system(system_text)
        player_name = extract_nick(player_text)
        logging.debug(
            "Normalised system='%s', player='%s'", system_name, player_name
        )

        self.adb.execute_steps(self.config.ui.get("swipe_to_composition", []))
        self.adb.execute_steps(self.config.ui.get("composition_fixed_tap", []))
        copy_sequence = self.config.ui.get("copy_sequence", [])
        if copy_sequence:
            self.adb.execute_steps(copy_sequence)
        time.sleep(4)

        host_clipboard = self.parser.read_host_clipboard()
        android_clipboard = self.adb.read_android_clipboard()

        items = None
        if copy_sequence:
            items = self.parser.parse_clipboards(
                android_clipboard, host_clipboard
            )

        if not items:
            screenshot = self.adb.screencap()
            if screenshot:
                ocr_text = self.ocr.extract_table(
                    screenshot,
                    "composition_table",
                    self.config.ocr_boxes,
                    psm=6,
                )
                items = self.parser.parse_from_ocr(ocr_text)

        if not items:
            logging.warning(
                "Failed to parse composition; skipping contract acceptance"
            )
            self.adb.execute_steps(self.config.ui.get("close_contract_card", []))
            self.adb.execute_steps(self.config.ui.get("close_contracts_window", []))
            time.sleep(poll_interval)
            return

        buyback_percent = self.buyback_manager.percent
        user_id = self.db.get_user_by_character(player_name)
        contract_id, est_total, bisk_credited = self.db.record_contract(
            system=system_name,
            player_name=player_name,
            buyback_percent=buyback_percent,
            items=items,
            user_id=user_id,
        )

        self.adb.execute_steps(self.config.ui.get("close_contract_card", []))
        self.adb.execute_steps(self.config.ui.get("accept_contract", []))
        self.adb.execute_steps(self.config.ui.get("close_contracts_window", []))
        logging.info(
            "Completed contract #%s processing, entering cooldown", contract_id
        )
        time.sleep(cooldown)

        if self.notification_callback:
            try:
                self.notification_callback(
                    ContractNotification(
                        contract_id=contract_id,
                        player_name=player_name,
                        system=system_name,
                        est_total=est_total,
                        bisk_credited=bisk_credited,
                        discord_user_id=self._resolve_discord_id(user_id),
                    )
                )
            except Exception:
                logging.exception("Notification callback failed")

    def _resolve_discord_id(self, user_id: Optional[int]) -> Optional[int]:
        if user_id is None:
            return None
        cur = self.db._connection.execute(  # using internal connection intentionally
            "SELECT discord_id FROM users WHERE id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if row and row["discord_id"]:
            return int(row["discord_id"])
        return None
