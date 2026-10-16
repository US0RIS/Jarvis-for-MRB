from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import proactive_explain, event_bus
from jarvis_mrb.deterministic_dispatch import dispatch
from jarvis_mrb.permissions import TOOL_RISK


class ProactiveExplanationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.path=Path(self.tmp.name)/"private_world.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, summary TEXT, "
                "occurred_at TEXT, payload_json TEXT, source_kind TEXT, event_type TEXT)"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def add_alert(self, summary: str, *, origin="unknown", severity="info", payload=None):
        detail=payload if payload is not None else {
            "origin":origin,"severity":severity,
        }
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO events (summary,occurred_at,payload_json,source_kind,event_type) "
                "VALUES (?,?,?,?,?)",
                (summary,"2026-10-15T19:00:00+00:00",
                 json.dumps(detail),"proactive_monitor","attention.proactive"),
            )

    def test_latest_receipt_explains_known_emitter_but_not_delivered_status(self):
        self.add_alert("GPU pressure is elevated.",origin="resource_pressure",severity="warning")
        receipt=proactive_explain.latest_receipt(self.path)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["origin"],"resource_pressure")
        self.assertEqual(receipt["severity"],"warning")
        self.assertIn("hardware or job-queue",receipt["origin_description"])
        self.assertFalse(receipt["has_independent_source_receipt"])
        self.assertIn("not confirmed delivery",receipt["scope"])
        summary=proactive_explain.describe_latest(self.path)
        self.assertIn("not that you received or heard it",summary)

    def test_unknown_origin_not_invented(self):
        self.add_alert("Some event occurred.",origin="untrusted_model_guess")
        receipt=proactive_explain.latest_receipt(self.path)
        self.assertEqual(receipt["origin"],"unknown")
        self.assertIn("not recorded",receipt["origin_description"].lower())

    def test_no_receipt_does_not_invent_history(self):
        self.assertFalse(proactive_explain.latest_receipt(self.path)["ok"])
        self.assertFalse(proactive_explain.latest_receipt(self.path.with_name("missing.db"))["ok"])

    def test_existing_legacy_event_remains_readable(self):
        self.add_alert("A past alert.",payload={"severity":"info"})
        receipt=proactive_explain.latest_receipt(self.path)
        self.assertEqual(receipt["origin"],"unknown")
        self.assertIn("A past alert.",receipt["message"])

    def test_recording_captures_specific_machine_owned_origin(self):
        observed=[]
        with (
            patch("jarvis_mrb.world_model.record_event",side_effect=lambda *a,**k: observed.append((a,k))),
            patch.object(event_bus.companion_events,"publish"),
            patch.dict("os.environ",{"JARVIS_ATTENTION_BUDGET_ENABLED":"0"}),
        ):
            event_bus.emit_proactive("A real alert.",severity="warning",origin="resource_pressure")
        self.assertEqual(len(observed),1)
        payload=observed[0][1]["payload"]
        self.assertEqual(payload["origin"],"resource_pressure")
        self.assertIn("occurrence_id",payload)
        self.assertEqual(observed[0][0][0],"attention.proactive")

    def test_model_cannot_choose_arbitrary_trusted_origin(self):
        observed=[]
        with patch("jarvis_mrb.world_model.record_event",side_effect=lambda *a,**k: observed.append(k)):
            event_bus._record_proactive_occurrence(
                "Injected content", "attention", "info", origin="authority:verified"
            )
        self.assertEqual(observed[0]["payload"]["origin"],"unknown")

    def test_user_explanation_uses_fixed_permissioned_route(self):
        route=dispatch("Why did you tell me this?")
        self.assertEqual(route.tool,"proactive.explain_last")
        self.assertEqual(TOOL_RISK["proactive.explain_last"],"read")


if __name__=="__main__":
    unittest.main()
