from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response

from jarvis_mrb import service


class MovementServiceTests(TestCase):
    def test_private_routes_exist_without_remote_due_runner(self):
        routes = {route.path for route in service.app.routes}
        expected = {
            "/world-armor/v3/movement-sources",
            "/world-armor/v3/movement-sources/transition",
            "/world-armor/v3/movement-sources/forget",
            "/world-armor/v3/movement/collect",
            "/world-armor/v3/movement/nearby",
            "/world-armor/v3/movement/track",
        }
        self.assertTrue(expected.issubset(routes))
        self.assertNotIn("/world-armor/v3/movement/run-due", routes)

    def test_movement_enrollment_requires_private_token(self):
        request = service.WorldArmorMovementEnrollRequest(
            label="Public LA airspace",
            kind="opensky_region",
            grant_class="public_publisher",
            terms_reference="Operator-reviewed OpenSky terms",
            latitude=34.05, longitude=-118.25, radius_km=80,
        )
        with patch.object(service, "API_TOKEN", "secret"), patch(
            "jarvis_mrb.world_armor_movement.enroll_source",
            return_value={"id": "a"*32},
        ) as enroll:
            with self.assertRaises(HTTPException) as ctx:
                service.world_armor_movement_enroll(
                    request, Response(), authorization=None
                )
            self.assertEqual(ctx.exception.status_code, 401)
            enroll.assert_not_called()
            response = Response()
            result = service.world_armor_movement_enroll(
                request, response, authorization="Bearer secret"
            )
            self.assertEqual(result["id"], "a"*32)
            self.assertEqual(response.headers["Cache-Control"],
                             "private, no-store")

    def test_native_ui_wires_movement_lifecycle_and_nearby_query(self):
        root = Path(__file__).resolve().parents[1]
        view = (root / "ios/JarvisIOS/WorldArmorView.swift").read_text(
            encoding="utf-8"
        )
        client = (root / "ios/JarvisIOS/JarvisAPIClient.swift").read_text(
            encoding="utf-8"
        )
        for token in (
            "movementConsole",
            "worldArmorMovementEnroll(",
            "worldArmorMovementCollect(",
            "worldArmorMovementNearby(",
            "worldArmorMovementTransition(",
            "worldArmorMovementForget(",
        ):
            self.assertIn(token, view)
        for path in (
            "world-armor/v3/movement-sources",
            "world-armor/v3/movement/collect",
            "world-armor/v3/movement/nearby",
        ):
            self.assertIn(path, client)

    def test_nearby_route_delegates_typed_query_only(self):
        with patch.object(service, "API_TOKEN", "secret"), patch(
            "jarvis_mrb.world_armor_movement.nearby",
            return_value={"entities": []},
        ) as nearby:
            response = Response()
            result = service.world_armor_movement_nearby(
                response,
                latitude=34.05, longitude=-118.25,
                radius_km=25, entity_type="aircraft",
                authorization="Bearer secret",
            )
        self.assertEqual(result["entities"], [])
        nearby.assert_called_once_with(
            34.05, -118.25, radius_km=25,
            entity_type="aircraft", after_seq=0, page_size=100,
        )
        self.assertEqual(response.headers["Cache-Control"],
                         "private, no-store")


if __name__ == "__main__":
    import unittest
    unittest.main()
