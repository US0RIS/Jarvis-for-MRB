from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.world_model as world_model
import jarvis_mrb.external_watches as watches


class ExternalWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = world_model.APP_DIR
        self.old_db = world_model.DB_PATH
        world_model.APP_DIR = Path(self.temp.name)
        world_model.DB_PATH = world_model.APP_DIR / "world_model.sqlite3"

    def tearDown(self) -> None:
        world_model.APP_DIR = self.old_dir
        world_model.DB_PATH = self.old_db
        self.temp.cleanup()

    def _create(self, scope: str = "personal") -> dict:
        return watches.create_watch(
            scope, "camera", "Mountain pass",
            {"camera_id": "caltrans-d7-196"},
            interval_seconds=900, expires_hours=2,
        )

    def test_first_snapshot_baselines_subsequent_change_is_provenance_record(self) -> None:
        watch = self._create()
        first = {
            "status": "ok", "summary": "Static mountain pass",
            "source_url": "https://cwwp2.dot.ca.gov/camera",
            "observed_at": "", "signature": "cars moving",
            "payload": {"description": "cars moving"},
        }
        with patch("jarvis_mrb.external_watches._fetch", return_value=first):
            baseline = watches.check_watch(watch["id"], "personal")
        self.assertEqual(baseline["change_kind"], "baseline")
        with patch("jarvis_mrb.external_watches._fetch", return_value={
            **first, "signature": "stopped traffic", "summary": "Traffic seems stopped",
        }):
            changed = watches.check_watch(watch["id"], "personal")
        self.assertEqual(changed["change_kind"], "changed")
        history = watches.watch_history(watch["id"], "personal")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["payload"]["description"], "cars moving")
        self.assertEqual(history[0]["change_kind"], "changed")

    def test_condition_alert_needs_two_distinct_positive_frames_and_rearms(self) -> None:
        watch = watches.create_watch(
            "personal", "camera", "Pass",
            {"camera_id": "caltrans-d7-196", "condition": "smoke_visible"},
            interval_seconds=900, expires_hours=2,
        )
        def frame(state: str, sha: str) -> dict:
            return {
                "status": "ok", "summary": "Unconfirmed camera model result",
                "source_url": "https://cwwp2.dot.ca.gov",
                "signature": [state, sha],
                "payload": {
                    "description": "candidate smoke",
                    "condition_status": state, "image_sha256": sha,
                },
            }
        with patch("jarvis_mrb.event_bus.emit_proactive") as notify:
            for data in (
                frame("observed", "image1"),
                frame("observed", "image1"),
            ):
                with patch("jarvis_mrb.external_watches._fetch", return_value=data):
                    watches.check_watch(watch["id"], "personal")
            notify.assert_not_called()
            with patch("jarvis_mrb.external_watches._fetch", return_value=frame("observed", "image2")):
                watches.check_watch(watch["id"], "personal")
            notify.assert_called_once()
            with patch("jarvis_mrb.external_watches._fetch", return_value=frame("observed", "image3")):
                watches.check_watch(watch["id"], "personal")
            notify.assert_called_once()
            with patch("jarvis_mrb.external_watches._fetch", return_value=frame("not_observed", "image4")):
                watches.check_watch(watch["id"], "personal")
            with patch("jarvis_mrb.external_watches._fetch", return_value=frame("observed", "image5")):
                watches.check_watch(watch["id"], "personal")
            with patch("jarvis_mrb.external_watches._fetch", return_value=frame("observed", "image6")):
                watches.check_watch(watch["id"], "personal")
            self.assertEqual(notify.call_count, 2)

    def test_return_to_old_condition_creates_new_change_evidence(self) -> None:
        watch = self._create()
        values = ["a", "b", "a"]
        for value in values:
            with patch("jarvis_mrb.external_watches._fetch", return_value={
                "status": "ok", "summary": "Source now " + value,
                "source_url": "https://cwwp2.dot.ca.gov",
                "signature": value,
                "payload": {"description": value},
            }):
                watches.check_watch(watch["id"], "personal")
        history = watches.watch_history(watch["id"], "personal")
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["change_kind"], "changed")
        self.assertEqual(history[0]["payload"]["description"], "a")

    def test_matter_scope_is_isolated_and_stop_disables(self) -> None:
        watch = self._create("matter:deal123")
        self.assertEqual(len(watches.list_watches("personal")), 0)
        with self.assertRaises(ValueError):
            watches.get_watch(watch["id"], "matter:another")
        result = watches.stop_watch(watch["id"], "matter:deal123")
        self.assertFalse(result["enabled"])
        self.assertEqual(
            watches.check_watch(watch["id"], "matter:deal123")["status"],
            "stopped_or_expired",
        )

    def test_provider_failure_is_not_a_source_change(self) -> None:
        watch = self._create()
        with patch("jarvis_mrb.external_watches._fetch", return_value={
            "status": "ok", "summary": "baseline", "signature": ["a"],
            "payload": {}, "source_url": "https://www.sec.gov",
        }):
            watches.check_watch(watch["id"], "personal")
        before = watches.get_watch(watch["id"], "personal")["last_digest"]
        with patch("jarvis_mrb.external_watches._fetch", side_effect=ConnectionError("offline")):
            result = watches.check_watch(watch["id"], "personal")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(watches.get_watch(watch["id"], "personal")["last_digest"], before)

    def test_watches_require_expiry_exact_provider_identity_and_bound_intervals(self) -> None:
        for kw in (
            {"scope": "matter:bad space"},
            {"kind": "webcam"},
            {"config": {"camera_id": "http://private-camera"}},
            {"interval_seconds": 10},
            {"expires_hours": 1000},
        ):
            params = dict(
                scope="personal", kind="camera", label="Pass",
                config={"camera_id": "caltrans-d7-196"},
                interval_seconds=900, expires_hours=3,
            )
            params.update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                watches.create_watch(**params)

    def test_sec_watch_normalizes_only_exact_numeric_cik(self) -> None:
        created = watches.create_watch(
            "matter:sample", "sec_filings", "Issuer filings",
            {"cik": "320193"}, interval_seconds=3600,
        )
        self.assertEqual(created["config"]["cik"], "0000320193")
        self.assertEqual(created["scope"], "matter:sample")


if __name__ == "__main__":
    unittest.main()
