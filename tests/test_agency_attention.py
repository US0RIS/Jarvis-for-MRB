from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agency_attention as agency_attention
import jarvis_mrb.world_model as world_model


class AgencyAttentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        agency_attention.DB_PATH = self.db
        world_model.status()
        agency_attention.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_low_value_changes_are_logged_but_do_not_interrupt(self) -> None:
        emitted: list[str] = []
        for index in range(12):
            result = agency_attention.consider(
                kind="low_value",
                message=f"Background change {index}",
                dedup_key=f"low:{index}",
                benefit=15,
                urgency=5,
                confidence=0.9,
                error_cost=5,
                attention_cost=25,
                emitter=emitted.append,
            )
            self.assertEqual(result["decision"], "log")
            self.assertFalse(result["emitted"])

        self.assertEqual(emitted, [])
        self.assertEqual(len(agency_attention.list_events()), 12)

    def test_high_value_exception_interrupts_once_and_duplicate_remains_queryable(self) -> None:
        emitted: list[str] = []
        kwargs = dict(
            kind="approval_required",
            message="Agency needs approval for a protected action.",
            desired_state_id="ds:1",
            dedup_key="approval:one",
            benefit=90,
            urgency=80,
            confidence=1.0,
            error_cost=0,
            attention_cost=15,
            threshold=60,
            dedup_seconds=3600,
            emitter=emitted.append,
        )
        first = agency_attention.consider(**kwargs)
        second = agency_attention.consider(**kwargs)

        self.assertEqual(first["decision"], "interrupt")
        self.assertTrue(first["emitted"])
        self.assertFalse(first["duplicate"])
        self.assertEqual(second["decision"], "interrupt")
        self.assertFalse(second["emitted"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(emitted, ["Agency needs approval for a protected action."])

        row = agency_attention.list_events(desired_state_id="ds:1")[0]
        self.assertEqual(int(row["occurrence_count"]), 2)
        self.assertEqual(int(row["emitted_count"]), 1)
        self.assertIn("threshold=60.0", str(row["rationale"]))

    def test_score_penalizes_uncertainty_and_interruption_cost(self) -> None:
        confident = agency_attention.attention_value(
            benefit=80,
            urgency=30,
            confidence=1.0,
            error_cost=5,
            attention_cost=10,
        )
        uncertain = agency_attention.attention_value(
            benefit=80,
            urgency=30,
            confidence=0.4,
            error_cost=20,
            attention_cost=25,
        )
        self.assertGreater(confident, uncertain)


if __name__ == "__main__":
    unittest.main()
