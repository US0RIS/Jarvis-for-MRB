from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb import reality_graph_missions as store
from jarvis_mrb.reality_diff import diff

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def iso(seconds=0):
    return (NOW + timedelta(seconds=seconds)).isoformat()


def row(ident, seconds, *, kind="order", **values):
    return {"id": ident, "kind": kind, "source": "user-reported-source",
            "observed_at": iso(seconds), **values}


class RealityDiffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for cm in (patch.object(store, "APP_DIR", Path(tmp.name)),
                   patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "1",
                                          "JARVIS_WORLD_ASSERTIONS_ENABLED": "0"}),
                   patch.object(store, "_utc", return_value=NOW)):
            cm.start()
            self.addCleanup(cm.stop)

    def mission(self):
        with patch.object(store, "_utc", return_value=NOW - timedelta(minutes=10)):
            return store.create("Keep a delivery on track", deadline=iso(1800))["id"]

    def test_meaningful_reported_state_transition_with_provenance(self):
        mid = self.mission()
        store.append(mid, [row("a", -90, status="picked_up"),
                           row("b", -5, status="delivered", delivered=True)])
        before = copy.deepcopy(store.snapshot(mid)["graph"])
        result = diff(mid, before=iso(-80), after=iso(-1))
        change = next(x for x in result["changes"] if x["fact"] == "reported_order_status")
        self.assertEqual(change["kind"], "reported_change")
        self.assertEqual(change["before"]["value"], "picked_up")
        self.assertEqual(change["after"]["value"], "delivered")
        self.assertEqual(change["before"]["observations"][0]["id"], "a")
        self.assertEqual(change["after"]["observations"][0]["id"], "b")
        self.assertFalse(change["physical_change_verified"])
        self.assertEqual(result["source_attestation"], "client_supplied_not_provider_verified")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["action_authority"], "none")
        self.assertFalse(result["persistent"])
        self.assertEqual(store.snapshot(mid)["graph"]["derived_facts"], before["derived_facts"])

    def test_new_evidence_is_not_mistaken_for_physical_appearance(self):
        mid = self.mission()
        store.append(mid, [row("a", -5, status="picked_up")])
        result = diff(mid, before=iso(-100), after=iso(-1))
        self.assertEqual(result["status"], "changes_reported")
        self.assertEqual(result["changes"][0]["kind"], "newly_supported")
        self.assertIsNone(result["changes"][0]["before"])
        self.assertIn("not that an object appeared", result["limitations"][1])

    def test_stale_evidence_not_interpreted_as_disappearance(self):
        mid = self.mission()
        with patch.object(store, "_utc", return_value=NOW - timedelta(seconds=300)):
            store.append(mid, [row("old", -301, status="picked_up")])
        result = diff(mid, before=iso(-299), after=iso(0))
        self.assertEqual(result["changes"][0]["kind"], "no_recent_evidence")
        self.assertIsNone(result["changes"][0]["after"])
        self.assertFalse(result["changes"][0]["physical_change_verified"])

    def test_same_report_is_not_a_change(self):
        mid = self.mission()
        store.append(mid, [row("only", -80, status="picked_up")])
        result = diff(mid, before=iso(-60), after=iso(-1))
        self.assertEqual(result["status"], "no_supported_change")
        self.assertEqual(result["changes"], [])

    def test_no_evidence_explicit_unknown(self):
        mid = self.mission()
        out = diff(mid, before=iso(-90), after=iso(-1))
        self.assertEqual(out["status"], "insufficient_evidence")
        self.assertEqual(out["changes"], [])

    def test_event_time_not_ingestion_time_is_disclosed(self):
        mid = self.mission()
        store.append(mid, [row("late-supplied", -30, status="picked_up")])
        result = diff(mid, before=iso(-20), after=iso(-1))
        self.assertFalse(result["coverage"]["before"]["ingestion_time_known"])
        self.assertFalse(result["coverage"]["after"]["continuous_recording"])

    def test_rejects_unbounded_or_foreign_mission_access(self):
        mid = self.mission()
        for a, b in [(iso(0), iso(-10)), (iso(-5), iso(-5)), (iso(-5), iso(5)),
                     ("2026-10-19T20:00:00", iso(-1)), (iso(-601), iso(-1))]:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                diff(mid, before=a, after=b)
        with self.assertRaises(ValueError):
            diff("../../data", before=iso(-30), after=iso(-1))
        with self.assertRaises(KeyError):
            diff("rg_missing", before=iso(-30), after=iso(-1))
        with patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "0"}):
            with self.assertRaises(store.GraphUnavailable):
                diff(mid, before=iso(-30), after=iso(-1))

    def test_private_endpoint_requires_token_and_no_store(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service
        mid = self.mission()
        store.append(mid, [row("r", -5, status="delivered")])
        client = TestClient(service.app)
        body = {"mission_id": mid, "before": iso(-90), "after": iso(-1)}
        with patch.object(service, "API_TOKEN", "secret"):
            self.assertEqual(client.post("/mesh/graph/missions/diff", json=body).status_code, 401)
            self.assertEqual(client.post("/mesh/graph/missions/diff", json=body,
                             headers={"Authorization": "Bearer wrong"}).status_code, 401)
            headers = {"Authorization": "Bearer secret"}
            good = client.post("/mesh/graph/missions/diff", json=body, headers=headers)
            self.assertEqual(good.status_code, 200, good.text)
            self.assertEqual(good.headers["cache-control"], "private, no-store")
            self.assertEqual(good.json()["action_authority"], "none")
            self.assertEqual(client.post("/mesh/graph/missions/diff",
                             json={**body, "before": iso(3)}, headers=headers).status_code, 422)
            self.assertEqual(client.post("/mesh/graph/missions/diff",
                             json={**body, "mission_id": "rg_missing"}, headers=headers).status_code, 404)
        with patch.object(service, "API_TOKEN", None):
            self.assertEqual(client.post("/mesh/graph/missions/diff", json=body).status_code, 503)


if __name__ == "__main__":
    unittest.main()
