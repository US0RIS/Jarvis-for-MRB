from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_platform as registry
from jarvis_mrb import world_armor_observe as runner
from jarvis_mrb import world_armor_perception as vision


class SourcePlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "source-platform.sqlite3"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        env = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_MAX_DB_MB": "32",
        })
        env.start()
        self.addCleanup(env.stop)

    def enroll(self, **updates):
        kwargs = dict(
            label="Public pass camera", kind="public_https",
            locator="https://public-camera.example/road.jpg",
            grant_class="public_publisher",
            terms_reference="Publisher terms checked by operator on 2026-09-25",
            authorized_automated_access=True,
            automated_min_interval_seconds=0,
            cadence_seconds=1,
            retention_days=30,
            scene_goal="visible heavy rain on the roadway",
            now=self.now, db_path=self.db,
        )
        kwargs.update(updates)
        return registry.enroll_source(**kwargs)

    @staticmethod
    def camera_frame(code="a"):
        return {
            "frame": b"some normalized image bytes",
            "sha256": code * 64,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "capture_time": None,
            "camera_ref": "public-camera",
            "camera_name": "Public camera",
            "media_kind": "published_still",
            "source_display": "https://public-camera.example/road.jpg",
        }

    @staticmethod
    def result(state="observed"):
        return {"condition_status": state,
                "description": "Apparent rain visible; capture time unknown.",
                "model": "local-moondream"}

    def test_empty_preflight_stable_contract_for_native_reader(self):
        report = registry.plan(db_path=self.db)
        self.assertEqual(report["available"], 0)
        self.assertEqual(report["automated"], 0)
        self.assertEqual(report["proposed_host_concurrency"], 4)
        self.assertFalse(report["provider_entitlement_independently_verified"])
        self.assertFalse(report["remote_distributed_workers"])

    def test_permission_reference_required_and_expiry_optional(self):
        with self.assertRaises(ValueError):
            self.enroll(terms_reference="")
        with self.assertRaises(ValueError):
            self.enroll(cadence_seconds=1, authorized_automated_access=False)
        with self.assertRaises(ValueError):
            self.enroll(cadence_seconds=4, automated_min_interval_seconds=10)
        with self.assertRaises(ValueError):
            self.enroll(
                consent_expires_at=(self.now-timedelta(seconds=1)).isoformat()
            )
        with self.assertRaises(ValueError):
            self.enroll(locator="https://127.0.0.1/security.jpg")
        source = self.enroll(
            sample_budget=None, consent_expires_at=None,
            retention_days=10000,
        )
        self.assertIsNone(source["sample_budget"])
        self.assertIsNone(source["consent_expires_at"])
        self.assertEqual(source["retention_days"], 10000)
        self.assertFalse(source["permission_verified_by_jarvis"])
        self.assertFalse(source["capture_time_verified"])

    def test_explicit_public_http_source_is_possible_without_private_ip_access(self):
        from jarvis_mrb.public_camera_media import validate_public_camera_url
        url = "http://public-camera.example/current.jpg"
        with self.assertRaises(ValueError):
            validate_public_camera_url(url)
        self.assertEqual(
            validate_public_camera_url(url, allow_http=True).host,
            "public-camera.example",
        )
        source = self.enroll(kind="public_http", locator=url,
                             authorized_automated_access=False,
                             cadence_seconds=0)
        self.assertEqual(source["kind"], "public_http")
        self.assertTrue(source["source_display"].startswith("http://"))
        self.assertNotIn("locator", source)
        with self.assertRaises(ValueError):
            self.enroll(kind="public_http",
                        locator="http://192.168.1.10/frame.jpg")
        with self.assertRaises(ValueError):
            self.enroll(kind="public_https", locator=url)

    def test_freeform_scene_goal_is_not_two_hardcoded_conditions(self):
        for condition in (
            "heavy rain visible on the highway",
            "ski lifts appear to be operating",
            "the highway appears covered by flood water",
            "there seems to be reduced visibility due to fog",
        ):
            self.assertEqual(vision.validate_scene_goal(condition), condition)
        for condition in (
            "identify that person by face",
            "read the license plate",
            "track a person across the beach",
        ):
            with self.subTest(condition=condition), self.assertRaises(ValueError):
                vision.validate_scene_goal(condition)

    def test_no_global_source_count_cap_and_paginated_evidence(self):
        # More than the old region camera cap of forty, and multiple pages.
        for i in range(43):
            self.enroll(label=f"Camera {i}", cadence_seconds=0,
                        authorized_automated_access=False)
        first = registry.list_sources(db_path=self.db, page_size=17)
        self.assertEqual(first["total"], 43)
        self.assertIsNone(first["global_source_count_cap"])
        self.assertEqual(len(first["sources"]), 17)
        second = registry.list_sources(
            db_path=self.db, offset=first["next_offset"], page_size=17,
        )
        third = registry.list_sources(
            db_path=self.db, offset=second["next_offset"], page_size=17,
        )
        self.assertEqual(len(second["sources"]), 17)
        self.assertEqual(len(third["sources"]), 9)
        self.assertIsNone(third["next_offset"])

    def test_duplicate_publication_avoids_second_model_call(self):
        source = self.enroll()
        with patch.object(runner.perception, "acquire_source",
                          side_effect=lambda *a: self.camera_frame("a")) as fetch, \
             patch.object(runner.perception, "interpret_frame",
                          return_value=self.result()) as model:
            one = runner.observe_source(
                source["id"], db_path=self.db, now=self.now,
            )
            two = runner.observe_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(one["model_calls"], 1)
        self.assertEqual(two["model_calls"], 0)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(fetch.call_count, 2)
        evidence = registry.observations(db_path=self.db)["observations"]
        self.assertEqual(len(evidence), 1)
        self.assertIsNone(evidence[0]["source_capture_at"])
        self.assertEqual(evidence[0]["adapter_mode"], "real_adapter")
        self.assertEqual(registry.get_source(
            source["id"], db_path=self.db,
        )["check_count"], 2)

    def test_distinct_positive_frames_alert_only_after_baseline_and_rearm(self):
        source = self.enroll()
        images = iter("aabcdef")
        states = iter((
            "observed", "observed", "observed", "not_observed",
            "observed", "observed",
        ))
        with patch.object(
            runner.perception, "acquire_source",
            side_effect=lambda *a: self.camera_frame(next(images)),
        ), patch.object(
            runner.perception, "interpret_frame",
            side_effect=lambda *a: self.result(next(states)),
        ) as interpret:
            a = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            b = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            c = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            d = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            e = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            f = runner.observe_source(source["id"], db_path=self.db, now=self.now)
            g = runner.observe_source(source["id"], db_path=self.db, now=self.now)
        self.assertFalse(a["notice_created"])
        self.assertEqual(b["model_calls"], 0)
        self.assertTrue(c["notice_created"])
        self.assertFalse(d["notice_created"])
        self.assertFalse(e["notice_created"])
        self.assertFalse(f["notice_created"])
        self.assertTrue(g["notice_created"])
        self.assertEqual(interpret.call_count, 6)
        notes = registry.notices(db_path=self.db)["notices"]
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("Unconfirmed" in note["summary"] for note in notes))

    def test_remote_camera_worker_lineage_persists_without_raw_frame(self):
        source = self.enroll()
        remote = {
            "status": "ok",
            "provider": "public_camera",
            "device_id": "macbook",
            "sha256": "b" * 64,
            "retrieved_at": self.now.isoformat(),
            "media_kind": "published_still",
            "source_display": "https://public-camera.example/road.jpg",
            "same_published_frame": False,
            "evaluation": self.result(),
            "raw_image_returned": False,
        }
        with patch("jarvis_mrb.reality_mesh.world_observe",
                   return_value=remote):
            receipt = runner.observe_source(
                source["id"], db_path=self.db, now=self.now,
                worker_id="macbook",
            )
        self.assertEqual(receipt["worker_id"], "macbook")
        self.assertTrue(receipt["no_image_retained"])
        evidence = registry.observations(db_path=self.db)["observations"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["worker_id"], "macbook")
        self.assertEqual(evidence[0]["image_sha256"], "b" * 64)

    def test_stop_during_http_blocks_evidence_and_notice(self):
        source = self.enroll()
        def stop_during_fetch(kind, locator):
            registry.transition_source(source["id"], "stop", db_path=self.db)
            return self.camera_frame("a")
        with patch.object(
            runner.perception, "acquire_source", side_effect=stop_during_fetch,
        ), patch.object(
            runner.perception, "interpret_frame", return_value=self.result(),
        ):
            outcome = runner.observe_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(outcome["status"], "revoked_or_superseded")
        self.assertEqual(
            registry.observations(db_path=self.db)["observations"], []
        )
        self.assertEqual(registry.notices(db_path=self.db)["notices"], [])

    def test_provider_failure_retains_unknown_not_all_clear(self):
        source = self.enroll()
        with patch.object(
            runner.perception, "acquire_source",
            side_effect=ConnectionError("private source unavailable"),
        ):
            outcome = runner.observe_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(outcome["status"], "unavailable")
        self.assertEqual(outcome["error_type"], "ConnectionError")
        self.assertEqual(outcome["source_status"], "unknown_not_all_clear")
        self.assertEqual(
            registry.get_source(source["id"], db_path=self.db)["check_count"], 1
        )

    def test_source_specific_request_floor_applies_to_manual_checks(self):
        source = self.enroll(cadence_seconds=120,
                             automated_min_interval_seconds=60)
        with patch.object(runner.perception, "acquire_source",
                          return_value=self.camera_frame()):
            runner.observe_source(source["id"], db_path=self.db, now=self.now)
            with self.assertRaisesRegex(ValueError, "minimum request interval"):
                runner.observe_source(
                    source["id"], db_path=self.db, now=self.now,
                )

    def test_no_automatic_runner_and_due_batch_is_host_sized(self):
        active = self.enroll()
        manual = self.enroll(
            label="Manually checked", cadence_seconds=0,
            authorized_automated_access=False,
        )
        with patch.object(runner.perception, "acquire_source",
                          return_value=self.camera_frame()), \
             patch.object(runner.perception, "interpret_frame",
                          return_value=self.result()):
            receipts = runner.run_due(db_path=self.db, limit=1, now=self.now)
        self.assertEqual(len(receipts["checks"]), 1)
        self.assertEqual(receipts["checks"][0]["source_id"], active["id"])
        self.assertEqual(registry.get_source(
            manual["id"], db_path=self.db,
        )["check_count"], 0)
        self.assertFalse(receipts["remote_workers"])

    def test_revoke_and_forget_still_possible_when_feature_flags_off(self):
        source = self.enroll()
        with patch.object(runner.perception, "acquire_source",
                          return_value=self.camera_frame()), \
             patch.object(runner.perception, "interpret_frame",
                          return_value=self.result()):
            runner.observe_source(source["id"], db_path=self.db, now=self.now)
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "0",
        }):
            with self.assertRaises(RuntimeError):
                self.enroll()
            stopped = registry.transition_source(
                source["id"], "stop", db_path=self.db
            )
            self.assertEqual(stopped["state"], "stopped")
            self.assertEqual(registry.forget_source(
                source["id"], db_path=self.db,
            )["deleted"], 1)
            self.assertEqual(
                registry.observations(db_path=self.db)["observations"], []
            )
            self.assertEqual(registry.notices(db_path=self.db)["notices"], [])

    def test_operator_plan_reports_permission_and_actual_source_counts(self):
        active = self.enroll()
        manual = self.enroll(label="Manual", cadence_seconds=0,
                             authorized_automated_access=False)
        report = registry.plan(db_path=self.db, max_concurrent=9)
        self.assertEqual(report["available"], 2)
        self.assertEqual(report["automated"], 1)
        self.assertFalse(report["provider_entitlement_independently_verified"])
        self.assertFalse(report["remote_distributed_workers"])
        self.assertIsNone(report["max_source_count"])
        with self.assertRaises(KeyError):
            registry.plan(db_path=self.db, source_ids=["f"*32])
