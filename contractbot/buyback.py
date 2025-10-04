"""Thread-safe holder for the current buyback percent."""
from __future__ import annotations

import logging
import threading


class BuybackManager:
    def __init__(self, initial_percent: float):
        self._percent = float(initial_percent)
        self._lock = threading.Lock()

    @property
    def percent(self) -> float:
        with self._lock:
            return self._percent

    def set_percent(self, value: float) -> None:
        with self._lock:
            self._percent = float(value)
        logging.info("Buyback percent updated to %.2f%%", value)
