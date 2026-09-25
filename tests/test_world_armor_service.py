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

    def test_disabled_create_does_not_touch_database(self):
        request=service.WorldArmorCreateRequest(
            label="Test",latitude=34.1,longitude=-118.2)
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED":"0"}), \
             patch.object(service,"API_TOKEN","private-secret"):
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_create(
                    request,Response(),authorization="Bearer private-secret")
            self.assertEqual(ctx.exception.status_code,503)


if __name__ == "__main__":
    import unittest
    unittest.main()
