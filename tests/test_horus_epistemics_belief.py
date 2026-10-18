from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import belief, epistemics as ep

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class FreshnessGateTests(unittest.TestCase):
    def test_routing_detects_mutable_claims_and_contradictions(self) -> None:
        self.assertTrue(ep.route_claim("Was the Pixel 12 just announced today?").requires_live_lookup)
        self.assertIn("release", ep.route_claim("Apple released a new model").categories)
        self.assertFalse(ep.route_claim("What is the square root of 81").requires_live_lookup)
        r = ep.route_claim("The capital of France is Paris", user_evidence_conflicts_with_prior=True)
        self.assertTrue(r.requires_live_lookup)
        self.assertTrue(r.contradiction)
        down = ep.route_claim("Is the store open now?", live_source_available=False)
        self.assertTrue(any("current-unverified" in x for x in down.reasons))

    def test_search_down_never_negates(self) -> None:
        receipt = ep.verify_claim("Acme announced the X1 today", [], provider="serper", query="acme x1",
                                  now=T0, search_failed=True)
        self.assertEqual(receipt.verdict, "unverified")
        self.assertEqual(ep.epistemic_cutoff_guard(True, receipt), "unverified")
        text = ep.answer_for_receipt(receipt)
        self.assertIn("not false", text)
        self.assertNotIn("definitely", text)

    def test_real_new_announcement_beats_model_prior(self) -> None:
        claim = "Acme announced the X1 today"
        ev = [ep.Evidence("e1", "acme.com", T0 - timedelta(minutes=5), [claim], first_party=True, category="release")]
        receipt = ep.verify_claim(claim, ev, provider="web", query="acme x1", now=T0)
        self.assertEqual(receipt.verdict, "supported")
        self.assertEqual(ep.epistemic_cutoff_guard(model_prior_says_false=True, receipt=receipt), "true")
        self.assertEqual(receipt.claim_support[claim], ["e1"])

    def test_conflicting_and_expired_evidence(self) -> None:
        claim = "Flight 12 is delayed"
        ev = [ep.Evidence("a", "airline", T0, [claim], category="flight"),
              ep.Evidence("b", "airport", T0, [claim], kind="conflicting", category="flight")]
        self.assertEqual(ep.verify_claim(claim, ev, provider="x", query="q", now=T0).verdict, "conflicting")
        stale = [ep.Evidence("a", "airline", T0 - timedelta(hours=2), [claim], category="flight")]
        self.assertEqual(ep.verify_claim(claim, stale, provider="x", query="q", now=T0).verdict, "unverified")

    def test_evidence_before_explanation(self) -> None:
        seq = ep.AdjudicationSequence()
        with self.assertRaises(RuntimeError):
            seq.forensic_analysis(["font mismatch"])
        seq.classify()
        seq.verify(ep.VerificationReceipt("c", "p", "q", T0, [], "supported"))
        out = seq.forensic_analysis(["font mismatch"])
        self.assertEqual(out["source_verification"], "supported")
        self.assertEqual(out["image_forensic_hypotheses"][0]["status"], "hypothesis")

    def test_linter_flags_unsupported_certainty_and_expired(self) -> None:
        answer = "That product definitely does not exist. The sky is blue."
        findings = ep.lint_answer(answer, [], now=T0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].problem, "unsupported-current-claim")
        ev = [ep.Evidence("w", "nws", T0 - timedelta(hours=3), ["it is raining in Ventura"], category="weather")]
        f2 = ep.lint_answer("It is raining in Ventura right now.", ev, now=T0)
        self.assertEqual(f2[0].problem, "evidence-expired:refresh-required")
        fresh = [ep.Evidence("w", "nws", T0, ["it is raining in Ventura"], category="weather")]
        self.assertEqual(ep.lint_answer("It is raining in Ventura right now.", fresh, now=T0), [])
        self.assertTrue(ep.enforce_evidence_bound(answer, [], now=T0).startswith("[unverified]"))

    def test_ttl_policy_is_configurable(self) -> None:
        p = ep.FreshnessPolicy({"weather": 60})
        self.assertFalse(p.is_fresh("weather", T0 - timedelta(minutes=2), T0))
        self.assertTrue(p.is_fresh("stable", T0 - timedelta(days=9999), T0))
        c = ep.Claim("x", ep.EXTERNALLY_VERIFIED, "price", verified_at=T0 - timedelta(hours=2), source_ids=["s"])
        self.assertTrue(c.needs_refresh(T0))
        self.assertEqual(ep.uncertainty_label(c, T0)["status"], "stale")
        self.assertEqual(ep.uncertainty_label(ep.Claim("y", ep.CURRENT_UNVERIFIED), T0)["status"], "unknown")

    def test_decay_contradiction_reputation_snapshot_lineage(self) -> None:
        self.assertAlmostEqual(ep.decayed_confidence(0.8, T0 - timedelta(hours=1), T0, 3600), 0.4)
        conflicts = ep.detect_contradictions([
            ep.SourceAssertion("nws", "road", "open", True, T0),
            ep.SourceAssertion("caltrans", "road", "open", False, T0),
        ])
        self.assertEqual(len(conflicts), 1)
        ledger = ep.SourceReputationLedger()
        for _ in range(8):
            ledger.record("good", correct=True)
        ledger.record("bad", correct=False)
        fused = ledger.fuse([("good", 1), ("bad", 2)])
        self.assertEqual(fused["value"], 1)
        self.assertTrue(fused["contested"])
        self.assertEqual(ep.SourceReputationLedger.from_dict(ledger.to_dict()).reliability("good"), ledger.reliability("good"))
        snap = ep.freeze_evidence("c", [ep.Evidence("e", "s", T0, ["c"])], T0)
        self.assertEqual(snap.evidence[0]["id"], "e")
        lin = ep.ClaimLineage()
        raw = lin.add("raw_observation", "camera frame 1")
        ext = lin.add("extraction", "smoke visible", [raw])
        concl = lin.add("conclusion", "possible fire", [ext])
        self.assertEqual(lin.raw_sources(concl), ["camera frame 1"])
        self.assertEqual([n["stage"] for n in lin.expand(concl)], ["raw_observation", "extraction", "conclusion"])


