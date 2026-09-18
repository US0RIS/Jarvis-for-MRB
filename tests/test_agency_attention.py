from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def test_concurrent_identical_exception_emits_exactly_once(self) -> None:
        start = threading.Barrier(2)
        emitted: list[str] = []
        emitted_lock = threading.Lock()

        def emitter(message: str) -> None:
            # Keep the winning emitter open briefly so the second producer overlaps.
            time.sleep(0.05)
            with emitted_lock:
                emitted.append(message)

        def run() -> dict:
            start.wait(timeout=2)
            return agency_attention.consider(
                kind="approval_required",
                message="Concurrent approval exception.",
                desired_state_id="ds:concurrent",
                dedup_key="approval:concurrent",
                benefit=95,
                urgency=90,
                confidence=1.0,
                error_cost=0,
                attention_cost=10,
                threshold=60,
                dedup_seconds=3600,
                emitter=emitter,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result() for future in [pool.submit(run), pool.submit(run)]]

        self.assertEqual(emitted, ["Concurrent approval exception."])
        self.assertEqual(sum(1 for item in results if item["emitted"]), 1)
        self.assertEqual(sum(1 for item in results if item["duplicate"]), 1)

        row = agency_attention.list_events(desired_state_id="ds:concurrent")[0]
        self.assertEqual(int(row["occurrence_count"]), 2)
        self.assertEqual(int(row["emitted_count"]), 1)
        self.assertTrue(row["last_emitted_at"])

    def test_failed_emitter_releases_reservation_for_later_retry(self) -> None:
        calls: list[str] = []

        def failing_emitter(message: str) -> None:
            calls.append("failed")
            raise RuntimeError("delivery unavailable")

        kwargs = dict(
            kind="approval_required",
            message="Retryable approval exception.",
            desired_state_id="ds:retry",
            dedup_key="approval:retry",
            benefit=95,
            urgency=90,
            confidence=1.0,
            error_cost=0,
            attention_cost=10,
            threshold=60,
            dedup_seconds=3600,
        )

        with self.assertRaises(RuntimeError):
            agency_attention.consider(**kwargs, emitter=failing_emitter)

        after_failure = agency_attention.list_events(desired_state_id="ds:retry")[0]
        self.assertEqual(int(after_failure["occurrence_count"]), 1)
        self.assertEqual(int(after_failure["emitted_count"]), 0)
        self.assertFalse(after_failure["last_emitted_at"])

        delivered: list[str] = []
        retry = agency_attention.consider(**kwargs, emitter=delivered.append)
        self.assertTrue(retry["emitted"])
        self.assertFalse(retry["duplicate"])
        self.assertEqual(delivered, ["Retryable approval exception."])

        final = agency_attention.list_events(desired_state_id="ds:retry")[0]
        self.assertEqual(int(final["occurrence_count"]), 2)
        self.assertEqual(int(final["emitted_count"]), 1)

    def test_deferred_interrupt_remains_eligible_for_later_emission(self) -> None:
        emitted: list[str] = []
        kwargs = dict(
            kind="approval_required",
            message="Deferred protected action approval.",
            desired_state_id="ds:deferred",
            dedup_key="approval:deferred",
            benefit=95,
            urgency=90,
            confidence=1.0,
            error_cost=0,
            attention_cost=10,
            threshold=60,
            dedup_seconds=3600,
            emitter=emitted.append,
        )

        deferred = agency_attention.consider(
            **kwargs,
            allow_emit=False,
            suppress_reason="cycle budget exhausted",
        )
        self.assertEqual(deferred["decision"], "interrupt")
        self.assertFalse(deferred["emitted"])
        self.assertTrue(deferred["suppressed"])
        self.assertFalse(deferred["duplicate"])
        self.assertEqual(emitted, [])

        later = agency_attention.consider(**kwargs)
        self.assertTrue(later["emitted"])
        self.assertFalse(later["suppressed"])
        self.assertFalse(later["duplicate"])
        self.assertEqual(emitted, ["Deferred protected action approval."])

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
