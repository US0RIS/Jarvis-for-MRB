from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.agency_self_model as agency_self_model
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_model as world_model


class AgencySelfModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"

        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        agency_self_model.DB_PATH = self.db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"

        world_model.status()
        agency_self_model.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_categories_remain_explicit_instead_of_flattening_into_profile(self) -> None:
        agency_self_model.upsert("fact", "home_city", "Los Angeles", source_ref="fact:1")
        agency_self_model.upsert("preference", "travel_quality", "prefer quality over modest savings", source_ref="pref:1")
        agency_self_model.upsert("policy", "external_messages", "confirm before sending", source_ref="policy:1")
        agency_self_model.upsert("objective", "trip", "maximize flight experience", source_ref="objective:1")
        agency_self_model.upsert("tradeoff", "time_vs_money", {"extra_usd": 500, "worth_minutes_saved": 90}, source_ref="tradeoff:1")

        context = agency_self_model.decision_context()
        self.assertEqual(context["fact"][0]["entry_key"], "home_city")
        self.assertEqual(context["preference"][0]["entry_key"], "travel_quality")
        self.assertEqual(context["policy"][0]["entry_key"], "external_messages")
        self.assertEqual(context["objective"][0]["entry_key"], "trip")
        self.assertEqual(context["tradeoff"][0]["entry_key"], "time_vs_money")

    def test_revision_supersedes_old_entry_but_preserves_history(self) -> None:
        first = agency_self_model.upsert(
            "preference",
            "restaurant_noise",
            "quiet preferred",
            confidence=0.7,
            source_ref="pref:old",
        )
        second = agency_self_model.upsert(
            "preference",
            "restaurant_noise",
            "moderate noise is fine",
            confidence=0.9,
            source_ref="pref:new",
        )

        current = agency_self_model.get("preference", "restaurant_noise")
        self.assertEqual(current["id"], second["id"])
        self.assertEqual(current["value"], "moderate noise is fine")

        history = agency_self_model.list_entries(kind="preference", include_superseded=True)
        self.assertEqual(len(history), 2)
        by_id = {item["id"]: item for item in history}
        self.assertEqual(by_id[first["id"]]["state"], "superseded")
        self.assertEqual(by_id[second["id"]]["state"], "current")

    def test_correction_preserves_prior_corrected_and_reason(self) -> None:
        item = agency_self_model.record_correction(
            "flight_cost_sensitivity",
            prior="always choose cheapest",
            corrected="pay more for materially better long-haul experience",
            reason="Observed repeated choices favored cabin/schedule quality.",
            source_ref="correction:test",
        )
        self.assertEqual(item["kind"], "correction")
        self.assertEqual(item["value"]["prior"], "always choose cheapest")
        self.assertIn("materially better", item["value"]["corrected"])
        self.assertIn("repeated choices", item["value"]["reason"])

    def test_inferred_preference_cannot_supersede_explicit_user_preference(self) -> None:
        explicit = agency_self_model.upsert(
            "preference",
            "travel_quality",
            "prefer the materially better experience",
            confidence=0.9,
            source_kind="explicit_user",
            source_ref="user:explicit",
        )
        current_after_inference = agency_self_model.upsert(
            "preference",
            "travel_quality",
            "always choose cheapest",
            confidence=1.0,
            source_kind="inferred_behavior",
            source_ref="inference:later",
        )

        self.assertEqual(current_after_inference["id"], explicit["id"])
        self.assertEqual(
            agency_self_model.get("preference", "travel_quality")["value"],
            "prefer the materially better experience",
        )
        history = agency_self_model.list_entries(
            kind="preference",
            include_superseded=True,
        )
        inferred = next(
            item for item in history
            if item["source_ref"] == "inference:later"
        )
        self.assertEqual(inferred["state"], "superseded")

    def test_explicit_user_preference_supersedes_prior_inference(self) -> None:
        inferred = agency_self_model.upsert(
            "preference",
            "restaurant_noise",
            "quiet is probably preferred",
            confidence=0.95,
            source_kind="inferred",
            source_ref="inference:first",
        )
        explicit = agency_self_model.upsert(
            "preference",
            "restaurant_noise",
            "moderate noise is fine",
            confidence=0.7,
            source_kind="explicit_user",
            source_ref="user:later",
        )

        self.assertNotEqual(explicit["id"], inferred["id"])
        self.assertEqual(explicit["value"], "moderate noise is fine")
        self.assertEqual(explicit["source_kind"], "explicit_user")

    def test_weaker_inference_does_not_replace_stronger_inference(self) -> None:
        stronger = agency_self_model.upsert(
            "tradeoff",
            "time_vs_money",
            {"prefer_time": True},
            confidence=0.9,
            source_kind="inferred",
            source_ref="inference:strong",
        )
        after = agency_self_model.upsert(
            "tradeoff",
            "time_vs_money",
            {"prefer_time": False},
            confidence=0.4,
            source_kind="model_inference",
            source_ref="inference:weak",
        )
        self.assertEqual(after["id"], stronger["id"])
        self.assertEqual(after["value"], {"prefer_time": True})

    def test_source_inference_classification_distinguishes_explicit_policy(self) -> None:
        self.assertTrue(agency_self_model.is_inferred_source("inferred"))
        self.assertTrue(agency_self_model.is_inferred_source("inferred_behavior"))
        self.assertTrue(agency_self_model.is_inferred_source("model_inference"))
        self.assertTrue(agency_self_model.is_inferred_source("decision_history"))
        self.assertFalse(agency_self_model.is_inferred_source("explicit_user"))
        self.assertFalse(agency_self_model.is_inferred_source("user_correction"))
        self.assertFalse(agency_self_model.is_inferred_source("explicit_policy"))
        self.assertFalse(agency_self_model.is_inferred_source("imported_context"))

    def test_approval_history_inference_requires_three_distinct_approvals(self) -> None:
        for index in range(2):
            world_model.record_event(
                "agency.step.approved",
                f"Approved calendar action {index}.",
                source_kind="jarvis_agency",
                source_ref=f"approval:{index}",
                payload={
                    "desired_state_id": "desired:test",
                    "plan_id": f"plan:{index}",
                    "step_id": f"step:{index}",
                    "tool": "calendar.create",
                    "risk": "external_write",
                    "requires_confirmation": True,
                },
                evidence="Explicit approval consumed.",
            )

        self.assertIsNone(
            agency_self_model.infer_approval_preference(
                "calendar.create"
            )
        )
        self.assertIsNone(
            agency_self_model.get(
                "preference",
                agency_self_model.approval_preference_key(
                    "calendar.create"
                ),
            )
        )

    def test_approval_history_inference_persists_exact_event_provenance(self) -> None:
        approval_ids: list[int] = []
        for index in range(3):
            approval_ids.append(
                world_model.record_event(
                    "agency.step.approved",
                    f"Approved calendar action {index}.",
                    source_kind="jarvis_agency",
                    source_ref=f"approval:provenance:{index}",
                    payload={
                        "desired_state_id": "desired:test",
                        "plan_id": f"plan:{index}",
                        "step_id": f"step:{index}",
                        "tool": "calendar.create",
                        "risk": "external_write",
                        "requires_confirmation": True,
                    },
                    evidence="Explicit approval consumed.",
                )
            )

        preference = agency_self_model.infer_approval_preference(
            "calendar.create"
        )
        self.assertIsNotNone(preference)
        assert preference is not None
        self.assertEqual(preference["source_kind"], "inferred_behavior")
        self.assertEqual(
            preference["entry_key"],
            "approval_style:calendar.create",
        )
        self.assertEqual(
            preference["value"]["supporting_approval_event_ids"],
            approval_ids,
        )
        self.assertEqual(
            preference["value"]["authority_effect"],
            "none",
        )

        conn = world_model._connect()
        try:
            row = conn.execute(
                """
                SELECT payload_json,source_ref FROM events
                WHERE event_type='agency.self_model.inferred'
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        payload = agency_self_model._loads(
            str(row["payload_json"]),
            {},
        )
        self.assertEqual(
            payload["supporting_approval_event_ids"],
            approval_ids,
        )
        self.assertEqual(payload["tool"], "calendar.create")
        self.assertEqual(payload["authority_effect"], "none")
        self.assertEqual(row["source_ref"], preference["source_ref"])

        authority = agency_self_model.authority_for(
            "calendar.create"
        )
        self.assertTrue(authority["allowed"])
        self.assertTrue(authority["requires_confirmation"])
        self.assertFalse(authority["self_model_can_override"])

    def test_high_confidence_preference_never_grants_external_write_authority(self) -> None:
        agency_self_model.upsert(
            "preference",
            "email_autonomy",
            "send routine emails automatically",
            confidence=1.0,
            source_ref="preference:test",
        )
        permissions.set_policy("external_write", "deny")

        authority = agency_self_model.authority_for("gmail.send")
        self.assertFalse(authority["allowed"])
        self.assertEqual(authority["risk"], "external_write")
        self.assertEqual(authority["authority_source"], "permissions")
        self.assertFalse(authority["self_model_can_override"])

    def test_confirm_policy_remains_confirm_even_if_self_model_policy_says_auto(self) -> None:
        agency_self_model.upsert(
            "policy",
            "email_autonomy",
            "routine email may be sent automatically",
            confidence=1.0,
            source_ref="policy:test",
        )

        authority = agency_self_model.authority_for("gmail.send")
        self.assertTrue(authority["allowed"])
        self.assertTrue(authority["requires_confirmation"])
        self.assertFalse(authority["self_model_can_override"])

    def test_compact_context_includes_provenance_and_confidence(self) -> None:
        agency_self_model.upsert(
            "preference",
            "reversibility",
            "prefer reversible experiments under uncertainty",
            confidence=0.85,
            source_kind="inferred",
            source_ref="decision-history:42",
        )
        rendered = agency_self_model.compact_context()
        self.assertIn("PREFERENCE", rendered)
        self.assertIn("reversibility", rendered)
        self.assertIn("confidence=0.85", rendered)
        self.assertIn("decision-history:42", rendered)


if __name__ == "__main__":
    unittest.main()
