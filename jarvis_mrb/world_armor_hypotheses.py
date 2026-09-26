from __future__ import annotations

"""Deterministic evidence graph and hypothesis reports for World Armor Phase 2.

Hypotheses are derived labels over retained observations. They are not facts,
predictions, accusations, causal conclusions, action grants, or model output.
"""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from jarvis_mrb.world_armor_correlate import correlate
from jarvis_mrb.world_armor_phase1 import _clock, _require_enabled, replay

_MAX_HYPOTHESES = 60
_MAX_EDGES = 240


def _stable_id(prefix: str, *parts: str) -> str:
    digest=sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _node(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": observation["id"],
        "source": observation["source"],
        "kind": observation["kind"],
        "observed_at": observation["observed_at"],
        "received_at": observation["received_at"],
        "revision": observation["revision"],
        "lineage": observation["lineage"],
        "geometry_basis": observation["geometry_basis"],
        "adapter_mode": observation.get("adapter_mode", "unknown"),
        "sample_coverage_status": observation.get("sample_coverage_status","unknown"),
        "sample_coverage_checked_at": observation.get("sample_coverage_checked_at"),
        "values": observation["values"],
    }


def build_evidence_graph(
    investigation_id: str, *, start_at: str, end_at: str,
    as_known_at: str | None = None,
    source_ids: list[str] | None = None,
    query_radius_km: float | None = None,
    db_path: Path | None = None,
    now=None,
) -> dict[str, Any]:
    """Build inspectable typed edges and non-causal candidate hypotheses."""
    _require_enabled()
    instant=_clock(now)
    joined=correlate(
        investigation_id,
        start_at=start_at,
        end_at=end_at,
        as_known_at=as_known_at,
        source_ids=source_ids,
        query_radius_km=query_radius_km,
        db_path=db_path,
        now=instant,
    )
    replayed=replay(
        investigation_id,
        as_known_at=joined["as_known_at"],
        db_path=db_path,
        now=instant,
    )
    eligible_ids={
        item["id"] for item in joined["timed_observations"]
    } | {
        item["id"] for item in joined["receipt_time_only_observations"]
    } | {
        item["id"] for item in joined["spatially_indeterminate_observations"]
    }
    nodes=[_node(item) for item in replayed["observations"]
           if item["id"] in eligible_ids]
    node_ids={item["id"] for item in nodes}
    history={item["id"]:item for item in replayed.get("observation_history", [])}
    window_start=datetime.fromisoformat(joined["observation_window"]["start"])
    window_end=datetime.fromisoformat(joined["observation_window"]["end"])

    def in_requested_time(item: dict[str, Any]) -> bool:
        raw=item.get("observed_at") or item.get("received_at")
        return bool(raw and window_start <= datetime.fromisoformat(raw) <= window_end)

    edges: list[dict[str, Any]]=[]
    for revision in replayed["revisions"]:
        if revision["new_id"] not in eligible_ids:
            continue
        older=history.get(revision["supersedes_id"])
        if older is None or not in_requested_time(older):
            continue
        if older["id"] not in node_ids:
            prior=_node(older)
            prior["graph_role"]="source_revision_context"
            nodes.append(prior)
            node_ids.add(older["id"])
        # Every emitted edge is now traversable inside this bounded graph.
        edges.append({
            "id":_stable_id("edge","revision",
                            revision["supersedes_id"],revision["new_id"]),
            "type":"same_provider_revision",
            "from":revision["supersedes_id"],
            "to":revision["new_id"],
            "assertion":"Source-native record revision.",
            "causal":False,
        })
    hypotheses=[]
    for pair in joined["candidate_links"][:_MAX_HYPOTHESES]:
        first=pair["first_observation_id"]
        second=pair["second_observation_id"]
        edge_id=_stable_id("edge","temporal",first,second)
        edges.append({
            "id":edge_id,
            "type":"temporal_overlap",
            "from":first,
            "to":second,
            "separation_seconds":pair["separation_seconds"],
            "spatial_basis":pair["spatial_basis"],
            "physical_colocation_verified":False,
            "causal":False,
            "assertion":"Independent source reports occurred close in source time.",
        })
        hid=_stable_id("hyp",first,second,joined["query_id"])
        exact_spatial=("publisher_epicenter_within_selected_query_radius"
                       in pair["spatial_basis"])
        missing=[
            "independent evidence of mechanism or dependency",
            "a third independent source or repeated observation",
        ]
        if not exact_spatial:
            missing.insert(0,"compatible source-specific spatial footprints")
        hypotheses.append({
            "id":hid,
            "status":"candidate_unverified",
            "type":"cross_source_temporal_cooccurrence",
            "claim":(
                f"{pair['first_source']} and {pair['second_source']} each "
                f"reported a phenomenon within {pair['separation_seconds']} "
                "seconds in the selected investigation scope."
            ),
            "supporting_observation_ids":[first,second],
            "supporting_edge_ids":[edge_id],
            "contradicting_observation_ids":[],
            "independent_lineage_count":2,
            "spatial_precision":(
                "one_source_epicenter_filtered_other_source_scope_coarse"
                if exact_spatial else "query_scope_only"
            ),
            "assumptions":[
                "provider timestamps are sufficiently comparable for this query",
                "retained records are not a complete history of the world",
            ],
            "missing_evidence":missing,
            "alternative_explanations":[
                "chance temporal coincidence",
                "different physical footprints inside the selected query scope",
                "provider publication or observation latency",
                "a shared upstream condition not represented in retained evidence",
            ],
            "prohibited_conclusion":"No causal, wrongdoing, safety, identity, or action conclusion.",
        })
    nodes.sort(key=lambda x:(x["received_at"],x["source"],x["id"]))
    edges=edges[:_MAX_EDGES]
    unavailable=[
        source for source,state in joined["source_coverage"].items()
        if state.get("status")!="ok"
    ]
    return {
        "schema":"jarvis.world_armor.evidence_graph.v1",
        "investigation_id":investigation_id,
        "query_id":joined["query_id"],
        "query_plan":joined["query_plan"],
        "as_known_at":joined["as_known_at"],
        "observation_window":joined["observation_window"],
        "query_region":joined["query_region"],
        "nodes":nodes,
        "edges":edges,
        "hypotheses":hypotheses,
        "source_coverage":joined["source_coverage"],
        "unavailable_or_unchecked_sources":sorted(unavailable),
        "receipt_time_only_count":len(joined["receipt_time_only_observations"]),
        "degraded_observation_count":len(joined["degraded_observations"]),
        "spatially_indeterminate_count":len(
            joined["spatially_indeterminate_observations"]
        ),
        "causal_claims":0,
        "wrongdoing_claims":0,
        "identity_claims":0,
        "external_requests":0,
        "external_actions":0,
        "model_calls":0,
        "qualifier":(
            "Hypotheses organize retained evidence for inspection. They do not "
            "promote correlation to cause, prove shared physical location, "
            "identify a person, or authorize any action."
        ),
    }
