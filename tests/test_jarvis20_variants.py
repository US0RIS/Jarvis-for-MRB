from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jarvis_mrb.jarvis20_variants import (
    generate_variant_bundle,
    validate_variant_bundle,
    write_variant_bundle,
)


class Jarvis20VariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.anchor = datetime(2031, 4, 5, 15, 30, tzinfo=timezone.utc)

    def test_same_seed_and_anchor_are_exactly_replayable(self) -> None:
        first = generate_variant_bundle("regression-alpha", anchor=self.anchor)
        second = generate_variant_bundle("regression-alpha", anchor=self.anchor)
        self.assertEqual(first.public, second.public)
        self.assertEqual(first.oracle, second.oracle)

    def test_different_seed_changes_world(self) -> None:
        first = generate_variant_bundle("regression-alpha", anchor=self.anchor)
        second = generate_variant_bundle("regression-beta", anchor=self.anchor)
        self.assertNotEqual(first.public["world_fixture"], second.public["world_fixture"])
        self.assertNotEqual(first.public["scenario_id"], second.public["scenario_id"])

    def test_variant_has_exactly_twenty_ordered_tests(self) -> None:
        bundle = generate_variant_bundle("twenty", anchor=self.anchor)
        self.assertEqual([row["id"] for row in bundle.public["tests"]], list(range(1, 21)))
        self.assertEqual(len(bundle.public["score_sheet"]["results"]), 20)

    def test_oracle_commitment_verifies_and_detects_tamper(self) -> None:
        bundle = generate_variant_bundle("oracle", anchor=self.anchor)
        result = validate_variant_bundle(bundle.public, bundle.oracle)
        self.assertTrue(result["ok"])
        self.assertTrue(result["oracle_verified"])

        tampered = json.loads(json.dumps(bundle.oracle))
        tampered["tests"]["1"]["expected_answer"] = "not-the-answer"
        result = validate_variant_bundle(bundle.public, tampered)
        self.assertFalse(result["ok"])
        self.assertFalse(result["oracle_verified"])

    def test_generated_world_contains_conflict_and_distractors(self) -> None:
        bundle = generate_variant_bundle("world", anchor=self.anchor)
        world = bundle.public["world_fixture"]
        hidden = bundle.oracle["world"]
        self.assertNotEqual(hidden["expected_current_term_value"], hidden["expected_conflicting_term_value"])
        self.assertGreaterEqual(len(world["distractor_people"]), 3)
        self.assertEqual(len(hidden["must_not_merge_person_ids"]), 3)
        self.assertIn(hidden["expected_current_term_value"], world["sources"]["newer_document"]["text"])
        self.assertIn(hidden["expected_conflicting_term_value"], world["sources"]["older_document"]["text"])

    def test_live_sensitive_values_are_not_generated_as_real_addresses_or_recipients(self) -> None:
        bundle = generate_variant_bundle("privacy", anchor=self.anchor)
        privacy = bundle.public["privacy"]
        self.assertFalse(privacy["contains_real_user_data"])
        self.assertFalse(privacy["generated_addresses"])
        primary_email = bundle.public["world_fixture"]["primary_person"]["email"]
        self.assertTrue(primary_email.endswith("@example.test"))

    def test_write_bundle_emits_public_oracle_and_score_files(self) -> None:
        bundle = generate_variant_bundle("files", anchor=self.anchor)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = write_variant_bundle(
                bundle,
                public_path=root / "scenario.json",
                oracle_path=root / "scenario.oracle.json",
                score_path=root / "scenario.score.json",
            )
            self.assertEqual(set(written), {"public", "oracle", "score_sheet"})
            self.assertTrue((root / "scenario.json").exists())
            self.assertTrue((root / "scenario.oracle.json").exists())
            self.assertTrue((root / "scenario.score.json").exists())


if __name__ == "__main__":
    unittest.main()
