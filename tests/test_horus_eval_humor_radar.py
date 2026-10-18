from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import evaluation as ev
from jarvis_mrb.horus import humor as hu
from jarvis_mrb.horus import radar as rd

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
S = timedelta(seconds=1)


def tts(name, **kw):
    base = dict(candidate=name, cold_start_s=5, ttfa_ms={"5": 200, "15": 250, "40": 300}, rtf=0.3, vram_gb=2,
                mos_naturalness=3.6, intelligibility=0.95, name_accuracy=0.8, long_stability=0.9,
                identity_consistency=0.95, streaming=True, cancel_latency_ms=80, releases_work_on_cancel=True,
                sequential_failures=0, recovers_after_restart=True, local_only=True, license_ok=True, api_contract_fit=True)
    base.update(kw)
    return ev.TTSMeasurement(**base)


class EvaluationTests(unittest.TestCase):
    def test_tts_baseline_kept_unless_demonstrably_better(self) -> None:
        base = tts("kokoro")
        slightly = tts("cosy", mos_naturalness=3.8)
        slow = tts("omni", mos_naturalness=4.8, name_accuracy=0.95, ttfa_ms={"5": 900, "15": 1000, "40": 1200})
        cloud = tts("cloudy", mos_naturalness=5, local_only=False)
        self.assertEqual(ev.tts_decision([base, slightly, slow, cloud], baseline="kokoro")["decision"], "kokoro")
        great = tts("great", mos_naturalness=4.7, name_accuracy=0.97, long_stability=0.98)
        d = ev.tts_decision([base, great], baseline="kokoro")
        self.assertTrue(d["replace"])
        with self.assertRaises(ValueError):
            ev.tts_decision([great], baseline="kokoro")
        m = ev.measure_ttfa(lambda text: iter([b"ab", b"cd"]), "hi")
        self.assertEqual(m["bytes"], 4)
        self.assertIn("kokoro-82m/bm_george (baseline)", ev.TTS_CANDIDATES)

    def test_model_promotion_rule(self) -> None:
        runs = []
        for i in range(30):
            runs.append(ev.ModelRun("qwen", f"t{i}", i % 3 != 0, True, i % 10 == 0, 300, 40, 9))
            runs.append(ev.ModelRun("gemma", f"t{i}", i % 5 != 0, True, i % 15 == 0, 350, 35, 14))
        self.assertTrue(ev.promotion_decision(runs, incumbent="qwen", candidate="gemma")["promote"])
        self.assertFalse(ev.promotion_decision(runs, incumbent="qwen", candidate="gemma", vram_budget_gb=12)["promote"])
        self.assertFalse(ev.promotion_decision(runs[:10], incumbent="qwen", candidate="gemma")["promote"])

    def test_matrix_traces_vision(self) -> None:
        mat = ev.eval_matrix({"a": lambda p: p.upper(), "b": lambda p: 1 / 0}, {"p1": "hi"}, {"p1": lambda o: o == "HI"})
        self.assertEqual(mat["pass_counts"], {"a": 1, "b": 0})
        tl = ev.TraceLedger()
        tid = tl.start("turn on porch light", T0)
        tl.span(tid, "tool", T0, name="homekit.set")
        self.assertFalse(tl.claim_supported(tid, "light is on")["supported"])
        tl.span(tid, "receipt", T0, verified=True, readback="on")
        self.assertTrue(tl.claim_supported(tid, "light is on")["supported"])
        vs = ev.score_vision([ev.VisionCase("c1", "img", "sign text?", "STOP", "ocr")],
                             {"c1": {"text": "It says STOP", "latency_ms": 400, "confidence": 0.9}}, latency_budget_ms=500)
        self.assertEqual(vs["accuracy"], 1.0)


def seg(speaker, text, i, laughter=False):
    return hu.Segment(speaker, text, T0 + i * 5 * S, T0 + (i * 5 + 4) * S, laughter)


