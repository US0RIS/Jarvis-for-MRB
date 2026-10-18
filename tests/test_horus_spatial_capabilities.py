from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import automation as au
from jarvis_mrb.horus import capabilities as cp
from jarvis_mrb.horus import continuity as ct
from jarvis_mrb.horus import spatial as sp

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
M = timedelta(minutes=1)


class SpatialTests(unittest.TestCase):
    def test_anchor_cross_device_drift_sharing(self) -> None:
        w = sp.WorldLayer()
        a = w.create("projector", "object", sp.AnchorObservation("iphone", "arkit-1", (1, 2, 0), 0.9, T0),
                     {"next_maintenance": "Dec"})
        est = w.relocalize(a.id, sp.AnchorObservation("quest", "oculus-9", (1.05, 2, 0), 0.8, T0))
        self.assertFalse(est["needs_reanchor"])
        self.assertEqual(w.by_vendor("quest", "oculus-9").id, a.id)
        drifted = w.relocalize(a.id, sp.AnchorObservation("glasses", "g-3", (2, 2, 0), 0.5, T0))
        self.assertTrue(drifted["needs_reanchor"])
        self.assertFalse(w.share(a.id, "guest", consented=False))
        self.assertTrue(w.share(a.id, "partner", consented=True))
        self.assertEqual(w.visible_to("partner"), [a.id])
        self.assertIn("status: on", w.label(a.id, {"status": "on"}))

    def test_semantic_map_locate_walk_into(self) -> None:
        kitchen = sp.Zone("k", "Kitchen", "cooking", polygon=[(0, 0), (4, 0), (4, 4), (0, 4)], interface="cooking_view",
                          normal_objects={"kettle", "knife block"}, controls={"switch_2": "pendant lights"})
        office = sp.Zone("o", "Office", "work", center_latlon=(34.0, -119.0), radius_m=30, interface="system_dashboard")
        m = sp.SemanticMap([kitchen, office])
        self.assertEqual(m.locate(local_xy=(1, 1))["name"], "Kitchen")
        self.assertEqual(m.locate(latlon=(34.0001, -119.0))["basis"], "GPS geofence")
        self.assertIsNone(m.locate()["zone"])
        launched = []
        ev = sp.walk_into(m, "me", "k", launched.append)
        self.assertEqual(launched, ["cooking_view"])
        ev = m.update("me", "o")
        self.assertEqual([e["event"] for e in ev], ["enter", "exit"])
        self.assertEqual(m.misplaced("k", ["kettle", "screwdriver"]), {"missing": ["knife block"], "unexpected": ["screwdriver"]})
        self.assertEqual(m.what_controls("pendant lights"), [("k", "switch_2")])

    def test_procedure_change_landmarks_objects_macro(self) -> None:
        po = sp.ProcedureOverlay([{"text": "close valve", "anchor": "valve", "done_when": lambda e: e.get("flow") == 0},
                                  {"text": "open drain", "anchor": "drain", "done_when": lambda e: e.get("drain") == "open"}])
        self.assertEqual(po.observe({"flow": 3}, T0)["status"], "waiting")
        self.assertEqual(po.observe({"flow": 0}, T0)["next"], "open drain")
        self.assertEqual(sp.visual_change({"chair": {"pos": (0, 0)}}, {"chair": {"pos": (1, 0)}, "box": {"pos": (2, 2)}}),
                         [{"object": "box", "change": "appeared"}, {"object": "chair", "change": "moved", "distance": 1.0}])
        lm = sp.LandmarkMemory()
        for _ in range(2):
            lm.learn("commute", "gas station", (34.0, -119.0), decision="turn left")
        self.assertIn("turn left", lm.guidance("commute", (34.001, -119.0))[0])
        reg = sp.ObjectRegistry()
        oid = reg.bind("the projector", ["white box", "lens", "ceiling mount"], controls=["power"])
        self.assertEqual(reg.recognize(["lens", "ceiling mount", "white box", "fan"])["id"], oid)
        self.assertTrue(reg.can(oid, "power"))
        macro = sp.learn_physical_macro([
            [{"action": "unplug", "object": "router"}, {"action": "wait", "object": "30s"}, {"action": "plug", "object": "router", "actuator": "smart_plug"}],
            [{"action": "unplug", "object": "router"}, {"action": "plug", "object": "router"}]])
        self.assertEqual([s["required"] for s in macro["steps"]], [True, False, True])
        self.assertEqual(macro["steps"][2]["mode"], "perform")

    def test_pointing_loop(self) -> None:
        loop = sp.PointingLoop(alpha=0.5)
        obs = (34.0, -119.0, 10.0)
        tgt = loop.lead((34.05, -119.0, 3000.0), (100.0, 0.0, -5.0), 2.0)
        self.assertGreater(tgt[0], 34.05)
        az, el = loop.command(obs, tgt)
        self.assertLess(abs(az - 0.0), 1.0)
        self.assertGreater(el, 0)
        r = loop.verify((az, el), (2.0, -1.0))
        self.assertEqual(r["offset"], (1.0, -0.5))
        self.assertFalse(loop.verify((az, el), None)["verified"])


class CapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = cp.CapabilityBus()
        self.bus.register(cp.Capability("cal.next", "Read your calendar", "next events", requires=["google"],
                                        permissions=["calendar.read"], entities=["calendar"], verbs=["observe"]),
                          lambda: ["standup"])
        self.bus.register(cp.Capability("lights.toggle", "Toggle a light", "HomeKit light", {"light": "str"},
                                        requires=["iphone"], permissions=["homekit"], effect="device", offline=True,
                                        entities=["light:porch"], verbs=["observe", "affect"]),
                          lambda light: {"toggled": light})

    def test_describe_graph_invoke_tray(self) -> None:
        text = self.bus.describe(up=["iphone"], granted=["homekit"], internet=False)
        self.assertIn("Toggle a light", text)
        self.assertIn("Unavailable: Read your calendar", text)
        self.assertIn("offline", text)
        self.assertEqual({g["verb"] for g in self.bus.graph()["light:porch"]}, {"observe", "affect"})
        r = self.bus.invoke("lights.toggle", modality="touch", granted=["homekit"], light="porch")
        self.assertEqual(r["result"], {"toggled": "porch"})
        self.assertFalse(self.bus.invoke("lights.toggle", modality="voice", granted=[], light="x")["ok"])
        for _ in range(3):
            self.bus.invoke("cal.next", modality="voice", granted=["calendar.read"])
        self.assertEqual([q["id"] for q in self.bus.quick_actions(pinned=["lights.toggle"])], ["lights.toggle", "cal.next"])
        with self.assertRaises(ValueError):
            self.bus.register(cp.Capability("x", " ", ""))

    def test_control_router_and_model_router(self) -> None:
        res = cp.route_control("rename file", {"native_api": lambda a: {"ok": False},
                                               "accessibility": lambda a: {"ok": True, "element": "btn"},
                                               "visual": lambda a: {"ok": True}})
        self.assertEqual(res["lane"], "accessibility")
        self.assertEqual([x["lane"] for x in res["attempts"]], ["native_api", "accessibility"])
        lanes = [cp.ModelLane("rules", 0, True, 1, 0, 0.0), cp.ModelLane("qwen8b", 1, True, 300, 0, 0.5),
                 cp.ModelLane("qwen27b", 2, True, 2000, 0, 0.8), cp.ModelLane("cloud", 3, False, 1500, 1, 1.0)]
        self.assertEqual(cp.route_model("open spotify", lanes, deterministic_match=True)["lane"], "rules")
        self.assertEqual(cp.route_model("classify this email", lanes)["lane"], "qwen8b")
        self.assertEqual(cp.route_model("debug the root cause of this crash", lanes)["lane"], "qwen27b")
        self.assertIsNone(cp.route_model("debug the root cause", lanes, max_latency_ms=500)["lane"])
        self.assertFalse(cp.should_sense(2, 0.5, cached_age_s=10, ttl_s=60)["sense"])
        self.assertTrue(cp.should_sense(2, 0.5)["sense"])

    def test_personal_api_blocks_microapp(self) -> None:
        store = {("car", "range_mi"): 120}
        api = cp.PersonalAPI(lambda e, a: store.get((e, a)), lambda e, a, v: store.update({(e, a): v}) or {"ok": True})
        tok = api.issue("widget", read=["car/*"])
        self.assertEqual(api.request(tok, "GET", "car/range_mi")["value"], 120)
        self.assertEqual(api.request(tok, "PUT", "car/range_mi", 1)["status"], 403)
        self.assertEqual(api.request("bad", "GET", "car/range_mi")["status"], 401)
        run = cp.compose({"km": lambda mi: mi * 1.609, "round": round}, ["km", "round"])
        self.assertEqual(run(100)["result"], 161)
        page = cp.micro_app("Log expense", cp.Capability("exp", "Log expense", "log", {"amount": "float", "note": "str"}),
                            endpoint="/api/invoke")
        self.assertIn('type="number"', page)
        self.assertIn('aria-live="polite"', page)

    def test_mission_recorder_and_mission(self) -> None:
        rec = cp.MissionRecorder("book flights")
        rec.set_subgoal("search", T0)
        self.assertTrue(rec.act("open airline site", T0, snapshot={"url": "x"}))
        rec.control("pause", T0)
        self.assertFalse(rec.act("click buy", T0))
        rec.control("resume", T0)
        rec.act("fill form", T0)
        self.assertTrue(rec.verify_integrity())
        rec.events[1]["action"] = "tampered"
        self.assertFalse(rec.verify_integrity())
        self.assertEqual(len(rec.replay(lambda a: a)), 2)
        mi = cp.Mission("Tokyo trip", started=T0)
        self.assertEqual(mi.auto_bind([{"kind": "email", "id": "m1", "text": "Your Tokyo hotel"},
                                       {"kind": "email", "id": "m2", "text": "newsletter"}], ["tokyo"]), 1)
        self.assertEqual(mi.attention_weight("email", "m1"), 2.0)
        self.assertIn("temporary watches", mi.close(T0, "returned home")["retire"])
        self.assertEqual(mi.attention_weight("email", "m1"), 1.0)

    def test_state_packet_site_capability_task_eval(self) -> None:
        pkt = cp.state_packet(mission="Tokyo", salient_memories=["prefers aisle"], commitments=[{"task": "book", "due": "fri"}],
                              hypotheses=[{"text": "flight delayed", "confidence": 0.4}], grants=[], provenance=["m1"])
        loaded = cp.load_state_packet(pkt)
        self.assertIn("Active mission: Tokyo", cp.context_preamble(loaded))
        with self.assertRaises(ValueError):
            cp.load_state_packet(pkt.replace("aisle", "window"))
        calls = {"n": 0}

        def adapter(req):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("DOM changed")
            return {"price": 10}

        site = cp.CompiledSiteCapability("price", adapter, lambda o: "price" in o, lambda r: {"price": 11})
        self.assertEqual(site.run({})["via"], "deterministic_adapter")
        self.assertEqual(site.run({})["via"], "agent_fallback")
        t = cp.ComputerTask("t1", "rename report", {"file": "report-final.pdf"})
        self.assertFalse(cp.evaluate_task(t, {"file": "report.pdf"})["passed"])
        self.assertTrue(cp.evaluate_task(t, {"file": "report-final.pdf"})["passed"])


