from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_term_context as world_term_context
import jarvis_mrb.world_terms as world_terms


class DynamicWorldDatabaseBindingTests(unittest.TestCase):
    def test_term_layers_follow_runtime_world_model_path(self) -> None:
        original_app_dir = world_model.APP_DIR
        original_db_path = world_model.DB_PATH
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            try:
                first_base = Path(first_temp)
                world_model.APP_DIR = first_base
                world_model.DB_PATH = first_base / "world_model.sqlite3"
                world_model.status()
                first_project = world_model.ensure_entity("project", "Project First")
                first_event = world_model.record_event(
                    "conversation.turn",
                    "Project First indemnity cap is 10%.",
                    source_kind="conversation",
                    source_ref="first",
                    participants=[(first_project, "project", 1.0)],
                )
                world_terms.observe_event(first_event)
                self.assertIn("10%", world_term_context.context_for_query("What's the indemnity cap on Project First?"))

                second_base = Path(second_temp)
                world_model.APP_DIR = second_base
                world_model.DB_PATH = second_base / "world_model.sqlite3"
                world_model.status()
                second_project = world_model.ensure_entity("project", "Project Second")
                second_event = world_model.record_event(
                    "conversation.turn",
                    "Project Second indemnity cap is 25%.",
                    source_kind="conversation",
                    source_ref="second",
                    participants=[(second_project, "project", 1.0)],
                )
                world_terms.observe_event(second_event)

                second_context = world_term_context.context_for_query("What's the indemnity cap on Project Second?")
                self.assertIn("25%", second_context)
                self.assertNotIn("10%", second_context)
                self.assertEqual(world_terms.latest_observations(second_project)[0]["value"], "25%")
            finally:
                world_model.APP_DIR = original_app_dir
                world_model.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
