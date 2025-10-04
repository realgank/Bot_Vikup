"""Configuration management for ContractBot."""
from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .utils import optional_int


@dataclass
class DiscordConfig:
    """Discord integration configuration."""

    token: str = ""
    guild_id: Optional[int] = None
    admin_role_name: Optional[str] = None
    admin_user_ids: Sequence[int] = dataclasses.field(default_factory=tuple)
    contracts_channel_id: Optional[int] = None
    public_command_replies: bool = False


@dataclass
class Config:
    """Runtime configuration for the ContractBot application."""

    adb_serial: str = "auto"
    db_path: Path = Path("contract_bot.sqlite")
    tesseract_cmd: Optional[str] = None
    ocr_lang: str = "eng"
    poll_interval_sec: float = 30.0
    cooldown_after_contract_sec: float = 5.0
    buyback_percent: float = 100.0
    ui: Dict[str, Sequence[Dict[str, Any]]] = dataclasses.field(default_factory=dict)
    ocr_boxes: Dict[str, Sequence[int]] = dataclasses.field(default_factory=dict)
    discord: DiscordConfig = dataclasses.field(default_factory=DiscordConfig)
    config_path: Path = Path("config.json")

    @staticmethod
    def load(path: Path) -> "Config":
        """Load configuration from ``path``."""

        logging.debug("Loading configuration from %s", path)
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        discord_raw = raw.get("discord", {})
        config = Config(
            adb_serial=raw.get("adb", {}).get("serial", "auto"),
            db_path=Path(raw.get("db_path", "contract_bot.sqlite")),
            tesseract_cmd=raw.get("tesseract_cmd"),
            ocr_lang=raw.get("ocr_lang", "eng"),
            poll_interval_sec=float(raw.get("poll_interval_sec", 30.0)),
            cooldown_after_contract_sec=float(
                raw.get("cooldown_after_contract_sec", 5.0)
            ),
            buyback_percent=float(raw.get("buyback_percent", 100.0)),
            ui=raw.get("ui", {}),
            ocr_boxes=raw.get("ocr_boxes", {}),
            discord=DiscordConfig(
                token=discord_raw.get("discord_token", ""),
                guild_id=optional_int(discord_raw.get("guild_id")),
                admin_role_name=discord_raw.get("admin_role_name"),
                admin_user_ids=tuple(discord_raw.get("admin_user_ids", [])),
                contracts_channel_id=optional_int(
                    discord_raw.get("contracts_channel_id")
                ),
                public_command_replies=bool(
                    discord_raw.get("public_command_replies", False)
                ),
            ),
            config_path=path,
        )
        return config

    def persist(self) -> None:
        """Persist the configuration back to :attr:`config_path`."""

        logging.debug("Persisting configuration to %s", self.config_path)
        base: Dict[str, Any] = {
            "adb": {"serial": self.adb_serial},
            "db_path": str(self.db_path),
            "tesseract_cmd": self.tesseract_cmd,
            "ocr_lang": self.ocr_lang,
            "poll_interval_sec": self.poll_interval_sec,
            "cooldown_after_contract_sec": self.cooldown_after_contract_sec,
            "buyback_percent": self.buyback_percent,
            "ui": self.ui,
            "ocr_boxes": self.ocr_boxes,
            "discord": {
                "discord_token": self.discord.token,
                "guild_id": self.discord.guild_id,
                "admin_role_name": self.discord.admin_role_name,
                "admin_user_ids": list(self.discord.admin_user_ids),
                "contracts_channel_id": self.discord.contracts_channel_id,
                "public_command_replies": self.discord.public_command_replies,
            },
        }
        with self.config_path.open("w", encoding="utf-8") as fh:
            json.dump(base, fh, indent=2, ensure_ascii=False)
