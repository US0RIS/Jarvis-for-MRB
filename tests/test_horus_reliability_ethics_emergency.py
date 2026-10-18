from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import emergency as em
from jarvis_mrb.horus import ethics as et
from jarvis_mrb.horus import reliability as rl

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


class ReliabilityTests(unittest.TestCase):
    def test_slo_error_budget(self) -> None:
        tr = rl.SLOTracker([rl.SLO("alerts", 0.9)])
        for i in range(10):
            tr.record("alerts", i != 0, T0)
        self.assertAlmostEqual(tr.report("alerts", T0)["error_budget_remaining"], 0.0)
        tr.record("alerts", False, T0)
        self.assertTrue(tr.report("alerts", T0)["exhausted"])
        self.assertEqual(tr.engineering_focus(T0)["focus"], "reliability")

    def test_registry_requires_ownership_and_cost_meter(self) -> None:
        reg = rl.AutomationRegistry()
        with self.assertRaises(ValueError):
            reg.register(rl.AutomationRecord("x", "", "me", "t", [], [], [], "r", "never"))
        reg.register(rl.AutomationRecord("porch", "light at dusk", "me", "sunset", ["hue"], ["lights"], ["light on"],
                                         "turn off", "move house", minutes_saved_per_run=0.1, runs_per_month=30,
                                         maintenance_minutes_per_month=30))
        audit = reg.audit(T0)
        self.assertIn("net-negative", audit[0]["issues"])
        self.assertIn("untested", audit[0]["issues"])

    def test_dependency_map_chaos_manifest(self) -> None:
        d = rl.DependencyMap()
        d.add("alerts", ["apns", "ntfy"], ["service"])
        d.add("service", ["windows_host"])
        d.add("calendar_brief", ["google_api"], ["service"])
        self.assertEqual(sorted(d.single_points_of_failure()["windows_host"]), ["alerts", "calendar_brief", "service"])
        self.assertNotIn("apns", d.single_points_of_failure())
        m = d.manifest({"google_api", "apns"})
        self.assertIn("alerts", m["available"])
        self.assertIn("calendar_brief", m["unavailable"])
        self.assertEqual(d.degradation_plan("alerts")[0]["fallbacks"], ["ntfy"])

    def test_failures_changes_snapshots_fix_memory(self) -> None:
        clusters = rl.cluster_failures([
            {"id": "1", "component": "tts", "message": "kokoro timeout on synth"},
            {"id": "2", "component": "tts", "message": "kokoro synth timeout again"},
            {"id": "3", "component": "gmail", "message": "oauth token expired"},
        ])
        self.assertEqual(clusters, [["1", "2"], ["3"]])
        ranked = rl.correlate_changes(T0, [{"id": "a", "at": T0 - 20 * H, "touches": ["tts"]},
                                           {"id": "b", "at": T0 - H, "touches": ["lights"]},
                                           {"id": "c", "at": T0 - 2 * H, "touches": ["tts"]}], affected=["tts"])
        self.assertEqual(ranked[0]["id"], "c")
        diff = rl.snapshot_diff({"a": 1, "net": {"dns": "1.1.1.1"}}, {"a": 1, "net": {"dns": "8.8.8.8"}})
        self.assertEqual(diff, [{"path": "net.dns", "known_good": "1.1.1.1", "current": "8.8.8.8"}])
        mem = rl.HumanFixMemory()
        mem.record({"service": "tts", "error": "cuda"}, "restart driver", True, T0)
        self.assertEqual(mem.suggest({"service": "tts", "error": "cuda", "gpu": "5080"})[0]["fix"], "restart driver")
        rb = rl.compile_runbook("tts down", [{"action": "restart"}, {"action": "decide model", "judgment": True}])
        self.assertEqual(rb["judgment_points"], [2])

    def test_rollout_and_rollback(self) -> None:
        applied, rolled = [], []
        res = rl.progressive_rollout(["a", "b", "c", "d"], lambda t: applied.append(t) or {"ok": True},
                                     lambda t: t != "c", rolled.append)
        self.assertEqual(res["status"], "halted_and_rolled_back")
        self.assertEqual(rolled, ["c", "b", "a"])
        ok = rl.progressive_rollout(["a", "b"], lambda t: {"ok": True}, lambda t: True, rolled.append)
        self.assertEqual(ok["applied"], ["a", "b"])
        state = {"v": 0}
        contract = rl.RollbackContract("set", lambda s: s["v"] == 1, lambda: state.update(v=0))
        self.assertEqual(contract.execute(lambda: state.update(v=2) or {}, lambda: dict(state))["status"], "rolled_back")
        self.assertEqual(state["v"], 0)

    def test_split_brain_and_reconciliation(self) -> None:
        issues = rl.detect_split_brain({"pc": {"authority": {"leader": "pc"}, "state": {"door": "locked"}},
                                        "pi": {"authority": {"leader": "pi"}, "state": {"door": "open"}}})
        self.assertEqual({i["kind"] for i in issues}, {"authority_conflict", "state_divergence"})
        pc, pi = rl.ReconciliationLedger("pc"), rl.ReconciliationLedger("pi")
        pc.record("temp", 20, T0)
        pi.record("temp", 22, T0 + H)
        pi.record("light", "on", T0, kind="action")
        merged = pc.merge(pi.export())
        self.assertEqual(merged["state"], {"temp": 22, "light": "on"})
        self.assertEqual(merged["conflicts"][0]["key"], "temp")
        self.assertEqual(pc.merge(pi.export())["new_entries"], 0)

    def test_capability_claims_drift_maintenance(self) -> None:
        self.assertEqual(rl.capability_claim(rl.CapabilityEvidence("x"), T0), "designed")
        self.assertEqual(rl.capability_claim(rl.CapabilityEvidence("x", commit="abc"), T0), "implemented-unverified")
        self.assertEqual(rl.capability_claim(rl.CapabilityEvidence("x", "abc", "win", T0 - 30 * 24 * H), T0), "verified-stale")
        drift = rl.detect_schema_drift({"data.temp_c": "float", "data.id": "str"}, {"data": {"temperature_c": 1.5, "id": "a"}})
        self.assertEqual(drift["candidate_renames"], [{"from": "data.temp_c", "to": "data.temperature_c"}])
        rep = rl.propose_repair(drift, [{"data": {"temperature_c": 1.0}}],
                                lambda p, m: p["data"][m["data.temp_c"].split(".")[-1]], lambda v: isinstance(v, float))
        self.assertEqual(rep["status"], "proposed")
        self.assertTrue(rep["requires_approval"])
        self.assertEqual(rl.condition_check({"cpu_temp": 95}, [rl.TelemetryLimit("cpu_temp", 80, 90)])[0]["level"], "critical")
        series = [(T0 + i * 24 * H, 40.0 + (0.01 * (i % 2))) for i in range(12)] + [(T0 + i * 24 * H, 46.0) for i in range(12, 15)]
        self.assertEqual(rl.degradation_trend(series)["status"], "drifting")
        env = rl.OperatingEnvelope("mode", "watts")
        env.fit([{"mode": "idle", "watts": w} for w in (50, 55, 60)])
        self.assertEqual(env.check({"mode": "idle", "watts": 300})["status"], "outside-envelope")
        self.assertEqual(env.check({"mode": "render", "watts": 300})["status"], "unseen-combination")
        v = rl.verify_maintenance(lambda s: s["fan"] == "stopped", {"fan": "stopped", "dns": "a"},
                                  {"fan": "ok", "dns": "b"}, {"fan": "ok", "dns": "a"})
        self.assertFalse(v["verified"])
        sm = rl.survival_mode([{"name": "llm27b", "class": "optional", "watts": 300},
                               {"name": "alerts", "class": "critical", "watts": 5},
                               {"name": "cloud_sync", "class": "important", "needs_internet": True}],
                              battery_fraction=0.3, grid_power=False, internet=False)
        self.assertEqual(sm["keep"], ["alerts"])
        b = rl.backup_status([{"location": "nas", "verified_at": T0}, {"location": "b2", "verified_at": T0 - 3 * 24 * H}], T0)
        self.assertFalse(b["healthy"])
        tl = rl.intervention_timeline("pump", [{"entity": "pump", "at": T0 + H, "kind": "alert"}],
                                      [{"entity": "pump", "at": T0, "kind": "config"}, {"entity": "x", "at": T0}])
        self.assertEqual([e["kind"] for e in tl], ["config", "alert"])


