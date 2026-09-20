from __future__ import annotations

"""Official EDGAR read model. Exact user-supplied CIK; no private name lookup.

Use only on non-confidential matters or with appropriate client authorization.
The matter/project identifier and private claims are never sent to SEC.
"""

from datetime import datetime, timezone
import os
import re
from typing import Any
import httpx

_SEC_DOCS = "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
_SEC_BASE = "https://data.sec.gov"
_MAX = 4_000_000
_ALLOWED_FORMS = {"8-K", "10-K", "10-Q", "20-F", "6-K", "S-1", "SC 13D", "SC 13G", "DEF 14A", "4", "3", "5"}


def normalize_cik(value: str | int) -> str:
    raw = str(value).strip()
    if not re.fullmatch(r"\d{1,10}", raw):
        raise ValueError("SEC CIK must contain 1–10 digits.")
    return raw.zfill(10)


def _headers() -> dict[str, str]:
    agent = os.environ.get("JARVIS_SEC_USER_AGENT", "").strip()
    if not agent or len(agent) < 12 or "@" not in agent or "\n" in agent or "\r" in agent:
        raise ValueError(
            "Set JARVIS_SEC_USER_AGENT to an identifying app name and contact email "
            "before accessing the SEC API (e.g. JarvisPersonal contact@example.com)."
        )
    return {"User-Agent": agent, "Accept": "application/json"}


def _get(path: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(12.0), follow_redirects=False) as client:
        with client.stream("GET", _SEC_BASE + path, headers=_headers()) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > _MAX:
                    raise ValueError("SEC response exceeded allowed size.")
    raw = __import__("json").loads(data)
    if not isinstance(raw, dict):
        raise ValueError("SEC response is not a JSON object.")
    return raw


def fetch_company_filings(cik: str | int, *, limit: int = 15) -> dict[str, Any]:
    canonical = normalize_cik(cik)
    limit = max(1, min(int(limit), 40))
    data = _get("/submissions/CIK" + canonical + ".json")
    if str(data.get("cik") or "").zfill(10) != canonical:
        raise ValueError("SEC returned a different CIK.")
    recent = (data.get("filings") or {}).get("recent") or {}
    if not isinstance(recent, dict):
        raise ValueError("SEC response missing recent filings.")
    forms = recent.get("form") or []
    if not isinstance(forms, list):
        raise ValueError("SEC filing forms have unexpected format.")
    def column(name: str, i: int) -> str:
        values = recent.get(name)
        return str(values[i] or "") if isinstance(values, list) and i < len(values) else ""

    results: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        if not isinstance(form, str):
            continue
        accession = column("accessionNumber", i)
        filed = column("filingDate", i)
        document = column("primaryDocument", i)
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", document):
            document = ""
        archive = (
            "https://www.sec.gov/Archives/edgar/data/"
            + str(int(canonical)) + "/" + accession.replace("-", "") + "/"
            + document
        ) if document else ""
        results.append({
            "accession": accession, "form": form[:35], "filed": filed,
            "document_url": archive,
            "source_url": "https://data.sec.gov/submissions/CIK" + canonical + ".json",
        })
        if len(results) >= limit:
            break
    return {
        "status": "ok", "cik": canonical,
        "registrant_name": str(data.get("name") or "")[:240],
        "tickers": [str(x)[:25] for x in (data.get("tickers") or [])[:20]],
        "filings": results, "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_url": _SEC_DOCS,
        "source_note": (
            "Exact CIK, SEC registrant submissions metadata, not a private-company "
            "registry or a comprehensive legal-entity/affiliate search. A new filing "
            "does not by itself contradict a negotiated agreement."
        ),
    }


def fetch_company_fact(
    cik: str | int,
    *,
    taxonomy: str,
    tag: str,
    unit: str = "USD",
    limit: int = 20,
) -> dict[str, Any]:
    canonical = normalize_cik(cik)
    if taxonomy not in {"us-gaap", "ifrs-full", "dei"} or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,100}", tag):
        raise ValueError("Unsupported SEC taxonomy or concept tag.")
    if unit not in {"USD", "shares", "pure"}:
        raise ValueError("Unsupported SEC unit.")
    data = _get("/api/xbrl/companyconcept/CIK" + canonical + "/" + taxonomy + "/" + tag + ".json")
    if str(data.get("cik") or "").zfill(10) != canonical:
        raise ValueError("SEC fact response has a mismatched CIK.")
    points = ((data.get("units") or {}).get(unit) or [])
    if not isinstance(points, list):
        raise ValueError("SEC facts contain unexpected units.")
    results = []
    for p in points:
        if not isinstance(p, dict) or not isinstance(p.get("val"), (int, float)):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(p.get("end") or "")):
            continue
        results.append({
            "value": p["val"], "end": p["end"],
            "start": str(p.get("start") or ""),
            "filed": str(p.get("filed") or ""),
            "form": str(p.get("form") or ""),
            "accession": str(p.get("accn") or ""),
            "frame": str(p.get("frame") or ""),
        })
    results.sort(key=lambda x: (x["end"], x["filed"], x["accession"]), reverse=True)
    return {
        "status": "ok", "cik": canonical,
        "concept": taxonomy + "/" + tag, "unit": unit,
        "registrant_name": str(data.get("entityName") or "")[:240],
        "facts": results[:max(1, min(int(limit), 50))],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_url": _SEC_DOCS,
        "source_note": (
            "Companyconcept facts retain unit, period, filing, and accession. "
            "Do not compare instantaneous balances with duration flows or different "
            "reporting periods, entities, currencies, accounting bases or amendments."
        ),
    }


def compare_explicit_claim(
    *,
    claim_value: float,
    claim_end: str,
    claim_unit: str,
    concept_result: dict[str, Any],
) -> dict[str, Any]:
    """Flag only an exact period/unit candidate; never decide a legal contradiction."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", claim_end):
        raise ValueError("Claim end date must be YYYY-MM-DD.")
    if claim_unit != concept_result.get("unit"):
        return {"status": "not_comparable", "reason": "Unit mismatch."}
    equal_period = [p for p in concept_result.get("facts") or [] if p.get("end") == claim_end]
    if not equal_period:
        return {"status": "not_comparable", "reason": "No fact found for same period end."}
    latest = max(equal_period, key=lambda p: (p.get("filed") or "", p.get("accession") or ""))
    actual = float(latest["value"])
    tolerance = max(0.01, abs(actual) * 0.000001)
    return {
        "status": "candidate_discrepancy" if abs(actual - claim_value) > tolerance else "numeric_agreement",
        "asserted": claim_value, "reported": actual,
        "period_end": claim_end, "unit": claim_unit,
        "filing": latest,
        "reason": (
            "Numerical comparison for explicitly selected concept/period/unit only; "
            "human review of context, accounting policy, restatements and legal "
            "significance required. Not a finding of misrepresentation."
        ),
    }
