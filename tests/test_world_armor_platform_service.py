from __future__ import annotations

import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response

from jarvis_mrb import service


class PlatformServiceTests(TestCase):
    def test_platform_routes_are_private_and_do_not_expose_remote_due_runner(self):
        routes = {r.path for r in service.app.routes}
        expected = {
            "/world-armor/v2/source-grants",
            "/world-armor/v2/source-grants/transition",
            "/world-armor/v2/source-grants/forget",
            "/world-armor/v2/sources/observe",
            "/world-armor/v2/observations",
            "/world-armor/v2/notices",
            "/world-armor/v2/plan",
            "/world-armor/v2/combined-evidence",
        }
        self.assertTrue(expected.issubset(routes))
        self.assertNotIn("/world-armor/v2/due", routes)
        with patch.object(service, "API_TOKEN", "private-secret"), patch(
            "jarvis_mrb.world_armor_platform.enroll_source",
            return_value={"id": "a"*32},
        ) as save:
            req = service.WorldArmorSourceEnrollRequest(
                label="Public camera", kind="public_https",
                locator="https://camera.example/image.jpg",
                grant_class="public_publisher",
                terms_reference="Operator checked publisher terms",
            )
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_source_enroll(
                    req, Response(), authorization=None
                )
            self.assertEqual(ctx.exception.status_code, 401)
            save.assert_not_called()
            response = Response()
            result = service.world_armor_source_enroll(
                req, response, authorization="Bearer private-secret"
            )
            self.assertEqual(result["id"], "a"*32)
            self.assertEqual(response.headers["Cache-Control"],
                             "private, no-store")
            self.assertEqual(save.call_args.kwargs["cadence_seconds"], 0)
            self.assertEqual(save.call_args.kwargs["retention_days"], 30)

    def test_when_off_authenticated_read_and_forget_not_automatically_blocked(self):
        with patch.object(service, "API_TOKEN", "private-secret"), patch.dict(
            os.environ, {"JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "0"},
        ), patch(
            "jarvis_mrb.world_armor_platform.list_sources",
            return_value={"sources": [], "total": 0},
        ) as list_sources, patch(
            "jarvis_mrb.world_armor_platform.forget_source",
            return_value={"deleted": 1},
        ) as forget:
            result = service.world_armor_sources(
                Response(), authorization="Bearer private-secret"
            )
            self.assertEqual(result["total"], 0)
            self.assertEqual(service.world_armor_source_forget(
                service.WorldArmorSourceIDRequest(source_id="a"*32),
                Response(), authorization="Bearer private-secret",
            )["deleted"], 1)
            self.assertEqual(list_sources.call_count, 1)
            self.assertEqual(forget.call_count, 1)

    def test_native_ui_exposes_source_authority_without_claiming_worker_push(self):
        root = Path(__file__).resolve().parents[1]
        view = (root / "ios/JarvisIOS/WorldArmorView.swift").read_text(
            encoding="utf-8"
        )
        client = (root / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(
            encoding="utf-8"
        )
        for term in (
            "sourceConsole", "worldArmorPlatformEnroll(",
            "worldArmorPlatformPlan(", "worldArmorPlatformObserve(",
            "worldArmorPlatformForget(", "worldArmorCombinedCameraEvidence(",
        ):
            self.assertIn(term, view)
        self.assertIn("world-armor/v2/source-grants", client)
        self.assertIn("world-armor/v2/combined-evidence", client)
        self.assertIn("Host collector is not started", view)
