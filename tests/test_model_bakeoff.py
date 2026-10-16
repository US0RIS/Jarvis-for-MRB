from __future__ import annotations

from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch

from jarvis_mrb import model_bakeoff as bakeoff


class FakeResponse:
    def __init__(self, text: str, *, bad: bool=False):
        self.text=text
        self.bad=bad

    def raise_for_status(self):
        if self.bad: raise ValueError("synthetic error")

    def iter_lines(self):
        yield json.dumps({"message":{"content":self.text[:15]}}).encode()
        yield json.dumps({
            "message":{"content":self.text[15:]},
            "eval_count":12,"eval_duration":300_000_000,
            "done":True,
        }).encode()


class FakeClient:
    def __init__(self, response: str):
        self.response=response
        self.calls=[]

    @contextmanager
    def stream(self,method,url,*,json,timeout):
        self.calls.append({"method":method,"url":url,"payload":json,"timeout":timeout})
        yield FakeResponse(self.response)


class ModelBakeoffTests(unittest.TestCase):
    def test_loopback_only_and_no_credentials_in_url(self):
        for bad in ("https://api.ollama.example","http://10.0.0.2:11434",
                    "http://user:pass@127.0.0.1:11434","file:///tmp/model",
                    "http://localhost:11434/?token=secret"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                bakeoff._assert_loopback(bad)

    def test_same_corpus_checks_actual_tool_json(self):
        client=FakeClient('{"tool":"web.search","arguments":{"query":"announcement"}}')
        cases=({"id":"new-model","prompt":"Was a model announced?","tool":"web.search"},)
        result=bakeoff.evaluate_model("gemma4:12b",client=client,corpus=cases)
        self.assertEqual(result["routing_correct"],1)
        self.assertEqual(result["parseable"],1)
        self.assertEqual(len(client.calls),1)
        self.assertFalse(result["eligible_for_automatic_promotion"])
        payload=client.calls[0]["payload"]
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["temperature"],0)
        self.assertEqual(payload["model"],"gemma4:12b")
        self.assertEqual(payload["messages"][-1]["content"],"Was a model announced?")

    def test_hallucinated_tool_and_bad_json_fail_without_acting(self):
        bad=FakeClient('{"tool":"delete_everything","arguments":{}}')
        rows=({"id":"test","prompt":"Are you sure?","tool":None},)
        out=bakeoff.evaluate_model("qwen3:8b",client=bad,corpus=rows)
        self.assertEqual(out["routing_correct"],0)
        self.assertTrue(out["cases"][0]["parseable"])
        unparseable=FakeClient("I have performed a search!")
        out=bakeoff.evaluate_model("qwen3:8b",client=unparseable,corpus=rows)
        self.assertFalse(out["cases"][0]["parseable"])
        self.assertEqual(out["routing_correct"],0)

    def test_no_automatic_model_switching(self):
        from jarvis_mrb import planner_model
        model=bakeoff.evaluate_model("gemma4:12b",client=FakeClient('{"tool":null,"arguments":{}}'),
                                     corpus=({"id":"definition","prompt":"Define a prism","tool":None},))
        self.assertEqual(model["model"],"gemma4:12b")
        self.assertNotIn("gemma4:12b",planner_model.SUPPORTED_MODELS)

    def test_invalid_model_name_rejected(self):
        with self.assertRaises(ValueError):
            bakeoff.evaluate_model("")
        with self.assertRaises(ValueError):
            bakeoff.evaluate_model("hello\nnot-a-model")


if __name__ == "__main__":
    unittest.main()
