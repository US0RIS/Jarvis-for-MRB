"""User-stated facts and corrections on world entities (criteria.md C03).

A fact the user states or corrects is stored as a belief whose source event is
``user_statement`` / ``user_correction``, with confidence 1.0, so it is always
distinguishable from inferred or provider-observed beliefs.  A correction
supersedes the prior current value but never deletes it: the history, the old
source and any disputed alternatives stay inspectable.  Entity resolution is
exact (canonical name or alias); ambiguity is reported, never guessed.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from typing import Any

import jarvis_mrb.world_model as world_model

_USER_SOURCES = {"user_statement", "user_correction"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _predicate(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", _norm(text)).strip("_")
    if not value or len(value) > 80:
        raise ValueError("Attribute name must be 1-80 letters/numbers.")
    return value


def find_entities(name: str) -> list[dict[str, Any]]:
    wanted = _norm(name)
    if not wanted:
        return []
    conn = sqlite3.connect(world_model.DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    with closing(conn):
        rows = conn.execute(
            """SELECT DISTINCT e.id,e.kind,e.canonical_name FROM entities e
               LEFT JOIN aliases a ON a.entity_id=e.id
               WHERE e.normalized_name=? OR a.normalized_alias=?
               ORDER BY e.last_seen_at DESC LIMIT 10""",
            (wanted, wanted),
        ).fetchall()
    return [{"id": str(r["id"]), "kind": str(r["kind"]), "name": str(r["canonical_name"])} for r in rows]


def _resolve(name: str, *, kind: str = "", create: bool = False) -> dict[str, Any]:
    matches = find_entities(name)
    if kind:
        matches = [m for m in matches if m["kind"] == _norm(kind).replace(" ", "_")] or matches
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"{name!r} matches more than one thing I track ("
            + "; ".join(f"{m['kind']} {m['name']}" for m in matches[:5])
            + "). Say which one, e.g. 'the project " + str(name) + "'."
        )
    if not create:
        raise ValueError(f"I don't have anything recorded as {name!r}.")
    entity_id = world_model.ensure_entity(kind or "thing", name)
    return {"id": entity_id, "kind": _norm(kind or "thing").replace(" ", "_"), "name": name.strip()}


def remember(name: str, attribute: str, value: str, *, kind: str = "", correction: bool = False) -> dict[str, Any]:
    predicate = _predicate(attribute)
    clean_value = " ".join(str(value or "").split())[:1000]
    if not clean_value:
        raise ValueError("A fact needs a value.")
    entity = _resolve(name, kind=kind, create=not correction)
    current = [
        b for b in (world_model.get_entity(entity["id"]) or {}).get("beliefs") or []
        if b["predicate"] == predicate
    ]
    source_kind = "user_correction" if correction else "user_statement"
    event_id = world_model.record_event(
        "world.user_correction" if correction else "world.user_fact",
        f"User {'corrected' if correction else 'stated'}: {entity['name']} {attribute} = {clean_value}",
        source_kind=source_kind,
        source_ref=f"{entity['id']}:{predicate}",
        payload={"entity_id": entity["id"], "predicate": predicate, "value": clean_value,
                 "previous": [{"value": b["value"], "source_event_id": b["source_event_id"],
                               "observed_at": b["observed_at"]} for b in current]},
        evidence="Direct user statement in conversation; authoritative over inference, recorded with its prior values.",
        confidence=1.0,
        participants=[(entity["id"], "subject", 1.0), (world_model.SELF_ID, "asserter", 1.0)],
    )
    belief_id = world_model.assert_belief(
        entity["id"], predicate, value=clean_value, source_event_id=event_id, confidence=1.0,
        evidence=f"{source_kind}: user said so",
    )
    return {"entity": entity, "predicate": predicate, "value": clean_value, "belief_id": belief_id,
            "event_id": event_id, "replaced": [b["value"] for b in current if str(b["value"]) != clean_value]}


def describe(name: str) -> dict[str, Any]:
    entity = _resolve(name)
    conn = sqlite3.connect(world_model.DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    with closing(conn):
        beliefs = conn.execute(
            """SELECT b.predicate,b.value_json,b.object_id,b.state,b.observed_at,b.confidence,
                      e.source_kind,e.source_ref,e.event_type
               FROM beliefs b LEFT JOIN events e ON e.id=b.source_event_id
               WHERE b.subject_id=? ORDER BY b.predicate, b.id DESC LIMIT 200""",
            (entity["id"],),
        ).fetchall()
        sources = conn.execute(
            """SELECT DISTINCT e.source_kind FROM event_entities x JOIN events e ON e.id=x.event_id
               WHERE x.entity_id=? LIMIT 50""", (entity["id"],)
        ).fetchall()
        external = conn.execute("SELECT namespace FROM external_ids WHERE entity_id=?", (entity["id"],)).fetchall()
    facts: dict[str, dict[str, Any]] = {}
    for row in beliefs:
        item = facts.setdefault(str(row["predicate"]), {"current": None, "disputed": [], "history": []})
        value = world_model._loads(row["value_json"], None) if row["value_json"] is not None else row["object_id"]
        origin = "you said" if row["source_kind"] in _USER_SOURCES else (
            f"observed via {row['source_kind']}" if row["source_kind"] else "inferred")
        record = {"value": value, "origin": origin, "source": row["source_kind"] or "", "observed_at": row["observed_at"],
                  "corrected_by_user": row["source_kind"] == "user_correction", "state": row["state"]}
        if row["state"] == "current" and item["current"] is None:
            item["current"] = record
        elif row["state"] == "disputed":
            item["disputed"].append(record)
        else:
            item["history"].append(record)
    return {"entity": entity, "facts": facts,
            "sources": sorted({str(r[0]) for r in sources} | {f"id:{r[0]}" for r in external})}


def describe_text(name: str) -> str:
    info = describe(name)
    entity = info["entity"]
    lines = []
    for predicate, item in sorted(info["facts"].items()):
        current = item["current"]
        if current is None:
            continue
        text = f"{predicate.replace('_', ' ')}: {current['value']} ({current['origin']}, {current['observed_at'][:16]})"
        if item["disputed"]:
            text += "; conflicting: " + ", ".join(
                f"{d['value']} ({d['origin']})" for d in item["disputed"][:3])
        superseded = [h for h in item["history"] if h["value"] != current["value"]][:2]
        if superseded:
            text += "; previously " + ", ".join(f"{h['value']} ({h['origin']})" for h in superseded)
        lines.append(text)
    header = f"{entity['name']} ({entity['kind']}), seen in: {', '.join(info['sources']) or 'no linked sources'}."
    if not lines:
        return header + " I have no recorded attributes for it."
    return header + " " + " | ".join(lines[:15]) + "."