class ContinuityTests(unittest.TestCase):
    def test_handoff_transport_packet(self) -> None:
        s = ct.Session("s1", "me", "glasses", "internet")
        s.say("user", "summarise the lease", T0)
        h = s.handoff("desktop", T0)
        self.assertTrue(h["expanded"])
        self.assertEqual(s.switch_transport(["push", "sms"], T0), "push")
        self.assertIsNone(s.switch_transport([], T0))
        s.handoff("watch", T0)
        self.assertTrue(s.render("x" * 100).endswith("…"))
        r = ct.Session.resume(s.continuation_packet(), device="phone", transport="lan")
        self.assertEqual(r.turns[0]["text"], "summarise the lease")

    def test_job_manager(self) -> None:
        jm = ct.JobManager()

        def work(progress, cancelled):
            for i in range(5):
                if cancelled():
                    return "partial"
                progress(i / 5, f"step {i}")
                time.sleep(0.01)
            return "done!"

        jid = jm.submit("research", work)
        jm.wait(jid)
        self.assertEqual(jm.status(jid)["status"], "done")
        self.assertEqual(jm.drain_results()[0]["result"], "done!")
        jid2 = jm.submit("slow", lambda p, c: (time.sleep(0.05), "x")[1] if not c() else "cancelled early", background=False)
        self.assertEqual(jm.status(jid2)["status"], "done")

    def test_presence_profiles_media(self) -> None:
        self.assertTrue(ct.presence_invocation("wake_word", relevance=0, mode="sleep", recently_invoked_s=1)["open"])
        self.assertFalse(ct.presence_invocation("entered_place", relevance=1, mode="meeting", recently_invoked_s=None)["open"])
        self.assertTrue(ct.presence_invocation("looked_at_object", relevance=0.9, mode="alone", recently_invoked_s=None)["open"])
        env = ct.resolve_environment([ct.Profile("a", True, {"temperature_c": 20, "privacy": "household"}),
                                      ct.Profile("b", True, {"temperature_c": 24, "privacy": "private"}, priority=1),
                                      ct.Profile("c", False, {"temperature_c": 30})])
        self.assertAlmostEqual(env["prefs"]["temperature_c"], 22.67, places=2)
        self.assertEqual(env["prefs"]["privacy"], "private")
        mf = ct.MediaFollower()
        mf.play("podcast", "kitchen", T0)
        mf.conversation_started(T0 + M)
        mf.conversation_ended(T0 + 3 * M)
        moved = mf.user_moved("office", T0 + 4 * M)
        self.assertEqual(moved["resume_at_s"], 120.0)
        self.assertGreater(mf.ambient_noise(80), mf.ambient_noise(30))


