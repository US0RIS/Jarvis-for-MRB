from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jarvis_mrb import reality_lens


def observation(*, aq: int = 41, alerts: int = 0,
                checked: str | None = None, unavailable: bool = False) -> dict:
    checked = checked or (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    return {
        "checked_at": checked,
        "cameras": {"status": "unsupported_region", "checked_at": checked, "cameras": []},
        "conditions": {
            "checked_at": checked,
            "air_quality": {"status": "unavailable" if unavailable else "ok", "us_aqi": aq},
            "weather_alerts": {"status": "unavailable" if unavailable else "ok",
                               "alerts": [{} for _ in range(alerts)]},
        },
        "incidents": {"status": "unavailable", "checked_at": checked, "events": []},
        "facilities": {"status": "unavailable", "checked_at": checked, "facilities": []},
    }


class RealityLensTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Path(self.tmp.name) / "lens.sqlite3"
        self.lat = 34.123456
        self.lon = -118.123456

    def tearDown(self):
        self.tmp.cleanup()

    def sense(self, *, aq=41, alerts=0, remember=False, unavailable=False,
              latitude=None, longitude=None, db_path=None):
        return reality_lens.sense_place(
            self.lat if latitude is None else latitude,
            self.lon if longitude is None else longitude,
            "My chosen place", remember=remember,
            observation=observation(aq=aq, alerts=alerts, unavailable=unavailable),
            db_path=self.db if db_path is None else db_path,
        )

    def test_one_shot_does_not_store_undisclosed_location(self):
        report = self.sense(aq=41)
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["action_authority"], "none")
        self.assertFalse(report["remembered"])
        self.assertFalse(report["baseline_available"])
        self.assertEqual(report["changes"], [])
        self.assertFalse(self.db.exists())
        self.assertEqual(report["unknown_metrics"], [
            "USGS regional event count", "Mapped public facility count"
        ])
        self.assertNotIn("latitude", report)
        self.assertNotIn("longitude", report)

    def test_explicit_memory_then_source_qualified_change(self):
        first = self.sense(aq=41, remember=True)
        self.assertTrue(first["remembered"])
        self.assertEqual(first["suggested_haptic_pulses"], 0)
        followup = self.sense(aq=79, alerts=2)
        self.assertTrue(followup["baseline_available"])
        self.assertFalse(followup["remembered"])
        self.assertEqual({x["id"] for x in followup["changes"]}, {
            "fact:air_quality", "fact:active_weather_alert_count"
        })
        self.assertEqual(followup["suggested_haptic_pulses"], 3)
        self.assertEqual(self.sense(aq=41)["suggested_haptic_pulses"], 0)
        self.assertEqual(len(reality_lens.list_memories(db_path=self.db)["memories"]), 1)

    def test_stale_current_provider_cannot_appear_as_no_change(self):
        self.sense(aq=41, remember=True)
        followup = self.sense(unavailable=True)
        self.assertEqual(followup["changes"], [])
        self.assertIn("Modelled US AQI", followup["unknown_metrics"])
        self.assertIn("NWS point alert count", followup["unknown_metrics"])
        self.assertEqual(followup["suggested_haptic_pulses"], 0)

    def test_future_dated_provider_is_unknown(self):
        self.sense(aq=41, remember=True)
        stamp = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        report = reality_lens.sense_place(
            self.lat, self.lon, "Chosen", observation=observation(aq=65, checked=stamp),
            db_path=self.db,
        )
        self.assertEqual(report["changes"], [])
        self.assertIn("Modelled US AQI", report["unknown_metrics"])

    def test_different_place_must_not_inherit_baseline(self):
        self.sense(remember=True)
        distant = self.sense(latitude=34.55)
        self.assertFalse(distant["baseline_available"])
        self.assertEqual(distant["changes"], [])

    def test_remember_saves_only_bounded_facts_not_raw_provider_payload(self):
        original = observation()
        original["cameras"]["cameras"] = [{"id": "camera-secret", "url": "private-secret"}]
        reality_lens.sense_place(
            self.lat, self.lon, "Chosen", remember=True,
            observation=original, db_path=self.db,
        )
        raw = self.db.read_bytes()
        for forbidden in (b"private-secret", b"camera-secret",
                          b"34.123456", b"-118.123456"):
            self.assertNotIn(forbidden, raw)
        payload = reality_lens.list_memories(db_path=self.db)["memories"]
        self.assertEqual(payload[0]["fact_count"], 2)
        self.assertNotIn("coordinates", payload[0])

    def test_explicit_forget_is_exact_place_only(self):
        self.sense(remember=True)
        self.sense(remember=True, latitude=35.0)
        self.assertEqual(reality_lens.forget_place(self.lat, self.lon, db_path=self.db)["deleted"], 1)
        remaining = reality_lens.list_memories(db_path=self.db)["memories"]
        self.assertEqual(len(remaining), 1)
        self.assertFalse(self.sense()["baseline_available"])

    def test_no_memory_to_forget_does_not_create_file(self):
        result = reality_lens.forget_place(self.lat, self.lon, db_path=self.db)
        self.assertEqual(result["deleted"], 0)
        self.assertFalse(self.db.exists())

    def test_old_baseline_expires(self):
        old = datetime.now(timezone.utc) - timedelta(days=31)
        reality_lens.sense_place(
            self.lat, self.lon, "Chosen", remember=True,
            observation=observation(), db_path=self.db, now=old,
        )
        self.assertFalse(self.sense()["baseline_available"])
        self.assertEqual(reality_lens.list_memories(db_path=self.db)["memories"], [])

    def test_total_snapshots_bounded(self):
        for _ in range(reality_lens.MAX_SNAPSHOTS + 4):
            self.sense(remember=True)
        con = reality_lens._connect(self.db)
        try:
            total = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(total, reality_lens.MAX_SNAPSHOTS)

    def test_invalid_coordinates_and_missing_label_rejected_without_io(self):
        for lat, lon in ((float("nan"), 3), (91, 0), (0, 181)):
            with self.assertRaises(ValueError):
                reality_lens.sense_place(lat, lon, "Chosen", db_path=self.db)
        with self.assertRaises(ValueError):
            reality_lens.sense_place(self.lat, self.lon, "  ", db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_service_requires_auth_for_all_lens_routes(self):
        path = Path(__file__).parents[1] / "jarvis_mrb" / "service.py"
        source = path.read_text(encoding="utf-8")
        for endpoint in ("/reality/lens/sense", "/reality/lens/memories", "/reality/lens/forget"):
            self.assertIn(endpoint, source)
        for name in ("def reality_lens_sense(", "def reality_lens_memories(", "def reality_lens_forget("):
            function = source.split(name, 1)[1].split("\n\n@app.", 1)[0]
            self.assertIn("_check_mesh_auth(authorization)", function)
            self.assertIn('response.headers["Cache-Control"] = "private, no-store"', function)


if __name__ == "__main__":
    unittest.main()
