from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response

from jarvis_mrb import service


class WorldArmorServiceBoundaryTests(TestCase):
    def test_private_token_required_even_if_enabled(self):
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"1"}), \
             patch.object(service, "API_TOKEN", "private-secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_capabilities(Response(), authorization=None)
            self.assertEqual(ctx.exception.status_code,401)
            response=Response()
            values=service.world_armor_capabilities(
                response,authorization="Bearer private-secret")
            self.assertTrue(values["enabled"])
            self.assertEqual(response.headers["Cache-Control"],"private, no-store")

    def test_tokenless_backend_cannot_expose_world_armor(self):
        with patch.object(service, "API_TOKEN", ""):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_capabilities(Response(),authorization=None)
            self.assertEqual(ctx.exception.status_code,503)

    def test_no_arbitrary_client_source_forgery_contract(self):
        self.assertEqual(set(service.WorldArmorIdRequest.model_fields),{"investigation_id"})
        self.assertEqual(set(service.WorldArmorReplayRequest.model_fields),
                         {"investigation_id","as_known_at"})
        routes={route.path for route in service.app.routes}
        self.assertNotIn("/world-armor/v1/fixture",routes)
        self.assertIn("/world-armor/v1/observe",routes)

    def test_correlate_requires_auth_and_accepts_only_typed_query(self):
        request=service.WorldArmorCorrelationRequest(
            investigation_id="0"*32,
            start_at="2026-09-24T18:00:00Z",
            end_at="2026-09-24T19:00:00Z",
        )
        self.assertEqual(
            set(service.WorldArmorCorrelationRequest.model_fields),
            {"investigation_id", "start_at", "end_at",
             "as_known_at", "source_ids", "query_radius_km"},
        )
        with patch.object(service,"API_TOKEN","private-secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_correlate(request,Response(),authorization=None)
            self.assertEqual(ctx.exception.status_code,401)
            with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
                response=Response()
                with self.assertRaises(HTTPException) as ctx:
                    service.world_armor_correlate(
                        request,response,
                        authorization="Bearer private-secret")
                self.assertEqual(ctx.exception.status_code,503)
                self.assertEqual(response.headers["Cache-Control"],"private, no-store")

    def test_hypothesis_query_requires_auth_and_has_no_freeform_claim_field(self):
        request=service.WorldArmorCorrelationRequest(
            investigation_id="0"*32,
            start_at="2026-09-24T18:00:00Z",
            end_at="2026-09-24T19:00:00Z",
            query_radius_km=10,
        )
        self.assertNotIn("claim",service.WorldArmorCorrelationRequest.model_fields)
        self.assertNotIn("prompt",service.WorldArmorCorrelationRequest.model_fields)
        with patch.object(service,"API_TOKEN","private-secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_hypotheses(
                    request,Response(),authorization=None)
            self.assertEqual(ctx.exception.status_code,401)
            with patch.dict(os.environ,{"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
                with self.assertRaises(HTTPException) as ctx:
                    service.world_armor_hypotheses(
                        request,Response(),
                        authorization="Bearer private-secret")
                self.assertEqual(ctx.exception.status_code,503)

    def test_ios_workbench_has_real_correlation_and_receipt_timeline_wiring(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        view=(root/"ios/JarvisIOS/WorldArmorView.swift").read_text(encoding="utf-8")
        client=(root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        self.assertIn("worldArmorCorrelate(",view)
        self.assertIn("worldArmorHypotheses(",view)
        self.assertIn("hypothesisPanel(",view)
        self.assertIn("candidate explanations",view)
        self.assertIn("alternativeExplanations",view)
        self.assertIn("missingEvidence",view)
        self.assertIn("MapCircle(",view)
        self.assertIn("temporalQueryPanel",view)
        self.assertIn("correlationPanel(",view)
        self.assertIn("sampleTimeline",view)
        self.assertIn("Rewind to a retained receipt",view)
        self.assertIn("source_coverage",view)
        self.assertIn("world-armor/v1/correlate",client)
        self.assertIn("world-armor/v1/hypotheses/query",client)
        self.assertIn("in: ...Date()",view)
        self.assertIn("UIApplication", (root/"ios/JarvisIOS/RealityMesh.swift").read_text(encoding="utf-8"))

    def test_disabled_create_does_not_touch_database(self):
        request=service.WorldArmorCreateRequest(
            label="Test",latitude=34.1,longitude=-118.2)
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}), \
             patch.object(service,"API_TOKEN","private-secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_create(
                    request,Response(),authorization="Bearer private-secret")
            self.assertEqual(ctx.exception.status_code,503)

    def test_source_delta_route_enforces_private_auth_and_never_polls(self):
        request=service.WorldArmorIdRequest(investigation_id="a"*32)
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch("jarvis_mrb.world_armor_phase1.compare_recent",
                   return_value={"comparison":"two_received_samples",
                                 "external_actions":0,"model_calls":0}) as read:
            with self.assertRaises(HTTPException) as context:
                service.world_armor_changes(request,Response(),authorization=None)
            self.assertEqual(context.exception.status_code,401)
            read.assert_not_called()
            response=Response()
            result=service.world_armor_changes(
                request,response,authorization="Bearer private-secret")
            self.assertEqual(result["comparison"],"two_received_samples")
            self.assertEqual(response.headers["Cache-Control"],"private, no-store")
            read.assert_called_once_with("a"*32)



if __name__ == "__main__":
    import unittest
    unittest.main()
