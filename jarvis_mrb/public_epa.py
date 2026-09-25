from __future__ import annotations

"""Official EPA ECHO facility snapshot by user-confirmed FRS registry ID.

Facilities are not companies: this does not infer parent/subsidiary ownership.
"""

from datetime import datetime, timezone
import re
from typing import Any

import httpx

_EPA = "https://echogeo.epa.gov/arcgis/rest/services/ECHO/Facilities/MapServer/0/query"
_DOCS = "https://echo.epa.gov/tools/web-services"
_MAX = 1_500_000
_FIELDS = (
    "REGISTRY_ID,FAC_NAME,FAC_STREET,FAC_CITY,FAC_STATE,"
    "FAC_ACTIVE_FLAG,FAC_INSPECTION_COUNT,FAC_FORMAL_ACTION_COUNT,"
    "FAC_TOTAL_PENALTIES,FAC_QTRS_IN_NC,FAC_CURR_COMPLIANCE_STATUS,"
    "FAC_CURR_SNC_FLG,DFR_URL"
)


def normalize_frs(value: str) -> str:
    v = str(value).strip()
    if not re.fullmatch(r"\d{12}", v):
        raise ValueError("EPA FRS registry ID must contain exactly 12 digits.")
    return v


def fetch_epa_facility(frs_id: str) -> dict[str, Any]:
    frs_id = normalize_frs(frs_id)
    checked = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=httpx.Timeout(14), follow_redirects=False) as client:
        with client.stream(
            "GET", _EPA,
            params={
                "where": "REGISTRY_ID='" + frs_id + "'",
                "outFields": _FIELDS,
                "returnGeometry": "false",
                "resultRecordCount": 5,
                "f": "json",
            },
            headers={"User-Agent": "JarvisForMRB/0.13 (public EPA facility review)", "Accept": "application/json"},
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > _MAX:
                    raise ValueError("EPA result exceeded size bound.")
    raw = __import__("json").loads(data)
    if not isinstance(raw, dict) or "error" in raw:
        raise ValueError("EPA returned an error response.")
    records = raw.get("features")
    if not isinstance(records, list):
        raise ValueError("EPA returned an unexpected facility structure.")
    matches: list[dict[str, Any]] = []
    for item in records:
        attr = item.get("attributes") if isinstance(item, dict) else None
        if not isinstance(attr, dict) or str(attr.get("REGISTRY_ID") or "") != frs_id:
            continue
        matches.append({
            "frs_id": frs_id,
            "facility_name": str(attr.get("FAC_NAME") or "")[:200],
            "address": " ".join(str(attr.get(k) or "") for k in
                              ("FAC_STREET", "FAC_CITY", "FAC_STATE")).strip()[:350],
            "active_flag": attr.get("FAC_ACTIVE_FLAG"),
            "inspection_count": attr.get("FAC_INSPECTION_COUNT"),
            "formal_action_count": attr.get("FAC_FORMAL_ACTION_COUNT"),
            "total_penalties": attr.get("FAC_TOTAL_PENALTIES"),
            "quarters_noncompliance": attr.get("FAC_QTRS_IN_NC"),
            "reported_current_compliance_status": attr.get("FAC_CURR_COMPLIANCE_STATUS"),
            "reported_significant_noncompliance": attr.get("FAC_CURR_SNC_FLG"),
            "detail_url": (
                str(attr.get("DFR_URL"))
                if str(attr.get("DFR_URL") or "").startswith("https://echo.epa.gov/")
                else ""
            ),
        })
    return {
        "status": "ok" if matches else "no_record_for_exact_frs_id",
        "frs_id": frs_id, "facilities": matches,
        "checked_at": checked, "source_url": _EPA,
        "source_note": (
            "Official EPA ECHO geospatial facility layer; exact user-confirmed "
            "FRS site ID. Historical enforcement counts and current compliance "
            "labels depend on program, reporting window, source refresh and "
            "facility-program matching. A missing result is not clearance or "
            "proof the company owns no regulated facilities."
        ),
        "documentation": _DOCS,
    }
