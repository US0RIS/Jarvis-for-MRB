from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import standing as st
from jarvis_mrb.horus import temporal as tp

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


class TemporalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        s = tp.TemporalStore()
        s.assert_fact("car", "location", "home", at=T0, source_episode="gps:1")
        s.assert_fact("car", "location", "office", at=T0 + H, source_episode="gps:2")
        s.assert_fact("car", "location", "home", at=T0 + 3 * H, source_episode="gps:3")
        s.assert_fact("door", "state", "closed", at=T0, source_episode="sensor:1")
        self.s = s

    def test_rewind_and_diff(self) -> None:
        self.assertEqual(self.s.state_at(T0 + 2 * H)["car"]["location"], "office")
        self.assertEqual(self.s.value_at("car", "location", T0 + 4 * H).value, "home")
        diff = self.s.diff(T0 + timedelta(minutes=30), T0 + 2 * H)
        self.assertEqual(diff, [{"entity": "car", "attribute": "location", "change": "changed",
                                 "before": "home", "after": "office"}])
        self.s.assert_fact("pkg", "status", "delivered", at=T0 + 2 * H, source_episode="email")
        self.assertIn("appeared", [c["change"] for c in self.s.diff(T0, T0 + 2.5 * H)])

    def test_late_arriving_observation_is_bounded(self) -> None:
        self.s.assert_fact("car", "location", "gas station", at=T0 + 2 * H, source_episode="late",
                           observed_at=T0 + 5 * H)
        self.assertEqual(self.s.state_at(T0 + 2.5 * H)["car"]["location"], "gas station")
        self.assertEqual(self.s.state_at(T0 + 4 * H)["car"]["location"], "home")
        # bitemporal: at T0+2.5h Jarvis didn't know yet
        self.assertEqual(self.s.known_at(T0 + 2.5 * H)["car"]["location"], "office")

    def test_temporal_queries(self) -> None:
        self.assertEqual(self.s.duration("car", "location", "office", T0, T0 + 5 * H), 2 * H)
        self.assertEqual(len(self.s.change_points("car", "location")), 2)
        self.assertEqual(self.s.first("car", "location", "home").source_episode, "gps:1")
        self.assertEqual(self.s.last("car", "location", "home").source_episode, "gps:3")
        self.assertEqual(self.s.recurrence("car", "location", "home")["occurrences"], 2)
        self.assertEqual(self.s.before("car", "location", T0 + 2 * H).value, "office")
        self.assertEqual(self.s.after("car", "location", T0 + 2 * H).value, "home")

    def test_bookmarks_correction_debugger_gc_export(self) -> None:
        self.s.bookmark("brief", at=T0 + timedelta(minutes=30), entities=["car"])
        changes = self.s.changed_since("brief", T0 + 2 * H)
        self.assertEqual(changes[0]["after"], "office")
        base = self.s.value_at("door", "state", T0)
        derived = self.s.assert_fact("house", "secure", True, at=T0, source_episode="rule",
                                     derivation="inferred:door_closed", derived_from=[base.id])
        info = self.s.explain(derived.id)
        self.assertEqual(info["derived_from"][0]["fact"]["id"], base.id)
        entry = self.s.correct(base.id, "open", at=T0 + H, by="user")
        self.assertIn(derived.id, entry["invalidated_dependents"])
        self.assertEqual(self.s.state_at(T0 + timedelta(seconds=10))["door"]["state"], "open")
        gc = self.s.garbage_collect(now=T0 + 100 * H, stale_after=24 * H)
        self.assertTrue(gc["retired"])
        restored = tp.TemporalStore.import_(self.s.export())
        self.assertEqual(len(restored.facts), len(self.s.facts))

    def test_alias_graph(self) -> None:
        g = tp.AliasGraph()
        g.learn("the Porsche", "vehicle:911")
        self.assertEqual(g.resolve("porsche")["entity"], "vehicle:911")
        g.learn("Matt's laptop", "dev:a")
        g.learn("Matt's laptop", "dev:b")
        self.assertEqual(g.resolve("matt's laptop")["status"], "ambiguous")
        self.assertEqual(g.resolve("matt's laptop", ["dev:b"])["entity"], "dev:b")
        g.correct("matt's laptop", "dev:b", "dev:a", at=T0)
        self.assertEqual(g.resolve("matt's laptop")["entity"], "dev:a")


