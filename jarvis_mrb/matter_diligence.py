from __future__ import annotations

"""Local, matter-isolated SEC diligence registry and explicit numeric claims.

No project names, uploaded documents, asserted values, or matter identifiers
are transmitted to SEC. This is an evidence review aid, not a legal opinion.
"""

from datetime import datetime, timezone
import json
import re
import sqlite3
import uuid
from typing import Any

import jarvis_mrb.world_model as world_model
from jarvis_mrb.public_diligence import (
    compare_explicit_claim,
    fetch_company_fact,
    fetch_company_filings,
    normalize_cik,
)

_SCOPE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _db() -> sqlite3.Connection:
    world_model.APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(world_model.APP_DIR / "matter_diligence.sqlite3", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS matters (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            project_entity_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS matter_issuers (
            matter_id TEXT NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
            cik TEXT NOT NULL,
            asserted_name TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            PRIMARY KEY(matter_id,cik)
        );
        CREATE TABLE IF NOT EXISTS numeric_claims (
            id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            cik TEXT NOT NULL,
            taxonomy TEXT NOT NULL,
            tag TEXT NOT NULL,
            unit TEXT NOT NULL,
            value REAL NOT NULL,
            end TEXT NOT NULL,
            start TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            context TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id,cik) REFERENCES matter_issuers(matter_id,cik)
        );
        CREATE INDEX IF NOT EXISTS idx_matter_claims ON numeric_claims(matter_id,cik);
        """
    )
    return conn


def _date() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_matter(label: str, *, project_entity_id: str = "") -> dict[str, Any]:
    if not 1 <= len(label.strip()) <= 140:
        raise ValueError("Matter label must contain 1–140 characters.")
    # A project relationship must be explicitly selected; do not auto-link
    # entities from corporate names, calendar participants or private contacts.
    if project_entity_id and (
        len(project_entity_id) > 150 or not world_model.get_entity(project_entity_id)
    ):
        raise ValueError("Selected world project/entity ID does not exist.")
    uid = uuid.uuid4().hex
    with _db() as conn:
        conn.execute(
            "INSERT INTO matters(id,label,project_entity_id,created_at) VALUES(?,?,?,?)",
            (uid, label.strip(), project_entity_id, _date()),
        )
        conn.commit()
    return {"id": uid, "label": label.strip(), "project_entity_id": project_entity_id}


def add_issuer(matter_id: str, cik: str, asserted_name: str) -> dict[str, Any]:
    if not _SCOPE.fullmatch(matter_id):
        raise ValueError("Invalid matter ID.")
    cik = normalize_cik(cik)
    if not 1 <= len(asserted_name.strip()) <= 200:
        raise ValueError("Company name must contain 1–200 characters.")
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM matters WHERE id=?", (matter_id,)).fetchone():
            raise ValueError("Unknown matter.")
        conn.execute(
            """INSERT INTO matter_issuers(matter_id,cik,asserted_name,registered_at)
            VALUES(?,?,?,?)
            ON CONFLICT(matter_id,cik) DO UPDATE SET asserted_name=excluded.asserted_name""",
            (matter_id, cik, asserted_name.strip(), _date()),
        )
        conn.commit()
    return {
        "matter_id": matter_id, "cik": cik,
        "asserted_name": asserted_name.strip(),
        "note": "CIK is user-confirmed; no fuzzy name-to-entity inference.",
    }


def get_matter(matter_id: str) -> dict[str, Any]:
    if not _SCOPE.fullmatch(matter_id):
        raise ValueError("Invalid matter ID.")
    with _db() as conn:
        m = conn.execute("SELECT * FROM matters WHERE id=?", (matter_id,)).fetchone()
        if not m:
            raise ValueError("Unknown matter.")
        issuers = conn.execute(
            "SELECT * FROM matter_issuers WHERE matter_id=? ORDER BY registered_at",
            (matter_id,),
        ).fetchall()
        claims = conn.execute(
            "SELECT * FROM numeric_claims WHERE matter_id=? ORDER BY created_at",
            (matter_id,),
        ).fetchall()
    result = {
        "id": m["id"], "label": m["label"],
        "project_entity_id": m["project_entity_id"],
        "issuers": [dict(x) for x in issuers],
        "claims": [dict(x) for x in claims],
    }
    project_id = result["project_entity_id"]
    if project_id:
        from jarvis_mrb.world_terms import project_terms
        result["existing_world_terms"] = project_terms(project_id)
        result["world_terms_note"] = (
            "Transaction terms are displayed as separate, dated, source-linked "
            "statements. They are not automatically equivalent to SEC concepts."
        )
    return result


def add_numeric_claim(
    matter_id: str,
    cik: str,
    *,
    taxonomy: str,
    tag: str,
    unit: str,
    value: float,
    end: str,
    source_ref: str,
    start: str = "",
    context: str = "",
) -> dict[str, Any]:
    if not _SCOPE.fullmatch(matter_id):
        raise ValueError("Invalid matter ID.")
    cik = normalize_cik(cik)
    if not 1 <= len(source_ref.strip()) <= 250:
        raise ValueError("Claim requires a specific document/source reference.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        raise ValueError("Claim end date must be YYYY-MM-DD.")
    if start and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
        raise ValueError("Claim start date must be YYYY-MM-DD.")
    import math
    if not math.isfinite(value):
        raise ValueError("Claim value must be finite.")
    if taxonomy not in {"us-gaap", "ifrs-full", "dei"} or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,100}", tag):
        raise ValueError("Invalid SEC XBRL taxonomy or concept tag.")
    if unit not in {"USD", "shares", "pure"}:
        raise ValueError("Unsupported fact unit.")
    item = {
        "id": uuid.uuid4().hex,
        "matter_id": matter_id, "cik": cik, "taxonomy": taxonomy,
        "tag": tag, "unit": unit, "value": value,
        "end": end, "start": start, "source_ref": source_ref.strip(),
        "context": context[:600], "created_at": _date(),
    }
    with _db() as conn:
        if not conn.execute(
            "SELECT 1 FROM matter_issuers WHERE matter_id=? AND cik=?",
            (matter_id, cik),
        ).fetchone():
            raise ValueError("Register the exact CIK within the matter first.")
        conn.execute(
            """INSERT INTO numeric_claims
            (id,matter_id,cik,taxonomy,tag,unit,value,end,start,source_ref,context,created_at)
            VALUES(:id,:matter_id,:cik,:taxonomy,:tag,:unit,:value,:end,:start,:source_ref,:context,:created_at)""",
            item,
        )
        conn.commit()
    return item


def check_matter(matter_id: str, *, claims: bool = True) -> dict[str, Any]:
    state = get_matter(matter_id)
    reports = []
    discrepancies = []
    for issuer in state["issuers"]:
        cik = issuer["cik"]
        try:
            response = fetch_company_filings(cik)
            # A differing registrant name is *not* necessarily a mismatch:
            # mergers, former names, subsidiaries and historical CIKs exist.
            name_review = (
                issuer["asserted_name"].casefold().strip()
                != response["registrant_name"].casefold().strip()
            )
            reports.append({
                "cik": cik, "status": "ok",
                "registrant_name": response["registrant_name"],
                "supplied_name": issuer["asserted_name"],
                "name_review_needed": name_review,
                "name_review_note": (
                    "Different names need entity-history review; no automatic adverse conclusion."
                    if name_review else ""
                ),
                "filings": response["filings"],
                "source_url": response["source_url"],
                "source_note": response["source_note"],
            })
        except Exception as exc:
            reports.append({
                "cik": cik, "status": "unavailable",
                "reason": str(exc)[:240], "filings": [],
            })
    if claims:
        for claim in state["claims"][:30]:
            try:
                concept = fetch_company_fact(
                    claim["cik"], taxonomy=claim["taxonomy"], tag=claim["tag"],
                    unit=claim["unit"],
                )
                comparison = compare_explicit_claim(
                    claim_value=claim["value"], claim_end=claim["end"],
                    claim_start=claim["start"], claim_unit=claim["unit"],
                    concept_result=concept,
                )
            except Exception as exc:
                comparison = {
                    "status": "unavailable",
                    "reason": "SEC XBRL check failed: " + type(exc).__name__,
                }
            result = {
                "claim_id": claim["id"], "source_ref": claim["source_ref"],
                "concept": claim["taxonomy"] + "/" + claim["tag"],
                "comparison": comparison,
                "sec_source": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
            }
            discrepancies.append(result)
    return {
        "status": "ok" if reports and all(r["status"] == "ok" for r in reports) else "partial",
        "matter_id": matter_id,
        "issuer_checks": reports, "claim_checks": discrepancies,
        "checked_at": _date(),
        "scope_note": (
            "Matter and document contents remain in local matter-isolated storage. "
            "Only exact CIKs and explicit SEC taxonomy/concepts are sent externally. "
            "An absent filing, empty public result, or number disagreement does not "
            "establish compliance, wrongdoing, or a breached representation."
        ),
    }
