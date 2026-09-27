from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jarvis_mrb.agency_plan as agency_plan
import jarvis_mrb.agency_runtime as agency_runtime
import jarvis_mrb.agent as agent
import jarvis_mrb.desired_state as desired_state
import jarvis_mrb.permissions as permissions
import jarvis_mrb.world_armor_full as world_armor_full
import jarvis_mrb.world_executive as world_executive
import jarvis_mrb.world_model as world_model
import jarvis_mrb.world_places as world_places
import jarvis_mrb.world_verification as world_verification
from jarvis_mrb.workflow_engine import _ALLOWED_NODE_TOOLS, _tool_signatures, _validate_plan

LAMP = "0f8e2c1a-3b4d-4e5f-8a9b-0c1d2e3f4a5b"
SEATTLE = {"name": "Seattle, Washington, United States", "latitude": 47.6062, "longitude": -122.3321,
           "resolution": "Open-Meteo public geocoder", "source": "open_meteo_geocoder"}


def _conditions(aqi: float | None = 42.0, alerts: int = 0, status: str = "ok") -> dict:
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "air_quality": (
            {"status": status, "us_aqi": aqi, "pm2_5_ug_m3": 5.0, "uv_index": 1.0,
             "model_time_utc": datetime.now(timezone.utc).isoformat(), "source_note": "model"}
            if status != "unavailable" else {"status": "unavailable", "source_note": "down"}
        ),
        "weather_alerts": {
            "status": "ok",
            "alerts": [{"id": f"nws-{i}", "event": "Heat Advisory"} for i in range(alerts)],
        },
    }


class AgencyWorldBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        db = self.base / "world_model.sqlite3"
        saved = {
            "wm_app": world_model.APP_DIR, "wm_db": world_model.DB_PATH,
            "we_db": world_executive.DB_PATH, "ds_db": desired_state.DB_PATH,
            "ap_db": agency_plan.DB_PATH, "ar_db": agency_runtime.DB_PATH,
            "wv_db": world_verification.DB_PATH, "perm_app": permissions.APP_DIR,
            "perm_path": permissions.POLICY_PATH, "full": world_armor_full.FULL_STORE,
        }

        def restore() -> None:
            world_model.APP_DIR, world_model.DB_PATH = saved["wm_app"], saved["wm_db"]
            world_executive.DB_PATH = saved["we_db"]
            desired_state.DB_PATH = saved["ds_db"]
            agency_plan.DB_PATH = saved["ap_db"]
            agency_runtime.DB_PATH = saved["ar_db"]
            world_verification.DB_PATH = saved["wv_db"]
            permissions.APP_DIR, permissions.POLICY_PATH = saved["perm_app"], saved["perm_path"]
            world_armor_full.FULL_STORE = saved["full"]

        self.addCleanup(restore)
        world_model.APP_DIR = self.base
        world_model.DB_PATH = db
        for module in (world_executive, desired_state, agency_plan, agency_runtime, world_verification):
            module.DB_PATH = db
        permissions.APP_DIR = self.base
        permissions.POLICY_PATH = self.base / "permissions.json"
        world_armor_full.FULL_STORE = self.base / "world_armor_full.sqlite3"
        for module in (world_model, world_executive, desired_state, agency_plan, agency_runtime, world_verification):
            module.status()
        world_places._last_refresh.clear()
        env = patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_ENABLED": "1", "JARVIS_WORLD_ARMOR_FULL_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        agent._PENDING_ACTION = None
        self.addCleanup(lambda: setattr(agent, "_PENDING_ACTION", None))

    # -- scope and permissions -------------------------------------------------

    def test_world_tools_are_in_agency_scope_with_argument_contracts(self) -> None:
        for tool in ("world.observe_place", "world.observe_camera", "presence.set_light", "mesh.nodes"):
            self.assertIn(tool, _ALLOWED_NODE_TOOLS)
            self.assertIn(tool, _tool_signatures())
        self.assertEqual(permissions.TOOL_RISK["presence.set_light"], "external_write")
        self.assertEqual(permissions.TOOL_RISK["world.observe_place"], "read")

    def test_physical_actuation_never_runs_without_confirmation(self) -> None:
        world_places.record_light_catalog([{"id": LAMP, "name": "Desk Lamp", "on": False, "reachable": True}])
        with patch("jarvis_mrb.event_bus.companion_events.publish") as publish:
            reply = agent.execute_tool("presence.set_light", {"light": "Desk Lamp", "on": True})
        self.assertIn("confirm", reply.message.lower())
        publish.assert_not_called()
        self.assertEqual(world_armor_full.list_presence_grants().get("grants") or [], [])

    # -- world observations ------------------------------------------------------

    def test_observe_place_records_provenance_and_keeps_gaps_as_gaps(self) -> None:
        with (
            patch.object(world_places, "resolve_place", return_value=dict(SEATTLE)),
            patch("jarvis_mrb.physical_conditions.physical_conditions", return_value=_conditions(status="unavailable", alerts=2)),
            patch("jarvis_mrb.public_incidents.regional_earthquakes", return_value={"status": "unavailable"}),
        ):
            reply = agent.execute_tool("world.observe_place", {"place": "Seattle, WA"})
        self.assertTrue(reply.ok)
        self.assertIn("2 active NWS alerts", reply.message)
        self.assertIn("not an all clear", reply.message)
        entity = world_model.get_entity(reply.data["entity_id"])
        predicates = {item["predicate"]: item for item in entity["beliefs"]}
        self.assertEqual(predicates["nws_alert_count"]["value"], 2)
        self.assertNotIn("us_aqi", predicates)  # unavailable model is not recorded as a value
        self.assertNotIn("usgs_quake_count", predicates)

    def test_compile_condition_grounds_places_and_devices_and_rejects_unknowns(self) -> None:
        with patch.object(world_places, "resolve_place", return_value=dict(SEATTLE)):
            crit = world_places.compile_condition(
                {"kind": "world_metric", "place": "Seattle", "predicate": "us_aqi", "op": "lt", "value": 100}
            )
        self.assertEqual(crit["kind"], "belief_compare")
        self.assertTrue(crit["entity_id"].startswith("place:"))
        self.assertTrue(crit["observed_after"])
        with self.assertRaises(ValueError):
            world_places.compile_condition({"kind": "world_metric", "place": "x", "predicate": "crime_rate"})
        with self.assertRaises(ValueError):
            world_places.compile_condition({"kind": "device_state", "device": "Garage Door", "predicate": "power_on"})
        world_places.record_light_catalog([{"id": LAMP, "name": "Desk Lamp", "on": False}])
        device = world_places.compile_condition(
            {"kind": "device_state", "device": "desk lamp", "predicate": "power_on", "value": "on"}
        )
        self.assertIs(device["value"], True)

    def test_belief_compare_requires_fresh_numeric_observation(self) -> None:
        with patch.object(world_places, "resolve_place", return_value=dict(SEATTLE)):
            entity = world_places.place_entity(SEATTLE)
        world_model.assert_belief(entity, "us_aqi", value=40, observed_at="2020-01-01T00:00:00+00:00")
        future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        state = desired_state.create_desired_state(
            "Air clean", [{"kind": "belief_compare", "entity_id": entity, "predicate": "us_aqi",
                           "op": "lt", "value": 100, "observed_after": future}],
            authority={"agency_enabled": True}, source_kind="test", source_ref="t",
        )
        self.assertFalse(desired_state.evaluate_desired_state(state["id"])["satisfied"])  # stale
        world_model.assert_belief(entity, "us_aqi", value="unavailable",
                                  observed_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())
        self.assertFalse(desired_state.evaluate_desired_state(state["id"])["satisfied"])  # non-numeric
        world_model.assert_belief(entity, "us_aqi", value=55,
                                  observed_at=(datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat())
        self.assertTrue(desired_state.evaluate_desired_state(state["id"])["satisfied"])

    # -- dormant goals -----------------------------------------------------------

    def test_planner_wait_until_makes_goal_dormant_and_real_observation_wakes_it(self) -> None:
        agency_runtime.set_mode("active")
        entity = world_model.ensure_entity("project", "Outdoor shoot")
        state = desired_state.create_desired_state(
            "Outdoor shoot scheduled",
            [{"kind": "belief_equals", "entity_id": entity, "predicate": "scheduled", "value": True}],
            authority={"agency_enabled": True}, source_kind="test", source_ref="dormant",
        )
        planner = lambda prompt: {
            "summary": "wait for clean air", "nodes": [], "missing_capability": None,
            "wait_until": {"condition": {"kind": "world_metric", "place": "Seattle", "predicate": "us_aqi",
                                         "op": "lt", "value": 100},
                           "reason": "Shoot only when air is acceptable."},
        }
        with patch.object(world_places, "resolve_place", return_value=dict(SEATTLE)):
            result = agency_runtime.tick_desired_state(
                state["id"], executor=lambda *a, **k: SimpleNamespace(ok=True, message=""), planner=planner,
            )
        self.assertEqual(result["status"], "blocked")
        refreshed = desired_state.get_desired_state(state["id"])
        self.assertIn("Dormant until us_aqi lt 100", refreshed["blocked_reason"])
        watches = desired_state.list_wake_watches(desired_state_id=state["id"])
        self.assertEqual(len(watches), 1)
        self.assertEqual(world_places.referenced_places(), [watches[0]["condition"]["entity_id"]])

        # Unrelated/unsatisfying observation keeps it dormant.
        with patch("jarvis_mrb.physical_conditions.physical_conditions", return_value=_conditions(aqi=180)), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes", return_value={"status": "unavailable"}):
            world_places.refresh_referenced(min_interval_seconds=0)
        self.assertEqual(desired_state.check_wake_watches()["triggered"], 0)
        # A fresh real observation satisfying the exact condition wakes it.
        with patch("jarvis_mrb.physical_conditions.physical_conditions", return_value=_conditions(aqi=35)), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes", return_value={"status": "unavailable"}):
            world_places.refresh_referenced(min_interval_seconds=0)
        self.assertEqual(desired_state.check_wake_watches()["triggered"], 1)
        self.assertEqual(desired_state.get_desired_state(state["id"])["state"], "active")
        prompt = agency_runtime._planner_prompt(desired_state.get_desired_state(state["id"]), {"missing": []}, None)
        self.assertIn("reactivated because its wake condition is now freshly observed", prompt)

    def test_wait_until_plan_contract_validation(self) -> None:
        _validate_plan({"summary": "s", "nodes": [], "missing_capability": None,
                        "wait_until": {"condition": {"kind": "world_metric"}, "reason": "r"}})
        with self.assertRaises(ValueError):
            _validate_plan({"summary": "s", "nodes": [{"id": "n1", "tool": "web.search", "arguments": {}}],
                            "wait_until": {"condition": {}, "reason": "r"}})
        with self.assertRaises(ValueError):
            _validate_plan({"summary": "s", "nodes": [], "wait_until": {"condition": {}, "reason": ""}})

    # -- presence verification ------------------------------------------------------

    def _dispatch_confirmed(self, on: bool = True):
        world_places.record_light_catalog([{"id": LAMP, "name": "Desk Lamp", "on": not on, "reachable": True}])
        # The confirmation boundary is covered separately; this exercises the
        # post-confirmation execution path directly.
        with patch("jarvis_mrb.event_bus.companion_events.publish"):
            return agent._execute_unchecked("presence.set_light", {"light": "Desk Lamp", "on": on})

    def test_presence_dispatch_is_unverified_until_readback(self) -> None:
        reply = self._dispatch_confirmed(on=True)
        self.assertTrue(reply.ok)
        self.assertIn("unverified", reply.message)
        plan = world_verification._plan("presence.set_light", {"light": "Desk Lamp", "on": True}, reply)
        self.assertEqual(plan["status"], "pending")
        self.assertEqual(plan["verifier"], "presence_reported_state")
        status, _ = world_verification._observe(plan["verifier"], plan["expected"])
        self.assertEqual(status, "pending")
        world_armor_full.record_presence_receipt(reply.data["request_id"], status="verified_reported_state",
                                                 message="Verified in Apple Home: Desk Lamp is on")
        status, evidence = world_verification._observe(plan["verifier"], plan["expected"])
        self.assertEqual(status, "verified", evidence)
        light = world_places.resolve_light("Desk Lamp")
        self.assertIs(light["power_on"], True)
        # The one-use grant is spent: no second actuation through that grant.
        with self.assertRaises(ValueError):
            world_armor_full.dispatch_presence(reply.data["grant_id"], desired_on=True)

    def test_presence_failure_and_unverified_readback_are_not_success(self) -> None:
        first = self._dispatch_confirmed(on=True)
        world_armor_full.record_presence_receipt(first.data["request_id"], status="blocked",
                                                 message="Accessory unreachable")
        plan = world_verification._plan("presence.set_light", {}, first)
        self.assertEqual(world_verification._observe(plan["verifier"], plan["expected"])[0], "failed")
        second = self._dispatch_confirmed(on=False)
        world_armor_full.record_presence_receipt(second.data["request_id"], status="unverified",
                                                 message="Write accepted; readback failed")
        plan = world_verification._plan("presence.set_light", {}, second)
        self.assertEqual(world_verification._observe(plan["verifier"], plan["expected"])[0], "unverified")

    def test_presence_refuses_unknown_light_and_disabled_layer(self) -> None:
        self.assertFalse(agent._execute_unchecked("presence.set_light", {"light": "Front Door Lock", "on": True}).ok)
        with patch.dict(os.environ, {"JARVIS_WORLD_ARMOR_FULL_ENABLED": "0"}):
            reply = agent._execute_unchecked("presence.set_light", {"light": "Desk Lamp", "on": True})
        self.assertFalse(reply.ok)
        self.assertIn("disabled", reply.message)

    # -- ordinary-language goal intake ---------------------------------------------

    def test_declared_goal_is_offered_for_pursuit_behind_confirmation(self) -> None:
        agency_runtime.set_mode("monitor")
        reply = agent._fast_path("My goal is to get the Apollo contract signed by Friday.")
        self.assertIsNotNone(reply)
        self.assertIn("recorded your goal", reply.message)
        self.assertIn("confirm", reply.message.lower())
        self.assertEqual(agency_runtime.get_mode(), "monitor")  # nothing expanded before confirmation
        with patch("jarvis_mrb.agency_goal_compiler._model_compile", side_effect=RuntimeError("offline")):
            confirmed = agent._fast_path("confirm")
        self.assertTrue(confirmed.ok, confirmed.message)
        self.assertEqual(agency_runtime.get_mode(), "active")
        states = [s for s in desired_state.list_desired_states() if "apollo" in s["title"].lower()]
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0]["state"], "active")
        self.assertIs(states[0]["authority"]["agency_enabled"], True)

    def test_catalog_endpoint_requires_private_auth(self) -> None:
        from fastapi import HTTPException
        from fastapi.responses import Response

        from jarvis_mrb import service

        request = service.PresenceCatalogRequest(lights=[{"id": LAMP, "name": "Desk Lamp", "on": True}])
        with patch.object(service, "API_TOKEN", "secret"):
            with self.assertRaises(HTTPException):
                service.world_armor_presence_catalog(request, Response(), authorization=None)
            result = service.world_armor_presence_catalog(request, Response(), authorization="Bearer secret")
        self.assertEqual(result["stored"], 1)


if __name__ == "__main__":
    unittest.main()
