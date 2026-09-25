from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jarvis_mrb import life_fabric as life


NOW = datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)


class LifeFabricTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "life.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def task(self, title="Return a package", deadline=None, **kw):
        return life.create(
            "task", title, "shopping",
            db_path=self.path, now=NOW, deadline_at=deadline, **kw
        )

    def test_no_fabricated_all_clear_from_empty_ledger(self):
        view = life.readiness(db_path=self.path, now=NOW)
        self.assertTrue(view["setup_required"])
        self.assertFalse(view["all_clear"])
        self.assertEqual(view["monitoring"], "on_request")
        self.assertEqual(view["model_calls"], 0)
        self.assertEqual(view["external_actions"], 0)

    def test_timezones_and_overdue_windows(self):
        self.task(deadline="2026-09-23T14:00:00-04:00")
        second = self.task("Pay a bill", deadline="2026-09-24T05:00:00Z")
        view = life.readiness(db_path=self.path, now=NOW)
        self.assertEqual([x["due_state"] for x in view["due"]], ["overdue", "next_24h"])
        self.assertEqual(view["due"][1]["id"], second["id"])
        with self.assertRaises(ValueError):
            self.task("Naive datetime", deadline="2026-09-24T05:00:00")

    def test_dependency_blocks_without_claiming_done(self):
        initial = self.task("Find compatible model")
        dependent = self.task("Make purchase", depends_on=[initial["id"]],
                              deadline="2026-09-24T00:00:00Z")
        view = life.readiness(db_path=self.path, now=NOW)
        self.assertEqual(view["blocked"][0]["id"], dependent["id"])
        self.assertEqual(view["due"][0]["blocked"], True)
        user = life.receipt(initial["id"], expected_version=1,
                            outcome="verified", source_kind="user_confirmation",
                            evidence_ref="User tapped confirm", db_path=self.path, now=NOW)
        self.assertEqual(user["completion_state"], "user_confirmed")
        self.assertEqual(life.readiness(db_path=self.path, now=NOW)["blocked"], [])

    def test_provider_claim_not_equated_with_actual_receipt(self):
        item = self.task()
        provider = life.receipt(
            item["id"], expected_version=1, outcome="verified",
            source_kind="provider_receipt", evidence_ref="Merchant order 321",
            db_path=self.path, now=NOW
        )
        self.assertEqual(provider["completion_state"], "provider_reported")
        independent = life.receipt(
            item["id"], expected_version=2, outcome="verified",
            source_kind="sensor_readback", evidence_ref="User-enrolled sensor 7",
            db_path=self.path, now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(independent["completion_state"], "sensor_observed")
        uncertain = life.receipt(
            item["id"], expected_version=3, outcome="unknown",
            source_kind="sensor_readback", evidence_ref="Sensor went offline",
            db_path=self.path, now=NOW + timedelta(seconds=2),
        )
        self.assertEqual(uncertain["completion_state"], "outcome_unknown")
        self.assertIn(item["id"], life.readiness(db_path=self.path, now=NOW)["unknown"])

    def test_replay_guard_and_request_id_conflict(self):
        a = self.task(client_request_id="phone-001")
        b = self.task(client_request_id="phone-001")
        self.assertEqual(a["id"], b["id"])
        with self.assertRaisesRegex(ValueError, "reused"):
            self.task("Different purchase", client_request_id="phone-001")
        self.assertEqual(len(life.list_records(db_path=self.path)["records"]), 1)

    def test_stale_versions_fail_closed_no_duplicate_receipt(self):
        item = self.task()
        life.receipt(item["id"], expected_version=1, outcome="verified",
                     source_kind="user_confirmation", evidence_ref="Explicit",
                     db_path=self.path)
        with self.assertRaisesRegex(ValueError, "Stale"):
            life.receipt(item["id"], expected_version=1, outcome="verified",
                         source_kind="user_confirmation", evidence_ref="Duplicate",
                         db_path=self.path)
        self.assertEqual(len(life.list_records(db_path=self.path)["records"][0]["receipts"]), 1)

    def test_retire_does_not_transform_task_into_completed(self):
        item = self.task()
        old = life.retire(item["id"], expected_version=1, db_path=self.path)
        self.assertEqual(old["completion_state"], "not_verified")
        self.assertIsNotNone(old["retired_at"])
        self.assertEqual(life.list_records(db_path=self.path)["records"], [])
        self.assertEqual(len(life.list_records(db_path=self.path, active_only=False)["records"]), 1)

    def test_forget_deletes_one_record_and_receipts_not_dependencies(self):
        root = self.task("Initial task")
        dependent = self.task("Follow-up", depends_on=[root["id"]])
        life.receipt(
            root["id"], expected_version=1, outcome="verified",
            source_kind="user_confirmation", evidence_ref="User confirmed",
            db_path=self.path
        )
        result = life.forget(root["id"], expected_version=2, db_path=self.path)
        self.assertEqual(result["deleted_records"], 1)
        self.assertEqual(result["deleted_receipts"], 1)
        current = life.list_records(db_path=self.path)["records"]
        self.assertEqual([x["id"] for x in current], [dependent["id"]])
        self.assertEqual(life.readiness(db_path=self.path, now=NOW)["blocked"][0]["id"], dependent["id"])
        with self.assertRaises(ValueError):
            life.forget(root["id"], expected_version=2, db_path=self.path)

    def test_friction_history_can_be_cleared(self):
        life.friction("Missed the bus", db_path=self.path, now=NOW)
        self.assertEqual(life.clear_friction(db_path=self.path)["deleted_friction_events"], 1)
        self.assertEqual(life.clear_friction(db_path=self.path)["deleted_friction_events"], 0)
        self.assertEqual(life.friction_candidates(db_path=self.path, now=NOW)["candidates"], [])

    def test_only_actual_dependencies_allowed(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.task(depends_on=["not-a-task"])
        item = self.task()
        with self.assertRaises(ValueError):
            self.task(depends_on=[item["id"], item["id"]])
        self.assertEqual(len(life.list_records(db_path=self.path)["records"]), 1)

    def test_manual_asset_ledger_does_not_assert_live_quantity(self):
        asset = life.create(
            "asset", "Laptop charger", "digital", quantity=1,
            location="Desk drawer", source_ref="User inventory",
            db_path=self.path, now=NOW
        )
        self.assertEqual(asset["completion_state"], "recorded")
        self.assertEqual(asset["data"]["quantity"], 1)
        self.assertTrue(asset["data"]["created_explicitly"])
        with self.assertRaises(ValueError):
            life.create("task", "Task", "home", quantity=2, db_path=self.path)

    def test_handoff_preserves_user_context_without_operating_machine(self):
        item = self.task()
        created = life.handoff(
            "Travel planning", "Decided to prioritize a nonstop flight.",
            "Check exact seat selection.", [item["id"]],
            client_request_id="handoff-1", db_path=self.path, now=NOW
        )
        self.assertEqual(life.handoff(
            "Travel planning", "Decided to prioritize a nonstop flight.",
            "Check exact seat selection.", [item["id"]],
            client_request_id="handoff-1", db_path=self.path, now=NOW
        )["id"], created["id"])
        packet = life.resume(created["id"], db_path=self.path)
        self.assertEqual(packet["linked_records"][0]["id"], item["id"])
        self.assertEqual(packet["external_actions"], 0)
        with self.assertRaises(ValueError):
            life.resume(item["id"], db_path=self.path)

    def test_transition_checklist_is_user_created_and_idempotent(self):
        result = life.transition(
            "moving", "Apartment move", client_request_id="move-1",
            db_path=self.path, now=NOW
        )
        self.assertEqual(len(result["tasks"]), 8)
        self.assertTrue(all(x["completion_state"] == "not_verified" for x in result["tasks"]))
        self.assertFalse(result["replayed"])
        replay = life.transition(
            "moving", "Apartment move", client_request_id="move-1",
            db_path=self.path, now=NOW
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(result["transition"]["id"], replay["transition"]["id"])
        self.assertEqual(len(life.list_records(db_path=self.path)["records"]), 9)
        with self.assertRaises(ValueError):
            life.transition("new_job", "Different",
                            client_request_id="move-1", db_path=self.path)

    def test_six_transition_families_present(self):
        self.assertEqual(set(life.TRANSITIONS), {
            "moving", "travel", "new_job", "purchase", "vehicle", "health_followup"
        })

    def test_friction_recurrence_requires_three_distinct_days_and_no_action(self):
        for i in range(2):
            event = life.friction(
                "Lost my keys",
                occurred_at=(NOW - timedelta(days=1, hours=i)).isoformat(),
                db_path=self.path, now=NOW,
            )
        self.assertFalse(event["candidate_repeated_friction"])
        for day in (2, 3):
            event = life.friction(
                "  LOST   MY KEYS ",
                occurred_at=(NOW - timedelta(days=day)).isoformat(),
                db_path=self.path, now=NOW,
            )
        self.assertTrue(event["candidate_repeated_friction"])
        self.assertEqual(event["external_actions"], 0)
        candidates = life.friction_candidates(db_path=self.path, now=NOW)["candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["days"], 3)

    def test_aged_friction_does_not_count(self):
        with self.assertRaises(ValueError):
            life.friction("Lost keys", occurred_at=(NOW-timedelta(days=31)).isoformat(),
                          db_path=self.path, now=NOW)
        with self.assertRaises(ValueError):
            life.friction("Lost keys", occurred_at=(NOW+timedelta(days=1)).isoformat(),
                          db_path=self.path, now=NOW)

    def test_what_if_is_explicit_arithmetic_not_calendar_prediction(self):
        report = life.simulate_minutes(activity_minutes=300, days=3, daily_free_minutes=60)
        self.assertEqual(report["remaining_minutes"], -120)
        self.assertFalse(report["fits_assumed_time_budget"])
        self.assertFalse(report["calendar_conflicts_checked"])
        self.assertFalse(report["forecast"])
        with self.assertRaises(ValueError):
            life.simulate_minutes(activity_minutes=True, days=3, daily_free_minutes=90)

    def test_payload_bounds_and_unknown_categories(self):
        with self.assertRaises(ValueError):
            self.task("x"*300)
        with self.assertRaises(ValueError):
            life.create("task", "Something", "not-a-domain", db_path=self.path)
        with self.assertRaises(ValueError):
            life.create("task", "X", "home", description="x"*1201, db_path=self.path)
        with self.assertRaises(ValueError):
            self.task(client_request_id="x"*101)

    def test_endpoints_require_private_token_and_no_store(self):
        service = (Path(__file__).parents[1] / "jarvis_mrb/service.py").read_text()
        for route in (
            "/life/capabilities", "/life/records/create", "/life/records",
            "/life/records/receipt", "/life/records/retire",
            "/life/readiness", "/life/transition", "/life/handoff",
            "/life/records/forget", "/life/friction/clear",
            "/life/handoff/resume", "/life/friction/log",
            "/life/friction/candidates", "/life/what-if/minutes",
        ):
            self.assertIn(route, service)
        for name in (
            "life_capabilities", "life_record_create", "life_records",
            "life_record_receipt", "life_record_retire", "life_readiness",
            "life_transition", "life_handoff", "life_handoff_resume",
            "life_record_forget", "life_friction_clear",
            "life_friction_log", "life_friction_candidates", "life_what_if_minutes",
        ):
            chunk = service.split("def " + name + "(", 1)[1].split("\n\n@app.", 1)[0]
            self.assertIn("_check_mesh_auth(authorization)", chunk)
            self.assertIn('response.headers["Cache-Control"] = "private, no-store"', chunk)

    def test_capability_manifest_discloses_unimplemented_life_automation(self):
        available = life.capabilities()
        self.assertIn("universal_account_access", available["not_implemented"])
        self.assertIn("genuine_future_prediction", available["not_implemented"])
        self.assertEqual(available["external_actions"], 0)


if __name__ == "__main__":
    unittest.main()
