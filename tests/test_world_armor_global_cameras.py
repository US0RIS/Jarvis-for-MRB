from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import public_camera_media as media
from jarvis_mrb import public_camera_windy as windy
from jarvis_mrb import world_armor_cameras as cameras
from jarvis_mrb import world_armor_phase1 as armor

NOW = datetime(2026, 9, 25, 18, tzinfo=timezone.utc)
EXAMPLE = "https://public-camera.example/road.jpg"


class PublicCameraGlobalTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "armor.sqlite3"
        flag = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "1",
        })
        flag.start()
        self.addCleanup(flag.stop)
        self.region = armor.create_investigation(
            "Selected public region", 34.12, -118.16,
            radius_km=30, db_path=self.db, now=NOW,
        )["id"]

    def test_public_url_rejects_credentials_localhost_ip_and_non_https(self):
        invalid = (
            "http://public-camera.example/image.jpg",
            "rtsp://public-camera.example/live",
            "https://localhost/live",
            "https://camera.local/live",
            "https://192.168.1.2/live",
            "https://[::1]/live",
            "https://user:password@public-camera.example/image",
            "https://public-camera.example:8080/live",
            "https://public-camera.example/image#secret",
            "https://public-camera.example/image?token=abc",
            "https://public-camera.example/image?api_key=abc",
            "https://public-camera.example/image?password=abc",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                media.validate_public_camera_url(url)
        accepted = media.validate_public_camera_url(
            "https://public-camera.example/image.jpg?frame=1"
        )
        self.assertNotIn("?frame", accepted.display)
        self.assertEqual(accepted.host, "public-camera.example")

    def test_public_dns_rejects_every_non_global_address_in_answer(self):
        def answer(value):
            return [(2, 1, 6, "", (addr, 443)) for addr in value]
        for group in (
            ["127.0.0.1"], ["169.254.169.254"],
            ["10.0.0.1"], ["8.8.8.8", "10.0.0.1"],
            ["::1"], ["fe80::1"], ["fd00::1"],
            ["192.0.2.9"], ["100.64.0.1"],
        ):
            with self.subTest(group=group), patch.object(
                media.socket, "getaddrinfo", return_value=answer(group),
            ), self.assertRaises(ValueError):
                media._public_address("public-camera.example")
        with patch.object(media.socket, "getaddrinfo",
                          return_value=answer(["8.8.8.8"])):
            self.assertEqual(
                media._public_address("public-camera.example"), "8.8.8.8"
            )

    def test_one_selected_html_page_yields_candidates_without_following_media(self):
        page = "<html><head><meta property='og:image' " \
               "content='/preview.jpg'></head><body>" \
               "<img class='webcam' src='https://cdn.public-camera.example/" \
               "snapshot.png'><iframe src='/hidden-player'></iframe>" \
               "<script src='/secret.js'></script></body></html>"
        with patch.object(
            media, "_get", return_value=(page.encode(), "text/html"),
        ) as provider:
            found = media.discover_public_page_media(
                "https://public-camera.example/camera"
            )
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(found["status"], "candidates_found")
        self.assertEqual(len(found["candidates"]), 2)
        self.assertTrue(found["candidates"][0]["same_origin"])
        self.assertFalse(found["candidates"][1]["same_origin"])
        self.assertTrue(all(
            "secret" not in item["url"] and "hidden-player" not in item["url"]
            for item in found["candidates"]
        ))
        self.assertTrue(all(
            x["needs_explicit_selection"] for x in found["candidates"]
        ))

    def test_public_webpage_discovery_never_fetches_credential_links(self):
        page = (
            '<img class="webcam" src="/live.jpg?token=secret"/>'
            '<img class="webcam" src="http://127.0.0.1/secret.jpg"/>'
            '<img class="webcam" src="/public.jpg"/>'
        )
        with patch.object(
            media, "_get", return_value=(page.encode(), "text/html"),
        ):
            response = media.discover_public_page_media(
                "https://public-camera.example/portal"
            )
        self.assertEqual(
            [x["url"] for x in response["candidates"]],
            ["https://public-camera.example/public.jpg"],
        )

    def test_mjpeg_extracts_one_frame_and_does_not_store_media(self):
        from PIL import Image
        from io import BytesIO
        img = BytesIO()
        Image.new("RGB", (12, 12)).save(img, format="JPEG")
        jpeg = img.getvalue()
        raw = b"--boundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n--boundary"
        converted, kind = media._image(
            raw, "multipart/x-mixed-replace",
        )
        self.assertEqual(kind, "jpeg")
        self.assertTrue(converted.startswith(b"\xff\xd8\xff"))

    def test_rejects_html_even_with_image_header(self):
        with self.assertRaises(ValueError):
            media._image(b"<html>not a camera</html>", "image/jpeg")
        with self.assertRaises(ValueError):
            media._image(b"\xff\xd8\xffbad", "text/html")

    def test_windy_filters_inactive_and_invalid_preview(self):
        raw = {
            "webcamId": 123456, "status": "active", "title": "Public mountain",
            "location": {"latitude": 34.11, "longitude": -118.16},
            "images": {"current": {"icon":
                "https://public-camera.example/frame.jpg"}},
            "urls": {"detail": "https://www.windy.com/webcams/123456"},
        }
        self.assertEqual(windy._entry(raw)["id"], "windy-123456")
        self.assertEqual(windy._entry({**raw, "status": "inactive"}), None)
        self.assertEqual(windy._entry({
            **raw, "images": {"current": {"icon":
                "https://localhost/frame.jpg"}}
        })["image_url"], "")
        with patch.dict(os.environ, {
            "JARVIS_WINDY_WEBCAMS_API_KEY": "",
        }):
            result = windy.discover_windy_cameras(34.1, -118.2)
            self.assertEqual(result["status"], "not_configured")

    def test_global_discovery_surfaces_caltrans_and_optional_windy_status(self):
        windy_rows = {"status": "ok", "cameras": [{
            "id": "windy-42", "title": "Mountain camera",
            "latitude": 34.11, "longitude": -118.16,
        }], "reported_total": 1}
        cal_rows = {"status": "ok", "cameras": [{
            "id": "caltrans-d7-196", "title": "Freeway camera",
            "latitude": 34.12, "longitude": -118.15,
        }], "matching_count": 1, "source_note": "published"}
        with patch(
            "jarvis_mrb.public_camera_windy.discover_windy_cameras",
            return_value=windy_rows,
        ), patch(
            "jarvis_mrb.public_camera_catalog.discover_public_cameras",
            return_value=cal_rows,
        ):
            result = cameras.discover_public_cameras_global(
                34.12, -118.16, limit=15
            )
        self.assertEqual(len(result["cameras"]), 2)
        self.assertEqual(len(result["provider_statuses"]), 2)
        self.assertFalse(result["camera_capture_time_verified"]
                         if "camera_capture_time_verified" in result
                         else result["qualifier"].find("camera") < 0)

    def _evidence(self, *, camera="abcd", image="a"*64):
        return {
            "camera_id": camera, "camera_name": "Public camera",
            "watch_condition": "smoke_visible", "condition_status": "uncertain",
            "image_sha256": image, "retrieved_at": NOW.isoformat(),
            "source_url": "https://public-camera.example/image.jpg",
            "source_kind": "user_enrolled_public_https_media",
            "media_kind": "published_still",
            "description": "Haze visible; origin unknown.",
        }

    def test_world_armor_camera_receipt_preserves_uncertainty_and_delete(self):
        url = EXAMPLE
        with patch(
            "jarvis_mrb.public_camera_vision.analyze_public_camera",
            return_value=self._evidence(camera="z"*64),
        ):
            result = cameras.inspect_camera(
                self.region, public_url=url, condition="smoke_visible",
                db_path=self.db, now=NOW,
            )
        self.assertIsNone(result["capture_time"])
        self.assertFalse(result["image_retained"])
        self.assertFalse(result["independent_incident_verified"])
        self.assertEqual(result["spatial_basis"],
                         "operator_associated_region_camera_location_unknown")
        self.assertEqual(result["change_state"], "baseline")
        listed = cameras.list_camera_receipts(
            self.region, db_path=self.db, now=NOW,
        )
        self.assertEqual(len(listed["camera_receipts"]), 1)
        self.assertFalse(listed["source_timed_correlation"])
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "0",
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "0",
        }):
            self.assertEqual(cameras.forget_camera_receipt(
                result["id"], db_path=self.db,
            )["deleted"], 1)
            self.assertEqual(cameras.list_camera_receipts(
                self.region, db_path=self.db, now=NOW,
            )["camera_receipts"], [])

    def test_cannot_claim_catalog_camera_outside_enrolled_region(self):
        with patch(
            "jarvis_mrb.world_armor_cameras._catalog_geography",
            return_value=(-37.813, 144.963),
        ), patch(
            "jarvis_mrb.public_camera_vision.analyze_public_camera",
        ) as analyze:
            with self.assertRaisesRegex(ValueError, "outside enrolled region"):
                cameras.inspect_camera(
                    self.region, camera_ref="windy-12345",
                    db_path=self.db, now=NOW,
                )
            analyze.assert_not_called()

    def test_exact_personal_camera_watch_import_has_no_new_provider_fetch(self):
        watch = {"id": "watch-one", "kind": "camera", "label": "Public road",
                 "config": {"camera_id": "caltrans-d7-196"}}
        prior = {
            "status": "ok", "checked_at": NOW.isoformat(),
            "payload": self._evidence(
                camera="caltrans-d7-196", image="1"*64,
            ),
        }
        with patch("jarvis_mrb.external_watches.get_watch",
                   return_value=watch) as selected, \
             patch("jarvis_mrb.external_watches.watch_history",
                   return_value=[prior]) as history, \
             patch("jarvis_mrb.public_camera_vision.analyze_public_camera",
                   side_effect=AssertionError("camera fetched")):
            imported = cameras.import_external_camera_watch(
                self.region, "watch-one", db_path=self.db, now=NOW,
            )
        selected.assert_called_once_with("watch-one", "personal")
        history.assert_called_once_with("watch-one", "personal", limit=1)
        self.assertEqual(imported["imported_watch_id"], "watch-one")
        self.assertEqual(imported["image_sha256"], "1"*64)
        self.assertIsNone(imported["capture_time"])
        self.assertEqual(imported["spatial_basis"],
                         "operator_associated_region_camera_location_unknown")
        self.assertEqual(cameras.list_camera_receipts(
            self.region, db_path=self.db, now=NOW,
        )["camera_receipts"][0]["id"], imported["id"])

    def test_external_watch_import_rejects_non_camera_or_unobserved_source(self):
        with patch("jarvis_mrb.external_watches.get_watch",
                   return_value={"kind": "airspace_region"}):
            with self.assertRaises(ValueError):
                cameras.import_external_camera_watch(
                    self.region, "watch-one", db_path=self.db, now=NOW,
                )
        with patch("jarvis_mrb.external_watches.get_watch",
                   return_value={"id": "watch-one", "kind": "camera"}), \
             patch("jarvis_mrb.external_watches.watch_history",
                   return_value=[]):
            with self.assertRaises(ValueError):
                cameras.import_external_camera_watch(
                    self.region, "watch-one", db_path=self.db, now=NOW,
                )

    def test_collection_flag_blocks_fetch_and_expired_region_blocks_storage(self):
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_CAMERAS_ENABLED": "0",
        }), patch(
            "jarvis_mrb.public_camera_vision.analyze_public_camera",
        ) as analyze:
            with self.assertRaises(armor.ArmorDisabled):
                cameras.inspect_camera(
                    self.region, public_url=EXAMPLE, db_path=self.db, now=NOW,
                )
            analyze.assert_not_called()
        expired_at = NOW + timedelta(hours=72)
        with patch(
            "jarvis_mrb.public_camera_vision.analyze_public_camera",
            return_value=self._evidence(),
        ):
            with self.assertRaises(KeyError):
                cameras.inspect_camera(
                    self.region, public_url=EXAMPLE,
                    db_path=self.db, now=expired_at,
                )

    def test_watch_config_accepts_one_public_image_and_no_user_credentials(self):
        from jarvis_mrb import external_watches as watches
        accepted = watches._validate(
            "personal", "camera", {
                "public_url": EXAMPLE, "condition": "road_congestion",
            }, 900, 2,
        )
        self.assertEqual(accepted["public_url"], EXAMPLE)
        for config in (
            {"public_url": "http://192.168.1.2/img.jpg"},
            {"camera_ref": "random-source"},
            {"camera_id": "caltrans-d3-1", "public_url": EXAMPLE},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                watches._validate("personal", "camera", config, 900, 2)
