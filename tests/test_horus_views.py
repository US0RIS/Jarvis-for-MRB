from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import attention as at
from jarvis_mrb.horus import ethics as et
from jarvis_mrb.horus import standing as st
from jarvis_mrb.horus import views as vw

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class ViewTests(unittest.TestCase):
    def test_command_center_and_cop(self) -> None:
        cc = vw.command_center(now=T0, health=[{"name": "pc", "state": "ok"}, {"name": "phone", "state": "stale"}],
                               modes={"home": "away"}, missions=["Tokyo"], alerts=[], next_items={})
        self.assertEqual(cc["overall"], "degraded")
        cop = vw.dynamic_cop("is the 101 flooding near Ventura", {
            "cameras": [{"id": "c1", "text": "101 at Ventura river camera", "lat": 34.28, "lon": -119.30},
                        {"id": "c2", "text": "101 at San Jose", "lat": 37.3, "lon": -121.9}],
            "music": [{"id": "m", "text": "playlist"}]}, region=(34.28, -119.29, 20000))
        self.assertEqual([i["id"] for i in cop["layers"]["cameras"]], ["c1"])
        self.assertIn("music", cop["omitted_layers"])

    def test_coverage_and_world_search(self) -> None:
        cov = vw.coverage_map([{"id": "s", "lat": 34.025, "lon": -119.025, "radius_m": 3000, "last_seen": T0}],
                              bbox=(34.0, -119.05, 34.05, -119.0), cell_deg=0.025, now=T0)
        self.assertGreater(cov["counts"]["live"], 0)
        self.assertIn("not an all-clear", cov["note"])
        obs = [{"id": "a", "kind": "aircraft", "lat": 34.1, "lon": -119.0, "trend": "descending"},
               {"id": "b", "kind": "aircraft", "lat": 36.0, "lon": -119.0, "trend": "descending"},
               {"id": "c", "kind": "aircraft", "lat": 34.05, "lon": -119.0, "trend": "climbing"}]
        res = vw.world_search(obs, "kind == 'aircraft' and trend == 'descending' and distance_mi < 20", near=(34.0, -119.0))
        self.assertEqual([r["id"] for r in res], ["a"])

    def test_describe_and_overlay(self) -> None:
        d = vw.describe_scene([{"label": "person", "confidence": 0.9}, {"label": "dog", "confidence": 0.3}],
                              previous=[{"label": "car", "confidence": 0.8}])
        self.assertEqual(d["important"], ["person"])
        self.assertEqual(d["maybe"], ["dog"])
        self.assertEqual(d["changed"], {"appeared": ["person"], "gone": ["car"]})
        ov = vw.semantic_overlay([{"role": "AXButton", "name": "Send"}, {"role": "EditControl", "name": ""},
                                  {"role": "group"}], app="mail")
        self.assertEqual([o["role"] for o in ov], ["button", "text_input"])
        self.assertFalse(ov[1]["accessible"])

    def test_guardian_alerts_are_proactive(self) -> None:
        wd = st.InvariantWatchdog([st.Assertion("no_leak", "leak == false", critical=True)])
        ctx = at.Context(now=T0, available_surfaces={"phone_notification", "phone_alarm"})
        out = vw.guardian_alerts(wd, "startup", {"no_leak": [{"source": "s1", "observed_at": T0, "leak": True}]},
                                 at.AttentionCommander(), ctx)
        self.assertEqual(out["delivery"]["shown"][0]["channel"], "phone_alarm")

    def test_reversible_first_response(self) -> None:
        done, escalated = [], []
        res = et.reversible_first_response(
            "water flow anomaly",
            [et.Intervention("close_valve", "valve", "main", True, 0.3, 0.0),
             et.Intervention("cut_power", "power", "house", False, 0.8, 0.5)],
            perform=lambda iv: done.append(iv.id) or {"ok": True}, escalate=lambda a, d: escalated.append(a))
        self.assertEqual(done, ["close_valve"])
        self.assertEqual(res["held_for_user"], ["cut_power"])
        self.assertEqual(escalated, ["water flow anomaly"])


if __name__ == "__main__":
    unittest.main()
