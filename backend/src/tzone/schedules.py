from collections.abc import Iterable
from typing import Any

from .d1 import D1Client


class ScheduleStore:
    """Availability persistence. Each method is an isolated D1 I/O operation."""

    def __init__(self, db: D1Client) -> None:
        self._db = db

    async def replace_user_schedule(
        self, guild_id: str, user_id: str, intervals: Iterable[dict[str, Any]]
    ) -> None:
        await self._db.execute(
            "DELETE FROM weekly_availability WHERE guild_id = ? AND user_id = ?",
            [guild_id, user_id],
        )
        for item in intervals:
            await self._db.execute(
                """INSERT INTO weekly_availability
                   (guild_id, user_id, weekday, start_hour, end_hour, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    guild_id, user_id, item["weekday"], item["start_hour"],
                    item["end_hour"], item["status"],
                ],
            )

    async def get_user_schedule(self, guild_id: str, user_id: str) -> list[dict[str, Any]]:
        return await self._db.query(
            """SELECT weekday, start_hour, end_hour, status
               FROM weekly_availability
               WHERE guild_id = ? AND user_id = ?
               ORDER BY weekday, start_hour""",
            [guild_id, user_id],
        )

    async def delete_user_schedule(self, guild_id: str, user_id: str) -> None:
        await self._db.execute(
            "DELETE FROM weekly_availability WHERE guild_id = ? AND user_id = ?",
            [guild_id, user_id],
        )

    async def get_hour(self, guild_id: str, weekday: int, hour: int) -> list[dict[str, Any]]:
        return await self._db.query(
            """SELECT user_id, status FROM weekly_availability
               WHERE guild_id = ? AND weekday = ?
                 AND start_hour <= ? AND end_hour > ?""",
            [guild_id, weekday, hour, hour],
        )
