"""Notification dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ContractNotification:
    contract_id: int
    player_name: str
    system: str
    est_total: float
    bisk_credited: float
    discord_user_id: Optional[int]
