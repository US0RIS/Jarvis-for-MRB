from __future__ import annotations

from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException,Response

from jarvis_mrb import service,user_belief_model as model


class UserBeliefAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.db=Path(self.temp.name)/"beliefs.sqlite3"
        self.settings=[
            patch.object(service,"API_TOKEN","only-this-test"),
            patch.object(model,"DEFAULT_PATH",self.db),
            patch.dict("os.environ",{"JARVIS_USER_BELIEF_MODEL_ENABLED":"1"}),
        ]
        for setting in self.settings:setting.start()
        self.auth="Bearer only-this-test"
        self.now=datetime.now(timezone.utc).replace(microsecond=0)

    def tearDown(self):
        for setting in reversed(self.settings):setting.stop()
        self.temp.cleanup()

    def test_auth_is_mandatory_even_when_server_can_be_tokenless(self):
        with self.assertRaises(HTTPException) as error:
            service.belief_model_divergences(Response(),authorization=None)
        self.assertEqual(error.exception.status_code,401)

    def test_api_supplied_world_fact_is_attested_and_no_auto_warning(self):
        record=service.belief_model_world(
            service.BeliefWorldRecordRequest(
                subject="contract:apollo",predicate="interest.rate",value="15%",
                evidence_id="operator:upload"
            ),
            Response(),authorization=self.auth,
        )
        self.assertEqual(record["source_kind"],"attested")
        service.belief_model_exposure(
            service.BeliefEvidenceRecordRequest(
                subject="contract:apollo",predicate="interest.rate",value="10%",
                evidence_id="user:spoken",kind="stated",
                observed_at=(self.now-timedelta(minutes=30)).isoformat(),
            ),Response(),authorization=self.auth,
        )
        service.belief_model_decision(
            service.BeliefDecisionRequest(
                subject="contract:apollo",predicate="interest.rate",label="Sign contract",
                deadline=(self.now+timedelta(minutes=15)).isoformat(),
                enrollment_id="explicit:approval",
            ),Response(),authorization=self.auth,
        )
        response=Response()
        data=service.belief_model_divergences(response,authorization=self.auth)
        self.assertEqual(data["warnings"],[])
        self.assertIn("world_not_independently_verified",str(data["suppressed"]))
        self.assertEqual(response.headers["cache-control"],"private, no-store")

    def test_explicit_forget_requires_literal_confirmation(self):
        with self.assertRaises(HTTPException) as error:
            service.belief_model_forget(service.BeliefForgetRequest(confirm="yes"),
                                        Response(),authorization=self.auth)
        self.assertEqual(error.exception.status_code,422)
        result=service.belief_model_forget(
            service.BeliefForgetRequest(confirm="DELETE_USER_BELIEF_MODEL"),
            Response(),authorization=self.auth
        )
        self.assertEqual(result,{"world":0,"belief":0,"decisions":0})


if __name__=="__main__":
    unittest.main()
