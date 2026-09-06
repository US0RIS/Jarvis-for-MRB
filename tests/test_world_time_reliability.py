from __future__ import annotations

import unittest
from datetime import datetime

import jarvis_mrb.world_executive_loop as world_executive_loop


class ExecutiveTimeReliabilityTests(unittest.TestCase):
    def test_rfc_email_timestamp_parses_for_executive_chronology(self) -> None:
        parsed = world_executive_loop._parse_time("Sun, 06 Sep 2026 10:15:00 -0400")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 9)
        self.assertEqual(parsed.day, 6)

    def test_malformed_timestamp_uses_platform_safe_floor_not_datetime_min(self) -> None:
        self.assertIsNone(world_executive_loop._parse_time("not a timestamp"))
        floor = world_executive_loop._TIME_FLOOR
        self.assertIsInstance(floor, datetime)
        self.assertIsNotNone(floor.tzinfo)
        self.assertEqual(floor.year, 1970)


if __name__ == "__main__":
    unittest.main()
