from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from jarvis_mrb.tools import google


class CalendarCreateReliabilityTests(unittest.TestCase):
    def test_unwraps_planner_datetime_mapping(self) -> None:
        text, parsed = google._normalize_calendar_datetime({"date_time": "2026-09-08T23:55:00-07:00"})
        self.assertIsNotNone(parsed)
        self.assertEqual(text, "2026-09-08T23:55:00-07:00")

    def test_unwraps_stringified_planner_datetime_mapping(self) -> None:
        text, parsed = google._normalize_calendar_datetime("{'date_time': '2026-09-08T23:55:00-07:00'}")
        self.assertIsNotNone(parsed)
        self.assertEqual(text, "2026-09-08T23:55:00-07:00")

    def test_naive_datetime_is_made_timezone_aware(self) -> None:
        text, parsed = google._normalize_calendar_datetime("2026-09-08T23:55:00")
        self.assertIsNotNone(parsed)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertRegex(text or "", r"(?:Z|[+-]\d\d:\d\d)$")

    @patch.object(google, "_load_credentials", return_value=object())
    @patch.object(google, "build")
    def test_create_normalizes_wrapped_times_before_google(self, build_mock: MagicMock, _creds: MagicMock) -> None:
        event_insert = build_mock.return_value.events.return_value.insert
        event_insert.return_value.execute.return_value = {"id": "evt-1", "htmlLink": "https://calendar.test/evt-1"}

        result = google.create_calendar_event(
            "Jarvis Live Verification",
            {"date_time": "2026-09-08T23:55:00-07:00"},
            {"date_time": "2026-09-09T00:00:00-07:00"},
            "Live verification event for Jarvis",
        )

        self.assertTrue(result.ok, result.message)
        body = event_insert.call_args.kwargs["body"]
        self.assertEqual(body["start"]["dateTime"], "2026-09-08T23:55:00-07:00")
        self.assertEqual(body["end"]["dateTime"], "2026-09-09T00:00:00-07:00")

    @patch.object(google, "_load_credentials", return_value=object())
    @patch.object(google, "build")
    def test_create_rejects_probable_seconds_for_minutes_error(self, build_mock: MagicMock, _creds: MagicMock) -> None:
        result = google.create_calendar_event(
            "Jarvis Live Verification",
            "2026-09-08T23:55:00-07:00",
            "2026-09-08T23:55:05-07:00",
        )

        self.assertFalse(result.ok)
        self.assertIn("under one minute", result.message)
        build_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
