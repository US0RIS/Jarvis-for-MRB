from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

import jarvis_mrb.agency_deliberation as agency_deliberation
import jarvis_mrb.world_model as world_model


class AgencyDeliberationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "world_model.sqlite3"
        world_model.APP_DIR = self.base
        world_model.DB_PATH = self.db
        agency_deliberation.DB_PATH = self.db
        world_model.status()
        agency_deliberation.status()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_workers_run_in_parallel_and_synthesis_sees_every_output(self) -> None:
        barrier = threading.Barrier(4)
        started: list[str] = []
        lock = threading.Lock()

        def worker(role: str, question: str, context: str) -> dict:
            with lock:
                started.append(role)
            barrier.wait(timeout=2)
            time.sleep(0.15)
            return {
                "conclusion": f"{role} conclusion",
                "claims": [{"claim": "shared claim", "confidence": 0.5, "evidence": role}],
                "risks": [],
                "unknowns": [],
            }

        synthesis_inputs: list[list[dict]] = []

        def synth(question: str, context: str, outputs: list[dict], disagreements: list[dict]) -> dict:
            synthesis_inputs.append(list(outputs))
            return {
                "answer": "combined",
                "consensus": [],
                "disagreements": disagreements,
                "unknowns": [],
                "recommended_next_evidence": [],
                "confidence": 0.6,
            }

        started_at = time.monotonic()
        result = agency_deliberation.deliberate(
            "Which path?",
            roles=["evidence", "skeptic", "feasibility", "risk_cost"],
            worker=worker,
            synthesizer=synth,
        )
        wall = time.monotonic() - started_at

        self.assertEqual(result["status"], "completed")
        self.assertEqual(set(started), {"evidence", "skeptic", "feasibility", "risk_cost"})
        self.assertEqual(len(synthesis_inputs), 1)
        self.assertEqual(len(synthesis_inputs[0]), 4)
        # Four 150ms workers would be >=600ms if serialized. Leave generous overhead
        # for SQLite and thread scheduling while still proving concurrent execution.
        self.assertLess(wall, 0.50)

        persisted = agency_deliberation.get(result["id"])
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(len(persisted["workers"]), 4)
        self.assertTrue(all(worker["status"] == "completed" for worker in persisted["workers"]))

    def test_material_disagreement_is_preserved_not_averaged_away(self) -> None:
        def worker(role: str, question: str, context: str) -> dict:
            confidence = 0.9 if role == "evidence" else 0.2 if role == "skeptic" else 0.55
            conclusion = "Proceed" if role in {"evidence", "feasibility"} else "Do not proceed"
            return {
                "conclusion": conclusion,
                "claims": [
                    {
                        "claim": "The dependency is reliable",
                        "confidence": confidence,
                        "evidence": f"{role} evidence",
                    }
                ],
                "risks": [f"{role} risk"],
                "unknowns": [],
            }

        result = agency_deliberation.deliberate(
            "Proceed?",
            worker=worker,
            synthesizer=lambda q, c, outputs, disagreements: {
                "answer": "There is a material dispute.",
                "consensus": [],
                "disagreements": disagreements,
                "unknowns": [],
                "recommended_next_evidence": ["Test dependency"],
                "confidence": 0.5,
            },
        )

        kinds = {item["type"] for item in result["disagreements"]}
        self.assertIn("confidence_divergence", kinds)
        self.assertIn("different_conclusions", kinds)
        persisted = agency_deliberation.get(result["id"])
        self.assertEqual(persisted["disagreements"], result["disagreements"])

    def test_worker_cannot_invent_provenance_identifier(self) -> None:
        context = "SOURCE:doc-123 says the dependency is available."

        result = agency_deliberation.deliberate(
            "Is it available?",
            context=context,
            roles=["evidence"],
            worker=lambda role, question, supplied_context: {
                "conclusion": "Available",
                "claims": [
                    {
                        "claim": "Dependency is available",
                        "confidence": 0.9,
                        "evidence": "Context says so",
                        "source": "context",
                    },
                    {
                        "claim": "Invented citation",
                        "confidence": 0.9,
                        "evidence": "Made up",
                        "source": "doc-999",
                    },
                ],
                "sources": ["doc-123", "doc-999"],
                "risks": [],
                "unknowns": [],
            },
            synthesizer=lambda q, c, outputs, disagreements: {
                "answer": "Available",
                "consensus": [],
                "disagreements": disagreements,
                "unknowns": [],
                "recommended_next_evidence": [],
                "confidence": 0.9,
            },
        )

        output = result["outputs"][0]
        self.assertEqual(output["sources"], ["doc-123"])
        self.assertEqual(output["claims"][0]["source"], "context")
        self.assertEqual(output["claims"][1]["source"], "unknown")

    def test_worker_failure_produces_partial_result_without_erasing_successes(self) -> None:
        def worker(role: str, question: str, context: str) -> dict:
            if role == "skeptic":
                raise RuntimeError("worker unavailable")
            return {"conclusion": role, "claims": [], "risks": [], "unknowns": []}

        result = agency_deliberation.deliberate(
            "Question",
            worker=worker,
            synthesizer=lambda q, c, outputs, disagreements: {
                "answer": "partial",
                "consensus": [],
                "disagreements": disagreements,
                "unknowns": [],
                "recommended_next_evidence": [],
                "confidence": 0.4,
            },
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["outputs"]), 3)
        self.assertTrue(any("skeptic" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
