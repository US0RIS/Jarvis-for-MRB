from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import analysis as an
from jarvis_mrb.horus import identity as idr

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class AnalysisTests(unittest.TestCase):
    def test_ach_posteriors_and_diagnosticity(self) -> None:
        m = an.ACHMatrix(["leak", "condensation", "sensor_fault"])
        m.add_evidence(an.EvidenceItem("e1", "water on floor"), {"leak": "CC", "condensation": "C", "sensor_fault": "II"})
        m.add_evidence(an.EvidenceItem("e2", "humid day"), {"leak": "N", "condensation": "C", "sensor_fault": "N"})
        m.add_evidence(an.EvidenceItem("e3", "meter spinning"), {"leak": "CC", "condensation": "II", "sensor_fault": "I"})
        s = m.summary()
        self.assertEqual(s["leading"], "leak")
        self.assertEqual(s["evidence_by_diagnosticity"][-1][0], "e2")
        self.assertLess(m.diagnosticity("e2"), m.diagnosticity("e1"))
        self.assertEqual(min(s["inconsistency"], key=s["inconsistency"].get), "leak")
        with self.assertRaises(ValueError):
            an.ACHMatrix(["only"])

    def test_information_gain_respects_authorization(self) -> None:
        prior = {"a": 0.5, "b": 0.5}
        perfect = an.CandidateObservation("perfect", 1, {"x": {"a": 1, "b": 0}, "y": {"a": 0, "b": 1}})
        useless = an.CandidateObservation("useless", 1, {"x": {"a": 0.5, "b": 0.5}, "y": {"a": 0.5, "b": 0.5}})
        illegal = an.CandidateObservation("illegal", 0.1, {"x": {"a": 1, "b": 0}, "y": {"a": 0, "b": 1}}, lawful=False)
        plan = an.plan_next_observation(prior, [useless, perfect, illegal])
        self.assertEqual(plan[0]["id"], "perfect")
        self.assertAlmostEqual(plan[0]["gain_bits"], 1.0)
        self.assertNotIn("illegal", [p["id"] for p in plan])

    def test_assumptions_expire_and_invalidate(self) -> None:
        reg = an.KeyAssumptionRegister()
        reg.add(an.Assumption("a1", "road open", ["leave at 5"], invalidated_by=["closure"]))
        reg.add(an.Assumption("a2", "rate is 10%", ["sign deal"], valid_until=T0))
        self.assertEqual(reg.check(now=T0 - timedelta(minutes=1)), [])
        self.assertEqual(reg.check(now=T0 + timedelta(minutes=1), new_evidence=["Caltrans closure on 101"]),
                         ["leave at 5", "sign deal"])

    def test_source_independence_and_stop_rule(self) -> None:
        g = an.SourceIndependenceGraph()
        for site in ("s1", "s2", "s3"):
            g.add_report(site, "wire-story")
        g.add_report("own-reporting")
        self.assertEqual(g.independent_count(["s1", "s2", "s3", "own-reporting"]), 2)
        self.assertEqual(an.should_stop({"a": 0.9}, threshold=0.8, spent=0, budget=1)[1], "decision-threshold-reached")
        self.assertTrue(an.should_stop({"a": 0.5, "b": 0.5}, threshold=0.8, spent=0, budget=5,
                                       best_remaining_gain_bits=0.0)[0])

    def test_investigation_loop(self) -> None:
        cands = [an.CandidateObservation("check_meter", 1, {"spin": {"leak": 0.9, "fault": 0.1},
                                                             "still": {"leak": 0.1, "fault": 0.9}})]
        result = an.run_investigation({"leak": 1, "fault": 1}, cands, lambda _id: "spin", threshold=0.85)
        self.assertEqual(result["best_explanation"], "leak")
        self.assertEqual(len(result["steps"]), 1)

    def test_calibration_and_surprise(self) -> None:
        c = an.ConfidenceCalibrator()
        for _ in range(20):
            c.record("weather", 0.9, False)
        self.assertLess(c.adjust("weather", 0.9), 0.5)
        self.assertGreater(c.brier("weather"), 0.5)
        v = an.verification_depth(0.95, 0.9, consequence="high")
        self.assertEqual(v["action"], "aggressively-corroborate-before-reporting")
        self.assertFalse(v["may_discard_for_surprise"])
        plain = an.verification_depth(0.9, 0.1, consequence="high", source_quality=0.2, independent_sources=1)
        self.assertGreaterEqual(plain["verification_rounds"], 4)

    def test_counterfactual_departure_and_fusion(self) -> None:
        d = an.departure_time(T0, {"drive": (30, 5), "parking": (10, 3), "security": (20, 8)})
        self.assertLess(datetime.fromisoformat(d["leave_by"]), T0 - timedelta(minutes=60))
        sim = an.simulate({"x": 0}, lambda s, r: {"x": r.random()}, outcome=lambda s: s["x"], runs=100)
        self.assertLess(sim["p10"], sim["p90"])
        fused = an.fuse_estimates("temp", [("a", 20.0, 1.0), ("b", 22.0, 1.0)])
        self.assertIn("21.000", fused.statement)
        self.assertEqual(fused.label, "derived")
        g = an.ConsequenceGraph()
        g.add("leak", "water_damage", 0.5)
        g.set_severity("water_damage", 10)
        g.set_severity("novel_ping", 1)
        self.assertEqual(g.prioritize(["novel_ping", "leak"])[0][0], "leak")
        self.assertTrue(an.alternative_explanations("x", "high"))
        self.assertTrue(an.disconfirmation_queries("the road is open", ["no snow"]))


