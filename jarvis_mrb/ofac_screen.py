from __future__ import annotations

"""Local candidate screening against one official OFAC SDN CSV export.

Download the whole list; names/claims/matter references are never transmitted
to OFAC. Candidate name coincidence IS NOT a sanctions determination.
"""

import csv
from datetime import datetime, timezone
import hashlib
import io
import re
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit
from typing import Any

import httpx

SDN_EXPORT = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
OFAC_DOCS = "https://ofac.treasury.gov/sanctions-list-service"
MAX_FILE_BYTES = 25_000_000
_MAX_AGE_SECONDS = 86400
_lock = Lock()
_snapshot: tuple[float, dict[str, Any]] | None = None
_ALLOWED_FINAL_HOSTS = {
    "sanctionslistservice.ofac.treas.gov",
    "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
}


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def _parse_sdn_csv(body: bytes, *, retrieved_at: str) -> dict[str, Any]:
    decoded = body.decode("utf-8-sig", errors="replace")
    by_name: dict[str, list[dict[str, str]]] = {}
    count = 0
    for row in csv.reader(io.StringIO(decoded)):
        if len(row) < 3 or not row[0].strip().isdigit():
            continue
        name = row[1].strip()
        kind = row[2].strip()
        key = _normalize_name(name)
        if not key:
            continue
        count += 1
        by_name.setdefault(key, []).append({
            "sdn_id": row[0].strip()[:40], "published_name": name[:200],
            "published_type": kind[:70],
        })
    if count < 100:
        raise ValueError("OFAC export did not contain a plausible SDN dataset.")
    return {
        "retrieved_at": retrieved_at,
        "sha256": hashlib.sha256(body).hexdigest(),
        "record_count": count, "by_name": by_name,
    }


def _download() -> dict[str, Any]:
    global _snapshot
    now = monotonic()
    with _lock:
        previous = _snapshot
        if previous and now - previous[0] < _MAX_AGE_SECONDS:
            return previous[1]
    with httpx.Client(timeout=httpx.Timeout(30, connect=5), follow_redirects=True) as client:
        with client.stream(
            "GET", SDN_EXPORT,
            headers={"User-Agent": "JarvisForMRB/0.13 (local OFAC CSV review)", "Accept": "text/csv,*/*"},
        ) as response:
            response.raise_for_status()
            parts = urlsplit(str(response.url))
            if parts.scheme != "https" or (parts.hostname or "").lower() not in _ALLOWED_FINAL_HOSTS:
                raise ValueError("OFAC export redirected to unapproved host.")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_FILE_BYTES:
                    raise ValueError("OFAC SDN file exceeded configured bound.")
    result = _parse_sdn_csv(bytes(body), retrieved_at=datetime.now(timezone.utc).isoformat())
    with _lock:
        _snapshot = (monotonic(), result)
    return result


def screen_exact_name(name: str) -> dict[str, Any]:
    if not 2 <= len(name.strip()) <= 200:
        raise ValueError("Name must contain 2–200 characters.")
    dataset = _download()
    candidates = dataset["by_name"].get(_normalize_name(name), [])[:20]
    return {
        "status": "review_candidates" if candidates else "no_exact_name_candidate_in_this_file",
        "queried_name": name.strip(),
        "candidates": candidates,
        "source_url": OFAC_DOCS,
        "dataset": "Official OFAC SDN primary-name CSV only",
        "dataset_sha256": dataset["sha256"],
        "dataset_retrieved_at": dataset["retrieved_at"],
        "record_count": dataset["record_count"],
        "source_note": (
            "A name coincidence is NOT an identity confirmation or legal conclusion. "
            "A nonmatch is NOT sanctions clearance: aliases, transliteration, "
            "non-SDN lists, indirect ownership including OFAC's 50 Percent Rule, "
            "other blocked interests and publication changes are NOT screened. "
            "Verify candidates using full identifying particulars and counsel."
        ),
    }
