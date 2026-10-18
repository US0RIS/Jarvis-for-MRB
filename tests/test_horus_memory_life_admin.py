from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from jarvis_mrb.horus import life_admin as la
from jarvis_mrb.horus import memory as mm

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)  # a Thursday
H = timedelta(hours=1)
HOME = (34.2805, -119.2945)
OFFICE = (34.4208, -119.6982)


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = mm.MemoryStore(mm.EntityTagger({"person:dana": ["Dana"], "project:atlas": ["Atlas"]}))

    def test_capture_context_and_tags(self) -> None:
        c = self.store.remember_this("Horus, remember this: Dana prefers morning calls about Atlas", at=T0,
                                     context={"mission": "atlas launch", "document": "plan.docx"})
        self.assertEqual(c.raw, "Dana prefers morning calls about Atlas")
        self.assertEqual(c.entities, ["person:dana", "project:atlas"])
        self.assertEqual(c.why, "while working on atlas launch")
        with self.assertRaises(ValueError):
            self.store.capture("hologram", "x", at=T0)

    def test_connections_promotion_revision(self) -> None:
        a = self.store.capture("thought", "Dana prefers morning calls", at=T0)
        b = self.store.capture("voice", "dana prefers morning calls", at=T0 + H)
        self.store.capture("url", "https://example.test/atlas-spec", at=T0, context={"nearby_entities": ["project:atlas"]})
        links = self.store.discover_connections()
        self.assertTrue(any({l["a"], l["b"]} == {a.id, b.id} for l in links))
        self.assertTrue(all(l["status"] == "suggested" for l in links))
        props = self.store.propose_promotions()
        self.assertEqual(props[0]["kind"], "preference")
        f = self.store.promote(props[0]["statement"], "preference", props[0]["provenance"], at=T0)
        with self.assertRaises(ValueError):
            self.store.promote("x", "fact", [], at=T0)
        self.store.capture("thought", "Dana does not prefer morning calls", at=T0 + 2 * H)
        self.store.capture("thought", "Dana does not prefer morning calls", at=T0 + 3 * H)
        conflict = [p for p in self.store.propose_promotions() if p["status"] == "needs_review"]
        self.assertEqual(conflict[0]["conflicts_with"], f.id)
        new = self.store.revise(f.id, "Dana prefers afternoon calls", at=T0 + 4 * H, provenance=[a.id], reason="user said")
        self.assertEqual(self.store.facts[f.id].superseded_by, new.id)
        self.assertEqual(self.store.provenance(new.id)[0]["id"], a.id)

    def test_resurfacing_queue_utility_spaced(self) -> None:
        c = self.store.capture("thought", "torque spec for bike stem is 5 Nm", at=T0, context={"latlon": HOME})
        hits = self.store.resurface(query_text="bike stem torque", latlon=HOME)
        self.assertEqual(hits[0]["id"], c.id)
        q = self.store.activation_queue(available_minutes=3)
        self.assertEqual(len(q), 1)
        self.assertIn("change", q[0]["prompt"])
        self.store.mark(c.id, "applied", decision_changed=True)
        self.assertEqual(self.store.utility_report()["thought"]["decisions"], 1)
        sr = mm.SpacedResurfacer()
        sr.add("concept", T0)
        d1 = sr.review("concept", True, T0 + 24 * H)
        d2 = sr.review("concept", True, d1)
        self.assertGreater(d2 - d1, d1 - (T0 + 24 * H))
        self.assertEqual(sr.due(d2 + H), ["concept"])
        comp = mm.compress("Alpha beta gamma. " * 3 + "The key finding is that torque matters. " + "Filler words here. " * 10)
        self.assertLessEqual(len(comp["w10"].split()), 11)
        self.assertIn("full", comp)

    def test_ask_with_disclosure(self) -> None:
        res = self.store.ask("when is the atlas review", {"email": [{"id": "m1", "text": "Atlas review moved to Friday",
                                                                     "at": T0 - 48 * H}]}, now=T0)
        self.assertEqual(res["answers"][0]["source"], "email")
        self.assertIn("2.0 days old", res["disclosure"][0])

    def test_friction_and_spatial(self) -> None:
        fl = mm.FrictionLog()
        for _ in range(3):
            fl.why_not_automatic("why do I have to turn on the porch light manually", at=T0)
        fl.why_not_automatic("export expense report again", at=T0)
        self.assertEqual(fl.cluster_moments()[0]["count"], 3)
        for i in range(3):
            for j, cmd in enumerate(["open vpn", "open jira", "open slack"]):
                fl.record_command(cmd, T0 + i * H + j * timedelta(minutes=1))
        self.assertEqual(fl.repeated_sequences()[0]["sequence"], ["open vpn", "open jira", "open slack"])
        fl.record_failure("what's my tire pressure", "vehicle telematics API", T0)
        fl.record_failure("is the garage open", "garage door sensor", T0)
        fl.record_failure("tire pressure?", "vehicle telematics API", T0)
        self.assertEqual(fl.capability_gaps()[0]["missing"], "vehicle telematics API")
        added = fl.harvest([{"title": "Porch light automation", "evidence": ["log"]},
                            {"title": "No evidence idea", "evidence": []},
                            {"title": "Push the pre-meeting brief", "evidence": ["x"]}],
                           existing_titles=["Push, don't pull, the pre-meeting brief"])
        self.assertEqual([a["title"] for a in added], ["Porch light automation"])
        sm = mm.SpatialMemory()
        sm.bookmark("garage bench", HOME, T0, objects=["screwdriver"])
        w = sm.where_is("screwdriver", T0 + 24 * H)
        self.assertEqual(w["status"], "last_observed")
        self.assertIn("not a claim", w["caveat"])
        self.assertEqual(sm.where_is("unicorn", T0)["status"], "never_observed")
        sm.leave_note("me", HOME, "Take the recycling out")
        self.assertEqual(sm.arrive("me", OFFICE, T0), [])
        self.assertEqual(sm.arrive("me", HOME, T0), ["Take the recycling out"])


