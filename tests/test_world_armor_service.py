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
        observation_section=view.split("struct ArmorObservation",1)[1].split(
            "struct ArmorSampleMoment",1
        )[0]
        coverage_section=view.split("struct ArmorCoverage",1)[1].split(
            "struct ArmorValues",1
        )[0]
        self.assertIn('sampleCoverageStatus = "sample_coverage_status"',
                      observation_section)
        self.assertNotIn("sampleCoverageStatus",coverage_section)
        self.assertIn("temporalQueryPanel",view)
        self.assertIn("correlationPanel(",view)
        self.assertIn("sampleTimeline",view)
        self.assertIn("Rewind to a retained receipt",view)
        self.assertIn("source_coverage",view)
        self.assertIn("world-armor/v1/correlate",client)
        self.assertIn("world-armor/v1/hypotheses/query",client)
        self.assertIn("in: ...Date()",view)
        self.assertIn("UIApplication", (root/"ios/JarvisIOS/RealityMesh.swift").read_text(encoding="utf-8"))

    def test_watch_management_requires_private_auth_and_explicit_feature_gate(self):
        request = service.WorldArmorWatchCreateRequest(
            investigation_id="f"*32, interval_minutes=60,
            max_checks=3, lifetime_hours=2,
        )
        self.assertEqual(
            set(service.WorldArmorWatchCreateRequest.model_fields),
            {"investigation_id", "interval_minutes", "max_checks",
             "lifetime_hours", "attention_kind", "attention_threshold",
             "attention_cooldown_minutes"},
        )
        routes = {route.path for route in service.app.routes}
        self.assertTrue({
            "/world-armor/v1/watches",
            "/world-armor/v1/watches/stop",
            "/world-armor/v1/watches/forget",
            "/world-armor/v1/watches/pause",
            "/world-armor/v1/watches/resume",
        }.issubset(routes))
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch("jarvis_mrb.world_armor_watches.create_watch",
                   return_value={"id": "a"*32, "state": "active"}) as create:
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_watch_create(
                    request, Response(), authorization=None,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            create.assert_not_called()
            response = Response()
            answer = service.world_armor_watch_create(
                request, response, authorization="Bearer private-secret",
            )
            self.assertEqual(answer["state"], "active")
            self.assertEqual(response.headers["Cache-Control"],
                             "private, no-store")
            create.assert_called_once_with(
                "f"*32, interval_minutes=60, max_checks=3,
                lifetime_hours=2, attention_kind="off",
                attention_threshold=None, attention_cooldown_minutes=60,
            )
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch.dict(os.environ, {
                 "JARVIS_WORLD_ARMOR_ENABLED": "1",
                 "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
             }):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_watch_create(
                    request, Response(), authorization="Bearer private-secret",
                )
            self.assertEqual(ctx.exception.status_code, 503)

    def test_watch_stop_remains_authorized_while_watches_disabled(self):
        request = service.WorldArmorWatchIdRequest(watch_id="e"*32)
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch("jarvis_mrb.world_armor_watches.stop_watch",
                   return_value={"state": "revoked"}) as stop, \
             patch.dict(os.environ, {
                 "JARVIS_WORLD_ARMOR_ENABLED": "0",
                 "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
             }):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_watch_stop(
                    request, Response(), authorization=None,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            stop.assert_not_called()
            self.assertEqual(service.world_armor_watch_stop(
                request, Response(),
                authorization="Bearer private-secret",
            )["state"], "revoked")
            stop.assert_called_once_with("e"*32)

    def test_ios_workbench_wires_actual_watch_management_not_auto_start(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        view = (root/"ios/JarvisIOS/WorldArmorView.swift").read_text(
            encoding="utf-8")
        client = (root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text(
            encoding="utf-8")
        self.assertIn("worldArmorWatchCreate(", view)
        self.assertIn("worldArmorWatchTransition(", view)
        self.assertIn("worldArmorWatchForget(", view)
        self.assertIn("worldArmorWatches()", view)
        self.assertIn("watchRunnerAutoStarted", view)
        self.assertIn("world-armor/v1/watches/", client)
        self.assertIn("Enrolling a watch does NOT start", view)

    def test_attention_contract_has_no_freeform_destination_and_requires_auth(self):
        fields = set(service.WorldArmorWatchCreateRequest.model_fields)
        self.assertEqual(fields, {
            "investigation_id", "interval_minutes", "max_checks",
            "lifetime_hours", "attention_kind", "attention_threshold",
            "attention_cooldown_minutes",
        })
        self.assertNotIn("recipient", fields)
        self.assertNotIn("prompt", fields)
        self.assertNotIn("url", fields)
        routes = {r.path for r in service.app.routes}
        self.assertTrue({
            "/world-armor/v1/notices",
            "/world-armor/v1/notices/read",
            "/world-armor/v1/notices/forget",
        }.issubset(routes))
        request = service.WorldArmorWatchCreateRequest(
            investigation_id="a"*32, attention_kind="new_nws_alert",
        )
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch("jarvis_mrb.world_armor_watches.create_watch",
                   return_value={"attention_kind":"new_nws_alert"}) as create:
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_watch_create(
                    request, Response(), authorization=None,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            create.assert_not_called()
            response=Response()
            result=service.world_armor_watch_create(
                request, response, authorization="Bearer private-secret"
            )
            self.assertEqual(result["attention_kind"], "new_nws_alert")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
            create.assert_called_once_with(
                "a"*32, interval_minutes=60, max_checks=6, lifetime_hours=6,
                attention_kind="new_nws_alert",
                attention_threshold=None, attention_cooldown_minutes=60,
            )

    def test_notice_inbox_and_lifecycle_auth_still_apply_when_world_off(self):
        request=service.WorldArmorNoticeIdRequest(notice_id="f"*32)
        with patch.object(service, "API_TOKEN", "private-secret"), \
             patch.dict(os.environ, {
                 "JARVIS_WORLD_ARMOR_ENABLED": "0",
                 "JARVIS_WORLD_ARMOR_WATCHES_ENABLED": "0",
             }), \
             patch("jarvis_mrb.world_armor_attention.list_notices",
                   return_value={"notices": [], "unread_count": 0}) as listed, \
             patch("jarvis_mrb.world_armor_attention.mark_read",
                   return_value={"read_at": "known"}) as read, \
             patch("jarvis_mrb.world_armor_attention.forget_notice",
                   return_value={"deleted": 1}) as forget:
            for action in (service.world_armor_notice_read,
                           service.world_armor_notice_forget):
                with self.assertRaises(HTTPException) as context:
                    action(request, Response(), authorization=None)
                self.assertEqual(context.exception.status_code, 401)
            response=Response()
            inbox=service.world_armor_notice_list(
                response, investigation_id="a"*32,
                authorization="Bearer private-secret",
            )
            self.assertEqual(inbox["unread_count"], 0)
            self.assertEqual(response.headers["Cache-Control"],"private, no-store")
            listed.assert_called_once_with(
                investigation_id="a"*32, watch_id=None, unread_only=False,
            )
            self.assertEqual(service.world_armor_notice_read(
                request, Response(),
                authorization="Bearer private-secret",
            )["read_at"],"known")
            self.assertEqual(service.world_armor_notice_forget(
                request, Response(),
                authorization="Bearer private-secret",
            )["deleted"],1)
            read.assert_called_once_with("f"*32)
            forget.assert_called_once_with("f"*32)

    def test_ios_foreground_attention_wired_without_claimed_push(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        view = (root/"ios/JarvisIOS/WorldArmorView.swift").read_text(encoding="utf-8")
        client = (root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        self.assertIn("worldArmorNotices(", view)
        self.assertIn("pollAttentionInbox()", view)
        self.assertIn("foregroundAttentionOptIn", view)
        self.assertIn("worldArmorNoticeRead(", view)
        self.assertIn("worldArmorNoticeForget(", view)
        self.assertIn("private_inbox_only_no_remote_push",
                      (root/"jarvis_mrb/world_armor_attention.py").read_text(
                          encoding="utf-8"))
        self.assertIn("world-armor/v1/notices", client)
        self.assertIn("attention_cooldown_minutes",client)

    def test_public_camera_routes_require_exact_private_auth_and_off_gate(self):
        routes = {route.path for route in service.app.routes}
        self.assertTrue({
            "/world-armor/v1/cameras/discover",
            "/world-armor/v1/cameras/page-media",
            "/world-armor/v1/cameras/inspect",
            "/world-armor/v1/cameras/import-watch",
            "/world-armor/v1/cameras/receipts",
            "/world-armor/v1/cameras/forget",
        }.issubset(routes))
        request = service.WorldArmorCameraInspectRequest(
            investigation_id="a"*32,
            public_url="https://public-camera.example/road.jpg",
            condition="road_congestion",
        )
        with patch.object(service, "API_TOKEN", "test-only-private-token"), \
             patch("jarvis_mrb.world_armor_cameras.inspect_camera",
                   return_value={"capture_time": None,
                                 "image_retained": False}) as inspect:
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_camera_inspect(
                    request, Response(), authorization=None,
                )
            self.assertEqual(ctx.exception.status_code, 401)
            inspect.assert_not_called()
            response = Response()
            receipt = service.world_armor_camera_inspect(
                request, response,
                authorization="Bearer test-only-private-token",
            )
            self.assertFalse(receipt["image_retained"])
            self.assertEqual(response.headers["Cache-Control"],
                             "private, no-store")
            inspect.assert_called_once_with(
                "a"*32, camera_ref="",
                public_url="https://public-camera.example/road.jpg",
                condition="road_congestion",
            )
        with patch.object(service, "API_TOKEN", "test-only-private-token"), \
             patch.dict(os.environ, {
                 "JARVIS_WORLD_ARMOR_ENABLED": "1",
                 "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "0",
             }), \
             patch("jarvis_mrb.public_camera_media.discover_public_page_media") as scan:
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_camera_page_media(
                    service.WorldArmorPublicPageRequest(
                        public_url="https://public-camera.example/public"
                    ), Response(),
                    authorization="Bearer test-only-private-token",
                )
            self.assertEqual(ctx.exception.status_code, 503)
            scan.assert_not_called()

    def test_world_armor_camera_native_view_wires_media_and_exact_watch(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        view = (root/"ios/JarvisIOS/WorldArmorView.swift").read_text(
            encoding="utf-8")
        client = (root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text(
            encoding="utf-8")
        self.assertIn("publicCameraWorkbench", view)
        self.assertIn("worldArmorPageMedia(", view)
        self.assertIn("worldArmorDiscoverCameras(", view)
        self.assertIn("worldArmorInspectCamera(", view)
        self.assertIn("worldArmorImportCameraWatch(", view)
        self.assertIn("worldArmorCameraReceipts(", view)
        self.assertIn("worldArmorForgetCameraReceipt(", view)
        self.assertIn('kind: "camera"', view)
        self.assertIn("world-armor/v1/cameras/inspect", client)
        self.assertIn("world-armor/v1/cameras/page-media", client)

    def test_cross_region_endpoint_requires_bearer_token_and_no_client_observations(self):
        expected = {
            "primary_id", "secondary_id", "start_at", "end_at", "as_known_at"
        }
        self.assertEqual(set(service.WorldArmorCrossRegionRequest.model_fields),
                         expected)
        body = service.WorldArmorCrossRegionRequest(
            primary_id="1"*32,secondary_id="2"*32,
            start_at="2026-09-25T12:00:00Z",
            end_at="2026-09-25T13:00:00Z",
        )
        response=Response()
        with patch.object(service, "API_TOKEN", "private-secret"):
            with self.assertRaises(HTTPException) as denied:
                service.world_armor_compare_regions(body, response,
                                                    authorization=None)
            self.assertEqual(denied.exception.status_code,401)
            with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
                with self.assertRaises(HTTPException) as disabled:
                    service.world_armor_compare_regions(
                        body,response,authorization="Bearer private-secret"
                    )
                self.assertEqual(disabled.exception.status_code,503)
        self.assertEqual(response.headers["Cache-Control"],"private, no-store")
        self.assertIn("/world-armor/v1/regions/compare",
                      {route.path for route in service.app.routes})

    def test_cross_region_ios_is_typed_and_clears_background_evidence(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        view=(root/"ios/JarvisIOS/WorldArmorView.swift").read_text(encoding="utf-8")
        client=(root/"ios/JarvisIOS/JarvisAPIClient.swift").read_text(encoding="utf-8")
        self.assertIn("worldArmorCompareRegions(",view)
        self.assertIn("crossRegionQueryPanel",view)
        self.assertIn("crossRegionPanel(",view)
        self.assertIn("crossRegionReport = nil",view)
        self.assertIn("secondRegionID",view)
        self.assertIn("modelledAQIComparisons",view)
        self.assertIn("regions/compare",client)

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