class StandingQueryTests(unittest.TestCase):
    def test_predicate_dsl(self) -> None:
        p = st.Predicate("distance_mi < 10 and altitude_trend == 'descending' and not on_ground")
        self.assertTrue(p({"distance_mi": 4, "altitude_trend": "descending", "on_ground": False}))
        self.assertFalse(p({"distance_mi": None, "altitude_trend": "descending"}))
        self.assertEqual(p.fields(), {"distance_mi", "altitude_trend", "on_ground"})
        self.assertTrue(st.Predicate("kind in ('plane', 'heli') or meta.priority >= 3")({"meta": {"priority": 5}}))
        with self.assertRaises(st.PredicateError):
            st.Predicate("__import__('os')")

    def test_engine_emits_only_on_change_and_retires(self) -> None:
        eng = st.StandingQueryEngine()
        eng.register(st.StandingQuery("near", "dist < 10", expires_at=T0 + 2 * H))
        e1 = eng.evaluate([{"id": "a", "dist": 5}, {"id": "b", "dist": 50}], T0)
        self.assertEqual([(e["event"], e["key"]) for e in e1], [("entered", "a")])
        self.assertEqual(eng.evaluate([{"id": "a", "dist": 4}], T0 + timedelta(seconds=60)), [])
        self.assertEqual(eng.evaluate([], T0 + timedelta(seconds=120))[0]["event"], "left")
        eng.evaluate([], T0 + 3 * H)
        self.assertEqual(eng.retired[0]["reason"], "ttl-expired")

    def test_reality_compiler(self) -> None:
        prog = st.compile_intent("Tell me if the tide height drops below 1.5 for the next two hours", now=T0)
        self.assertEqual(prog["status"], "compiled")
        self.assertEqual(prog["where"], "tide_height < 1.5")
        self.assertEqual(prog["expires_at"], (T0 + 2 * H).isoformat())
        q = st.to_standing_query(prog)
        self.assertTrue(q.predicate()({"tide_height": 1.0}))
        watch = st.compile_intent("watch this for the next 30 minutes", now=T0, context_entity="Highway 33")
        self.assertIn("highway 33", watch["where"])
        self.assertEqual(st.compile_intent("make me a sandwich")["status"], "needs_clarification")

    def test_assertions_failure_state_and_redundancy(self) -> None:
        a = st.Assertion("no_leak", "leak == false", required_sources=2, max_age_s=600)
        fresh = lambda src, leak, **kw: {"source": src, "observed_at": T0, "leak": leak, **kw}  # noqa: E731
        self.assertEqual(st.evaluate_assertion(a, [fresh("s1", False)], T0)["status"], "insufficient_evidence")
        self.assertEqual(st.evaluate_assertion(a, [fresh("s1", False), fresh("s2", False)], T0)["status"], "holds")
        self.assertEqual(st.evaluate_assertion(a, [fresh("s1", False), fresh("s2", True)], T0)["status"],
                         "sensor_disagreement")
        common = [fresh("s1", False, depends_on=["hub"]), fresh("s2", False, depends_on=["hub"])]
        r = st.evaluate_assertion(a, common, T0)
        self.assertEqual(r["status"], "insufficient_evidence")
        self.assertIn("hub", r["common_mode_dependencies"])
        stale = [{"source": "s1", "observed_at": T0 - H, "leak": False}, fresh("s2", False, battery=0.01)]
        self.assertFalse(st.evaluate_assertion(a, stale, T0)["all_clear"])

    def test_invariant_watchdog_catches_offline_violation_on_startup(self) -> None:
        wd = st.InvariantWatchdog([st.Assertion("freezer", "temp_c < -10")])
        readings = {"freezer": [{"source": "probe", "observed_at": T0, "temp_c": 2}]}
        self.assertEqual(len(wd.check("startup", readings, T0)), 1)
        self.assertEqual(len(wd.check("periodic", readings, T0)), 0)  # unchanged level, no spam
        self.assertEqual(len(wd.check("reconnect", readings, T0)), 1)

    def test_replay_recurrence_tasks_events_web(self) -> None:
        hist = [{"id": str(i), "at": T0 + i * H, "motion": i % 2 == 0} for i in range(6)]
        res = st.replay_automation("motion == true", hist, labels={"0": True, "2": False, "4": True, "5": True})
        self.assertEqual(res["would_fire"], 3)
        self.assertEqual(res["false_positives"], ["2"])
        self.assertEqual(res["missed"], ["5"])
        rec = st.ConditionRecurrence("replace filter", "filter_changed", timedelta(days=30))
        rec.observe("filter_changed", T0)
        self.assertFalse(rec.is_due(T0 + timedelta(days=29)))
        self.assertTrue(rec.is_due(T0 + timedelta(days=31)))
        task = st.SelfResolvingTask("charge car", "charging == true")
        self.assertFalse(task.offer({"charging": False}))
        self.assertTrue(task.offer({"charging": True}))
        series = [(T0 + i * H, v) for i, v in enumerate([1, 2, 6, 7, 4.9, 3, 6])]
        ev = st.eventify(series, threshold=5, hysteresis=0.5, name="rain")
        self.assertEqual([e["event"] for e in ev], ["rain_rose_above", "rain_fell_below", "rain_rose_above"])
        w = st.WebObservation("https://example.test/status")
        self.assertIsNone(w.observe("<p>Status: open. Updated 10:01</p>", T0))
        self.assertIsNone(w.observe("<p>Status: open. Updated 10:05</p>", T0 + H))
        self.assertEqual(w.observe("<p>Status: closed. Updated 10:09</p>", T0 + 2 * H)["event"], "web_changed")

    def test_state_machine_restoration_versions_closed_loop(self) -> None:
        sm = st.StateMachine("home", ["home", "away", "sleep"], {"home": ["away", "sleep"], "away": ["home"]}, "home")
        self.assertIn("because", sm.transition("away", cause="phone left geofence", at=T0)["announce"])
        with self.assertRaises(PermissionError):
            sm.transition("sleep", cause="x", at=T0)
        box = {"v": 40}
        r = st.StateRestorer()
        r.apply("volume", box["v"], 5, lambda v: box.__setitem__("v", v))
        self.assertEqual(box["v"], 5)
        r.restore("volume", lambda v: box.__setitem__("v", v))
        self.assertEqual(box["v"], 40)
        av = st.AutomationVersions("porch")
        av.commit("motion == true", author="u", note="v1", tests=[({"motion": True}, True)])
        av.commit("motion == true and dark == true", author="u", note="v2")
        self.assertEqual(av.rollback(1), "motion == true")
        with self.assertRaises(AssertionError):
            av.commit("motion == false", author="u", note="bad", tests=[({"motion": True}, True)])
        world = {"temp": 30}
        res = st.closed_loop_step(
            "temp < 25", lambda: dict(world),
            [{"id": "open_window", "reversible": True}, {"id": "ac_on", "reversible": True, "cost": 2}],
            lambda iv: (world.__setitem__("temp", 22) if iv["id"] == "ac_on" else None) or {"applied": True},
            authorized={"ac_on"})
        self.assertEqual(res["status"], "satisfied_after_intervention")
        self.assertEqual(res["trail"][0]["skipped"], "not authorized")
        self.assertEqual(st.follow_entity((34.0, -119.0), [{"id": "cam1", "lat": 34.001, "lon": -119.0},
                                                           {"id": "cam2", "lat": 35, "lon": -119}], radius_m=500),
                         ["cam1"])


if __name__ == "__main__":
    unittest.main()