class HumorTests(unittest.TestCase):
    def engine(self, mode="commentary"):
        e = hu.HumorEngine(hu.HumorState(session_consented=True), seed=1)
        e.set_mode(mode)
        e.verify_output("earbud", connected=True)
        return e

    def test_private_output_required(self) -> None:
        e = hu.HumorEngine(hu.HumorState(session_consented=True))
        e.set_mode("commentary")
        self.assertFalse(e.verify_output("living_room_speaker", connected=True))
        w = [seg("bob", "Oops, I dropped my phone again", 0)]
        self.assertEqual(e.consider(w, w[-1].end)["reason"], "private output device not verified")

    def test_canonical_triggers(self) -> None:
        cases = [
            ("bob", "We should open a restaurant on the moon, that would be amazing", "no_plan"),
            ("bob", "Turns out it's cold in winter", "obvious"),
            ("bob", "I'm pretty sure birds aren't real", "bizarre"),
            ("bob", "Wow, you're so slow today", "rome"),
            ("cashier", "Paper or plastic?", "checkout"),
            ("user", "Can I ask you something?", "be_honest"),
            ("bob", "Oops, I spilled coffee on the keyboard", "trout"),
        ]
        for speaker, text, bit in cases:
            e = self.engine()
            w = [seg(speaker, text, 0)]
            d = e.consider(w, w[-1].end)
            self.assertTrue(d["deliver"], (text, d))
            self.assertEqual(d["bit"], bit)
            self.assertFalse(d["speak_publicly"])

    def test_gates_distress_late_cooldown_stutter(self) -> None:
        e = self.engine()
        w = [seg("bob", "My dad passed away last week and I dropped everything", 0)]
        self.assertIn("distress", e.consider(w, w[-1].end)["reason"])
        w = [seg("bob", "Oops, I spilled it", 0)]
        self.assertEqual(e.consider(w, w[-1].end + 10 * S)["reason"], "too late; moment passed")
        self.assertTrue(e.consider(w, w[-1].end)["deliver"])
        w2 = [seg("bob", "Turns out water is wet", 1)]
        self.assertEqual(e.consider(w2, w2[-1].end)["reason"], "cooldown")
        e2 = self.engine()
        st = [seg("ann", "I I I um think we we should uh um go go now", 0)]
        self.assertNotEqual(e2.consider(st, st[-1].end, stutter_speakers=["ann"]).get("bit"), "stumble")

    def test_dark_humor_commentary_only(self) -> None:
        w = [seg("bob", "haha", 0, laughter=True),
             seg("bob", "Back when my parents got divorced they bought me a pony, it was years ago", 1, laughter=True)]
        self.assertEqual(self.engine("commentary").consider(w, w[-1].end)["bit"], "not_their_fault")
        self.assertFalse(self.engine("suggestion").consider(w, w[-1].end)["deliver"])

    def test_feedback_and_harness(self) -> None:
        e = self.engine()
        e.feedback("trout", "socially_off")
        e.feedback("trout", "socially_off")
        w = [seg("bob", "Oops, I spilled it", 0)]
        self.assertIn("threshold", e.consider(w, w[-1].end)["reason"])
        e2 = self.engine()
        segs = [seg("bob", "Hey how are you", 0), seg("bob", "Oops, I tripped on the rug", 1),
                seg("bob", "Anyway the weather is nice", 2)]
        res = hu.evaluate_transcript(e2, segs, openings={1: "trout"})
        self.assertEqual(res["hits"], 1)
        self.assertEqual(res["false_interruptions"], 0)
        e2.mute()
        self.assertEqual(e2.state.mode, "off")


class RadarTests(unittest.TestCase):
    def test_catalog_and_scoring(self) -> None:
        self.assertGreater(len(rd.CATALOG), 50)
        self.assertTrue(all(c.status == "research_candidate" for c in rd.CATALOG))
        meta = {"full_name": "x/geofence-db", "description": "realtime geofence spatial index database",
                "topics": ["geospatial"], "pushed_at": T0 - timedelta(days=3), "license": "MIT", "stargazers_count": 10}
        s = rd.score_candidate(meta, gaps=["geofence enter exit spatial index"], now=T0)
        self.assertTrue(s["interesting"])
        q = rd.RadarQueue()
        self.assertTrue(q.offer(s))
        self.assertFalse(q.offer(s))
        popular = rd.score_candidate({"full_name": "y/ai-agent", "description": "awesome ai agent framework",
                                      "pushed_at": T0, "license": "MIT", "stargazers_count": 90000},
                                     gaps=["geofence enter exit spatial index"], now=T0)
        self.assertFalse(popular["interesting"])
        self.assertIn("topic:tts stars:>200", rd.discovery_queries(["tts"], year=2026))

    def test_meta_tools(self) -> None:
        self.assertTrue(any(c["concept"] == "sterile cockpit" for c in rd.concept_importer("cockpit focus mode")))
        af = rd.anti_features(["too many notifications!", "it's so annoying", "creepy listening"])
        self.assertEqual([a["theme"] for a in af], ["distraction"])
        b = rd.ComplexityBudget(10)
        self.assertTrue(b.request("a", 4)["approved"])
        self.assertTrue(b.request("b", 4)["approved"])
        self.assertFalse(b.request("c", 4)["approved"])
        self.assertTrue(b.request("unified", 5, collapses=["a", "b"])["approved"])
        cl = rd.crystallize(["One-command temporary watch", "Standing query alert trigger", "Reality Rewind history",
                             "Reality Diff changed state"])
        self.assertEqual({c["primitive"] for c in cl}, {"standing query engine", "temporal truth model"})


if __name__ == "__main__":
    unittest.main()
