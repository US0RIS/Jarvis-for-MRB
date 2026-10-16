from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import user_belief_model as beliefs


class UserBeliefModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=TemporaryDirectory()
        self.db=Path(self.temp.name)/"user_beliefs.sqlite3"
        self.opt_in=patch.dict("os.environ", {"JARVIS_USER_BELIEF_MODEL_ENABLED":"1"})
        self.opt_in.start()
        self.now=datetime.now(timezone.utc).replace(microsecond=0)
        self.subject="contract:apollo"
        self.predicate="interest.rate"

    def tearDown(self) -> None:
        self.opt_in.stop()
        self.temp.cleanup()

    def belief(self, value: str, *, kind: str="stated", minutes_ago: int=30):
        return beliefs.observe_belief(
            self.subject, self.predicate, value, kind=kind, evidence_id="user:spoken",
            observed_at=self.now-timedelta(minutes=minutes_ago), db_path=self.db,
        )

    def world(self, value: str, *, minutes_ago: int=15, verified: bool=False):
        return beliefs.observe_world(
            self.subject, self.predicate, value, evidence_id="provider:document:v2",
            observed_at=self.now-timedelta(minutes=minutes_ago), db_path=self.db,
            _independently_verified=verified,
        )

    def decision(self, minutes_ahead: int=12):
        return beliefs.enroll_decision(
            self.subject,self.predicate,"Sign the Apollo contract",
            deadline=self.now+timedelta(minutes=minutes_ahead),
            enrollment_id="explicit:user:signature:approval",db_path=self.db,
        )

    def result(self, now=None):
        return beliefs.evaluate(db_path=self.db,now=now or self.now)

    def test_opt_in_required_even_for_read(self):
        with patch.dict("os.environ", {"JARVIS_USER_BELIEF_MODEL_ENABLED":"0"}):
            with self.assertRaises(RuntimeError): self.result()
            with self.assertRaises(RuntimeError): self.belief("10%")

    def test_apollo_exposes_decision_relevant_gap_without_claiming_mind_reading(self):
        self.belief("10%")
        fact=self.world("15%",verified=True)
        decision=self.decision()
        out=self.result()
        self.assertEqual(len(out["warnings"]),1)
        warning=out["warnings"][0]
        self.assertEqual(warning["decision_id"],decision["id"])
        self.assertEqual(warning["last_stated_value"],"10%")
        self.assertEqual(warning["latest_verified_value"],"15%")
        self.assertEqual(warning["world_evidence_id"],"provider:document:v2")
        self.assertEqual(warning["minutes_until_deadline"],12)
        self.assertIn("may have changed",warning["uncertainty"])
        self.assertIn("no_automatic",warning["action"])
        self.assertEqual(fact["source_kind"],"provider_verified")

    def test_unverified_world_record_must_not_generate_alert(self):
        self.belief("10%")
        record=self.world("15%")
        self.decision()
        self.assertEqual(record["status"],"recorded_not_independently_verified")
        out=self.result()
        self.assertEqual(out["warnings"],[])
        self.assertEqual(out["suppressed"][0]["reason"],"world_not_independently_verified")

    def test_exposure_is_not_assumed_comprehension(self):
        self.belief("10%")
        self.world("15%",verified=True)
        self.belief("15%",kind="exposed",minutes_ago=5)
        self.decision()
        self.assertEqual(len(self.result()["warnings"]),1)

    def test_explicit_acknowledgement_suppresses_stale_warning(self):
        self.belief("10%")
        self.world("15%",verified=True)
        self.belief("15%",kind="acknowledged",minutes_ago=5)
        self.decision()
        out=self.result()
        self.assertEqual(out["warnings"],[])
        self.assertEqual(out["suppressed"][0]["reason"],"user_acknowledged_new_value")

    def test_later_explicit_user_statement_does_not_claim_they_still_believe_old_state(self):
        self.belief("10%")
        self.world("15%",verified=True)
        self.belief("13%",minutes_ago=5)
        self.decision()
        out=self.result()
        self.assertEqual(out["warnings"],[])
        self.assertEqual(out["suppressed"][0]["reason"],"later_user_statement_needs_reconciliation")

    def test_outside_horizon_or_resolved_does_not_warn(self):
        self.belief("10%")
        self.world("15%",verified=True)
        decision=self.decision(minutes_ahead=180)
        self.assertEqual(self.result()["warnings"],[])
        self.assertTrue(beliefs.resolve_decision(decision["id"],db_path=self.db)["resolved"])
        self.assertEqual(self.result()["warnings"],[])

    def test_old_facts_expire_even_if_they_were_once_verified(self):
        self.belief("10%",minutes_ago=2400)
        self.world("15%",minutes_ago=1800,verified=True)
        self.decision()
        out=self.result()
        self.assertEqual(out["warnings"],[])
        self.assertEqual(out["suppressed"][0]["reason"],"world_evidence_expired")

    def test_bad_timestamps_and_malformed_sources_are_rejected(self):
        with self.assertRaises(ValueError):
            beliefs.enroll_decision(self.subject,self.predicate,"Sign",
                deadline=self.now+timedelta(days=60), enrollment_id="user", db_path=self.db)
        with self.assertRaises(ValueError):
            beliefs.observe_belief(self.subject,self.predicate,"10%",
                kind="inferred",evidence_id="guess",db_path=self.db)
        with self.assertRaises(ValueError):
            beliefs.observe_world(self.subject,"../../database","10%",
                evidence_id="source",db_path=self.db)
        with self.assertRaises(ValueError):
            beliefs.observe_world(self.subject,self.predicate,"10%",
                evidence_id="source",observed_at="2026-11-02",db_path=self.db)

    def test_forget_erases_all_records(self):
        self.belief("10%")
        self.world("15%",verified=True)
        self.decision()
        self.assertEqual(beliefs.forget(db_path=self.db),{"world":1,"belief":1,"decisions":1})
        self.assertEqual(self.result()["warnings"],[])


if __name__ == "__main__":
    unittest.main()
