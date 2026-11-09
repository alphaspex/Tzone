import asyncio
import logging

import discord
from discord.ext import commands

from .discord_commands import register_commands
from .nickname_queue import NicknameQueue
from .schedules import ScheduleStore


log = logging.getLogger("tzone.bot")


class TzoneBot(commands.Bot):
    def __init__(self, settings, db):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=settings.discord_application_id,
        )
        self.settings = settings
        self.db = db
        self.schedule_store = ScheduleStore(db)
        self.nickname_queue = NicknameQueue(
            db,
            updates_per_second=settings.nickname_updates_per_second,
            max_attempts=settings.nickname_max_attempts,
        )
        self.wizard_drafts = {}
        self.scheduler_task = None
        register_commands(self, self.schedule_store, self.wizard_drafts)

    async def setup_hook(self):
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s commands to guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global application commands", len(synced))
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def on_ready(self):
        log.info("Tzone connected as %s", self.user)

    async def _scheduler_loop(self):
        while not self.is_closed():
            for guild in self.guilds:
                try:
                    timezone_rows = await self.schedule_store.get_guild_timezones(
                        str(guild.id)
                    )
                    if timezone_rows:
                        result = await self.nickname_queue.run_guild(
                            guild,
                            timezone_rows,
                            window_minutes=self.settings.nickname_window_minutes,
                        )
                        if result["checked"]:
                            log.info("Guild %s nickname cycle: %s", guild.id, result)
                except Exception:
                    log.exception("Hourly nickname scheduler failed for guild %s", guild.id)
            await asyncio.sleep(30)

    async def close(self):
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        await super().close()
