"""Application runner wiring all components together."""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Sequence

from .adb import ADBClient
from .buyback import BuybackManager
from .config import Config
from .database import Database
from .notifications import ContractNotification
from .ocr import OcrEngine
from .parsing import CompositionParser
from .processor import ContractProcessor


class ContractBotApplication:
    def __init__(self, config: Config):
        self.config = config
        self.db = Database(config.db_path)
        self.buyback_manager = BuybackManager(config.buyback_percent)
        self.parser = CompositionParser()

    def run(self) -> None:
        logging.info("ContractBot service starting")
        adb_serial = self._ensure_adb_serial()
        adb_client = ADBClient(adb_serial)
        ocr_engine = OcrEngine(self.config.ocr_lang, self.config.tesseract_cmd)

        from . import discord_bot

        has_discord = (
            self.config.discord.token
            and getattr(discord_bot, "discord", None) is not None
        )

        if has_discord:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            notification_queue: "asyncio.Queue[ContractNotification]" = asyncio.Queue()

            def notify(notification: ContractNotification) -> None:
                loop.call_soon_threadsafe(notification_queue.put_nowait, notification)

            processor = ContractProcessor(
                adb_client,
                ocr_engine,
                self.db,
                self.parser,
                self.buyback_manager,
                self.config,
                notification_callback=notify,
            )

            processor_thread = threading.Thread(
                target=processor.run_forever, daemon=True
            )
            processor_thread.start()

            bot = discord_bot.DiscordContractBot(
                db=self.db,
                buyback_manager=self.buyback_manager,
                discord_config=self.config.discord,
                notification_queue=notification_queue,
            )

            try:
                loop.run_until_complete(bot.start(self.config.discord.token))
            except KeyboardInterrupt:
                logging.info(
                    "Keyboard interrupt received, shutting down Discord bot"
                )
            finally:
                processor.stop()
                processor_thread.join(timeout=5)
                loop.run_until_complete(bot.close())
                loop.close()
        else:
            if self.config.discord.token and getattr(discord_bot, "discord", None) is None:
                logging.warning(
                    "Discord token provided but discord.py is not installed – running without Discord integration"
                )
            else:
                logging.info(
                    "Discord token not provided – running without Discord integration"
                )

            processor = ContractProcessor(
                adb_client,
                ocr_engine,
                self.db,
                self.parser,
                self.buyback_manager,
                self.config,
                notification_callback=lambda notification: logging.info(
                    "Contract #%s recorded (player: %s, system: %s)",
                    notification.contract_id,
                    notification.player_name,
                    notification.system,
                ),
            )
            try:
                processor.run_forever()
            except KeyboardInterrupt:
                logging.info("Keyboard interrupt received, stopping service")

    def _ensure_adb_serial(self) -> str:
        serial = self.config.adb_serial
        if serial and serial != "auto":
            return serial
        devices = ADBClient.list_devices()
        serial = ADBClient.prompt_for_device(devices)
        self.config.adb_serial = serial
        self.config.persist()
        return serial


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    argv = list(argv or [])
    config_path = Path("config.json")
    if argv:
        config_path = Path(argv[0])
    if not config_path.exists():
        logging.error("Configuration file %s not found", config_path)
        return 1
    config = Config.load(config_path)
    app = ContractBotApplication(config)
    app.run()
    return 0