class UserBeliefModelTests(unittest.TestCase):
    def test_apollo_moment_intervention(self) -> None:
        m = belief.UserBeliefModel()
        m.record_exposure(belief.Exposure("deal.rate", "10%", "viewed_document", T0 - timedelta(days=2)))
        m.record_fact(belief.VerifiedFact("deal.rate", "15%", T0, T0 - timedelta(hours=3), ["draft-v4"]))
        m.record_exposure(belief.Exposure("deal.rate", "15%", "sent_to_user_unopened", T0 - timedelta(hours=2)))
        acts = [belief.PendingAction("sign agreement", ["deal.rate"], T0 + timedelta(minutes=12),
                                     irreversible=True, consequence="critical")]
        out = m.interventions(acts, now=T0)
        self.assertEqual(len(out), 1)
        self.assertIn("12 minutes", out[0]["message"])
        self.assertFalse(out[0]["exposed_to_change"])

    def test_acknowledged_change_suppresses_and_unknown(self) -> None:
        m = belief.UserBeliefModel()
        self.assertEqual(m.estimate("x").status, "unknown")
        m.record_exposure(belief.Exposure("x", 1, "viewed_document", T0 - timedelta(days=1)))
        m.record_fact(belief.VerifiedFact("x", 2, T0, T0 - timedelta(hours=1)))
        m.record_exposure(belief.Exposure("x", 2, "explicit_acknowledgment", T0 - timedelta(minutes=30)))
        acts = [belief.PendingAction("pay", ["x"], T0 + timedelta(hours=1))]
        self.assertEqual(m.interventions(acts, now=T0), [])
        self.assertEqual(m.estimate("x").believed_value, 2)


if __name__ == "__main__":
    unittest.main()
