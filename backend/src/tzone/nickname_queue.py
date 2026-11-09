import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

import discord

from .d1 import D1Client


class NicknameQueue:
    """DB-backed queue; Discord edit callback is injected as the I/O boundary."""

    def __init__(self, db: D1Client, updates_per_second: float = 40.0, max_attempts: int = 4) -> None:
        self._db = db
        self._interval = 1.0 / max(1.0, updates_per_second)
        self._max_attempts = min(4, max(1, max_attempts))

    async def enqueue(self, guild_id: str, user_id: str, cycle_key: str, target_nickname: str | None) -> None:
        await self._db.execute(
            """INSERT INTO nickname_updates
               (guild_id, user_id, target_nickname, cycle_key, status, attempts, last_error, updated_at)
               VALUES (?, ?, ?, ?, 'pending', 0, NULL, ?)
               ON CONFLICT(guild_id, user_id, cycle_key) DO UPDATE SET
                 target_nickname = excluded.target_nickname,
                 status = 'pending', attempts = 0, last_error = NULL, updated_at = excluded.updated_at""",
            [guild_id, user_id, target_nickname, cycle_key, datetime.now(timezone.utc).isoformat()],
        )

    async def run_member(
        self, guild: discord.Guild, user_id: str, cycle_key: str, target_nickname: str | None,
        edit_member: Callable[[discord.Member, str | None], Awaitable[None]], previous_attempts: int = 0,
    ) -> None:
        member = guild.get_member(int(user_id))
        if member is None:
            try:
                member = await guild.fetch_member(int(user_id))
            except discord.NotFound as exc:
                await self._record_failure(str(guild.id), user_id, cycle_key, str(exc), self._max_attempts, True)
                return

        for attempt in range(previous_attempts + 1, self._max_attempts + 1):
            try:
                await edit_member(member, target_nickname)
                await self._db.execute(
                    """UPDATE nickname_updates SET status = 'success', attempts = ?,
                       last_error = NULL, updated_at = ?
                       WHERE guild_id = ? AND user_id = ? AND cycle_key = ?""",
                    [attempt, datetime.now(timezone.utc).isoformat(), str(guild.id), user_id, cycle_key],
                )
                return
            except (discord.Forbidden, discord.HTTPException) as exc:
                terminal = attempt >= self._max_attempts or isinstance(exc, discord.Forbidden)
                await self._record_failure(str(guild.id), user_id, cycle_key, str(exc), attempt, terminal)
                if terminal:
                    return
                retry_after = getattr(exc, "retry_after", None)
                await asyncio.sleep(float(retry_after) if retry_after else min(2 ** (attempt - 1), 8))

    async def _record_failure(
        self, guild_id: str, user_id: str, cycle_key: str, error: str, attempts: int, terminal: bool,
    ) -> None:
        await self._db.execute(
            """UPDATE nickname_updates SET status = ?, attempts = ?, last_error = ?, updated_at = ?
               WHERE guild_id = ? AND user_id = ? AND cycle_key = ?""",
            ["failed" if terminal else "pending", attempts, error[:1000],
             datetime.now(timezone.utc).isoformat(), guild_id, user_id, cycle_key],
        )

    async def run_cycle(
        self, guild: discord.Guild, cycle_key: str,
        edit_member: Callable[[discord.Member, str | None], Awaitable[None]],
    ) -> None:
        rows = await self._db.query(
            """SELECT user_id, target_nickname, attempts FROM nickname_updates
               WHERE guild_id = ? AND cycle_key = ? AND status = 'pending'
                 AND attempts < ? ORDER BY updated_at""",
            [str(guild.id), cycle_key, self._max_attempts],
        )
        for row in rows:
            await self.run_member(
                guild, str(row["user_id"]), cycle_key, row.get("target_nickname"),
                edit_member, int(row.get("attempts") or 0),
            )
            await asyncio.sleep(self._interval)
