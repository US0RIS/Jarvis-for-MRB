from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb.reality_graph import build_mission_graph
from jarvis_mrb.reality_shadow import simulate_eta_branches

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def snapshot(*, eta_offset=600, observed_offset=-5, deadline_offset=900, delivered=False):
    observations = [{"kind": "courier", "source": "client-route", "mission_id": "mission-A",
                     "observed_at": (NOW + timedelta(seconds=observed_offset)).isoformat(),
                     "eta_at": (NOW + timedelta(seconds=eta_offset)).isoformat()}]
    if delivered:
        observations.append({"kind": "order", "source": "client-order", "mission_id": "mission-A",
                             "observed_at": (NOW - timedelta(seconds=4)).isoformat(), "delivered": True})
    graph = build_mission_graph({"id": "mission-A", "goal": "Package arrives",
                                 "deadline": (NOW + timedelta(seconds=deadline_offset)).isoformat(),
                                 "status": "active"}, observations, now=NOW)
    graph["source_attestation"] = "client_supplied_not_provider_verified"
    return graph


class RealityShadowTests(unittest.TestCase):
    def test_branches_are_isolated_conditionals_with_real_evidence_provenance(self):
        graph = snapshot()
        original = copy.deepcopy(graph)
        out = simulate_eta_branches(graph, [
            {"id": "leave_earlier", "eta_shift_minutes": -5},
            {"id": "wait", "eta_shift_minutes": 10},
        ], now=NOW)
        self.assertEqual(graph, original)
        self.assertEqual(out["status"], "hypothetical")
        self.assertEqual(out["baseline"]["deadline_margin_seconds"], 300)
        self.assertEqual([x["deadline_margin_seconds"] for x in out["branches"]], [600, -300])
        self.assertEqual(out["branches"][1]["conditional_assessment"], "reported_eta_after_deadline")
        self.assertEqual(out["baseline"]["evidence"]["source"], "client-route")
        self.assertEqual(out["baseline"]["evidence"]["source_attestation"], "client_supplied_not_provider_verified")
        self.assertTrue(all(x["prediction"] is False for x in out["branches"]))
        self.assertEqual(out["action_authority"], "none")
        self.assertFalse(out["persistent"])
        self.assertEqual(out["model_calls"], 0)

    def test_no_eta_never_fabricates_outcomes(self):
        graph = snapshot(observed_offset=-1000)
        result = simulate_eta_branches(graph, [{"id": "delay", "eta_shift_minutes": 15}], now=NOW)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["branches"][0]["deadline_margin_seconds"])
        self.assertEqual(result["branches"][0]["conditional_assessment"], "unknown")

    def test_stale_snapshot_and_forged_freshness_do_not_restore_confidence(self):
        graph = snapshot()
        graph["generated_at"] = (NOW - timedelta(minutes=10)).isoformat()
        self.assertEqual(simulate_eta_branches(graph, [{"id": "a", "eta_shift_minutes": 0}], now=NOW)["status"], "insufficient_evidence")
        graph = snapshot()
        graph["evidence"][0]["observed_at"] = (NOW - timedelta(hours=1)).isoformat()
        graph["evidence"][0]["freshness"] = "fresh"
        self.assertEqual(simulate_eta_branches(graph, [{"id": "a", "eta_shift_minutes": 0}], now=NOW)["status"], "insufficient_evidence")

    def test_delivered_expired_and_stopped_missions_not_simulated(self):
        cases = [snapshot(delivered=True), snapshot(deadline_offset=-10), snapshot()]
        cases[-1]["entities"][0]["attributes"]["status"] = "stopped"
        for graph in cases:
            result = simulate_eta_branches(graph, [{"id": "wait", "eta_shift_minutes": 15}], now=NOW)
            self.assertEqual(result["status"], "insufficient_evidence")
            self.assertIsNone(result["branches"][0]["deadline_margin_seconds"])

    def test_foreign_mission_evidence_cannot_supply_eta(self):
        graph = build_mission_graph({"id": "mission-A", "deadline": (NOW + timedelta(minutes=20)).isoformat()},
                                    [{"kind": "courier", "mission_id": "mission-B", "source": "caller",
                                      "observed_at": NOW.isoformat(), "eta_at": NOW.isoformat()}], now=NOW)
        result = simulate_eta_branches(graph, [{"id": "other", "eta_shift_minutes": 1}], now=NOW)
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_branch_contract_rejects_execution_or_unbounded_inputs(self):
        graph = snapshot()
        invalid = [[], [{}], [{"id": "x", "eta_shift_minutes": True}],
                   [{"id": "x", "eta_shift_minutes": 1.5}],
                   [{"id": "x", "eta_shift_minutes": 121}],
                   [{"id": "x", "eta_shift_minutes": 0, "send_message": True}],
                   [{"id": "x", "eta_shift_minutes": 0}]*2,
                   [{"id": str(i), "eta_shift_minutes": 0} for i in range(7)]]
        for branches in invalid:
            with self.subTest(branches=branches), self.assertRaises(ValueError):
                simulate_eta_branches(graph, branches, now=NOW)
        with self.assertRaises(ValueError):
            simulate_eta_branches({**graph, "action_authority": "write"}, [{"id": "a", "eta_shift_minutes": 0}], now=NOW)
        with self.assertRaises(ValueError):
            simulate_eta_branches(graph, [{"id": "a", "eta_shift_minutes": 0}], now=datetime(2026, 10, 19))

    def test_private_ephemeral_endpoint_enforces_token_and_no_store(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service
        client = TestClient(service.app)
        clock = datetime.now(timezone.utc)
        body = {"mission": {"id": "mission-A", "goal": "Package arrives",
                            "deadline": (clock + timedelta(minutes=20)).isoformat()},
                "observations": [{"kind": "courier", "source": "caller",
                                  "observed_at": clock.isoformat(),
                                  "eta_at": (clock + timedelta(minutes=15)).isoformat()}],
                "branches": [{"id": "delay", "eta_shift_minutes": 5}]}
        with patch.object(service, "API_TOKEN", "test-secret"):
            self.assertEqual(client.post("/mesh/graph/mission/shadow", json=body).status_code, 401)
            self.assertEqual(client.post("/mesh/graph/mission/shadow", json=body, headers={"Authorization": "Bearer wrong"}).status_code, 401)
            response = client.post("/mesh/graph/mission/shadow", json=body, headers={"Authorization": "Bearer test-secret"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["cache-control"], "private, no-store")
            self.assertEqual(response.json()["status"], "hypothetical")
            self.assertEqual(response.json()["action_authority"], "none")
        with patch.object(service, "API_TOKEN", None):
            self.assertEqual(client.post("/mesh/graph/mission/shadow", json=body).status_code, 503)

    def test_stored_mission_endpoint_respects_opt_in_and_never_writes(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service, reality_graph_missions as store
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(store, "APP_DIR", Path(directory)), \
             patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "1"}), \
             patch.object(service, "API_TOKEN", "test-secret"):
            clock = datetime.now(timezone.utc)
            mission = store.create("Package delivered", deadline=(clock + timedelta(minutes=20)).isoformat())
            mid = mission["id"]
            store.append(mid, [{"id": "courier-1", "kind": "courier", "source": "enrolled-client",
                                "observed_at": clock.isoformat(),
                                "eta_at": (clock + timedelta(minutes=15)).isoformat()}])
            before = store.snapshot(mid)["graph"]["observation_count"]
            client = TestClient(service.app)
            body = {"mission_id": mid, "branches": [{"id": "five_late", "eta_shift_minutes": 5}]}
            response = client.post("/mesh/graph/missions/shadow", json=body,
                                   headers={"Authorization": "Bearer test-secret"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["cache-control"], "private, no-store")
            self.assertEqual(response.json()["status"], "hypothetical")
            self.assertEqual(store.snapshot(mid)["graph"]["observation_count"], before)
            with patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "0"}):
                self.assertEqual(client.post("/mesh/graph/missions/shadow", json=body,
                                             headers={"Authorization": "Bearer test-secret"}).status_code, 503)
            self.assertEqual(client.post("/mesh/graph/missions/shadow", json={**body, "mission_id": "rg_missing"},
                                         headers={"Authorization": "Bearer test-secret"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
