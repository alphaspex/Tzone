import unittest
from unittest.mock import patch

from tzone.nickname_queue import NicknameQueue


class FakeDatabase:
    def __init__(self):
        self.states = []

    async def batch(self, statements):
        for _sql, params in statements:
            self.states.append({
                "guild_id": params[0],
                "user_id": params[1],
                "target_nickname": params[2],
                "cycle_key": params[3],
                "status": params[4],
                "attempts": int(params[5]),
                "last_error": params[6],
            })


class FakeMember:
    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    async def edit(self, nick, reason):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("simulated Discord failure")


class NicknameRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_until_success_and_persists_attempt_count(self):
        db = FakeDatabase()
        queue = NicknameQueue(db)
        queue._interval = 0
        member = FakeMember(failures=2)
        job = {
            "guild_id": "guild",
            "user_id": "member",
            "cycle_key": "2026-11-09-10",
            "target_nickname": "Alex | 11 AM",
            "member": member,
            "attempts": 0,
        }

        async def no_wait(_seconds):
            return None

        with patch("tzone.nickname_queue.asyncio.sleep", new=no_wait):
            result = await queue._run_jobs([job])

        self.assertEqual(member.calls, 3)
        self.assertEqual(result, {"updated": 1, "failed": 0})
        self.assertEqual(db.states[-1]["status"], "success")
        self.assertEqual(db.states[-1]["attempts"], 3)

    async def test_never_exceeds_four_total_attempts(self):
        db = FakeDatabase()
        queue = NicknameQueue(db)
        queue._interval = 0
        member = FakeMember(failures=99)
        job = {
            "guild_id": "guild",
            "user_id": "member",
            "cycle_key": "2026-11-09-10",
            "target_nickname": "Alex | 11 AM",
            "member": member,
            "attempts": 0,
        }

        async def no_wait(_seconds):
            return None

        with patch("tzone.nickname_queue.asyncio.sleep", new=no_wait):
            result = await queue._run_jobs([job])

        self.assertEqual(member.calls, 4)
        self.assertEqual(result, {"updated": 0, "failed": 1})
        self.assertEqual(db.states[-1]["status"], "failed")
        self.assertEqual(db.states[-1]["attempts"], 4)


if __name__ == "__main__":
    unittest.main()
