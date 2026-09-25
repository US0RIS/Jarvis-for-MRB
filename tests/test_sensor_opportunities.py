from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import jarvis_mrb.sensor_opportunities as radar


class AmbientOpportunityTests(unittest.TestCase):
    def setUp(self) -> None:
        radar._LIVE.clear()
        radar._NEXT_WEATHER.clear()
        self.now = datetime(2026, 9, 20, 20, 0, tzinfo=timezone.utc)
        self.goals = [
            {"id": "home", "title": "Remind me to call Alex when I get home", "confidence": 1.0},
            {"id": "leave", "title": "Remind me to take my bag when I leave home", "confidence": 1.0},
            {"id": "bell", "title": "Remind me to check the delivery when the doorbell rings", "confidence": 1.0},
            {"id": "cold", "title": "Remind me to bring a jacket when it's cold", "confidence": 1.0},
            {"id": "hot", "title": "Remind me to refill my bottle when it's hot outside", "confidence": 1.0},
            {"id": "write", "title": "Turn on the lights when I get home", "confidence": 1.0},
        ]

    def snapshot(self, *, state: str = "away", moment: datetime | None = None) -> dict:
        stamp = (moment or self.now).isoformat()
        return {
            "source_id": "phone-01", "enabled": True, "observed_at": stamp,
            "location": {
                "latitude": 34.1, "longitude": -118.1,
                "observed_at": stamp, "home_state": state, "home_observed_at": stamp,
            },
            "weather_opt_in": True, "motion": {"activity": "walking", "observed_at": stamp},
            "audio": {"conversation_active": False},
        }

    @patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True})
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_transition_requires_second_distinct_state_and_never_executes(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        self.assertEqual(radar.ingest(self.snapshot(), now=self.now), [])
        self.assertEqual(radar.ingest(self.snapshot(), now=self.now), [])
        next_time = self.now + timedelta(seconds=5)
        result = radar.ingest(self.snapshot(state="home", moment=next_time), now=next_time)
        self.assertEqual(len(result), 1)
        request = consider.call_args.kwargs
        self.assertEqual(request["desired_state_id"], "home")
        self.assertEqual(request["kind"], "ambient_goal_opportunity")
        self.assertIn("call Alex", request["message"])
        self.assertNotIn("tool", request)
        self.assertNotIn("execute", request)
        self.assertEqual(len(radar.ingest(self.snapshot(state="home", moment=next_time), now=next_time)), 0)
        next_time += timedelta(seconds=5)
        result = radar.ingest(self.snapshot(state="away", moment=next_time), now=next_time)
        self.assertEqual(len(result), 1)
        self.assertEqual(consider.call_args.kwargs["desired_state_id"], "leave")

    @patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True})
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_doorbell_only_once_per_observation_and_not_independent_microphone(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        sample = self.snapshot()
        sample["sound"] = {
            "identifier": "door_bell", "confidence": 0.90,
            "observed_at": self.now.isoformat(),
        }
        self.assertEqual(len(radar.ingest(sample, now=self.now)), 1)
        self.assertEqual(len(radar.ingest(sample, now=self.now + timedelta(seconds=2))), 0)
        sample["sound"]["observed_at"] = (self.now + timedelta(seconds=6)).isoformat()
        self.assertEqual(len(radar.ingest(sample, now=self.now + timedelta(seconds=6))), 1)
        self.assertEqual(consider.call_count, 2)
        self.assertIn("may have heard", consider.call_args.kwargs["message"])

    @patch("jarvis_mrb.agency_attention.consider")
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_replay_low_confidence_privacy_and_driving_never_fire(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        old = self.snapshot(moment=self.now - timedelta(minutes=7))
        self.assertEqual(radar.ingest(old, now=self.now), [])
        first = self.snapshot()
        radar.ingest(first, now=self.now)
        driving = self.snapshot(state="home", moment=self.now + timedelta(seconds=2))
        driving["motion"]["activity"] = "driving"
        self.assertEqual(radar.ingest(driving, now=self.now + timedelta(seconds=2)), [])
        radar.ingest({"source_id": "phone-01", "enabled": False})
        self.assertEqual(radar._LIVE, {})
        # Re-enabling must establish a new baseline, not fire a replayed arrival.
        self.assertEqual(radar.ingest(driving, now=self.now + timedelta(seconds=2)), [])
        driving["motion"]["activity"] = "walking"
        driving["sound"] = {
            "identifier": "doorbell", "confidence": 0.78,
            "observed_at": driving["observed_at"],
        }
        self.assertEqual(radar.ingest(driving, now=self.now + timedelta(seconds=2)), [])
        consider.assert_not_called()

    @patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True})
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_weather_provider_is_opt_in_attributed_fresh_and_modelled(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        radar.ingest(self.snapshot(), now=self.now)
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None
            def json(self) -> dict:
                return {"current": {"time": "2026-09-20T19:45", "temperature_2m": 8.4}}
        class FakeClient:
            def __init__(self) -> None:
                self.calls = []
            def get(self, url: str, *, params: dict) -> FakeResponse:
                self.calls.append((url, params))
                return FakeResponse()
        client = FakeClient()
        result = radar.check_weather(now=self.now, client=client)
        self.assertEqual(len(result), 1)
        call = consider.call_args.kwargs
        self.assertEqual(call["desired_state_id"], "cold")
        self.assertIn("modelled outdoor temperature", call["message"])
        self.assertIn("Open-Meteo", call["message"])
        self.assertNotIn("tool", call)
        self.assertEqual(client.calls[0][1]["current"], "temperature_2m")
        self.assertEqual(radar.check_weather(now=self.now, client=client), [])
        self.assertEqual(len(client.calls), 1)

    @patch("jarvis_mrb.agency_attention.consider")
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_stale_weather_and_location_never_fire(self, goals, consider) -> None:
        goals.return_value = self.goals
        sample = self.snapshot()
        sample["weather_opt_in"] = False
        radar.ingest(sample, now=self.now)
        self.assertEqual(radar.check_weather(now=self.now), [])
        sample["weather_opt_in"] = True
        sample["location"]["observed_at"] = (self.now - timedelta(minutes=5)).isoformat()
        radar.ingest(sample, now=self.now)
        self.assertEqual(radar.check_weather(now=self.now), [])
        consider.assert_not_called()

    def test_reminder_compiler_rejects_unapproved_actions_and_political_inference(self) -> None:
        with patch("jarvis_mrb.world_executive.active_intentions", return_value=self.goals):
            parsed = radar._reminders()
        self.assertEqual({v["id"] for v in parsed}, {"home", "leave", "bell", "cold", "hot"})
        with patch("jarvis_mrb.world_executive.active_intentions", return_value=[
            {"id": "danger", "title": "Remind me to unlock the door automatically when I get home", "confidence": 1},
            {"id": "low", "title": "Remind me to call Alex when I get home", "confidence": .4},
            {"id": "vague", "title": "Help me when I get home", "confidence": 1},
        ]):
            self.assertEqual(radar._reminders(), [])

    @patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True})
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_interruptions_are_deferred_until_quiet_and_are_expiring(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        radar.ingest(self.snapshot(), now=self.now)
        arrival_at = self.now + timedelta(seconds=4)
        arrival = self.snapshot(state="home", moment=arrival_at)
        arrival["audio"]["conversation_active"] = True
        self.assertEqual(radar.ingest(arrival, now=arrival_at), [])
        self.assertEqual(len(radar._LIVE["phone-01"]["pending"]), 1)
        quiet_at = arrival_at + timedelta(seconds=8)
        quiet = self.snapshot(state="home", moment=quiet_at)
        self.assertEqual(len(radar.ingest(quiet, now=quiet_at)), 1)
        self.assertIn("while you were occupied", consider.call_args.kwargs["message"])
        self.assertEqual(radar.ingest(quiet, now=quiet_at), [])
        self.assertEqual(radar._LIVE["phone-01"]["pending"], [])

        # A new event withheld for more than three minutes is discarded.
        leave_at = quiet_at + timedelta(seconds=5)
        leaving = self.snapshot(state="away", moment=leave_at)
        leaving["audio"]["conversation_active"] = True
        radar.ingest(leaving, now=leave_at)
        late_at = leave_at + timedelta(seconds=190)
        late = self.snapshot(state="away", moment=late_at)
        self.assertEqual(radar.ingest(late, now=late_at), [])
        self.assertEqual(consider.call_count, 1)

    @patch("jarvis_mrb.agency_attention.consider", return_value={"emitted": True})
    @patch("jarvis_mrb.world_executive.active_intentions")
    def test_monitoring_veto_and_late_packets_do_not_trigger_actions(
        self, goals, consider
    ) -> None:
        goals.return_value = self.goals
        radar.ingest(self.snapshot(), now=self.now)
        later = self.now + timedelta(seconds=25)
        next_sample = self.snapshot(state="home", moment=later)
        with patch("jarvis_mrb.environment_state.get_state", return_value={
            "preferences": {"proactive_monitoring": False}
        }):
            self.assertEqual(radar.ingest(next_sample, now=later), [])
            self.assertEqual(radar.check_weather(now=later), [])
        self.assertEqual(consider.call_count, 0)
        # A late away packet should not roll back the home baseline.
        previous = self.snapshot(state="away", moment=self.now + timedelta(seconds=5))
        self.assertEqual(radar.ingest(previous, now=self.now + timedelta(seconds=5)), [])
        later += timedelta(seconds=2)
        self.assertEqual(radar.ingest(self.snapshot(state="home", moment=later), now=later), [])
        self.assertEqual(consider.call_count, 0)

    def test_status_does_not_claim_camera_or_unrestricted_physical_control(self) -> None:
        info = radar.status()
        self.assertIs(info["camera_required"], False)
        self.assertIs(info["can_actuate"], False)
        self.assertIs(info["transcripts_or_raw_audio_persisted"], False)


if __name__ == "__main__":
    unittest.main()