class AutomationTests(unittest.TestCase):
    def test_routine_learning(self) -> None:
        log = [{"action": "lights_on", "context": {"place": "home", "hour_bucket": "evening"}} for _ in range(5)]
        log.append({"action": "none", "context": {"place": "home", "hour_bucket": "evening", "guest": True}})
        props = au.learn_routines(log)
        self.assertEqual(props[0]["do"], "lights_on")
        self.assertEqual(props[0]["status"], "ask_user")
        self.assertTrue(props[0]["exceptions"])

    def test_do_the_rest(self) -> None:
        r = au.do_the_rest([("IMG_001.jpg", "trip_IMG_001.jpg")], ["IMG_002.jpg"])
        self.assertEqual(r["preview"][0]["output"], "trip_IMG_002.jpg")
        r2 = au.do_the_rest([("Smith, John", "John Smith"), ("Doe, Jane", "Jane Doe")], ["Lee, Ann"])
        self.assertEqual(r2["preview"][0]["output"], "Ann Lee")
        self.assertEqual(au.do_the_rest([("2026-10-01", "10/01/2026")], ["2027-01-31"])["preview"][0]["output"], "01/31/2027")
        self.assertEqual(au.do_the_rest([("a", "zzz9"), ("b", "q")], ["c"])["status"], "no_consistent_rule")

    def test_demonstrate_compile_verify(self) -> None:
        demo = [au.Step("open_folder", {"path": "C:/Invoices/Oct"}), au.Step("rename", {"pattern": "inv-{n}.pdf"}),
                au.Step("upload", {"dest": "drive:/finance"})]
        wf = au.compile_demonstrations("file invoices", [demo], context_values={"open_folder": "C:/Invoices/Oct"})
        self.assertEqual(len(wf.questions), 1)
        self.assertIn("whichever open folder", wf.questions[0])
        var = next(iter(wf.variables))
        au.answer_question(wf, var)
        executed = []
        res = au.verify_replay(wf, {var: "C:/Invoices/Nov"}, lambda s: executed.append(s.args) or {"ok": True}, lambda: True)
        self.assertTrue(res["verified"])
        self.assertEqual(executed[0], {"path": "C:/Invoices/Nov"})
        demo2 = [au.Step("open_folder", {"path": "C:/Invoices/Nov"}), au.Step("rename", {"pattern": "inv-{n}.pdf"}),
                 au.Step("upload", {"dest": "drive:/finance"})]
        wf2 = au.compile_demonstrations("file invoices", [demo, demo2])
        self.assertEqual(list(wf2.variables), ["step0_path"])
        self.assertEqual(wf2.constants["step2_dest"], "drive:/finance")
        with self.assertRaises(KeyError):
            au.instantiate(wf2, {})
        state = {"i": 0}
        rr = au.replay_with_checkpoints(au.instantiate(wf2, {"step0_path": "x"}), lambda s: {"ok": True},
                                        lambda i: i != 1 or state["i"] > 0, lambda i, s: state.update(i=1) or {"ok": True})
        self.assertEqual(rr["status"], "complete")


if __name__ == "__main__":
    unittest.main()
