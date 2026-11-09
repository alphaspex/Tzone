import asyncio
import logging
import time
from datetime import datetime, timezone

import discord

from .d1 import D1Client
from .time_utils import due_cycle, get_timezone, nickname_for


log = logging.getLogger("tzone.nickname")
MAX_ATTEMPTS = 4
BATCH_SIZE = 20


class NicknameQueue:
    """D1-backed per-member queue; each state transition is persisted."""

    def __init__(
        self, db: D1Client, updates_per_second: float = 40.0,
        max_attempts: int = 4,
    ) -> None:
        self._db = db
        self._interval = 1.0 / max(1.0, min(40.0, updates_per_second))
        self._max_attempts = min(MAX_ATTEMPTS, max(1, max_attempts))
        self._last_request = 0.0
        self._cleanup_day = None
        self._cleaned_guilds: set[str] = set()

    async def run_guild(
        self, guild: discord.Guild, timezone_rows: list[dict],
        window_minutes: int = 10, now: datetime | None = None,
    ) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        summary = {"checked": 0, "updated": 0, "failed": 0, "skipped": 0}

        if self._cleanup_day != now.date():
            self._cleanup_day = now.date()
            self._cleaned_guilds.clear()
        if str(guild.id) not in self._cleaned_guilds:
            await self._db.execute(
                """DELETE FROM nickname_updates
                   WHERE julianday(updated_at) < julianday('now', '-3 days')"""
            )
            self._cleaned_guilds.add(str(guild.id))

        if not guild.chunked:
            await guild.chunk(cache=True)

        due = []
        for row in timezone_rows:
            local_now = now.astimezone(get_timezone(row["timezone"]))
            cycle = due_cycle(local_now, window_minutes)
            if cycle is None:
                continue

            member = guild.get_member(int(row["user_id"]))
            if member is None or member.bot:
                summary["skipped"] += 1
                continue

            cycle_key, display_hour = cycle
            due.append({
                "guild_id": str(guild.id),
                "user_id": str(member.id),
                "cycle_key": cycle_key,
                "target_nickname": nickname_for(member.nick or member.name, display_hour),
                "member": member,
            })

        if not due:
            return summary

        jobs = await self._db.query(
            """SELECT user_id, cycle_key, target_nickname, status, attempts
               FROM nickname_updates WHERE guild_id = ?""",
            [str(guild.id)],
        )
        job_map = {(str(row["user_id"]), row["cycle_key"]): row for row in jobs}
        pending = []
        immediate_states = []

        for item in due:
            summary["checked"] += 1
            existing = job_map.get((item["user_id"], item["cycle_key"]))
            attempts = int(existing["attempts"]) if existing else 0
            status = existing["status"] if existing else "pending"
            item["attempts"] = attempts
            item["status"] = status

            if item["member"].nick == item["target_nickname"]:
                immediate_states.append({
                    **item, "status": "success", "last_error": "",
                })
                summary["skipped"] += 1
                continue

            if attempts >= self._max_attempts:
                if status != "failed":
                    immediate_states.append({
                        **item, "status": "failed",
                        "last_error": "Maximum attempts reached for this hourly cycle.",
                    })
                summary["failed"] += 1
                continue

            pending.append(item)

        await self._save_states(immediate_states)
        if pending:
            # Insert new rows and preserve existing attempt counts.
            await self._insert_jobs(pending)
            result = await self._run_jobs(pending)
            summary["updated"] += result["updated"]
            summary["failed"] += result["failed"]
        return summary

    async def _insert_jobs(self, jobs: list[dict]) -> None:
        statements = []
        for job in jobs:
            statements.append((
                """INSERT OR IGNORE INTO nickname_updates
                   (guild_id, user_id, target_nickname, cycle_key, status, attempts, last_error)
                   VALUES (?, ?, ?, ?, 'pending', 0, NULL)""",
                [job["guild_id"], job["user_id"], job["target_nickname"], job["cycle_key"]],
            ))
        await self._db.batch(statements)

    async def _save_states(self, jobs: list[dict]) -> None:
        statements = []
        for job in jobs:
            statements.append((
                """INSERT INTO nickname_updates
                   (guild_id, user_id, target_nickname, cycle_key, status,
                    attempts, last_error, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                   ON CONFLICT(guild_id, user_id, cycle_key) DO UPDATE SET
                     target_nickname = excluded.target_nickname,
                     status = excluded.status,
                     attempts = excluded.attempts,
                     last_error = excluded.last_error,
                     updated_at = excluded.updated_at""",
                [
                    job["guild_id"], job["user_id"], job["target_nickname"],
                    job["cycle_key"], job["status"], job["attempts"],
                    job.get("last_error") or None,
                ],
            ))
        await self._db.batch(statements)

    async def _run_jobs(self, jobs: list[dict]) -> dict[str, int]:
        pending = jobs
        round_number = 0
        updated = 0
        failed = 0

        while pending:
            if round_number:
                await asyncio.sleep(min(2 ** (round_number - 1), 4))
            retry_jobs = []

            for offset in range(0, len(pending), BATCH_SIZE):
                group = pending[offset : offset + BATCH_SIZE]
                marked = [
                    {
                        **job,
                        "attempts": job["attempts"] + 1,
                        "status": "pending",
                        "last_error": "",
                    }
                    for job in group
                ]
                # Consume the attempt in D1 before the external Discord request.
                await self._save_states(marked)

                outcomes = []
                for job in marked:
                    wait = self._interval - (time.monotonic() - self._last_request)
                    if self._last_request and wait > 0:
                        await asyncio.sleep(wait)
                    self._last_request = time.monotonic()

                    try:
                        await job["member"].edit(
                            nick=job["target_nickname"],
                            reason="Tzone hourly local-time refresh",
                        )
                        outcomes.append({
                            **job, "status": "success", "last_error": "",
                        })
                        updated += 1
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {exc}"[:500]
                        terminal = job["attempts"] >= self._max_attempts
                        outcome = {
                            **job,
                            "status": "failed" if terminal else "pending",
                            "last_error": error,
                        }
                        outcomes.append(outcome)
                        if terminal:
                            failed += 1
                        else:
                            retry_jobs.append(outcome)
                        log.warning(
                            "Nickname update failed: guild=%s member=%s attempt=%s/%s error=%s",
                            job["guild_id"], job["user_id"], job["attempts"],
                            self._max_attempts, error,
                        )
                await self._save_states(outcomes)

            pending = retry_jobs
            round_number += 1

        return {"updated": updated, "failed": failed}