class IdentityResolverFixtureTests(unittest.TestCase):
    """Synthetic fixture mirroring the future.md acceptance case (no real person)."""

    def setUp(self) -> None:
        g = idr.IdentityGraph()
        add = lambda *a, **k: g.add_claim(idr.IdentityClaim(*a, retrieved_at=T0, **k))  # noqa: E731
        add("p:alex", "employer", "Harbor Labs", "peoplefinder-a", "broker", upstream="db-x")
        add("p:alex", "employer", "Harbor Labs", "peoplefinder-b", "derivative", upstream="db-x")
        add("p:alex", "employer", "Harbor Labs", "peoplefinder-c", "derivative", upstream="db-x")
        add("p:sam", "employer", "Harbor Labs", "harborlabs.example/staff", "person_specific_professional")
        add("p:alex", "employer", "Delta Marine", "deltamarine.example/team", "person_specific_professional")
        add("p:alex", "employer", "Delta Marine", "state-license-board", "primary_record")
        add("p:alex", "residential_address", "12 Elm St", "peoplefinder-a", "broker", upstream="db-x")
        g.add_relationship(idr.Relationship("p:alex", "p:sam", "spouse"))
        self.g = g

    def test_household_contamination_detected_and_derivatives_collapse(self) -> None:
        a = self.g.assess("p:alex", "employer", "Harbor Labs")
        self.assertEqual(a.status, "lead_only")
        self.assertEqual(a.independent_origins, 1)
        types = {h["type"] for h in a.hypotheses}
        self.assertIn("HOUSEHOLD_RELATIVE_ATTRIBUTE_CONTAMINATION", types)
        self.assertIn("DERIVATIVE_REPRODUCTION", types)

    def test_independent_primary_sources_verify(self) -> None:
        a = self.g.assess("p:alex", "employer", "Delta Marine")
        self.assertEqual(a.status, "verified")
        surprising = self.g.assess("p:alex", "employer", "Delta Marine", surprise=0.95)
        self.assertEqual(surprising.status, "supported")  # extra scrutiny, not rejection
        self.assertGreater(surprising.required_verification_rounds, a.required_verification_rounds)
        self.assertEqual(self.g.assess("p:alex", "employer", "Nowhere Inc").status, "unknown")

    def test_minimization_and_permissions(self) -> None:
        purpose = idr.Purpose("vet a contractor", {"employer", "license"})
        addr = next(c for c in self.g.claims if c.attribute == "residential_address")
        self.assertEqual(idr.salience(addr, purpose), "discoverable")
        perms = idr.permissions(addr, purpose)
        self.assertFalse(perms["disclose"])
        self.assertFalse(perms["act"])
        self.assertFalse(perms["retain"])
        receipt = idr.research_receipt(self.g, self.g.assess("p:alex", "employer", "Delta Marine"), purpose)
        self.assertEqual(receipt["status"], "verified")
        self.assertTrue(receipt["evidence_for"])

    def test_alias_clusters_are_hypotheses(self) -> None:
        clusters = idr.cluster_aliases(["Jon Smyth", "Jon Smith", "Robert Kline"])
        self.assertEqual(len(clusters), 2)
        self.assertTrue(all(c["status"] == "hypothesis" for c in clusters))


if __name__ == "__main__":
    unittest.main()
