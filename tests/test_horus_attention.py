from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import attention as at

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
M = timedelta(minutes=1)


def info(**kw):
    base = dict(id="i1", title="Leak", body="Water under sink", urgency="high", evidence=["sensor:7"],
                reason="assertion:no_leak", confidence=0.9)
    base.update(kw)
    return at.InfoObject(**base)


class DeliveryTests(unittest.TestCase):
    def test_weak_case_stays_silent_and_why(self) -> None:
        ctx = at.Context(now=T0, available_surfaces={"phone_notification"})
        self.assertEqual(at.choose_channel(info(evidence=[]), ctx)["action"], "silence")
        d = at.choose_channel(info(), ctx)
        self.assertEqual(d["action"], "deliver")
        self.assertEqual(d["why"]["evidence"], ["sensor:7"])

    def test_least_intrusive_adequate_channel(self) -> None:
        ctx = at.Context(now=T0, available_surfaces={"status_glyph", "phone_notification", "speaker", "hud_text"})
        self.assertEqual(at.choose_channel(info(urgency="low", body="ok"), ctx)["channel"], "status_glyph")
        self.assertEqual(at.choose_channel(info(urgency="high"), ctx)["channel"], "phone_notification")

    def test_social_modes_privacy_and_sterile(self) -> None:
        guest = at.Context(mode="guest", now=T0, available_surfaces={"phone_notification", "speaker"})
        self.assertEqual(at.choose_channel(info(privacy="private"), guest)["action"], "defer")
        self.assertFalse(at.capability_allowed("read_messages_aloud", guest))
        self.assertTrue(at.capability_allowed("read_messages_aloud", at.Context()))
        sterile = at.Context(now=T0, sterile=True, available_surfaces={"phone_notification", "status_glyph"})
        self.assertEqual(at.choose_channel(info(urgency="high"), sterile)["action"], "ambient")
        self.assertEqual(at.choose_channel(info(urgency="critical"), sterile)["action"], "deliver")
        driving = at.Context(mode="driving", now=T0, available_surfaces={"hud_text", "private_audio"})
        self.assertEqual(at.choose_channel(info(), driving)["channel"], "private_audio")

    def test_prerequisites_and_expiry(self) -> None:
        ctx = at.Context(now=T0, available_surfaces={"phone_notification"})
        self.assertEqual(at.choose_channel(info(prerequisites=["at_store"]), ctx)["waiting_for"], ["at_store"])
        ctx.facts.add("at_store")
        self.assertEqual(at.choose_channel(info(prerequisites=["at_store"]), ctx)["action"], "deliver")
        self.assertEqual(at.choose_channel(info(expires_at=T0 - M), ctx)["action"], "drop")
        self.assertEqual(at.render_all_modalities(info(urgency="critical"))["haptic"], "pulse-pulse-pulse")


class ArbitrationTests(unittest.TestCase):
    def test_budget_commander_triage_window(self) -> None:
        b = at.AttentionBudget(per_hour=1)
        self.assertTrue(b.try_spend(info(), T0))
        self.assertFalse(b.try_spend(info(id="i2"), T0 + M))
        self.assertTrue(b.try_spend(info(id="i3", urgency="critical"), T0 + M))
        w = at.decision_window(info(urgency="low", decision_deadline=T0 + 8 * M), T0)
        self.assertEqual(w["urgency"], "critical")
        cmd = at.AttentionCommander(slots=1, budget=at.AttentionBudget(per_hour=10))
        items = [info(id="trivia", urgency="normal", consequence=0.1, relevance=0.1),
                 info(id="deadline", urgency="normal", consequence=0.9, relevance=0.9, decision_deadline=T0 + 30 * M)]
        res = cmd.arbitrate(items, at.Context(now=T0, available_surfaces={"phone_notification"}))
        self.assertEqual([s["id"] for s in res["shown"]], ["deadline"])
        self.assertEqual(res["demoted"][0]["id"], "trivia")

    def test_tempo_and_load(self) -> None:
        events = [T0 - i * M for i in range(10)]
        self.assertEqual(at.operational_tempo(events, T0)["tempo"], "accelerating")
        self.assertEqual(at.operational_tempo([T0 - 40 * M - i * M for i in range(10)], T0)["tempo"], "resolving")
        self.assertGreaterEqual(at.cognitive_load(driving=True, in_conversation=True), 0.8)

    def test_escalation_ladder(self) -> None:
        lad = at.EscalationLadder([("status_glyph", 5 * M), ("phone_notification", 5 * M), ("phone_alarm", 5 * M)])
        lad.start("a", T0)
        self.assertIsNone(lad.tick("a", T0 + M))
        self.assertEqual(lad.tick("a", T0 + 6 * M), "phone_notification")
        self.assertEqual(lad.tick("a", T0 + 7 * M, worsened=True), "phone_alarm")
        self.assertEqual(lad.acknowledge("a", "phone_alarm", T0 + 8 * M), ["status_glyph", "phone_notification"])
        self.assertIsNone(lad.tick("a", T0 + 60 * M))


