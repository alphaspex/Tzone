from collections.abc import Iterable
from typing import Any

from .d1 import D1Client


class ScheduleStore:
    """Timezone and weekly availability persistence."""

    def __init__(self, db: D1Client) -> None:
        self._db = db

    async def save_user_schedule(
        self, guild_id: str, user_id: str, timezone_name: str,
        intervals: Iterable[dict[str, Any]],
    ) -> None:
        statements: list[tuple[str, list[Any]]] = [
            (
                """INSERT INTO user_timezones (guild_id, user_id, timezone, updated_at)
                   VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                     timezone = excluded.timezone,
                     updated_at = excluded.updated_at""",
                [guild_id, user_id, timezone_name],
            ),
            (
                "DELETE FROM weekly_availability WHERE guild_id = ? AND user_id = ?",
                [guild_id, user_id],
            ),
        ]
        for item in intervals:
            statements.append((
                """INSERT INTO weekly_availability
                   (guild_id, user_id, weekday, start_hour, end_hour, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    guild_id, user_id, item["weekday"], item["start_hour"],
                    item["end_hour"], item["status"],
                ],
            ))
        await self._db.batch(statements)

    async def get_user_timezone(self, guild_id: str, user_id: str) -> str | None:
        rows = await self._db.query(
            "SELECT timezone FROM user_timezones WHERE guild_id = ? AND user_id = ? LIMIT 1",
            [guild_id, user_id],
        )
        return rows[0]["timezone"] if rows else None

    async def get_guild_timezones(self, guild_id: str) -> list[dict[str, Any]]:
        return await self._db.query(
            "SELECT user_id, timezone FROM user_timezones WHERE guild_id = ? ORDER BY user_id",
            [guild_id],
        )

    async def get_guild_schedules(self, guild_id: str) -> list[dict[str, Any]]:
        rows = await self._db.query(
            """SELECT tz.user_id, tz.timezone, a.weekday, a.start_hour, a.end_hour, a.status
               FROM user_timezones tz
               LEFT JOIN weekly_availability a
                 ON a.guild_id = tz.guild_id AND a.user_id = tz.user_id
               WHERE tz.guild_id = ?
               ORDER BY tz.user_id, a.weekday, a.start_hour""",
            [guild_id],
        )
        profiles: dict[str, dict[str, Any]] = {}
        for row in rows:
            user_id = str(row["user_id"])
            profiles.setdefault(user_id, {
                "user_id": user_id,
                "timezone": row["timezone"],
                "intervals": [],
            })
            if row["weekday"] is not None:
                profiles[user_id]["intervals"].append({
                    "weekday": int(row["weekday"]),
                    "start_hour": int(row["start_hour"]),
                    "end_hour": int(row["end_hour"]),
                    "status": row["status"],
                })
        return list(profiles.values())

    async def delete_user(self, guild_id: str, user_id: str) -> None:
        await self._db.batch([
            ("DELETE FROM weekly_availability WHERE guild_id = ? AND user_id = ?", [guild_id, user_id]),
            ("DELETE FROM nickname_updates WHERE guild_id = ? AND user_id = ?", [guild_id, user_id]),
            ("DELETE FROM user_timezones WHERE guild_id = ? AND user_id = ?", [guild_id, user_id]),
        ])
