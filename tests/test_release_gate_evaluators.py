from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jarvis_mrb.cloud_cognition as cloud
import jarvis_mrb.release_gates as gates
import jarvis_mrb.release_soak as soak
import jarvis_mrb.world_armor_full as full
import jarvis_mrb.world_model as world_model

SHA = "e" * 40
LAMP = "0f8e2c1a-3b4d-4e5f-8a9b-0c1d2e3f4a5b"


class EvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        saved = (world_model.APP_DIR, world_model.DB_PATH, full.FULL_STORE)
        self.addCleanup(lambda: (setattr(world_model, "APP_DIR", saved[0]),
                                 setattr(world_model, "DB_PATH", saved[1]),
                                 setattr(full, "FULL_STORE", saved[2])))
        world_model.APP_DIR = base
        world_model.DB_PATH = base / "world_model.sqlite3"
        world_model.status()
        full.FULL_STORE = base / "full.sqlite3"
        for item in (patch.object(gates, "LEDGER_PATH", base / "ledger.sqlite3"),
                     patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED": "1", "JARVIS_WORLD_ARMOR_FULL_ENABLED": "1"})):
            item.start()
            self.addCleanup(item.stop)
        import jarvis_mrb.release_gate_evaluators as evaluators  # registers
        self.evaluators = evaluators
        self.session = {
            "id": "release-session:test", "gate": "C19", "sha": SHA,
            "started_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "baseline": {"world_event_id": 0, "service_boot_id": "boot-a"},
        }
        self.session["started_at_local"] = datetime.fromisoformat(self.session["started_at"]).astimezone().isoformat()

    def test_all_machine_evaluated_gates_are_registered(self) -> None:
        for gate in ("C00", "C08", "C12", "C16", "C17", "C18", "C19", "C21"):
            self.assertIn(gate, gates.EVALUATORS)

    def test_c19_requires_readback_later_refusal_and_a_failure_case(self) -> None:
        checks = {c["name"]: c["passed"] for c in self.evaluators._c19(self.session)}
        self.assertFalse(any(checks.values()))
        with patch("jarvis_mrb.event_bus.companion_events.publish"):
            grant = full.create_presence_grant(actuator_kind="homekit_light", target_id=LAMP,
                                               target_label="Desk Lamp", lifetime_seconds=120, max_uses=1)
            ok = full.dispatch_presence(grant["id"], desired_on=True)
            full.record_presence_receipt(ok["request_id"], status="verified_reported_state", message="Verified")
            with self.assertRaises(ValueError):
                full.dispatch_presence(grant["id"], desired_on=False)  # exhausted
            second = full.create_presence_grant(actuator_kind="homekit_light", target_id=LAMP,
                                                target_label="Desk Lamp", lifetime_seconds=120, max_uses=1)
            bad = full.dispatch_presence(second["id"], desired_on=False)
            full.record_presence_receipt(bad["request_id"], status="blocked", message="Accessory unreachable")
        checks = {c["name"]: c["passed"] for c in self.evaluators._c19(self.session)}
        self.assertTrue(all(checks.values()), checks)

    def test_c12_needs_every_tier_real_result_fallback_redaction_and_protected_proposal(self) -> None:
        with patch.object(cloud, "_telemetry_path", return_value=Path(self.tmp.name) / "tele.sqlite3"):
            checks = {c["name"]: c["passed"] for c in self.evaluators._c12(self.session)}
            self.assertFalse(any(checks.values()))
            now = 0
            for tier, redactions in (("deterministic", 0), ("local", 0), ("cloud", 1)):
                cloud._emit_telemetry({"at": now or int(datetime.now().timestamp()), "event": "route",
                                       "tier": tier, "redactions": redactions, "request_fingerprint": tier})
            cloud._emit_telemetry({"at": int(datetime.now().timestamp()), "event": "cloud_result", "provider": "groq"})
            cloud._emit_telemetry({"at": int(datetime.now().timestamp()), "event": "execution_outcome",
                                   "proposal_tool": "calendar.create", "execution_ok": True})
            fallback = cloud.record_fallback("missing-task", "URLError: offline")
            self.assertFalse(fallback["task_known"])
            checks = {c["name"]: c["passed"] for c in self.evaluators._c12(self.session)}
        self.assertTrue(all(checks.values()), checks)

    def test_fallback_consumes_pending_task_so_late_result_cannot_resolve(self) -> None:
        with patch.object(cloud, "_telemetry_path", return_value=Path(self.tmp.name) / "tele.sqlite3"):
            prepared = cloud.prepare_cloud_task("cloud: compare two plans", session_id="s", force="cloud")
            self.assertTrue(prepared["task_id"])
            self.assertTrue(cloud.record_fallback(prepared["task_id"], "HTTP 429")["task_known"])
            with self.assertRaises(ValueError):
                cloud.consume_cloud_task(prepared["task_id"])

    def test_c21_soak_evaluator_uses_only_recorded_samples(self) -> None:
        start = datetime.now(timezone.utc) - timedelta(hours=25)

        def sample(minutes: int, *, healthy: bool = True, verified: int = 0, boot: str = "b1") -> dict:
            return {
                "sampled_at": (start + timedelta(minutes=minutes)).isoformat(),
                "service": {"reachable": healthy, "code_sha": SHA, "boot_id": boot},
                "health": {"status": "ok", "world_model": "ready", "proactive_monitor": "running"},
                "world": {"active_goal_ids": ["ds:1"], "verifications": {"verified": verified},
                          "secret_like_recent_events": 0, "active_wake_watches": 1},
                "push": {"pending": 0, "max_pending": 2000},
                "world_armor_live": {"heartbeat_age_seconds": 20},
                "storage_bytes": {"data_dir_total": 1000 + minutes},
                "phones_last_seen": [{"device_id": "d", "build_sha": SHA, "last_seen": str(minutes // 60)}],
            }
        session = {**self.session, "id": "release-session:soak", "gate": "C21"}
        with closing(soak._ledger()) as conn, conn:
            for minute in range(0, 25 * 60 + 1, 20):
                item = sample(minute, verified=1 if minute > 600 else 0,
                              healthy=not (300 <= minute < 320), boot="b1" if minute < 310 else "b2")
                conn.execute("INSERT INTO release_soak_samples(session_id,sampled_at,sample_json) VALUES(?,?,?)",
                             (session["id"], item["sampled_at"], json.dumps(item)))
        checks = {c["name"]: c for c in soak.evaluate(session)}
        self.assertTrue(all(c["passed"] for c in checks.values()),
                        {k: v["evidence"] for k, v in checks.items() if not v["passed"]})
        short = {**session, "id": "release-session:short"}
        with closing(soak._ledger()) as conn, conn:
            for minute in (0, 20):
                item = sample(minute)
                conn.execute("INSERT INTO release_soak_samples(session_id,sampled_at,sample_json) VALUES(?,?,?)",
                             (short["id"], item["sampled_at"], json.dumps(item)))
        self.assertFalse(all(c["passed"] for c in soak.evaluate(short)))


if __name__ == "__main__":
    unittest.main()