class ModesTests(unittest.TestCase):
    def test_annunciation_surprise_manual(self) -> None:
        mm = at.ModeManager()
        self.assertIn("because", mm.set_mode("home", "away", cause="geofence exit", at=T0)["annunciation"])
        mm.take_control("thermostat", "eco-away")
        s = mm.surprise("thermostat", 18, 24)
        self.assertIn("eco-away", s["explanation"])
        self.assertIsNone(mm.surprise("thermostat", 18, 18))
        h = mm.return_to_manual("thermostat", lost="sensor offline", left_state="18C", at=T0)
        self.assertIn("manual", h["message"])

    def test_loadout_restores(self) -> None:
        state = {"dnd": False}
        runner = at.LoadoutRunner(lambda a: state.update(dnd=True) or {"action": a, "ok": True},
                                  lambda: dict(state), lambda s: state.update(s))
        runner.define(at.Loadout("focus", ["dnd_on", "open_docs"]))
        self.assertEqual(runner.invoke("Horus, set up my focus loadout")["status"], "active")
        self.assertTrue(state["dnd"])
        runner.exit("focus")
        self.assertFalse(state["dnd"])
        self.assertEqual(runner.invoke("set up my gym loadout")["status"], "unknown_loadout")

    def test_barge_in(self) -> None:
        b = at.BargeIn()
        r = b.interrupt("Horus, stop", ["tts:1", "plan:2"])
        self.assertEqual(r["cancelled"], ["tts:1", "plan:2"])
        self.assertEqual(b.classify("put it on my desktop")["device"], "desktop")
        self.assertEqual(b.classify("give me the tl;dr")["command"], "shorter")
        self.assertFalse(b.interrupt("what's the weather", [])["interrupted"])


class AlarmTests(unittest.TestCase):
    def test_metrics_rationalization_flood(self) -> None:
        nm = at.NudgeMetrics()
        for _ in range(12):
            nm.record("hydrate", "dismissed")
        for _ in range(6):
            nm.record("leave_now", "acted")
        for _ in range(6):
            nm.record("leave_now", "ignored")
        self.assertEqual(nm.recommendations(), {"hydrate": "retire", "leave_now": "keep"})
        hist = [{"alarm": "wifi_flap", "at": T0 - i * timedelta(hours=1), "cleared_at": T0, "action_taken": False}
                for i in range(25)]
        hist += [{"alarm": "router_down", "at": T0 - i * timedelta(hours=1) + timedelta(seconds=10), "cleared_at": T0,
                  "action_taken": True} for i in range(25)]
        findings = at.rationalize_alarms(hist, now=T0)
        kinds = {i for f in findings for i in f["issues"]}
        self.assertIn("nuisance:frequent", kinds)
        self.assertIn("never-changes-behavior", kinds)
        self.assertIn("duplicate:co-fire", kinds)
        flood = at.collapse_flood([{"alarm": "cam1_offline", "at": T0 + M}, {"alarm": "switch_down", "at": T0},
                                   {"alarm": "cam2_offline", "at": T0 + 2 * M}],
                                  {"cam1_offline": "switch", "cam2_offline": "switch", "switch_down": "switch"})
        self.assertEqual(len(flood), 1)
        self.assertEqual(flood[0]["first_out"]["alarm"], "switch_down")
        ind = at.status_indicators({"pc": {"ok": True, "last_seen": T0}, "phone": {"ok": True, "last_seen": T0 - 60 * M}}, T0)
        self.assertEqual([i["state"] for i in ind], ["ok", "stale"])


if __name__ == "__main__":
    unittest.main()
