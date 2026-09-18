from __future__ import annotations

import unittest
from unittest.mock import patch

import jarvis_mrb.agent as agent


class AgentConfirmationSecurityTests(unittest.TestCase):
    def test_foreground_custom_run_names_destination_and_fields_without_values(self) -> None:
        args = {
            "name": "private_weather",
            "arguments": {
                "city": "Pasadena",
                "private_note": "SECRET VALUE 99127",
            },
        }
        with patch.object(
            agent,
            "list_custom_tools",
            return_value=[
                {
                    "name": "private_weather",
                    "enabled": True,
                    "risk": "read",
                    "allowed_hosts": ["weather.example.com"],
                }
            ],
        ):
            rendered = agent._describe_action("custom.run", args)

        self.assertIn("private_weather", rendered)
        self.assertIn("weather.example.com", rendered)
        self.assertIn("city", rendered)
        self.assertIn("private_note", rendered)
        self.assertIn("values omitted", rendered)
        self.assertNotIn("Pasadena", rendered)
        self.assertNotIn("SECRET VALUE", rendered)
        self.assertNotIn("99127", rendered)

    def test_custom_synthesis_confirmation_discloses_host_and_risk_not_api_spec(self) -> None:
        rendered = agent._describe_action(
            "custom.synthesize",
            {
                "name": "private_weather",
                "risk": "read",
                "allowed_hosts": ["weather.example.com"],
                "api_spec": "TOP SECRET INTERNAL SPEC 4815",
            },
        )
        self.assertIn("private_weather", rendered)
        self.assertIn("weather.example.com", rendered)
        self.assertIn("read", rendered)
        self.assertIn("specification omitted", rendered)
        self.assertNotIn("TOP SECRET INTERNAL SPEC", rendered)
        self.assertNotIn("4815", rendered)

    def test_custom_run_http_status_controls_agent_success(self) -> None:
        with patch.object(
            agent,
            "run_custom_tool",
            return_value={
                "status_code": 200,
                "body": {"ok": True},
            },
        ):
            success = agent._execute_unchecked(
                "custom.run",
                {"name": "private_weather", "arguments": {"city": "Pasadena"}},
            )
        self.assertTrue(success.ok)
        self.assertIn("HTTP 200", success.message)

        with patch.object(
            agent,
            "run_custom_tool",
            return_value={
                "status_code": 503,
                "body": {"error": "temporarily unavailable"},
            },
        ):
            failure = agent._execute_unchecked(
                "custom.run",
                {"name": "private_weather", "arguments": {"city": "Pasadena"}},
            )
        self.assertFalse(failure.ok)
        self.assertIn("HTTP 503", failure.message)

    def test_custom_enable_confirmation_states_resulting_enablement(self) -> None:
        enabled = agent._describe_action(
            "custom.enable",
            {"name": "private_weather", "enabled": True},
        )
        disabled = agent._describe_action(
            "custom.enable",
            {"name": "private_weather", "enabled": False},
        )
        self.assertIn("enabled=True", enabled)
        self.assertIn("enabled=False", disabled)


if __name__ == "__main__":
    unittest.main()