class EthicsTests(unittest.TestCase):
    def test_hard_boundaries_and_pretext(self) -> None:
        for probe in et.RED_TEAM_PROBES:
            decision = et.run_scenario({k: v for k, v in probe.items() if k not in ("name", "expect")})
            self.assertIn(decision, probe["expect"], probe["name"])

    def test_regression_scenarios_distinguish_context(self) -> None:
        for sc in et.ETHICS_SCENARIOS:
            allowed = et.run_scenario(sc["allowed_when"])
            denied = et.run_scenario(sc["denied_when"])
            self.assertIn(allowed, {"allow", "allow_with_scoped_authority"}, sc["name"])
            self.assertIn(denied, {"deny", "escalate_to_human"}, sc["name"])

    def test_least_intervention_and_exhaustion(self) -> None:
        ctx = et.EthicalContext("stop flooding", "user", set(), {"neighbor": ["property"]}, "property_major", 10,
                                "verified", 0.95)
        big = et.Intervention("break_pipe", "physical", "pipe", False, 0.9, 0.5, "narrow_exceptional_intervention")
        small = et.Intervention("call_utility", "communication", "utility", True, 0.1, 0.0,
                                "contact_responsible_humans_or_emergency_services")
        rec = et.evaluate(ctx, big, [small, big])
        self.assertEqual(rec.decision, "deny")
        self.assertIn("call_utility", rec.reasons[0])
        ex = et.AlternativeExhaustion()
        ex.record("call_utility", "attempted_failed", T0)
        rec2 = et.evaluate(ctx, big, [small, big], ex)
        self.assertEqual(rec2.decision, "deny")  # irreversible below health threat
        self.assertIn("Would change if", et.explain(rec2))

    def test_scoped_authority_ttl_firewall_retraction(self) -> None:
        ctx = et.EthicalContext("free trapped person", "user", set(), {"owner": ["property"]}, "life", 3, "verified", 0.9)
        iv = et.Intervention("open_door", "unlock", "door:7", True, 0.5, 0.2, "reversible_protective_intervention")
        rec = et.evaluate(ctx, iv, [])
        self.assertEqual(rec.decision, "allow_with_scoped_authority")
        auth = et.EmergencyAuthority()
        g = auth.grant(rec, ctx, iv, now=T0, ttl=timedelta(days=3), max_uses=2)
        self.assertEqual(g.expires_at, T0 + et.EmergencyAuthority.MAX_TTL)
        self.assertFalse(auth.authorize(g.id, target="alarm_panel", action_class="disable", now=T0))
        self.assertTrue(auth.authorize(g.id, target="door:7", action_class="unlock", now=T0))
        auth.record_temporary_change(g.id, "door unlocked", "relock door")
        auth.predicate_cleared(T0 + timedelta(minutes=5))
        self.assertFalse(auth.authorize(g.id, target="door:7", action_class="unlock", now=T0 + timedelta(minutes=6)))
        self.assertEqual(len(auth.restoration_checklist()), 1)
        self.assertIn("scope-firewall-block", [a["event"] for a in auth.audit])
        with self.assertRaises(PermissionError):
            auth.grant(et.DecisionRecord("x", "deny", [], [], [], [], {}), ctx, iv, now=T0)

    def test_classification_and_loop(self) -> None:
        self.assertEqual(et.classify_emergency(True, 0, 0, sensors_degraded=True), "credible_possible")
        self.assertEqual(et.classify_emergency(True, 0, 2, sensors_degraded=False), "contradicted_claim")
        self.assertEqual(et.classify_emergency(True, 2, 0, False), "verified")
        met = {"v": False}
        r = et.exceptional_step_loop(["a", "b", "c"], lambda s: met.update(v=(s == "a")), lambda: met["v"])
        self.assertEqual(r["performed"], ["a"])
        self.assertEqual(et.damage_budget([{"id": 1, "effective": True, "damage": 5},
                                           {"id": 2, "effective": True, "damage": 2}], 10)["id"], 2)

    def test_security_guards(self) -> None:
        self.assertFalse(et.speaker_gate("device", None, enrolled=False)["allowed"])
        self.assertFalse(et.speaker_gate("device", 0.95, True, liveness=False)["allowed"])
        self.assertTrue(et.speaker_gate("device", 0.85, True)["allowed"])
        pg = et.PaymentGuard(b"k")
        code = pg.challenge(1999, "acme", "n1")
        self.assertFalse(pg.confirm(2999, "acme", "n1", code, speaker_ok=True))
        self.assertTrue(pg.confirm(1999, "acme", "n1", code, speaker_ok=True))
        self.assertFalse(pg.confirm(1999, "acme", "n1", code, speaker_ok=True))  # replay
        self.assertEqual(et.new_breaches(["A"], [{"Name": "A"}, {"Name": "B"}]), [{"Name": "B"}])
        self.assertEqual(len(et.stale_grants([{"app": "x", "last_used": T0 - 400 * 24 * H}, {"app": "y", "last_used": T0}], T0)), 1)
        trk = et.persistent_trackers([{"device": "tag1", "place": p, "at": T0 + i * H} for i, p in enumerate("abc")]
                                     + [{"device": "mine", "place": p, "at": T0 + i * H} for i, p in enumerate("abc")],
                                     known_devices=["mine"])
        self.assertEqual([t["device"] for t in trk], ["tag1"])
        self.assertEqual(et.new_lan_devices({"AA:BB": "tv"}, [{"mac": "aa:bb"}, {"mac": "cc:dd"}]), [{"mac": "cc:dd"}])
        self.assertIn("verified_outcome", et.after_action_entry("geofence", "lights", "on", at=T0, evidence=["readback"]))

    def test_delegation(self) -> None:
        svc = et.DelegationService(b"s")
        cap = svc.issue("sitter", ["light:porch"], ["toggle"], now=T0, ttl=4 * H, rate_per_hour=2)
        self.assertEqual(svc.check(cap.token, "lock:front", "toggle", T0)[1], "out of scope")
        self.assertTrue(svc.check(cap.token, "light:porch", "toggle", T0)[0])
        svc.check(cap.token, "light:porch", "toggle", T0)
        self.assertEqual(svc.check(cap.token, "light:porch", "toggle", T0)[1], "rate limited")
        self.assertEqual(svc.check(cap.token, "light:porch", "toggle", T0 + 5 * H)[1], "expired")
        svc.revoke(cap.token)
        self.assertEqual(svc.check(cap.token, "light:porch", "toggle", T0)[1], "revoked")


