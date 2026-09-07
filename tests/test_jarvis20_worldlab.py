from __future__ import annotations

import unittest
from datetime import datetime, timezone

from jarvis_mrb.jarvis20_variants import generate_variant_bundle
from jarvis_mrb.jarvis20_worldlab import _temporal_rebaser, run_world_variant


class Jarvis20WorldLabTests(unittest.TestCase):
    def test_temporal_rebase_preserves_offsets(self) -> None:
        rebase = _temporal_rebaser("2031-01-01T12:00:00+00:00")
        anchor_now = datetime.fromisoformat(rebase("2031-01-01T12:00:00+00:00"))
        future = datetime.fromisoformat(rebase("2031-01-01T12:25:00+00:00"))
        past = datetime.fromisoformat(rebase("2031-01-01T10:00:00+00:00"))
        self.assertEqual(int((future - anchor_now).total_seconds()), 25 * 60)
        self.assertEqual(int((anchor_now - past).total_seconds()), 2 * 60 * 60)

    def test_generated_world_preflight_exercises_tests_five_through_ten(self) -> None:
        # Deliberately use an old/future fixed anchor to prove the materializer does
        # not depend on the bundle having been generated moments before execution.
        bundle = generate_variant_bundle(
            "worldlab-regression-1",
            anchor=datetime(2031, 4, 5, 15, 30, tzinfo=timezone.utc),
        )
        result = run_world_variant(bundle.public, bundle.oracle)
        self.assertFalse(result["mutates_user_data"])
        self.assertFalse(result["uses_external_services"])
        self.assertFalse(result["awards_behavioral_score"])
        self.assertEqual(set(result["tests"]), {"5", "6", "7", "8", "9", "10"})
        self.assertTrue(result["ok"], result.get("failed_checks"))


if __name__ == "__main__":
    unittest.main()
