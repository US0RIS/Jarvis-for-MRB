from __future__ import annotations

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb import reality_graph_missions as store

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def iso(seconds: int = 0) -> str:
    return (NOW + timedelta(seconds=seconds)).isoformat()


def row(oid: str, seconds: int, kind: str = "order", **kwargs):
    return {
        "id": oid, "kind": kind, "source": "enrolled-client",
        "observed_at": iso(seconds), **kwargs,
    }


class RealityRewindTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = patch.object(store, "APP_DIR", Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        clock = patch.object(store, "_utc", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def mission(self) -> str:
        # Model a ten-minute-old enrollment, then ingest observations at NOW.
        with patch.object(store, "_utc", return_value=NOW - timedelta(minutes=10)):
            return store.create("Dinner delivered", deadline=iso(1800), lifetime_hours=2)["id"]

    def test_as_of_reconstruction_excludes_later_delivered_event(self):
        mid = self.mission()
        store.append(mid, [
            row("pickup", -90, status="picked_up"),
            row("delivered", -5, status="delivered", delivered=True),
        ])
        early = store.rewind(mid, at=iso(-80))
        later = store.rewind(mid, at=iso(-1))
        early_facts = {fact["id"]: fact["value"] for fact in early["graph"]["derived_facts"]}
        later_facts = {fact["id"]: fact["value"] for fact in later["graph"]["derived_facts"]}
        self.assertEqual(early["status"], "observed")
        self.assertEqual(early_facts["fact:order_status"], "picked_up")
        self.assertNotIn("fact:provider_reports_delivered", early_facts)
        self.assertEqual(later_facts["fact:provider_reports_delivered"], True)
        self.assertEqual(early["coverage"]["observations_at_or_before"], 1)
        self.assertEqual(later["coverage"]["observations_at_or_before"], 2)
        self.assertEqual(early["as_of"], iso(-80))
        self.assertEqual(early["graph"]["generated_at"], iso(-80))
        self.assertEqual(early["graph"]["evidence"][0]["source_observation_id"], "pickup")
        self.assertEqual(early["source_attestation"], "client_supplied_not_provider_verified")
        self.assertEqual(early["model_calls"], 0)
        self.assertEqual(early["action_authority"], "none")

    def test_no_evidence_returns_unknown_not_fabricated_state(self):
        mid = self.mission()
        store.append(mid, [row("later", -5, status="delivered", delivered=True)])
        result = store.rewind(mid, at=iso(-180))
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["graph"]["derived_facts"], [])
        self.assertEqual(result["coverage"]["observations_at_or_before"], 0)
        self.assertIsNone(result["coverage"]["latest_observed_at"])
        self.assertFalse(result["coverage"]["continuous_recording"])
        self.assertFalse(result["coverage"]["ingestion_time_known"])

    def test_stale_record_is_not_promoted_to_current_fact(self):
        mid = self.mission()
        # A past client ingest was permissible when it was originally sent.
        with patch.object(store, "_utc", return_value=NOW - timedelta(seconds=350)):
            store.append(mid, [row("stale", -355, status="picked_up")])
        result = store.rewind(mid, at=iso(-1))
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["graph"]["derived_facts"], [])
        self.assertEqual(result["coverage"]["observations_at_or_before"], 1)
        self.assertEqual(result["coverage"]["fresh_evidence_count"], 0)
        self.assertEqual(result["graph"]["evidence"][0]["freshness"], "stale")

    def test_as_of_limit_precedes_latest_hundred_reduction(self):
        mid = self.mission()
        for batch in range(7):
            events = [row(f"order-{batch}-{i}", -170 + batch * 20 + i, status=f"phase-{batch}-{i}")
                      for i in range(20)]
            store.append(mid, events)
        historical = store.rewind(mid, at=iso(-30))
        self.assertEqual(historical["coverage"]["observations_at_or_before"], 140)
        self.assertEqual(historical["coverage"]["observations_reduced"], 100)
        self.assertTrue(historical["coverage"]["truncated_to_recent_100"])
        facts = {r["id"]: r["value"] for r in historical["graph"]["derived_facts"]}
        self.assertEqual(facts["fact:order_status"], "phase-6-19")
        # Observation IDs and source provenance survive the graph reducer.
        self.assertEqual(len(historical["graph"]["evidence"]), 100)

    def test_time_validation_prevents_other_mission_or_future_queries(self):
        mid = self.mission()
        for at in ["2026-10-19T20:00:00", "nonsense", iso(1), iso(-601),
                   iso(10000)]:
            with self.subTest(at=at), self.assertRaises(ValueError):
                store.rewind(mid, at=at)
        with self.assertRaises(ValueError):
            store.rewind("../../etc/passwd", at=iso(-10))
        with self.assertRaises(KeyError):
            store.rewind("rg_missing", at=iso(-10))

    def test_stopped_mission_history_read_does_not_retroactively_claim_stopped(self):
        mid = self.mission()
        store.append(mid, [row("order", -5, status="picked_up")])
        self.assertEqual(store.stop(mid)["state"], "stopped")
        result = store.rewind(mid, at=iso(-1))
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["coverage"]["historical_mission_status_known"])
        self.assertEqual(result["graph"]["entities"][0]["attributes"]["status"], "unknown")
        self.assertEqual(store.snapshot(mid)["graph"]["entities"][0]["attributes"]["status"], "stopped")
        store.delete(mid)
        with self.assertRaises(KeyError):
            store.rewind(mid, at=iso(-1))

    def test_replay_does_not_write_or_mutate_source_records(self):
        mid = self.mission()
        store.append(mid, [row("first", -15, "courier", eta_at=iso(300)),
                           row("second", -10, "traffic", route_id="abc", delay_seconds=420)])
        before = copy.deepcopy(store.snapshot(mid)["graph"])
        with store._LOCK, store._db() as db:
            rows_before = [(x["id"], x["data_json"]) for x in
                           db.execute("SELECT id,data_json FROM graph_observations WHERE mission_id=? ORDER BY id", (mid,))]
        for _ in range(2):
            rewind = store.rewind(mid, at=iso(-1))
            self.assertEqual(rewind["graph"]["model_calls"], 0)
        with store._LOCK, store._db() as db:
            rows_after = [(x["id"], x["data_json"]) for x in
                          db.execute("SELECT id,data_json FROM graph_observations WHERE mission_id=? ORDER BY id", (mid,))]
        self.assertEqual(rows_before, rows_after)
        self.assertEqual(store.snapshot(mid)["graph"]["derived_facts"], before["derived_facts"])

    def test_http_token_opt_in_errors_and_no_store(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service
        mid = self.mission()
        store.append(mid, [row("r1", -5, status="picked_up")])
        client = TestClient(service.app)
        payload = {"mission_id": mid, "at": iso(-1)}
        with patch.object(service, "API_TOKEN", "test-secret"):
            self.assertEqual(client.post("/mesh/graph/missions/rewind", json=payload).status_code, 401)
            self.assertEqual(client.post("/mesh/graph/missions/rewind", json=payload,
                                         headers={"Authorization": "Bearer wrong"}).status_code, 401)
            headers = {"Authorization": "Bearer test-secret"}
            good = client.post("/mesh/graph/missions/rewind", json=payload, headers=headers)
            self.assertEqual(good.status_code, 200, good.text)
            self.assertEqual(good.headers["cache-control"], "private, no-store")
            self.assertEqual(good.json()["status"], "observed")
            self.assertEqual(client.post("/mesh/graph/missions/rewind",
                                         json={**payload, "at": iso(1)}, headers=headers).status_code, 422)
            self.assertEqual(client.post("/mesh/graph/missions/rewind",
                                         json={**payload, "mission_id": "rg_missing"}, headers=headers).status_code, 404)
            with patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "0"}):
                self.assertEqual(client.post("/mesh/graph/missions/rewind", json=payload,
                                             headers=headers).status_code, 503)
        with patch.object(service, "API_TOKEN", None):
            self.assertEqual(client.post("/mesh/graph/missions/rewind", json=payload).status_code, 503)


if __name__ == "__main__":
    unittest.main()
