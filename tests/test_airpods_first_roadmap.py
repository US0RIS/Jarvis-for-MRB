"""Documentation contract: camera-free Horus requirements retain archive traceability."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "AIRPODS_FIRST_VISION.md"
TRACE = ROOT / "docs" / "implementation_batches" / "TRACE.md"
FUTURE = ROOT / "future.md"


class AirPodsFirstRoadmapTests(unittest.TestCase):
    def test_active_roadmap_is_camera_free_and_kept_focused(self):
        content = FUTURE.read_text(encoding="utf-8")
        self.assertLess(len(content.splitlines()), 100)
        self.assertIn("AirPods", content)
        self.assertIn("No user-worn camera", content)
        self.assertIn("AIRPODS_FIRST_VISION.md", content)
        self.assertIn("Camera-off acceptance", content)

    def test_crosswalk_validates_against_full_unchanged_historical_trace(self):
        audit = AUDIT.read_text(encoding="utf-8")
        trace = TRACE.read_text(encoding="utf-8")
        archive = (ROOT / "docs" / "archive" / "FUTURE_IDEAS_2026_10.md").read_text(encoding="utf-8")
        source = archive.splitlines()
        records = re.findall(
            r"^\| \[L(\d+)\]\(archive/FUTURE_IDEAS_2026_10\.md#L\d+\) "
            r"\| (P\d\d-\d+) \| (CORE|OUTPUT|EXTERNAL|GATED|RESEARCH) \|",
            audit, flags=re.MULTILINE,
        )
        self.assertGreaterEqual(len(records), 70)
        self.assertEqual(len(records), len(set((line, packet) for line, packet, _ in records)))
        for line, packet, _ in records:
            with self.subTest(line=line, packet=packet):
                self.assertLessEqual(int(line), len(source))
                self.assertIn(
                    f"[L{line}](../archive/FUTURE_IDEAS_2026_10.md#L{line}) | "
                    f"[{packet}]",
                    trace,
                )
        self.assertIn("Objects perceived through glasses/phone cameras", archive)

    def test_camera_free_rules_bind_the_packet_queue(self):
        queue = (ROOT / "docs" / "implementation_batches" / "README.md").read_text(encoding="utf-8")
        self.assertIn("AirPods-first camera-dependency audit", queue)
        self.assertIn("no user-mounted camera", queue)
        for filename, packets in {
            "06_PHYSICAL_WORLD.md": ["P06-010", "P06-011", "P06-012", "P06-013", "P06-016", "P06-027"],
            "02_INTERFACES.md": ["P02-001", "P02-005", "P02-010"],
            "05_AUTOMATION.md": ["P05-002", "P05-004", "P05-005"],
            "09_EVALUATIONS.md": ["P09-005", "P09-018", "P09-031"],
        }.items():
            data = (ROOT / "docs" / "implementation_batches" / filename).read_text(encoding="utf-8")
            for ident in packets:
                with self.subTest(packet=ident):
                    found = re.search(
                        rf"(?ms)^### {re.escape(ident)}\n(.*?)(?=^### P\d\d-|\Z)",
                        data,
                    )
                    self.assertIsNotNone(found)
                    self.assertIn("AirPods-first acceptance", found.group(1))

    def test_visual_only_claims_remain_explicitly_gated(self):
        audit = AUDIT.read_text(encoding="utf-8")
        for phrase in ("Precise 3-D anchors", "Scene recognition", "Physical procedure verification",
                       "Object appeared", "PTZ visual lock", "AirPods", "unknown"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, audit)


if __name__ == "__main__":
    unittest.main()
