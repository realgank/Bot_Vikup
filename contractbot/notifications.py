"""Notification dataclasses."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class OcrResult:
    """Represents OCR output for a specific named box."""

    box_name: str
    coordinates: Tuple[int, int, int, int]
    recognized_text: str
    image_path: Optional[str] = None


@dataclass
class ContractNotification:
    contract_id: int
    player_name: str
    system: str
    est_total: float
    bisk_credited: float
    discord_user_id: Optional[int]
    ocr_results: Sequence[OcrResult] = dataclasses.field(default_factory=tuple)
    screenshot_path: Optional[str] = None
