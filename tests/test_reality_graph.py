from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb import reality_graph


OBS = {
    "status": "ok",
    "checked_at": "2026-09-23T05:00:00+00:00",
    "cameras": {
        "status": "ok", "checked_at": "2026-09-23T05:00:00+00:00",
        "cameras": [{"id": "cam-1", "name": "Main St"}, {"id": "cam-2", "name": "2nd St"}],
    },
    "conditions": {
        "checked_at": "2026-09-23T05:00:00+00:00",
        "air_quality": {"status": "ok", "us_aqi": 41.2},
        "weather_alerts": {"status": "ok", "alerts": []},
    },
    "incidents": {"status": "ok", "checked_at": "2026-09-23T05:00:00+00:00", "events": []},
    "facilities": {"status": "ok", "checked_at": "2026-09-23T05:00:00+00:00", "facilities": [{}, {}]},
}


class RealityGraphTests(unittest.TestCase):
    def test_compiles_provider_data_without_model_or_action_authority(self):
        graph = reality_graph.build_place_graph(34.1, -118.2, OBS)
        self.assertEqual(graph["schema"], "jarvis.reality_graph.v1")
        self.assertEqual(graph["model_calls"], 0)
        self.assertEqual(graph["action_authority"], "none")
        self.assertEqual(sum(x["kind"] == "public_camera" for x in graph["entities"]), 2)
        facts = {x["id"]: x for x in graph["derived_facts"]}
        self.assertEqual(facts["fact:air_quality"]["value"], 41)
        self.assertEqual(facts["fact:active_weather_alert_count"]["value"], 0)
        self.assertEqual(facts["fact:observation_completeness"]["value"], "complete_for_integrated_sources")

    def test_camera_catalog_never_becomes_live_camera_claim(self):
        graph = reality_graph.build_place_graph(34.1, -118.2, OBS)
        cameras = [x for x in graph["entities"] if x["kind"] == "public_camera"]
        self.assertTrue(all(x["attributes"]["live_image_verified"] is False for x in cameras))
        claims = " ".join(x["claim"] for x in graph["evidence"])
        self.assertIn("not proof of current imagery", claims)

    def test_deterministic_answers_bypass_model_and_unknown_question_escalates(self):
        graph = reality_graph.build_place_graph(34.1, -118.2, OBS)
        answer = reality_graph.answer_place_question(graph, "what is the air quality?")
        self.assertTrue(answer["answered_without_model"])
        self.assertIn("41", answer["answer"])
        self.assertIsNone(reality_graph.answer_place_question(graph, "why is the traffic weird today?"))

    def test_model_packet_omits_raw_payloads(self):
        graph = reality_graph.build_place_graph(34.1, -118.2, OBS)
        packet = reality_graph.model_context(graph)
        self.assertTrue(packet["omitted_raw_provider_payloads"])
        self.assertNotIn("entities", packet)
        self.assertNotIn("relations", packet)
        self.assertNotIn("cameras", packet)

    def test_partial_provider_state_is_uncertainty_not_all_clear(self):
        obs = {**OBS, "cameras": {"status": "unavailable", "cameras": []}}
        graph = reality_graph.build_place_graph(34.1, -118.2, obs)
        facts = {x["id"]: x for x in graph["derived_facts"]}
        self.assertEqual(facts["fact:observation_completeness"]["value"], "partial")
        self.assertIn("cameras", facts["fact:observation_completeness"]["explanation"])

    def test_service_has_private_no_store_graph_routes(self):
        from pathlib import Path
        source = (Path(__file__).parents[1] / "jarvis_mrb/service.py").read_text()
        for route in ("/mesh/graph", "/mesh/graph/context", "/mesh/graph/answer", "/mesh/graph/mission"):
            self.assertIn(route, source)
        self.assertIn("_check_mesh_auth(authorization)", source)
        self.assertIn('response.headers["Cache-Control"] = "private, no-store"', source)


    def test_mission_graph_correlates_fresh_sources_without_model(self):
        from datetime import datetime, timezone
        now = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
        graph = reality_graph.build_mission_graph(
            {"id": "dinner-1", "goal": "Dinner delivered", "deadline": "2026-09-23T05:20:00+00:00"},
            [
                {"kind": "order", "source": "provider", "observed_at": "2026-09-23T04:59:30+00:00", "status": "picked_up"},
                {"kind": "courier", "source": "provider", "observed_at": "2026-09-23T04:59:40+00:00", "eta_at": "2026-09-23T05:28:00+00:00", "moving": False, "stationary_seconds": 420},
                {"kind": "traffic", "source": "route", "observed_at": "2026-09-23T04:59:45+00:00", "delay_seconds": 720, "disruption": "collision"},
                {"kind": "camera", "source": "public-camera", "observed_at": "2026-09-23T04:59:50+00:00", "traffic_state": "stopped"},
            ],
            now=now,
        )
        facts = {x["id"]: x for x in graph["derived_facts"]}
        self.assertEqual(graph["model_calls"], 0)
        self.assertEqual(graph["action_authority"], "none")
        self.assertEqual(facts["fact:deadline_margin_seconds"]["value"], -480)
        self.assertIn("fact:delay_correlation", facts)
        self.assertEqual(facts["fact:camera_route_congestion"]["confidence"], "tentative")
        direct = reality_graph.answer_mission_question(graph, "why is it delayed?")
        self.assertTrue(direct["answered_without_model"])

    def test_stale_mission_observation_cannot_drive_fact(self):
        from datetime import datetime, timezone
        now = datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)
        graph = reality_graph.build_mission_graph(
            {"id": "x", "deadline": "2026-09-23T05:30:00+00:00"},
            [{"kind": "courier", "source": "provider", "observed_at": "2026-09-23T04:40:00+00:00",
              "eta_at": "2026-09-23T05:40:00+00:00", "moving": False, "stationary_seconds": 1200}],
            now=now,
        )
        ids = {x["id"] for x in graph["derived_facts"]}
        self.assertNotIn("fact:provider_eta_seconds", ids)
        self.assertNotIn("fact:courier_stationary", ids)


if __name__ == "__main__":
    unittest.main()
