"""Discord bot integration for ContractBot."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Iterable, List, Optional

try:  # pragma: no cover - optional dependency guards
    import discord
    from discord import app_commands
    from discord.ext import commands
except ImportError:  # pragma: no cover - runtime guard
    discord = None  # type: ignore[assignment]
    app_commands = None  # type: ignore[assignment]
    commands = None  # type: ignore[assignment]

from .buyback import BuybackManager
from .config import DiscordConfig
from .database import Database
from .notifications import ContractNotification


if commands is None:  # pragma: no cover - runtime guard

    class DiscordContractBot:  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - simple proxy
            raise RuntimeError(
                "discord.py is not installed – DiscordContractBot cannot be used"
            )

else:

    class DiscordContractBot(commands.Bot):  # type: ignore[misc]
        def __init__(
            self,
            db: Database,
            buyback_manager: BuybackManager,
            discord_config: DiscordConfig,
            notification_queue: "asyncio.Queue[ContractNotification]",
        ) -> None:
            intents = discord.Intents.none()
            intents.guilds = True
            intents.members = True
            super().__init__(command_prefix="!", intents=intents)
            self.db = db
            self.buyback_manager = buyback_manager
            self.discord_config = discord_config
            self.notification_queue = notification_queue
            self.tree = app_commands.CommandTree(self)
            self.public_replies = discord_config.public_command_replies
            self.contracts_channel_id = discord_config.contracts_channel_id
            self.guild_id = discord_config.guild_id
            self.admin_channel_id = self._load_admin_channel_id()
            self._register_commands()

        async def setup_hook(self) -> None:
            try:
                if self.guild_id:
                    guild = discord.Object(id=self.guild_id)
                    await self.tree.sync(guild=guild)
                    logging.info("Synced slash commands to guild %s", self.guild_id)
                else:
                    await self.tree.sync()
                    logging.info("Synced global slash commands")
            except Exception:
                logging.exception(
                    "Failed to sync guild-specific commands; falling back to global"
                )
                await self.tree.sync()

            self.loop.create_task(self._notification_worker())

        # ------------------------------------------------------------------
        # Slash commands
        # ------------------------------------------------------------------

        def _register_commands(self) -> None:
            @self.tree.command(description="Register your in-game nickname")
            async def register(interaction: discord.Interaction, game_nick: str) -> None:
                await self._ensure_response(interaction)
                user_id = self.db.get_or_create_user(
                    discord_id=interaction.user.id,
                    display_name=str(interaction.user),
                )
                self.db.link_character(user_id, game_nick)
                await interaction.followup.send(
                    f"Nickname **{game_nick}** linked to your account.",
                    ephemeral=not self.public_replies,
                )

            @self.tree.command(description="Show your BISK balance")
            async def balance(interaction: discord.Interaction) -> None:
                await self._ensure_response(interaction)
                user_id = self.db.get_or_create_user(
                    discord_id=interaction.user.id,
                    display_name=str(interaction.user),
                )
                balance_value = self.db.calculate_balance(user_id)
                await interaction.followup.send(
                    f"Your current balance: **{balance_value:.2f} BISK**.",
                    ephemeral=not self.public_replies,
                )

            @self.tree.command(description="Update current buyback percent")
            @app_commands.describe(percent="New buyback percentage value")
            async def set_buyback(
                interaction: discord.Interaction, percent: float
            ) -> None:
                await self._ensure_response(interaction)
                if not await self._is_admin(interaction):
                    await interaction.followup.send(
                        "You do not have permission to change the buyback percent.",
                        ephemeral=True,
                    )
                    return
                self.buyback_manager.set_percent(percent)
                await interaction.followup.send(
                    f"Buyback percent updated to {percent:.2f}%.",
                    ephemeral=not self.public_replies,
                )

            @self.tree.command(description="Назначить канал подтверждения контрактов")
            @app_commands.describe(channel="Канал для проверки OCR администраторами")
            async def set_admin_channel(
                interaction: discord.Interaction, channel: discord.TextChannel
            ) -> None:
                await self._ensure_response(interaction)
                if not await self._is_admin(interaction):
                    await interaction.followup.send(
                        "У вас нет прав для изменения канала администратора.",
                        ephemeral=True,
                    )
                    return
                self.admin_channel_id = channel.id
                self.db.set_setting("discord_admin_channel_id", str(channel.id))
                await interaction.followup.send(
                    f"Канал администратора установлен: {channel.mention}",
                    ephemeral=not self.public_replies,
                )

            @self.tree.command(description="Подтвердить OCR данные контракта")
            @app_commands.describe(contract_id="Идентификатор контракта")
            async def ocr_confirm(
                interaction: discord.Interaction, contract_id: int
            ) -> None:
                await self._ensure_response(interaction)
                if not await self._is_admin(interaction):
                    await interaction.followup.send(
                        "Только администратор может подтверждать OCR.",
                        ephemeral=True,
                    )
                    return
                samples = self.db.confirm_ocr_contract(
                    contract_id,
                    reviewer_id=interaction.user.id,
                    reviewer_name=str(interaction.user),
                )
                if not samples:
                    await interaction.followup.send(
                        "Для указанного контракта нет OCR данных.",
                        ephemeral=True,
                    )
                    return
                words = self._extract_training_words(
                    final_text for _, final_text in samples
                )
                self.db.queue_training_words(words)
                await interaction.followup.send(
                    f"OCR данные для контракта #{contract_id} подтверждены.",
                    ephemeral=not self.public_replies,
                )

            @self.tree.command(description="Исправить распознанный OCR текст")
            @app_commands.describe(
                contract_id="Идентификатор контракта",
                field="Название OCR области",
                corrected_text="Исправленный текст",
            )
            async def ocr_correct(
                interaction: discord.Interaction,
                contract_id: int,
                field: str,
                corrected_text: str,
            ) -> None:
                await self._ensure_response(interaction)
                if not await self._is_admin(interaction):
                    await interaction.followup.send(
                        "Только администратор может исправлять OCR.",
                        ephemeral=True,
                    )
                    return
                sample = self.db.get_ocr_sample(contract_id, field)
                if sample is None:
                    await interaction.followup.send(
                        "Не удалось найти указанную область OCR для этого контракта.",
                        ephemeral=True,
                    )
                    return
                final_text = self.db.correct_ocr_sample(
                    contract_id,
                    field,
                    corrected_text,
                    reviewer_id=interaction.user.id,
                    reviewer_name=str(interaction.user),
                )
                if final_text is None:
                    await interaction.followup.send(
                        "Не удалось сохранить исправление OCR.",
                        ephemeral=True,
                    )
                    return
                words = self._extract_training_words([final_text])
                self.db.queue_training_words(words)
                await interaction.followup.send(
                    (
                        "Исправление сохранено."
                        f" Было: `{sample['recognized_text']}`; стало: `{final_text}`."
                    ),
                    ephemeral=not self.public_replies,
                )

        async def _ensure_response(self, interaction: discord.Interaction) -> None:
            if interaction.response.is_done():
                return
            await interaction.response.defer(ephemeral=not self.public_replies)

        async def _is_admin(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id in self.discord_config.admin_user_ids:
                return True
            if self.discord_config.admin_role_name and isinstance(
                interaction.user, discord.Member
            ):
                for role in interaction.user.roles:
                    if role.name == self.discord_config.admin_role_name:
                        return True
            return False

        async def _notification_worker(self) -> None:
            while True:
                notification = await self.notification_queue.get()
                try:
                    await self._handle_notification(notification)
                except Exception:
                    logging.exception("Failed to send contract notification")

        async def _handle_notification(
            self, notification: ContractNotification
        ) -> None:
            if self.contracts_channel_id is None:
                logging.info(
                    "Discord notification suppressed (contracts_channel_id not configured)"
                )
                return
            channel = self.get_channel(self.contracts_channel_id)
            if channel is None:
                logging.warning(
                    "Discord channel %s not found", self.contracts_channel_id
                )
                return
            mention = (
                f" <@{notification.discord_user_id}>"
                if notification.discord_user_id
                else ""
            )
            message = (
                f"Создан контракт #{notification.contract_id} на игровое имя {notification.player_name}"
                f" (система: {notification.system}). Оценка: {notification.est_total:.2f},"
                f" зачтено в BISK: {notification.bisk_credited:.2f}.{mention}"
            )
            await channel.send(message)
            await self._send_admin_notification(notification)

        async def _send_admin_notification(
            self, notification: ContractNotification
        ) -> None:
            if self.admin_channel_id is None:
                return
            channel = await self._resolve_text_channel(self.admin_channel_id)
            if channel is None:
                logging.warning(
                    "Discord admin channel %s not found", self.admin_channel_id
                )
                return

            lines = [
                f"Контракт #{notification.contract_id} для {notification.player_name} (система {notification.system}).",
                "Проверьте результаты OCR и подтвердите через /ocr_confirm или исправьте через /ocr_correct.",
                "Распознанные области:",
            ]
            for result in notification.ocr_results:
                coords = ", ".join(str(value) for value in result.coordinates)
                text = result.recognized_text or "<пусто>"
                lines.append(
                    f"• {result.box_name}: `{text}` (box: [{coords}])"
                )
            if not notification.ocr_results:
                lines.append("• Нет сохранённых OCR результатов")

            files: List[discord.File] = []
            handles: List = []
            try:
                if notification.screenshot_path:
                    screenshot_path = Path(notification.screenshot_path)
                    if screenshot_path.exists():
                        handle = screenshot_path.open("rb")
                        handles.append(handle)
                        files.append(
                            discord.File(
                                handle, filename=screenshot_path.name, spoiler=False
                            )
                        )
                for result in notification.ocr_results:
                    if not result.image_path:
                        continue
                    crop_path = Path(result.image_path)
                    if not crop_path.exists():
                        continue
                    handle = crop_path.open("rb")
                    handles.append(handle)
                    files.append(
                        discord.File(handle, filename=f"{notification.contract_id}_{crop_path.name}")
                    )
                await channel.send("\n".join(lines), files=files)
            finally:
                for handle in handles:
                    handle.close()

        async def _resolve_text_channel(
            self, channel_id: Optional[int]
        ) -> Optional[discord.TextChannel]:
            if channel_id is None:
                return None
            channel = self.get_channel(channel_id)
            if channel is not None and isinstance(channel, discord.TextChannel):
                return channel
            try:
                fetched = await self.fetch_channel(channel_id)
            except Exception:
                logging.exception("Failed to fetch channel %s", channel_id)
                return None
            if isinstance(fetched, discord.TextChannel):
                return fetched
            return None

        def _load_admin_channel_id(self) -> Optional[int]:
            stored = self.db.get_setting("discord_admin_channel_id")
            if not stored:
                return None
            try:
                return int(stored)
            except (TypeError, ValueError):
                logging.warning("Invalid admin channel id stored in settings: %s", stored)
                return None

        def _extract_training_words(
            self, texts: Iterable[str]
        ) -> List[str]:
            words: List[str] = []
            for text in texts:
                words.extend(re.findall(r"[\w\-']+", text, re.UNICODE))
            return words
