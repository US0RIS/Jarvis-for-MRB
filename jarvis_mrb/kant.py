"""Kant: HORUS deep-reasoning compatibility facade."""
from jarvis_mrb.planner_model import QUALITY_MODEL

NAME = "Kant"
MODEL = QUALITY_MODEL

def status() -> dict[str, str]:
    return {"name": NAME, "role": "deep_reasoning", "model": MODEL}