class LifeAdminTests(unittest.TestCase):
    def test_brief_geofence_health(self) -> None:
        ev = la.Event("e1", "Board meeting", T0 + 30 * timedelta(minutes=1), T0 + 2 * H, location="Office",
                      importance="high")
        self.assertEqual(la.brief_schedule([ev], now=T0)[0]["push_at"], (T0 + 15 * timedelta(minutes=1)).isoformat())
        self.assertEqual(la.geofence_eta_alert(ev, HOME, T0)["status"], "unbound")
        la.bind_location(ev, {"office": OFFICE})
        alert = la.geofence_eta_alert(ev, HOME, T0)
        self.assertEqual(alert["status"], "at_risk")
        self.assertIn("starts in 30", alert["message"])
        morning = la.Event("e2", "Board", T0.replace(hour=9), T0.replace(hour=10), importance="high")
        self.assertIn("slept 4 hours", la.health_flags([morning], 4, day=T0.date())[0])
        self.assertEqual(la.health_flags([morning], None, day=T0.date()), [])

    def test_email_actions_obligations(self) -> None:
        self.assertTrue(la.triage_email({"subject": "Please sign the contract", "body": ""})["needs_decision"])
        sched = la.triage_email({"subject": "Can we meet?", "body": "", "from_name": "Dana Lee"})
        self.assertEqual(sched["send_status"], "awaiting_explicit_approval")
        self.assertIn("Dana", sched["draft"])
        notes = "- Dana will send the revised deck by Friday.\n- I will book the venue by tomorrow.\nRandom line."
        items = la.extract_action_items(notes, meeting_id="m1", ended_at=T0)
        self.assertEqual([i["owner"] for i in items], ["Dana", "me"])
        self.assertEqual(items[0]["due"][:10], "2026-10-02")
        self.assertEqual(items[1]["due"][:10], "2026-10-02")
        og = la.ObligationGraph()
        og.ingest("I'll send the invoice by tomorrow. Could you review the lease?", source="mail:1", author="me", at=T0)
        og.ingest("Can you please confirm the date?", source="mail:2", author="dana", at=T0)
        mine = og.open_for("me")
        self.assertEqual(len(mine), 2)
        og.resolve(mine[0]["id"], "mail:3")
        self.assertEqual(len(og.open_for("me")), 1)

    def test_receipts_spending_contracts(self) -> None:
        r = la.parse_receipt({"id": "r1", "from_name": "StreamCo", "subject": "Your subscription",
                              "body": "You will be charged $15.99 monthly. Next billing 2026-10-05."})
        self.assertTrue(r["subscription"])
        self.assertEqual(r["renews_on"], "2026-10-05")
        self.assertEqual(la.renewal_deadlines([r], today=date(2026, 10, 1))[0]["days_until_renewal"], 4)
        hist = [{"merchant": "Grocer", "amount": a} for a in (80, 95, 102, 88, 91)]
        flagged = la.spending_anomalies(hist, [{"merchant": "Grocer", "amount": 640}, {"merchant": "Grocer", "amount": 99}])
        self.assertEqual([f["amount"] for f in flagged], [640])
        c = la.extract_contract_clauses("This lease shall terminate on 2027-03-31. It will automatically renew for "
                                        "successive one-year terms unless either party gives sixty (60) days' written notice.")
        self.assertTrue(c["auto_renews"])
        self.assertEqual(c["notice_days"], 60)
        self.assertEqual(c["notice_deadline"], "2027-01-30")

    def test_vehicle_packages_docs_trip_receipts(self) -> None:
        due = la.vehicle_due([la.MaintenanceItem("oil", 5000, 180, 40000, date(2026, 5, 1)),
                              la.MaintenanceItem("tires", 7500, None, 44000, date(2026, 9, 1))],
                             odometer=45200, today=date(2026, 10, 1))
        self.assertEqual(due, [{"item": "oil", "status": "overdue", "detail": "-200 miles left, 27 days left"}])
        pk = la.correlate_packages([{"subject": "Delivered", "body": "1Z999AA10123456784 was delivered", "at": T0}],
                                   [{"id": "door:1", "at": T0 + timedelta(minutes=5)}])
        self.assertEqual(pk[0]["status"], "arrived")
        ev = la.Event("m", "Review", T0 + H, T0 + 2 * H, documents=["deck"])
        notes = la.document_freshness(ev, {"deck": [{"at": T0 - timedelta(minutes=40)}]}, {"deck": T0 - 24 * H}, T0)
        self.assertIn("40 minutes ago", notes[0])
        trip = la.trip_timeline([{"id": "c1", "subject": "Your flight UA 123", "body": "UA123 SBA -> SFO", "at": T0}],
                                destination_checks={"wildfire": "red flag warning"})
        self.assertEqual(trip["timeline"][0]["to"], "SFO")
        self.assertIn("review wildfire before departure", trip["checklist"])
        ar = la.ActionReceipts()
        ar.expect("dinner", "table for 2", ["reservation", "confirmed"], deadline=T0 + H)
        self.assertEqual(ar.offer({"id": "m9", "subject": "Reservation confirmed", "body": ""}), ["dinner"])
        ar.expect("form", "DMV form", ["dmv"], deadline=T0)
        self.assertEqual(ar.overdue(T0 + H), ["form"])

    def test_preparation_opportunities_hud_progress(self) -> None:
        ev = la.Event("f", "Flight", T0 + 20 * H, T0 + 23 * H)
        steps = la.prepare(ev, vehicle_range_mi=60, trip_distance_mi=40, forecast={"precip_prob": 0.7},
                           travel_min=50, parking_min=15, security_min=30, changed_docs=["itinerary"])
        dos = [s["do"] for s in steps]
        self.assertEqual(dos[0], "charge/fuel vehicle tonight")
        self.assertIn("bring rain gear", dos)
        self.assertIn("leave", dos)
        gaps = la.free_gaps([la.Event("a", "A", T0 + H, T0 + 2 * H)], day_start=T0, day_end=T0 + 3 * H)
        self.assertEqual(len(gaps), 2)
        near = (HOME[0] + 0.001, HOME[1])
        res = la.opportunities(here=HOME, free_minutes=18, errands=[
            la.Errand("post", "drop off the return", 5, near, value=2),
            la.Errand("atm", "grab cash", 4, near),
            la.Errand("far", "hardware store", 10, OFFICE),
            la.Errand("run", "go for a run", 15, None, outdoor=True)])
        self.assertEqual(sorted(res["bundle"]), ["atm", "post"])
        self.assertIn("18 free minutes", res["message"])
        hud = la.nearest_obligations(now=T0, events=[ev], deadlines=[{"task": "tax", "due": "2026-10-15"}],
                                     places=[{"name": "office", "latlon": OFFICE}], here=HOME)
        self.assertEqual(hud["next_event"]["title"], "Flight")
        p = la.progress([{"status": "done"}] * 6 + [{"status": "open"}] * 4, streak_days=3)
        self.assertEqual((p["percent"], p["level"], p["next_milestone"]), (60, 2, 4))
        s = la.evening_summary([ev], [ev], [{"task": "pay rent", "due": "2026-10-02"}], sleep_avg=5.5)
        self.assertIn("pay rent", s)


if __name__ == "__main__":
    unittest.main()
