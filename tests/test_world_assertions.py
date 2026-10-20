from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb import reality_graph_missions as store
from jarvis_mrb import world_assertions as assertions

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def iso(seconds=0):
    return (NOW + timedelta(seconds=seconds)).isoformat()


def row(ident, seconds, *, kind="order", **values):
    return {"id": ident, "kind": kind, "source": "test-client",
            "observed_at": iso(seconds), **values}


class WorldAssertionsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for cm in (patch.object(store, "APP_DIR", Path(tmp.name)),
                   patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "1",
                                          "JARVIS_WORLD_ASSERTIONS_ENABLED": "1"}),
                   patch.object(store, "_utc", return_value=NOW)):
            cm.start()
            self.addCleanup(cm.stop)

    def mission(self):
        with patch.object(store, "_utc", return_value=NOW - timedelta(minutes=10)):
            return store.create("Track the shipment", deadline=iso(1800))["id"]

    def test_enrolled_predicate_updates_on_append_without_actions(self):
        mid = self.mission()
        a = assertions.enroll(mid, {"kind": "order_status_equals", "expected": "delivered"})
        self.assertEqual(a["state"], "unknown")
        self.assertEqual(a["action_authority"], "none")
        store.append(mid, [row("first", -50, status="picked_up")])
        check = assertions.check(mid)
        self.assertEqual(check["assertions"][0]["state"], "violated")
        self.assertIsNotNone(check["assertions"][0]["suggested_review"])
        self.assertFalse(check["assertions"][0]["intervention_executed"])
        self.assertFalse(check["continuous_monitoring"])
        store.append(mid, [row("second", -5, status="delivered")])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")
        transitions = assertions.history(mid, a["id"])["transitions"]
        self.assertEqual([(t["from"], t["to"]) for t in transitions],
                         [("violated", "met"), ("unknown", "violated")])
        self.assertEqual(transitions[0]["evidence"]["observation_id"], "second")
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")
        self.assertEqual(len(assertions.history(mid, a["id"])["transitions"]), 2)

    def test_stale_latest_evidence_is_unknown_not_replaced_by_older_good(self):
        mid = self.mission()
        a = assertions.enroll(mid, {"kind": "order_status_equals", "expected": "delivered"})
        store.append(mid, [row("good", -50, status="delivered"),
                           row("later", -5, status="pending")])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "violated")
        with patch.object(store, "_utc", return_value=NOW + timedelta(minutes=6)):
            self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "unknown")
        self.assertEqual(assertions.history(mid, a["id"])["transitions"][0]["to"], "unknown")

    def test_exact_route_scoping_and_numeric_threshold(self):
        mid = self.mission()
        a = assertions.enroll(mid, {"kind": "route_delay_at_most",
                                     "route_id": "route-A", "max_seconds": 180})
        store.append(mid, [row("other", -5, kind="traffic",
                               route_id="route-B", delay_seconds=4000)])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "unknown")
        store.append(mid, [row("ours", -4, kind="traffic",
                               route_id="route-A", delay_seconds=600)])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "violated")
        self.assertEqual(assertions.check(mid)["assertions"][0]["evidence"]["observation_id"], "ours")
        store.append(mid, [row("resolved", -3, kind="traffic",
                               route_id="route-A", delay_seconds=60)])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")
        self.assertEqual(a["definition"]["route_id"], "route-A")

    def test_eta_predicate_uses_fresh_report_and_exact_mission_deadline(self):
        mid = self.mission()
        a = assertions.enroll(mid, {"kind": "reported_eta_before_deadline"})
        store.append(mid, [row("later", -20, kind="courier", eta_at=iso(2100))])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "violated")
        store.append(mid, [row("earlier", -5, kind="courier", eta_at=iso(1500))])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")
        self.assertEqual(a["definition"], {"kind": "reported_eta_before_deadline"})

    def test_validation_and_per_mission_limit(self):
        mid = self.mission()
        invalid = [
            {}, {"kind": "execute_command", "command": "unlock"}, {"kind": ["order_status_equals"]},
            {"kind": "order_status_equals", "expected": ""},
            {"kind": "order_status_equals", "expected": "delivered", "notify": True},
            {"kind": "route_delay_at_most", "route_id": "../etc", "max_seconds": 30},
            {"kind": "route_delay_at_most", "route_id": "a", "max_seconds": True},
            {"kind": "route_delay_at_most", "route_id": "a", "max_seconds": -1},
            {"kind": "reported_eta_before_deadline", "auto_fix": True},
        ]
        for definition in invalid:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                assertions.enroll(mid, definition)
        for i in range(12):
            assertions.enroll(mid, {"kind": "order_status_equals", "expected": f"status-{i}"})
        with self.assertRaises(store.GraphUnavailable):
            assertions.enroll(mid, {"kind": "order_status_equals", "expected": "extra"})

    def test_independent_feature_switch_fail_closed_and_reenable(self):
        mid = self.mission()
        with patch.dict(os.environ, {"JARVIS_WORLD_ASSERTIONS_ENABLED": "0"}):
            with self.assertRaises(store.GraphUnavailable):
                assertions.enroll(mid, {"kind": "order_status_equals", "expected": "done"})
            with self.assertRaises(store.GraphUnavailable):
                assertions.check(mid)
        a = assertions.enroll(mid, {"kind": "order_status_equals", "expected": "done"})
        with patch.dict(os.environ, {"JARVIS_WORLD_ASSERTIONS_ENABLED": "0"}):
            store.append(mid, [row("new", -5, status="done")])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")
        self.assertEqual(assertions.history(mid, a["id"])["transitions"][0]["to"], "met")
        with patch.dict(os.environ, {"JARVIS_REALITY_GRAPH_MISSIONS_ENABLED": "0"}):
            with self.assertRaises(store.GraphUnavailable):
                assertions.check(mid)

    def test_revoke_is_scoped_and_mission_delete_cascades(self):
        m1, m2 = self.mission(), self.mission()
        a = assertions.enroll(m1, {"kind": "order_status_equals", "expected": "done"})
        with self.assertRaises(KeyError):
            assertions.revoke(m2, a["id"])
        with self.assertRaises(KeyError):
            assertions.history(m2, a["id"])
        self.assertEqual(assertions.revoke(m1, a["id"])["state"], "revoked")
        self.assertEqual(assertions.check(m1)["assertions"], [])
        a = assertions.enroll(m1, {"kind": "order_status_equals", "expected": "done"})
        store.delete(m1)
        with assertions.missions._db() as db:
            assertions._schema(db)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM world_assertions WHERE mission_id=?",
                                        (m1,)).fetchone()[0], 0)
        with self.assertRaises(KeyError):
            assertions.check(m1)
        self.assertEqual(assertions.check(m2)["assertions"], [])

    def test_stopped_and_expired_mission_not_silently_monitored(self):
        mid = self.mission()
        assertions.enroll(mid, {"kind": "order_status_equals", "expected": "done"})
        store.stop(mid)
        with self.assertRaises(store.GraphUnavailable):
            assertions.check(mid)
        with self.assertRaises(store.GraphUnavailable):
            assertions.enroll(mid, {"kind": "order_status_equals", "expected": "done"})

    def test_future_dated_client_report_cannot_preempt_actual_state(self):
        mid = self.mission()
        assertions.enroll(mid, {"kind": "order_status_equals", "expected": "delivered"})
        # The ingest layer permits at most 30 seconds of client clock skew.
        # Desired-state evaluation must not mistake that as a current observation.
        store.append(mid, [row("future", 20, status="delivered")])
        self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "unknown")
        with patch.object(store, "_utc", return_value=NOW + timedelta(seconds=21)):
            self.assertEqual(assertions.check(mid)["assertions"][0]["state"], "met")

    def test_retention_prune_removes_assertions_and_history(self):
        with patch.object(store, "_utc", return_value=NOW - timedelta(hours=100)):
            mid = store.create("Old private observation", lifetime_hours=1)["id"]
            a = assertions.enroll(mid, {"kind": "order_status_equals", "expected": "done"})
        with store._LOCK, store._db() as db:
            store._prune(db, NOW)
            db.commit()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM world_assertions "
                                        "WHERE mission_id=?", (mid,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM world_assertion_events "
                                        "WHERE assertion_id=?", (a["id"],)).fetchone()[0], 0)

    def test_private_endpoints_authorization_revoke_history(self):
        from fastapi.testclient import TestClient
        from jarvis_mrb import service
        mid = self.mission()
        client = TestClient(service.app)
        body = {"mission_id": mid, "definition": {"kind": "order_status_equals", "expected": "done"}}
        with patch.object(service, "API_TOKEN", "secret"):
            self.assertEqual(client.post("/mesh/graph/missions/assertions/enroll", json=body).status_code, 401)
            self.assertEqual(client.post("/mesh/graph/missions/assertions/enroll", json=body,
                                         headers={"Authorization": "Bearer no"}).status_code, 401)
            headers = {"Authorization": "Bearer secret"}
            created = client.post("/mesh/graph/missions/assertions/enroll", json=body, headers=headers)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.headers["cache-control"], "private, no-store")
            ident = {"mission_id": mid, "assertion_id": created.json()["id"]}
            check = client.post("/mesh/graph/missions/assertions/check",
                                json={"mission_id": mid}, headers=headers)
            self.assertEqual(check.status_code, 200, check.text)
            self.assertEqual(check.json()["assertions"][0]["state"], "unknown")
            history = client.post("/mesh/graph/missions/assertions/history",
                                  json=ident, headers=headers)
            self.assertEqual(history.status_code, 200, history.text)
            revoke = client.post("/mesh/graph/missions/assertions/revoke",
                                 json=ident, headers=headers)
            self.assertEqual(revoke.status_code, 200, revoke.text)
            self.assertEqual(client.post("/mesh/graph/missions/assertions/history",
                                         json=ident, headers=headers).status_code, 404)
            with patch.dict(os.environ, {"JARVIS_WORLD_ASSERTIONS_ENABLED": "0"}):
                self.assertEqual(client.post("/mesh/graph/missions/assertions/check",
                                             json={"mission_id": mid}, headers=headers).status_code, 503)
        with patch.object(service, "API_TOKEN", None):
            self.assertEqual(client.post("/mesh/graph/missions/assertions/check",
                                         json={"mission_id": mid}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