class EmergencyTests(unittest.TestCase):
    def test_retrieval_before_generation(self) -> None:
        lib = em.PlaybookLibrary()
        a = em.emergency_answer("our CO alarm is going off", lib)
        self.assertEqual(a["playbook"], "carbon_monoxide")
        self.assertEqual(a["route"], "deterministic")
        unk = em.emergency_answer("the hydraulic press is making a strange noise", lib)
        self.assertEqual(unk["route"], "escalate")
        self.assertIn("won't improvise", unk["message"])
        self.assertEqual(lib.stale_playbooks(datetime(2028, 1, 1, tzinfo=timezone.utc)), list(lib.playbooks))
        pack = lib.export_pack(contacts=[{"name": "Mom"}], capabilities=em.CapabilityIndex(), maps=["ventura.mbtiles"])
        self.assertIn("horus-emergency-pack", pack)
        self.assertEqual(em.minimal_context_package("x", {"a": 1, "ssn": 2}, ["a"])["facts"], {"a": 1})

    def test_state_machine_gate(self) -> None:
        m = em.EmergencyStateMachine({("assess", "confirmed"): lambda e: e.get("sources", 0) >= 1})
        m.fire("detected", {}, T0)
        self.assertEqual(m.fire("confirmed", {"sources": 0}, T0), "assess")
        self.assertEqual(m.fire("confirmed", {"sources": 2}, T0), "protect")
        with self.assertRaises(ValueError):
            m.fire("restored", {}, T0)

    def test_packet_snapshot_selftest_drill(self) -> None:
        pkt = em.responder_packet(nature="smoke in garage", location=None, callback="+1-555-0100", hazards=["EV charging"])
        self.assertIn("Location: UNKNOWN", pkt)
        snap = em.evidence_snapshot([{"at": T0 - 3 * H, "v": 1}, {"at": T0 - H, "v": 2}], T0)
        self.assertEqual(len(snap["items"]), 1)
        st = em.self_test({"playbooks": lambda: True, "contacts": lambda: 1 / 0})
        self.assertEqual(st["failing"], ["contacts"])
        lib = em.PlaybookLibrary()
        self.assertTrue(em.run_drill({"situation": "flash flood warning, water rising", "expected_playbook": "flash_flood"}, lib)["passed"])
        self.assertTrue(em.run_drill({"situation": "strange hum", "expected_playbook": None}, lib)["passed"])

    def test_ibw_threshold_failover_beacon(self) -> None:
        self.assertEqual(em.parse_ibw({"event": "Flash Flood Warning",
                                       "parameters": {"flashFloodDamageThreat": ["CONSIDERABLE"]}})["priority"], "urgent")
        self.assertEqual(em.parse_ibw({"event": "Flash Flood Warning",
                                       "description": "...FLASH FLOOD DAMAGE THREAT...CATASTROPHIC"})["priority"], "critical")
        self.assertEqual(em.parse_ibw({"event": "Flash Flood Warning"})["priority"], "warning")
        self.assertEqual(em.rainfall_threshold(1.0, "high"), 0.5)
        self.assertEqual(em.rainfall_threshold(1.0, "low", slope_deg=35), 0.5)
        sent = []
        paths = [em.AlertPath("push", lambda a: sent.append("push") or True, needs_internet=True),
                 em.AlertPath("buzzer", lambda a: sent.append("buzzer") or True),
                 em.AlertPath("lan_webhook", lambda a: sent.append("lan") or True, needs_grid=True)]
        r = em.dispatch_failover({"priority": "critical"}, paths, internet=False, grid=False)
        self.assertEqual(r["delivered"], ["buzzer"])
        self.assertEqual(em.ntfy_payload("t", "x", "y", "critical")["priority"], 5)
        fb = em.FamilyBeacon()
        for m in ("me", "kid"):
            fb.enroll(m)
        w = fb.declare("me", ["kid", "stranger"], now=T0, duration=6 * H)
        self.assertEqual(w.members, {"kid"})
        self.assertTrue(fb.report(w.id, "kid", "safe", T0 + H))
        self.assertFalse(fb.report(w.id, "kid", "safe", T0 + 7 * H))
        self.assertTrue(fb.board(w.id, T0 + 7 * H)["closed"])


if __name__ == "__main__":
    unittest.main()
