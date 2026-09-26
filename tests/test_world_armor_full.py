from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from jarvis_mrb import world_armor_full as full

NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
FLAGS = {
    "JARVIS_WORLD_ARMOR_ENABLED": "1",
    "JARVIS_WORLD_ARMOR_FULL_ENABLED": "1",
}


def live_page():
    return {
        "events": [
            {
                "seq": 1,
                "kind": "movement_receipt",
                "subsystem": "movement",
                "source_id": "air-la",
                "status": "ok",
                "priority": "info",
                "created_at": NOW.isoformat(),
                "summary": "movement",
                "payload": {"observations_saved": 7},
            },
            {
                "seq": 2,
                "kind": "camera_receipt",
                "subsystem": "camera",
                "source_id": "camera-1",
                "status": "ok",
                "priority": "info",
                "created_at": (NOW + timedelta(minutes=1)).isoformat(),
                "summary": "camera",
                "payload": {"evidence_saved": True},
            },
            {
                "seq": 3,
                "kind": "attention_notice",
                "subsystem": "watch",
                "source_id": "watch-1",
                "status": "attention",
                "priority": "warning",
                "created_at": (NOW + timedelta(minutes=2)).isoformat(),
                "summary": "attention",
                "payload": {},
            },
        ],
        "next_seq": 3,
        "oldest_seq": 1,
        "latest_seq": 3,
        "replay_gap": False,
        "truncated": False,
    }


class WorldArmorFullScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.db = Path(self.temp.name) / "full.sqlite3"
        self.flags = patch.dict("os.environ", FLAGS, clear=False)
        self.flags.start()

    def tearDown(self):
        self.flags.stop()
        self.temp.cleanup()

    def test_full_scope_status_keeps_all_five_layers(self):
        with patch(
            "jarvis_mrb.world_armor_live.status",
            return_value={"running": True, "heartbeat_age_seconds": 1},
        ), patch(
            "jarvis_mrb.world_armor_distributed.available_workers",
            return_value={"workers": [{"id": "windows"}]},
        ):
            value = full.full_status(db_path=self.db)
        self.assertTrue(value["enabled"])
        self.assertEqual(set(value["layers"]), {
            "reality_browser", "synthetic_senses", "causal_debugger",
            "parallel_existence", "presence",
        })
        self.assertFalse(value["source_authority_expansion"])
        self.assertFalse(value["arbitrary_rpc"])
        self.assertFalse(value["person_tracking"])

    def test_reality_browser_is_provenance_preserving_and_non_interpolating(self):
        with patch("jarvis_mrb.world_armor_live.events", return_value=live_page()):
            result = full.reality_browser(
                start_at=NOW.isoformat(),
                end_at=(NOW + timedelta(minutes=3)).isoformat(),
            )
        self.assertEqual(len(result["timeline"]), 3)
        self.assertTrue(result["missing_time_is_unknown"])
        self.assertFalse(result["interpolation_performed"])
        self.assertEqual(result["external_actions"], 0)
        self.assertEqual(
            result["timeline"][0]["provenance"]["live_event_seq"], 1
        )

    def test_synthetic_senses_are_explicitly_derived(self):
        with patch("jarvis_mrb.world_armor_live.events", return_value=live_page()):
            result = full.synthetic_senses()
        by_id = {row["id"]: row for row in result["signals"]}
        self.assertEqual(
            by_id["synthetic:movement_positions"]["value"], 7
        )
        self.assertEqual(
            by_id["synthetic:camera_changes"]["value"], 1
        )
        self.assertEqual(by_id["synthetic:attention"]["value"], 1)
        self.assertTrue(all(x["derived"] for x in result["signals"]))
        self.assertTrue(all(not x["world_fact"] for x in result["signals"]))

    def test_causal_debugger_never_promotes_correlation_to_cause(self):
        graph = {
            "query_id": "q1",
            "source_coverage": {"nws": {"status": "ok"}},
            "unavailable_or_unchecked_sources": ["camera"],
            "hypotheses": [{
                "id": "hyp:1",
                "claim": "A and B were close in source time.",
                "supporting_observation_ids": ["a", "b"],
                "contradicting_observation_ids": [],
                "independent_lineage_count": 2,
                "missing_evidence": ["mechanism"],
                "alternative_explanations": ["chance"],
            }],
        }
        with patch(
            "jarvis_mrb.world_armor_hypotheses.build_evidence_graph",
            return_value=graph,
        ):
            result = full.causal_debugger(
                "f" * 32,
                start_at=NOW.isoformat(),
                end_at=(NOW + timedelta(hours=1)).isoformat(),
            )
        report = result["reports"][0]
        self.assertEqual(report["status"], "mechanism_unverified")
        self.assertFalse(report["causal_conclusion"])
        self.assertFalse(report["intervention_performed"])
        self.assertEqual(result["causal_claims"], 0)
        self.assertTrue(all(
            not item["action_authority"]
            for item in report["observational_tests"]
        ))

    def test_presence_uses_short_lived_exact_homekit_grant_and_separate_receipt(self):
        target = str(uuid4())
        grant = full.create_presence_grant(
            actuator_kind="homekit_light",
            target_id=target,
            target_label="Desk light",
            lifetime_seconds=60,
            db_path=self.db,
            now=NOW,
        )
        emitted = []
        with patch(
            "jarvis_mrb.event_bus.companion_events.publish",
            side_effect=lambda value: emitted.append(value),
        ):
            receipt = full.dispatch_presence(
                grant["id"], desired_on=True, db_path=self.db, now=NOW
            )
        self.assertEqual(receipt["status"], "dispatched_unverified")
        self.assertFalse(receipt["physical_effect_verified"])
        self.assertEqual(emitted[0]["type"], "world_armor_presence_request")
        self.assertEqual(emitted[0]["target_id"], target)
        completed = full.record_presence_receipt(
            receipt["request_id"],
            status="verified_reported_state",
            message="Verified in Apple Home: Desk light reports on.",
            db_path=self.db,
            now=NOW + timedelta(seconds=2),
        )
        self.assertTrue(completed["physical_effect_verified"])
        self.assertEqual(
            completed["verification_basis"],
            "iphone_homekit_fresh_accessory_readback",
        )

    def test_presence_rejects_unknown_actuator_and_expired_or_revoked_grant(self):
        with self.assertRaises(ValueError):
            full.create_presence_grant(
                actuator_kind="arbitrary_http",
                target_id=str(uuid4()),
                target_label="No",
                db_path=self.db,
                now=NOW,
            )
        grant = full.create_presence_grant(
            actuator_kind="homekit_light",
            target_id=str(uuid4()),
            target_label="Lamp",
            lifetime_seconds=15,
            db_path=self.db,
            now=NOW,
        )
        full.revoke_presence_grant(grant["id"], db_path=self.db)
        with self.assertRaises(ValueError):
            full.dispatch_presence(
                grant["id"], desired_on=True, db_path=self.db, now=NOW
            )

    def test_parallel_existence_runs_bounded_read_only_tasks(self):
        with patch.object(
            full, "reality_browser", return_value={"timeline": []}
        ), patch.object(
            full, "synthetic_senses", return_value={"signals": []}
        ), patch.object(
            full, "_worker_fabric_snapshot", return_value={"workers": []}
        ), patch.object(
            full, "_live_status_snapshot", return_value={"running": True}
        ):
            result = full.parallel_existence(db_path=self.db)
        self.assertEqual(result["parallel_task_count"], 4)
        self.assertEqual(result["ok_count"], 4)
        self.assertEqual(result["degraded_count"], 0)
        self.assertFalse(result["remote_authority_expansion"])
        self.assertEqual(result["external_actions"], 0)


if __name__ == "__main__":
    unittest.main()
