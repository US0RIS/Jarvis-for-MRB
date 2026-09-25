from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jarvis_mrb import conductor, reality_mesh


class ConductorMissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = patch.object(conductor, "APP_DIR", Path(self.directory.name))
        path.start()
        self.addCleanup(path.stop)
        optin = patch.dict(os.environ, {"JARVIS_CONDUCTOR_ENABLED": "1"})
        optin.start()
        self.addCleanup(optin.stop)
        probe = patch.object(reality_mesh, "probe", return_value={
            "status": "online", "capabilities": {
                "app_launch": "exact_user_tap_only",
                "screen": "session_opt_in",
            },
        })
        probe.start()
        self.addCleanup(probe.stop)
        self.actions: list[tuple[str, str]] = []

    def status(self, states: list[str], node: str = "macbook"):
        observed = datetime.now(timezone.utc) - timedelta(seconds=4)
        n = iter(states)
        def observe(which):
            self.assertEqual(which, node)
            val = next(n)
            observed_at = (observed + timedelta(seconds=len(self.actions) + 1)).isoformat()
            return {
                "node_id": node, "observed_at": observed_at,
                "source": "independent exact process enumeration",
                "apps": {"Safari": val, "Notes": val},
            }
        return observe

    def test_draft_is_no_execution_and_grant_never_persisted(self):
        with patch.object(reality_mesh, "launch_exact_mac_app",
                          side_effect=AssertionError("actuated during draft")):
            draft = conductor.plan("macbook", ["Safari"], screen=True)
        self.assertEqual(draft["status"], "planned")
        self.assertTrue(draft["one_use_grant_redeemable"])
        self.assertGreaterEqual(len(draft["one_use_grant"]), 32)
        self.assertNotIn("one_use_grant", conductor.get(draft["id"]))
        db_bytes = (Path(self.directory.name) / "conductor.sqlite3").read_bytes()
        self.assertNotIn(draft["one_use_grant"].encode(), db_bytes)
        self.assertIn(hashlib.sha256(draft["one_use_grant"].encode()).hexdigest().encode(), db_bytes)

    def test_one_time_grant_exact_node_and_apps_not_replayable(self):
        draft = conductor.plan("macbook", ["Safari"])
        g = draft["one_use_grant"]
        for node, apps, grant in [
            ("macmini", ["Safari"], g),
            ("macbook", ["Notes"], g),
            ("macbook", ["Safari"], "wrong"),
        ]:
            with self.subTest(node=node, apps=apps, grant=grant):
                with self.assertRaises(conductor.MissionBlocked):
                    conductor.execute(draft["id"], grant, node, apps)
        counter = iter(["not_running", "running"])
        def fresh(node):
            return {
                "node_id": "macbook",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source": "macOS pgrep",
                "apps": {"Safari": next(counter)},
            }
        with patch.object(reality_mesh, "exact_app_observations", side_effect=fresh):
            with patch.object(reality_mesh, "launch_exact_mac_app", return_value={
                "status": "launch_accepted_process_observed"
            }) as launch:
                result = conductor.execute(draft["id"], g, "macbook", ["Safari"])
        launch.assert_called_once_with("macbook", "Safari")
        self.assertEqual(result["status"], "verified_apps")
        self.assertEqual(result["steps"][0]["result"], "verified_running")
        self.assertNotIn("one_use_grant", result)
        with self.assertRaises(conductor.MissionBlocked):
            conductor.execute(draft["id"], g, "macbook", ["Safari"])

    def test_preexisting_process_skips_side_effect_but_verifies_new_read(self):
        draft = conductor.plan("macbook", ["Notes"])
        timestamps = iter([
            datetime.now(timezone.utc) - timedelta(seconds=1),
            datetime.now(timezone.utc) + timedelta(seconds=1),
        ])
        def observe(node):
            return {
                "node_id": node, "source": "macOS pgrep",
                "observed_at": next(timestamps).isoformat(),
                "apps": {"Notes": "running"},
            }
        with patch.object(reality_mesh, "exact_app_observations", side_effect=observe):
            with patch.object(reality_mesh, "launch_exact_mac_app",
                              side_effect=AssertionError("pre-existing app launched")):
                result = conductor.execute(
                    draft["id"], draft["one_use_grant"], "macbook", ["Notes"]
                )
        self.assertEqual(result["status"], "verified_apps")
        self.assertEqual(result["steps"][0]["result"], "already_running")
        self.assertEqual(result["steps"][0]["attempted_at"], "")

    def test_stale_or_missing_independent_observation_is_not_success(self):
        draft = conductor.plan("macbook", ["Safari"])
        earlier = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        observations = iter([
            {"node_id": "macbook", "source": "pre", "observed_at": earlier,
             "apps": {"Safari": "not_running"}},
            {"node_id": "macbook", "source": "post", "observed_at": earlier,
             "apps": {"Safari": "running"}},
        ])
        with patch.object(reality_mesh, "exact_app_observations",
                          side_effect=lambda _: next(observations)):
            with patch.object(reality_mesh, "launch_exact_mac_app",
                              return_value={"status": "launch_accepted_process_observed"}):
                outcome = conductor.execute(
                    draft["id"], draft["one_use_grant"], "macbook", ["Safari"]
                )
        self.assertEqual(outcome["status"], "partial_or_unverified")
        self.assertEqual(outcome["steps"][0]["result"], "unverified")
        self.assertEqual(outcome["steps"][0]["after_state"], "unknown")

    def test_recent_persisted_receipts_cannot_recover_raw_grants(self):
        draft = conductor.plan("macbook", ["Safari"])
        older = conductor.recent()
        self.assertEqual(older["missions"][0]["id"], draft["id"])
        self.assertFalse(older["one_use_grants_returned"])
        self.assertNotIn("one_use_grant", older["missions"][0])
        conductor.revoke(draft["id"])
        self.assertEqual(conductor.recent()["missions"][0]["status"], "revoked")

    def test_revoked_or_expired_grant_never_executes(self):
        draft = conductor.plan("macbook", ["Safari"])
        self.assertEqual(conductor.revoke(draft["id"])["status"], "revoked")
        with self.assertRaises(conductor.MissionBlocked):
            conductor.execute(
                draft["id"], draft["one_use_grant"], "macbook", ["Safari"]
            )
        second = conductor.plan("macbook", ["Safari"])
        with patch.object(conductor, "_now",
                          return_value=datetime.now(timezone.utc)
                                       + timedelta(minutes=3)):
            with self.assertRaises(conductor.MissionBlocked):
                conductor.execute(
                    second["id"], second["one_use_grant"], "macbook", ["Safari"]
                )

    def test_no_generic_remote_execution_or_unregistered_apps(self):
        for node, apps in [
            ("macbook", ["Terminal"]), ("macbook", ["Safari", "Safari"]),
            ("windows", ["PowerShell"]), ("macmini", []),
            ("macbook", ["Safari", "Notes", "Preview", "Finder"]),
            ("another-host", ["Safari"]),
        ]:
            with self.subTest(node=node, apps=apps):
                with self.assertRaises((ValueError, conductor.MissionBlocked)):
                    conductor.plan(node, apps)
        with patch.dict(os.environ, {"JARVIS_CONDUCTOR_ENABLED": "0"}):
            with self.assertRaises(conductor.MissionBlocked):
                conductor.plan("macbook", ["Safari"])

    def test_failed_launch_and_unknown_post_evidence_do_not_retry(self):
        draft = conductor.plan("macbook", ["Safari"])
        observed = iter([
            {"node_id": "macbook", "observed_at": (
                datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat(),
             "source": "before", "apps": {"Safari": "not_running"}},
            {"node_id": "macbook", "observed_at": (
                datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
             "source": "after", "apps": {"Safari": "not_running"}},
        ])
        with patch.object(reality_mesh, "exact_app_observations",
                          side_effect=lambda _: next(observed)):
            with patch.object(reality_mesh, "launch_exact_mac_app",
                              side_effect=reality_mesh.NodeUnavailable("no response")) as action:
                outcome = conductor.execute(
                    draft["id"], draft["one_use_grant"], "macbook", ["Safari"]
                )
        self.assertEqual(outcome["status"], "partial_or_unverified")
        self.assertEqual(outcome["steps"][0]["result"], "unverified")
        self.assertIn("MAY have occurred", outcome["steps"][0]["receipt"])
        action.assert_called_once()

    def test_source_http_routes_are_bearer_protected(self):
        service = (Path(__file__).parents[1] / "jarvis_mrb/service.py").read_text(encoding="utf-8")
        for name in ("plan", "execute", "status", "revoke"):
            self.assertIn('"/conductor/workstation/' + name + '"', service)
        self.assertIn("_check_mesh_auth(authorization)", service)
        self.assertIn("conductor.execute(", service)
        self.assertIn('@app.get("/conductor/workstation/recent")', service)
        node = (Path(__file__).parents[1] / "scripts/jarvis-mac-node.py").read_text(encoding="utf-8")
        self.assertIn('self.path == "/v1/apps"', node)
        self.assertIn('"/usr/bin/pgrep", "-x", name', node)
        swift = (Path(__file__).parents[1] / "ios/JarvisIOS/RealityMesh.swift").read_text(encoding="utf-8")
        self.assertIn("func executeConductor() async", swift)
        self.assertIn("func revokeConductor() async", swift)
        self.assertIn("func inspectConductorReceipt(_ id: String) async", swift)
        self.assertIn("conductorHasOneUseGrant", swift)
        self.assertIn("conductorOneUseGrant = nil", swift)
        self.assertIn("Approve these exact actions once", swift)
        self.assertIn("func executeSpokenExactApp(nodeID: String, appName: String)", swift)
        self.assertIn("conductorPlanWorkstation(", swift)
        self.assertIn("conductorExecuteWorkstation(", swift)
        voice = (Path(__file__).parents[1] / "ios/JarvisIOS/JarvisAppModel.swift").read_text(encoding="utf-8")
        self.assertIn("private static func exactSpokenAppIntent", voice)
        self.assertIn("executeSpokenExactApp(", voice)
        self.assertIn('routeReason: "iPhone exact spoken Conductor app / separately enrolled one-use action"', voice)
        settings = (Path(__file__).parents[1] / "ios/JarvisIOS/SettingsStore.swift").read_text(encoding="utf-8")
        self.assertIn('exactVoiceAppActionsEnabled = defaults.object(forKey: "jarvis.exactVoiceAppActionsEnabled") as? Bool ?? false', settings)
        privacy = (Path(__file__).parents[1] / "ios/JarvisIOS/LocalPowerFeatures.swift").read_text(encoding="utf-8")
        self.assertIn("appModel.settings.exactVoiceAppActionsEnabled = false", privacy)


if __name__ == "__main__":
    unittest.main()
