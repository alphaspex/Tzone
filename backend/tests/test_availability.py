import unittest
from datetime import datetime, timezone

from tzone.availability import parse_schedule_fields, weekly_hours
from tzone.time_utils import due_cycle, nickname_for


class AvailabilityTests(unittest.TestCase):
    def test_parses_multiple_whole_hour_ranges(self):
        rows = parse_schedule_fields({
            "mon_free": "09-14, 18-21",
            "mon_chat": "14-18",
        })
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["start_hour"], 9)
        self.assertEqual(rows[0]["end_hour"], 14)

    def test_overnight_range_wraps_to_next_weekday(self):
        rows = parse_schedule_fields({"sun_free": "22-02"})
        self.assertEqual(
            [(row["weekday"], row["start_hour"], row["end_hour"]) for row in rows],
            [(6, 22, 24), (0, 0, 2)],
        )

    def test_free_and_chat_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_schedule_fields({
                "mon_free": "09-14",
                "mon_chat": "13-18",
            })

    def test_nickname_uses_hour_without_minutes_and_preserves_name(self):
        local_hour = datetime(2026, 11, 9, 14, 37, tzinfo=timezone.utc)
        self.assertEqual(nickname_for("Alex | 1 PM", local_hour), "Alex | 2 PM")

    def test_nickname_respects_discord_length(self):
        local_hour = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)
        self.assertLessEqual(len(nickname_for("A" * 50, local_hour)), 32)

    def test_due_window_prepares_next_hour_and_recovers_after_boundary(self):
        during_window = datetime(2026, 11, 9, 10, 55, tzinfo=timezone.utc)
        cycle, display = due_cycle(during_window)
        self.assertEqual(cycle, "2026-11-09-10")
        self.assertEqual(display.hour, 11)

        after_boundary = datetime(2026, 11, 9, 11, 3, tzinfo=timezone.utc)
        cycle, display = due_cycle(after_boundary)
        self.assertEqual(cycle, "2026-11-09-10")
        self.assertEqual(display.hour, 11)

    def test_weekly_heatmap_thresholds(self):
        profiles = [
            {
                "timezone": "UTC",
                "intervals": [
                    {"weekday": 0, "status": "free", "start_hour": 14, "end_hour": 15}
                ],
            }
            for _ in range(3)
        ]
        _, rows = weekly_hours(
            profiles,
            "UTC",
            0,
            datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(rows[14]["free"], 3)
        self.assertEqual(rows[14]["color"], "🟩")
        self.assertEqual(rows[0]["color"], "⬛")
        self.assertEqual(rows[13]["color"], "🟥")


if __name__ == "__main__":
    unittest.main()
