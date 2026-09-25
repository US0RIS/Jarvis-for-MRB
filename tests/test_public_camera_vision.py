from __future__ import annotations

import unittest
from unittest.mock import patch

import jarvis_mrb.public_camera_vision as vision


_RECORD = {
    "id": "caltrans-d7-196",
    "title": "I-110 at Avenue 26",
    "image_url": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/still.jpg",
}


class OfficialCameraVisionTests(unittest.TestCase):
    def test_rejects_arbitrary_url_id_and_stream_only(self) -> None:
        for value in ("https://192.168.1.1/view", "../etc/passwd", "caltrans-d25-3"):
            with self.assertRaises(ValueError):
                vision._pick(value)
        with patch(
            "jarvis_mrb.public_camera_vision._get_district",
            return_value=([{**_RECORD, "image_url": ""}], "2026-09-19T20:00:00+00:00"),
        ):
            with self.assertRaisesRegex(ValueError, "no supported published still"):
                vision._pick(_RECORD["id"])

    def test_rejects_stale_catalog_and_wrong_image_bytes(self) -> None:
        with patch(
            "jarvis_mrb.public_camera_vision._get_district",
            return_value=([_RECORD], "2026-09-19 (stale; refresh failed)"),
        ):
            with self.assertRaisesRegex(ValueError, "stale"):
                vision._pick(_RECORD["id"])
        self.assertFalse(vision._jpeg_or_png(b"<html>login</html>", "image/jpeg"))
        self.assertFalse(vision._jpeg_or_png(b"\\xff\\xd8\\xff", "text/html"))
        self.assertTrue(vision._jpeg_or_png(bytes([0xff, 0xd8, 0xff]), "image/jpeg"))
        self.assertTrue(vision._jpeg_or_png(bytes([0x89]) + b"PNG\r\n\x1a\n", "image/png"))

    def test_explicit_publisher_still_uses_local_ollama_and_no_memory(self) -> None:
        with (
            patch("jarvis_mrb.public_camera_vision._get_district", return_value=([_RECORD], "2026-09-19")),
            patch("jarvis_mrb.public_camera_vision.httpx.Client") as client,
        ):
            handle = client.return_value.__enter__.return_value
            still = handle.stream.return_value.__enter__.return_value
            still.headers = {"Content-Type": "image/jpeg"}
            still.iter_bytes.return_value = [bytes([0xff, 0xd8, 0xff, 0, 1])]
            llm = handle.post.return_value
            llm.json.return_value = {"message": {"content": "Several cars are visible. Their current location is not verified."}}
            result = vision.analyze_official_still(_RECORD["id"])
            self.assertEqual(result["status"], "ok")
            self.assertIsNone(result["capture_time"])
            self.assertIn("not proof", result["source_note"])
            url = handle.post.call_args.args[0]
            self.assertIn("/api/chat", url)
            prompt = handle.post.call_args.kwargs["json"]["messages"][0]["content"]
            self.assertIn("Do NOT identify people or license plates", prompt)
            self.assertEqual(result["camera_id"], _RECORD["id"])


if __name__ == "__main__":
    unittest.main()
