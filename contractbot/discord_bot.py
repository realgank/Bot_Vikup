"""Discord bot integration for ContractBot."""
from __future__ import annotations

import asyncio
import logging

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
