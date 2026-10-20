import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_mrb import inference


class FakeKeyring:
    keys = {}

    def set_password(self, service, provider, key):
        self.keys[(service, provider)] = key

    def get_password(self, service, provider):
        return self.keys.get((service, provider))


class InferenceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "inference.json"
        FakeKeyring.keys = {}
        self.p1 = patch.object(inference, "SETTINGS_PATH", self.path)
        self.p2 = patch.object(inference, "_keyring", return_value=FakeKeyring())
        self.p1.start()
        self.p2.start()
        self.addCleanup(self.p1.stop)
        self.addCleanup(self.p2.stop)

    def test_settings_do_not_include_secret(self):
        status = inference.configure_inference("openai", "gpt-5.5", "sk-secret-value")
        self.assertEqual(status["provider"], "openai")
        self.assertTrue(status["key_configured"])
        self.assertNotIn("sk-secret-value", self.path.read_text())
        self.assertNotIn("sk-secret-value", json.dumps(status))

    def test_cannot_switch_to_provider_without_secret(self):
        with self.assertRaises(ValueError):
            inference.configure_inference("anthropic", "claude-sonnet-4-5")
        self.assertFalse(self.path.exists())

    def test_rejects_unknown_provider_and_model(self):
        for provider, model in [("untrusted", "x"), ("openai", "bad\\nmodel")]:
            with self.subTest(provider=provider, model=model), self.assertRaises(ValueError):
                inference.configure_inference(provider, model, "sk-test")

    def test_plan_parses_json_and_never_executes_tools(self):
        inference.configure_inference("openai", "gpt-5.5", "sk-test")
        fake = type("Response", (), {
            "status_code": 200,
            "raise_for_status": lambda self: None,
            "json": lambda self: {"choices": [{"message": {"content": '{"tool":null,"response":"Hello"}'}}]},
        })()
        class Client:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def post(self, url, json, headers):
                self.assert_target(url, headers)
                return fake
            def assert_target(self, url, headers):
                assert url == inference.PROVIDERS["openai"]
                assert headers["Authorization"] == "Bearer sk-test"
        with patch.object(inference.httpx, "Client", Client):
            result = inference.plan_with_provider([{"role": "user", "content": "Hi"}])
        self.assertEqual(result["response"], "Hello")


if __name__ == "__main__":
    unittest.main()
