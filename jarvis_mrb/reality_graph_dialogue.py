from __future__ import annotations

"""Model-free natural language routing for enrolled Reality Graph mission facts.

Read-only and narrow by design. No mission creation, data ingestion, purchases,
camera queries, control authority, implicit mission selection among several.
"""

import re

from jarvis_mrb import reality_graph_missions as ledger


def _summary(graph: dict) -> str:
    facts = {f["id"]: f for f in graph.get("derived_facts", [])}
    parts = []
    if graph.get("source_attestation") == "client_supplied_not_provider_verified":
        parts.append("These observations came from an enrolled client; source authenticity is not independently verified.")
    if "fact:order_status" in facts:
        parts.append("Reported order status: " + str(facts["fact:order_status"]["value"]) + ".")
    if "fact:provider_reports_delivered" in facts:
        parts.append("The source reports delivery complete; personal receipt is unconfirmed.")
    if "fact:provider_eta_seconds" in facts:
        seconds = int(facts["fact:provider_eta_seconds"]["value"])
        parts.append("Reported ETA is " + str(abs(seconds) // 60) +
                     (" minute(s) from now." if seconds >= 0 else " minute(s) in the past."))
    if "fact:deadline_margin_seconds" in facts:
        seconds = int(facts["fact:deadline_margin_seconds"]["value"])
        parts.append("Reported ETA is " + str(abs(seconds) // 60) +
                     (" minute(s) before your deadline." if seconds >= 0 else " minute(s) after your deadline."))
    if "fact:courier_stationary" in facts:
        parts.append("Courier telemetry reports stationary for at least three minutes.")
    if "fact:route_disruption" in facts:
        parts.append("Route report: " + str(facts["fact:route_disruption"]["value"])[:120] + ".")
    if "fact:delay_correlation" in facts:
        parts.append("Matching-route evidence is consistent with a traffic delay; cause remains unproven.")
    if not graph.get("fresh_observation_kinds"):
        parts.append("There are no fresh recognized observations. Current status is unknown.")
    if graph.get("observations_truncated_to_recent"):
        parts.append("This status uses the 100 most recent retained observations.")
    return " ".join(parts)


def answer(text: str) -> str | None:
    """Return None for unrelated language, an answer for exact graph queries."""
    stripped = re.sub(r"^jarvis[, ]+", "", text.strip(), flags=re.IGNORECASE)
    q = " ".join(stripped.lower().strip(" ?.!" ).split())
    if q in {"reality graph missions", "my reality graph missions",
             "show reality graph missions", "show my reality graph missions"}:
        try:
            missions = ledger.list_active()
        except ledger.GraphUnavailable as exc:
            return str(exc)
        if not missions:
            return "No active enrolled Reality Graph missions."
        return "Active missions: " + "; ".join(
            m["id"] + " — " + m["goal"][:90] for m in missions)

    exact = re.fullmatch(
        r"(?:reality graph|graph mission) (rg_[0-9a-f]{24})(?: (.*))?", q
    )
    question = ""
    mid = None
    if exact:
        mid, remainder = exact.groups()
        candidate = (remainder or "status").strip()
        if candidate in {"status", "summary", "what's happening", "what is happening"}:
            question = ""
        elif candidate in {"is it late", "will it be late", "why is it delayed",
                           "has it arrived", "is it delivered", "was it delivered"}:
            question = candidate
        else:
            return "I have no deterministic rule for that mission question."
    else:
        delivery_questions = {
            "has my delivery arrived": "has it arrived",
            "is my delivery here": "has it arrived",
            "is my delivery late": "is it late",
            "will my delivery be late": "will it be late",
            "why is my delivery delayed": "why is it delayed",
            "what is happening with my delivery": "",
            "how is my delivery": "",
        }
        if q not in delivery_questions:
            return None
        question = delivery_questions[q]
        try:
            matches = [m for m in ledger.list_active()
                       if any(word in m["goal"].lower()
                              for word in ("deliver", "dinner", "food", "courier"))]
        except ledger.GraphUnavailable as exc:
            return str(exc)
        if not matches:
            return "No active enrolled delivery mission. I cannot infer courier status from a camera catalog."
        if len(matches) > 1:
            return "There are several active delivery missions. Ask for an exact mission ID."
        mid = matches[0]["id"]

    try:
        result = ledger.snapshot(mid, question=question)
    except (KeyError, ValueError, ledger.GraphUnavailable) as exc:
        return "Reality Graph mission unavailable: " + str(exc)[:160]
    if question:
        if result["answer"] is not None:
            suffix = (" Source labels are client supplied, not independently authenticated."
                      if result["graph"].get("source_attestation") else "")
            return result["answer"]["answer"] + suffix
        return "Not enough fresh, linked observations to answer that reliably. " + _summary(result["graph"])
    return _summary(result["graph"])
