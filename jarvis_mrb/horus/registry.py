"""Traceability: every future.md idea -> the code that implements or evaluates it.

``kind`` values:

* ``implemented`` — a deterministic primitive in this package (or an existing
  module) implements the idea's software core.  Device/provider acceptance on the
  real Windows/iPhone/Pi hardware is still separate evidence (see
  ``reliability.capability_claim``); nothing here is an "observed deployed" claim.
* ``harness`` — the idea is "evaluate/benchmark X"; the measured harness and
  decision rule are implemented, the measurement must run on the real machine.
* ``catalog`` — an external repository recorded as a research candidate in
  ``radar.CATALOG`` with the primitive it could supply, plus the HORUS-side
  primitive that already covers the pattern.
* ``naming`` — vocabulary already defined in ``jarvis_mrb.names``.

References are ``module:attribute``; a bare module is relative to
``jarvis_mrb.horus``.  ``tests/test_horus_registry.py`` parses future.md and fails
if any idea is unmapped or any reference does not resolve.
"""
from __future__ import annotations

import importlib
from typing import Any

I, H, C, N = "implemented", "harness", "catalog", "naming"

IDEAS: dict[str, tuple[str, list[str]]] = {
    # ---- HORUS naming architecture
    "Kant": (N, ["jarvis_mrb.names:KANT", "jarvis_mrb.kant"]),
    "Carcosa": (N, ["jarvis_mrb.names:CARCOSA", "temporal:TemporalStore"]),
    "Ariadne": (N, ["jarvis_mrb.names:ARIADNE", "analysis:run_investigation"]),
    "Cassandra": (N, ["jarvis_mrb.names:CASSANDRA", "standing:StandingQueryEngine"]),
    "Mnemosyne": (N, ["jarvis_mrb.names:MNEMOSYNE", "memory:MemoryStore"]),
    "Cerberus": (N, ["jarvis_mrb.names:CERBERUS", "ethics:EmergencyAuthority"]),
    "Mercury": (N, ["jarvis_mrb.names:MERCURY", "attention:choose_channel"]),
    "Sisyphus": (N, ["jarvis_mrb.names:SISYPHUS", "reliability:propose_repair"]),
    # ---- Proactive / situational awareness
    "Push, don't pull, the pre-meeting brief.": (I, ["life_admin:brief_schedule"]),
    "Bind calendar events to exact Reality Lens coordinates.": (I, ["life_admin:bind_location", "life_admin:geofence_eta_alert"]),
    "Real-time Guardian alerting, not just read-only evidence.": (I, ["views:guardian_alerts", "standing:InvariantWatchdog"]),
    "Health-aware scheduling flags.": (I, ["life_admin:health_flags"]),
    "Indoor / place-of-context awareness.": (I, ["spatial:SemanticMap"]),
    # ---- Email / admin automation
    "Email triage + drafted replies awaiting approval.": (I, ["life_admin:triage_email"]),
    "Post-meeting action-item extraction → Life Fabric task creation.": (I, ["life_admin:extract_action_items"]),
    "Subscription/renewal and bill tracking from email receipts.": (I, ["life_admin:parse_receipt", "life_admin:renewal_deadlines"]),
    # ---- Interaction model / UX
    '"What can you do?" self-describing capability statement.': (I, ["capabilities:CapabilityBus"]),
    "Nearest-obligation glanceable HUD.": (I, ["life_admin:nearest_obligations"]),
    "Passive system status indicators.": (I, ["attention:status_indicators"]),
    "Action tray / quick-action palette.": (I, ["capabilities:CapabilityBus"]),
    'Explicit, guaranteed "stop talking" barge-in command.': (I, ["attention:BargeIn"]),
    "Named preset/loadout invocation.": (I, ["attention:LoadoutRunner"]),
    "Context-gated capability sets.": (I, ["attention:capability_allowed", "attention:CAPABILITY_GATES"]),
    "Command-center / world-model dashboard as a real destination view.": (I, ["views:command_center"]),
    "Gamified progress on mundane admin tasks.": (I, ["life_admin:progress"]),
    # ---- Severe weather
    "Ingest NWS Impact-Based Warnings (IBW) feeds.": (I, ["emergency:parse_ibw"]),
    "Ingest California Geological Survey (CGS) and USGS slope data.": (I, ["emergency:rainfall_threshold"]),
    "Local failover alerting.": (I, ["emergency:dispatch_failover", "emergency:ntfy_payload"]),
    # ---- Physical/sensor providers
    "More state DOT camera feeds": (I, ["providers:normalize_dot_cameras"]),
    "ALERTWildfire public camera network": (I, ["providers:wildfire_camera_observation"]),
    "Harbor/coastal webcams": (I, ["providers:is_webcam_stream", "providers:gateway_plan"]),
    "NOAA/NDBC marine buoy data": (I, ["providers:parse_ndbc"]),
    "PurpleAir / AirNow air-quality sensors": (I, ["providers:parse_purpleair", "providers:parse_airnow", "providers:pm25_to_aqi"]),
    "GTFS-realtime public transit feeds": (I, ["providers:gtfs_delays"]),
    "FAA NOTAMs": (I, ["providers:parse_notam"]),
    "Smart plugs/switches via HomeKit": (I, ["providers:HomeAssistantBus"]),
    "A second CrunchLabs-style bench sensor node": (I, ["providers:verify_sensor_report"]),
    # ---- Security hardening
    "Speaker verification for Conductor actions.": (I, ["ethics:speaker_gate"]),
    "Breach/exposure monitoring for your own enrolled accounts.": (I, ["ethics:new_breaches"]),
    "Stale OAuth/grant audit.": (I, ["ethics:stale_grants"]),
    "Post-action audit log.": (I, ["ethics:after_action_entry"]),
    "Unknown-tracker alerts.": (I, ["ethics:persistent_trackers"]),
    "Your own home-network security posture.": (I, ["ethics:new_lan_devices"]),
    # ---- Life admin & memory
    "Spending-anomaly detection against your own history.": (I, ["life_admin:spending_anomalies"]),
    "Contract/lease clause extraction.": (I, ["life_admin:extract_contract_clauses"]),
    "Vehicle maintenance tracking": (I, ["life_admin:vehicle_due"]),
    "Package/delivery correlation.": (I, ["life_admin:correlate_packages"]),
    'Ambient "remember this" voice capture': (I, ["memory:MemoryStore", "memory:EntityTagger"]),
    "Self-hosted backup/failover for your own services.": (I, ["reliability:backup_status"]),
    # ---- More scope
    "Meeting document freshness check.": (I, ["life_admin:document_freshness"]),
    "Trip timeline fusion.": (I, ["life_admin:trip_timeline"]),
    "General action-receipt capture.": (I, ["life_admin:ActionReceipts"]),
    "Evening wind-down summary.": (I, ["life_admin:evening_summary"]),
    "Opt-in family safety beacon.": (I, ["emergency:FamilyBeacon"]),
    # ---- Reality / intelligence / agency
    "Counterfactual Engine / Shadow Reality.": (I, ["analysis:simulate", "analysis:departure_time"]),
    "Reality Rewind / physical-world DVR.": (I, ["temporal:TemporalStore"]),
    "Reality Diff.": (I, ["temporal:TemporalStore", "standing:WebObservation"]),
    "World Assertions / desired-state controller.": (I, ["standing:evaluate_assertion", "standing:closed_loop_step",
                                                          "jarvis_mrb.desired_state"]),
    "Reality Compiler.": (I, ["standing:compile_intent"]),
    "Universal Object Interface.": (I, ["spatial:ObjectRegistry"]),
    "Spatial Bookmarks.": (I, ["memory:SpatialMemory"]),
    "Physical Ctrl-F.": (I, ["memory:SpatialMemory"]),
    "World Search.": (I, ["views:world_search"]),
    "Sensor-Fusion Superresolution.": (I, ["analysis:fuse_estimates"]),
    "Autonomous Investigation.": (I, ["analysis:run_investigation"]),
    "Physical Macros.": (I, ["spatial:learn_physical_macro"]),
    "Mission Mode.": (I, ["capabilities:Mission"]),
    "Closed-loop Outcome Mode.": (I, ["standing:closed_loop_step"]),
    # ---- Small ideas
    '"Why did you tell me this?"': (I, ["attention:InfoObject"]),
    "Attention budget.": (I, ["attention:AttentionBudget"]),
    "Observation TTLs.": (I, ["epistemics:FreshnessPolicy"]),
    "Confidence decay.": (I, ["epistemics:decayed_confidence"]),
    "Contradiction detector.": (I, ["epistemics:detect_contradictions"]),
    "Source reputation ledger.": (I, ["epistemics:SourceReputationLedger"]),
    "Coverage map.": (I, ["views:coverage_map"]),
    "Capability graph.": (I, ["capabilities:CapabilityBus"]),
    "Cost-aware sensing.": (I, ["capabilities:should_sense"]),
    "Model router by cognitive difficulty.": (I, ["capabilities:route_model", "jarvis_mrb.model_router"]),
    "Evidence snapshots.": (I, ["epistemics:freeze_evidence"]),
    "Uncertainty UI.": (I, ["epistemics:uncertainty_label"]),
    "One-command temporary watch.": (I, ["standing:compile_intent"]),
    "Follow-the-entity.": (I, ["standing:follow_entity"]),
    "Automatic watch retirement.": (I, ["standing:StandingQueryEngine"]),
    "Replayable automations.": (I, ["standing:replay_automation"]),
    "Failure rehearsal.": (I, ["reliability:DependencyMap"]),
    "Offline degradation plans.": (I, ["reliability:DependencyMap"]),
    "World-model garbage collection.": (I, ["temporal:TemporalStore"]),
    "Personal vocabulary/alias graph.": (I, ["temporal:AliasGraph"]),
    "Teach-by-correction.": (I, ["temporal:TemporalStore", "temporal:AliasGraph"]),
    "Temporal questions as a first-class query language.": (I, ["temporal:TemporalStore"]),
    "World-model bookmarks in conversation.": (I, ["temporal:TemporalStore"]),
    "Reality Graph debugger.": (I, ["temporal:TemporalStore"]),
    # ---- Internet idea mining
    "Contextual Delivery / Follow-Me Information.": (I, ["attention:InfoObject", "attention:choose_channel"]),
    "Ambient Output Fabric.": (I, ["attention:choose_channel", "attention:CHANNELS"]),
    "Social Context Modes.": (I, ["attention:SOCIAL_MODES"]),
    "Temporary Delegated Capability.": (I, ["ethics:DelegationService"]),
    "Presence-as-Invocation.": (I, ["continuity:presence_invocation"]),
    "Conversation Handoff.": (I, ["continuity:Session"]),
    "Interruptibility as a primitive.": (I, ["attention:BargeIn"]),
    "Zero-Friction Capture Bus.": (I, ["memory:MemoryStore"]),
    "Capture Current Context Automatically.": (I, ["memory:MemoryStore"]),
    "Automatic Connection Discovery.": (I, ["memory:MemoryStore"]),
    "Memory Promotion Pipeline.": (I, ["memory:MemoryStore"]),
    "Memory Provenance + Revision.": (I, ["memory:MemoryStore", "temporal:TemporalStore"]),
    "Routine Learning Without Programming.": (I, ["automation:learn_routines", "memory:FrictionLog"]),
    "Counterfactual Automation Testing.": (I, ["standing:replay_automation"]),
    "Behavioral Automation Success Metrics.": (I, ["attention:NudgeMetrics"]),
    "Falsifiable Proactivity.": (I, ["attention:falsifiable"]),
    "Opportunity Detector.": (I, ["life_admin:opportunities"]),
    "Obligation Extraction.": (I, ["life_admin:ObligationGraph"]),
    "Auto-Resolving Tasks.": (I, ["standing:SelfResolvingTask"]),
    "Condition-Relative Recurrence.": (I, ["standing:ConditionRecurrence"]),
    "Preparation Engine.": (I, ["life_admin:prepare"]),
    "Reversible First Response.": (I, ["ethics:reversible_first_response"]),
    "Invariant Watchdog.": (I, ["standing:InvariantWatchdog"]),
    "Critical-Sensor Redundancy.": (I, ["standing:evaluate_assertion"]),
    "Failure-State Awareness.": (I, ["standing:evaluate_assertion"]),
    "Automation State Machines.": (I, ["standing:StateMachine"]),
    "State Restoration.": (I, ["standing:StateRestorer", "attention:LoadoutRunner"]),
    "Personalized Environment Profiles.": (I, ["continuity:resolve_environment"]),
    "World-Aware Media.": (I, ["continuity:MediaFollower"]),
    "Physical Status Vocabulary.": (I, ["attention:STATUS_VOCABULARY"]),
    "Multi-Modal Escalation Ladder.": (I, ["attention:EscalationLadder"]),
    "Personal Digital Twin for Mundane Work.": (I, ["capabilities:state_packet", "capabilities:context_preamble"]),
    "Local-First / Cloud-Escalation Router.": (I, ["capabilities:route_model"]),
    "Offline Capability Manifest.": (I, ["reliability:DependencyMap", "capabilities:CapabilityBus"]),
    "Self-Healing Integrations.": (I, ["reliability:detect_schema_drift", "reliability:propose_repair"]),
    "Automation Dependency Map.": (I, ["reliability:DependencyMap"]),
    "Physical Consequence Graph.": (I, ["analysis:ConsequenceGraph"]),
    "Useful Boredom Detector.": (I, ["life_admin:opportunities", "life_admin:free_gaps"]),
    "Micro-Opportunity Bundling.": (I, ["life_admin:opportunities"]),
    "Personal Friction Miner.": (I, ["memory:FrictionLog"]),
    '"Why isn\'t this automatic?" log.': (I, ["memory:FrictionLog"]),
    "Capability Gap Detection.": (I, ["memory:FrictionLog"]),
    "Feature-Idea Harvester.": (I, ["memory:FrictionLog"]),
    # ---- Attention, command
    "Attention Commander.": (I, ["attention:AttentionCommander"]),
    "Dynamic Common Operating Picture.": (I, ["views:dynamic_cop"]),
    "Information Triage Officer.": (I, ["attention:triage_score"]),
    "Decision Window Detection.": (I, ["attention:decision_window"]),
    "Operational Tempo.": (I, ["attention:operational_tempo"]),
    "Cognitive-Load Governor.": (I, ["attention:cognitive_load", "attention:choose_channel"]),
    "Sterile-Cockpit Mode.": (I, ["attention:Context", "attention:choose_channel"]),
    "Mode Annunciation.": (I, ["attention:ModeManager", "standing:StateMachine"]),
    "Automation Surprise Detector.": (I, ["attention:ModeManager"]),
    "Return-to-Manual Handoff.": (I, ["attention:ModeManager"]),
    # ---- Intelligence analysis
    "Analysis of Competing Hypotheses (ACH) Engine.": (I, ["analysis:ACHMatrix"]),
    "Key-Assumption Register.": (I, ["analysis:KeyAssumptionRegister"]),
    "Disconfirm-Me Mode.": (I, ["analysis:disconfirmation_queries"]),
    "Evidence Diagnosticity Scoring.": (I, ["analysis:ACHMatrix"]),
    "Information-Gain Planner.": (I, ["analysis:plan_next_observation"]),
    "Source Independence Graph.": (I, ["analysis:SourceIndependenceGraph"]),
    "Claim Lineage.": (I, ["epistemics:ClaimLineage"]),
    "Assumption Expiry.": (I, ["analysis:KeyAssumptionRegister"]),
    "Collection Plan Generator.": (I, ["analysis:collection_plan"]),
    "Investigation Stop Rule.": (I, ["analysis:should_stop"]),
    "Alternative-Explanation Prompt.": (I, ["analysis:alternative_explanations"]),
    "Analytic Confidence Calibration.": (I, ["analysis:ConfidenceCalibrator"]),
    # ---- Reliability
    "Jarvis Reliability SLOs.": (I, ["reliability:SLOTracker"]),
    "Capability Error Budgets.": (I, ["reliability:SLOTracker"]),
    "Automation Ownership Registry.": (I, ["reliability:AutomationRegistry"]),
    "Automation Maintenance Cost Meter.": (I, ["reliability:AutomationRegistry"]),
    "Runbook Compiler.": (I, ["reliability:compile_runbook"]),
    "Human-Fix Memory.": (I, ["reliability:HumanFixMemory"]),
    "Recurring-Failure Clustering.": (I, ["reliability:cluster_failures"]),
    "Known-Good State Snapshots.": (I, ["reliability:snapshot_diff"]),
    "Change-Correlation Engine.": (I, ["reliability:correlate_changes"]),
    "Canary Actions.": (I, ["reliability:progressive_rollout"]),
    "Progressive Rollout.": (I, ["reliability:progressive_rollout"]),
    "Automatic Rollback Contract.": (I, ["reliability:RollbackContract"]),
    "Chaos Jarvis.": (I, ["reliability:DependencyMap"]),
    "Graceful-Degradation Planner.": (I, ["reliability:DependencyMap"]),
    "Split-Brain Detector.": (I, ["reliability:detect_split_brain"]),
    "Eventual-Reconciliation Ledger.": (I, ["reliability:ReconciliationLedger"]),
    "Local Mesh Sync.": (I, ["reliability:ReconciliationLedger"]),
    "Long-Now Export.": (I, ["temporal:TemporalStore", "emergency:PlaybookLibrary"]),
    # ---- Industrial control
    "Alarm Rationalization.": (I, ["attention:rationalize_alarms"]),
    "Alarm Flood Mode.": (I, ["attention:collapse_flood"]),
    "First-Out Analysis.": (I, ["attention:collapse_flood"]),
    "Intervention Timeline.": (I, ["reliability:intervention_timeline"]),
    "Condition-Based Maintenance for Jarvis Hardware.": (I, ["reliability:condition_check"]),
    "Degradation Trend Detector.": (I, ["reliability:degradation_trend"]),
    "Operating Envelope Model.": (I, ["reliability:OperatingEnvelope"]),
    "Maintenance Verification.": (I, ["reliability:verify_maintenance"]),
    # ---- Spatial
    "Persistent World Layer.": (I, ["spatial:WorldLayer"]),
    "Cross-Device Spatial Anchor Abstraction.": (I, ["spatial:Anchor", "spatial:WorldLayer"]),
    "Anchor Confidence + Drift.": (I, ["spatial:Anchor"]),
    "Walk-Into Interfaces.": (I, ["spatial:walk_into"]),
    "Live Physical Labels.": (I, ["spatial:WorldLayer"]),
    "Spatial Inbox.": (I, ["memory:SpatialMemory"]),
    "Shared Spatial Context.": (I, ["spatial:WorldLayer"]),
    "Spatial Procedure Overlay.": (I, ["spatial:ProcedureOverlay"]),
    "Visual Change Memory.": (I, ["spatial:visual_change"]),
    "Semantic Room Map.": (I, ["spatial:SemanticMap"]),
    "Place-Bound Live Data.": (I, ["spatial:Zone", "spatial:SemanticMap"]),
    # ---- Accessibility
    "Input-Modality Independence.": (I, ["capabilities:CapabilityBus"]),
    "Output-Modality Independence.": (I, ["attention:render_all_modalities"]),
    "Interaction Capability Negotiation.": (I, ["attention:negotiate_modalities"]),
    "Describe-on-Demand.": (I, ["views:describe_scene"]),
    "Navigation Landmark Memory.": (I, ["spatial:LandmarkMemory"]),
    "Interface Semantic Overlay.": (I, ["views:semantic_overlay"]),
    "Accessibility as Core Architecture.": (I, ["capabilities:Capability", "capabilities:micro_app"]),
    # ---- End-user programming
    "Demonstrate -> Compile -> Verify.": (I, ["automation:compile_demonstrations", "automation:verify_replay"]),
    "Just-in-Time Automation.": (I, ["automation:do_the_rest"]),
    "Automation Generalization Dialog.": (I, ["automation:compile_demonstrations", "automation:answer_question"]),
    "Automation Versioning.": (I, ["standing:AutomationVersions"]),
    "Editable Generated Logic.": (I, ["standing:Predicate", "standing:compile_intent"]),
    "Composable Capability Blocks.": (I, ["capabilities:compose"]),
    "Personal Micro-App Generator.": (I, ["capabilities:micro_app"]),
    "Interface-by-Use.": (I, ["capabilities:CapabilityBus"]),
    "Personal API.": (I, ["capabilities:PersonalAPI"]),
    # ---- Memory that returns
    "Why-I-Saved-It Memory.": (I, ["memory:Capture", "memory:MemoryStore"]),
    "Contextual Resurfacing.": (I, ["memory:MemoryStore"]),
    "Knowledge Activation Queue.": (I, ["memory:MemoryStore"]),
    "Application Test for Knowledge.": (I, ["memory:application_prompt"]),
    "Memory Utility Tracking.": (I, ["memory:MemoryStore"]),
    "Forgetting-Aware Compression.": (I, ["memory:compress"]),
    "Spaced Resurfacing for Important Non-Tasks.": (I, ["memory:SpacedResurfacer"]),
    # ---- Meta
    "Concept Importer.": (I, ["radar:concept_importer"]),
    "Anti-Feature Detector.": (I, ["radar:anti_features"]),
    "Complexity Budget.": (I, ["radar:ComplexityBudget"]),
    "Feature Crystallization.": (I, ["radar:crystallize"]),
    # ---- Ethics
    "Ethical Context Engine.": (I, ["ethics:evaluate", "ethics:DecisionRecord"]),
    "Necessity & Proportionality Engine.": (I, ["ethics:evaluate"]),
    "Least-Intervention Planner.": (I, ["ethics:least_intervention"]),
    "Scoped Emergency Authority.": (I, ["ethics:EmergencyAuthority", "ethics:ScopedGrant"]),
    "Emergency Authority TTL.": (I, ["ethics:EmergencyAuthority"]),
    "Emergency Scope Firewall.": (I, ["ethics:EmergencyAuthority"]),
    "Circumstance Verification.": (I, ["ethics:classify_emergency"]),
    "Evidence-Weighted Urgency.": (I, ["ethics:evidence_weighted_threshold"]),
    "Competing-Interest Model.": (I, ["ethics:competing_interests"]),
    "Protect-Life Priority Without Blank Check.": (I, ["ethics:evidence_weighted_threshold", "ethics:evaluate"]),
    "Emergency Escalation Ladder.": (I, ["ethics:ESCALATION_LADDER", "ethics:least_intervention"]),
    "Alternative Exhaustion Record.": (I, ["ethics:AlternativeExhaustion"]),
    "Reversible-First Bias.": (I, ["ethics:least_intervention"]),
    "Minimum Necessary Damage Budget.": (I, ["ethics:damage_budget"]),
    "Exceptional-Action Verification Loop.": (I, ["ethics:exceptional_step_loop"]),
    "Automatic Authority Retraction.": (I, ["ethics:EmergencyAuthority"]),
    "Mandatory Exceptional-Action Audit.": (I, ["ethics:EmergencyAuthority"]),
    "Post-Emergency Restoration.": (I, ["ethics:EmergencyAuthority"]),
    "Uncertain-Emergency Handling.": (I, ["ethics:classify_emergency", "ethics:EMERGENCY_STATES"]),
    "Anti-Pretext Checks.": (I, ["ethics:anti_pretext"]),
    "No Concealment Benefit.": (I, ["ethics:HARD_BOUNDARIES"]),
    "Ethical Decision Explainability.": (I, ["ethics:explain"]),
    "Policy/Value Separation.": (I, ["ethics:HARD_BOUNDARIES", "ethics:EthicalContext"]),
    "Ethics Regression Tests.": (I, ["ethics:ETHICS_SCENARIOS", "ethics:run_scenario"]),
    "Ethical Red-Team Simulator.": (I, ["ethics:RED_TEAM_PROBES"]),
    # ---- Emergency competence
    "Emergency Playbook Library.": (I, ["emergency:PlaybookLibrary", "emergency:SEED_PLAYBOOKS"]),
    "Emergency Capability Index.": (I, ["emergency:CapabilityIndex"]),
    "Deterministic Emergency State Machine.": (I, ["emergency:EmergencyStateMachine"]),
    "Procedure Retrieval Before Generation.": (I, ["emergency:emergency_answer"]),
    "Offline Emergency Knowledge Pack.": (I, ["emergency:PlaybookLibrary"]),
    "Emergency Model Escalation.": (I, ["emergency:minimal_context_package", "emergency:emergency_answer"]),
    "Competence-Aware Routing.": (I, ["emergency:emergency_answer"]),
    "Don't-Let-the-8B-Wing-It Rule.": (I, ["emergency:emergency_answer"]),
    "Emergency Communications Composer.": (I, ["emergency:responder_packet"]),
    "Emergency Evidence Snapshot.": (I, ["emergency:evidence_snapshot"]),
    "Power/Connectivity Survival Mode.": (I, ["reliability:survival_mode"]),
    "Emergency Self-Test.": (I, ["emergency:self_test"]),
    "Emergency Drill Mode.": (I, ["emergency:run_drill"]),
    # ---- GitHub survey: computer use
    "opensymph/open-computer-use — accessibility-first desktop MCP.": (C, ["radar:CATALOG", "capabilities:route_control"]),
    "heaventree/cua-desktop-ai (Cua) — computer-use infrastructure + evaluation.": (C, ["radar:CATALOG", "capabilities:evaluate_task"]),
    "microsoft/UFO — Windows multi-app AgentOS.": (C, ["radar:CATALOG", "capabilities:route_control"]),
    "bytedance/UI-TARS-desktop — local/remote GUI + browser operator.": (C, ["radar:CATALOG", "capabilities:route_control"]),
    "browser-use/browser-use — browser agency.": (C, ["radar:CATALOG", "capabilities:CompiledSiteCapability"]),
    "arthurkatcher/desktop-use — observable computer-use mission control.": (C, ["radar:CATALOG", "capabilities:MissionRecorder"]),
    "shlawgathon/Computer-Use — demonstrate/record/replay desktop workflows.": (C, ["radar:CATALOG", "automation:compile_demonstrations"]),
    "getzep/graphiti — temporal knowledge graphs.": (C, ["radar:CATALOG", "temporal:TemporalStore"]),
    "neo4j-labs/agent-memory — graph-native agent memory.": (C, ["radar:CATALOG", "memory:MemoryStore"]),
    "letta-ai/letta-code / letta-agent-sdk — persistent agent identity/state.": (C, ["radar:CATALOG", "capabilities:state_packet"]),
    "AlexxIT/go2rtc — universal camera stream normalization.": (C, ["radar:CATALOG", "providers:gateway_plan"]),
    "koush/scrypted — high-performance video integration platform.": (C, ["radar:CATALOG", "providers:zone_crossings"]),
    "blakeblackshear/frigate — local camera perception/NVR.": (C, ["radar:CATALOG", "providers:zone_crossings"]),
    "streamlink/streamlink + yt-dlp/yt-dlp — public livestream resolution.": (C, ["radar:CATALOG", "providers:is_webcam_stream"]),
    "dgtlmoon/changedetection.io — generalized web Reality Diff.": (C, ["radar:CATALOG", "standing:WebObservation"]),
    "huginn/huginn — persistent event agents.": (C, ["radar:CATALOG", "standing:compile_intent"]),
    "binwiederhier/ntfy — self-hosted push bus.": (C, ["radar:CATALOG", "emergency:ntfy_payload"]),
    "livekit/agents — realtime multimodal agent transport.": (C, ["radar:CATALOG", "continuity:Session"]),
    "rhasspy/wyoming — small interoperable voice-service protocol.": (C, ["radar:CATALOG", "continuity:Session"]),
    "The-OASIS-Project/dawn — multi-room local JARVIS-style assistant.": (C, ["radar:CATALOG", "continuity:MediaFollower"]),
    "home-assistant/core — use Home Assistant as a capability bus, not merely a smart-home UI.": (C, ["radar:CATALOG", "providers:HomeAssistantBus"]),
    "meshtastic/firmware — off-grid Jarvis mesh.": (C, ["radar:CATALOG", "providers:lora_compact"]),
    "juanfont/headscale — self-hosted private device mesh control plane.": (C, ["radar:CATALOG", "continuity:Session"]),
    # ---- synthesized from repositories
    "Semantic-First Computer Control Router.": (I, ["capabilities:route_control"]),
    "Observable Autonomy / Mission Recorder.": (I, ["capabilities:MissionRecorder"]),
    "Temporal Truth Model.": (I, ["temporal:Fact", "temporal:TemporalStore"]),
    "Universal Media Gateway.": (I, ["providers:CameraSource", "providers:gateway_plan"]),
    "Eventification Layer.": (I, ["standing:eventify", "providers:zone_crossings"]),
    "Web Observation Fabric.": (I, ["standing:WebObservation"]),
    "Transport-Independent Presence.": (I, ["continuity:Session"]),
    "Capability Bus Adapters.": (I, ["providers:HomeAssistantBus"]),
    "Agent State Portability.": (I, ["capabilities:state_packet", "capabilities:load_state_packet"]),
    "Repository Radar.": (I, ["radar:score_candidate", "radar:RadarQueue"]),
    # ---- Voice stack candidates
    "VoiceStudio OmniVoice — cloned/designed Jarvis voice candidate.": (H, ["evaluation:tts_decision", "evaluation:TTS_CANDIDATES"]),
    "VoiceStudio / CosyVoice 3 — instructed zero-shot clone candidate.": (H, ["evaluation:tts_decision"]),
    "VoiceStudio / IndexTTS 2.5 — expressive/emotional voice candidate.": (H, ["evaluation:tts_decision"]),
    "OpenMOSS/MOSS-TTS-Nano — low-resource cloned-voice fallback.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "Kyutai PocketTTS through VoiceStudio — ultra-low-latency CPU clone lane.": (H, ["evaluation:tts_decision"]),
    "resemble-ai/chatterbox — standalone high-quality open TTS candidate.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "SWivid/F5-TTS — standalone zero-shot cloning candidate.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "fishaudio/fish-speech — expressive standalone candidate.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "ServeurpersoCom/qwentts.cpp — native/quantized Qwen TTS path.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    # ---- Mechanical sweep
    'QwenAudio/qwen-audio-agent — realtime "agent presence" runtime.': (C, ["radar:CATALOG", "continuity:JobManager"]),
    "Intent-Lab/VisionClaw — direct Ray-Ban realtime voice+vision reference implementation.": (C, ["radar:CATALOG", "continuity:Session"]),
    "xzf-thu/VoiceMem — streaming memory specifically designed for voice agents.": (C, ["radar:CATALOG", "memory:MemoryStore"]),
    "FireRedTeam/FireRedTTS3 — another serious voice-design/cloning bake-off candidate.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "k2-fsa/OmniVoice — inspect upstream directly, not only through VoiceStudio.": (H, ["evaluation:tts_decision", "radar:CATALOG"]),
    "ruvnet/RuView — Wi-Fi CSI as a camera-free room sensor.": (C, ["radar:CATALOG", "providers:csi_presence"]),
    "esphome/esphome — sensor-node fabric.": (C, ["radar:CATALOG", "providers:parse_esphome_state"]),
    "merbanan/rtl_433 — local RF sensor receiver.": (C, ["radar:CATALOG", "providers:parse_rtl433"]),
    "trycua/cua — canonical current Cua repo.": (C, ["radar:CATALOG", "capabilities:evaluate_task"]),
    "mediar-ai/terminator — deterministic Windows automation with AI recovery.": (C, ["radar:CATALOG", "automation:replay_with_checkpoints"]),
    "ShawnPana/phone-harness — no-jailbreak control of a real iPhone through Apple's iPhone Mirroring.": (C, ["radar:CATALOG", "capabilities:route_control"]),
    'jackwener/OpenCLI — "crystallize websites into tools."': (C, ["radar:CATALOG", "capabilities:CompiledSiteCapability"]),
    "omxyz/lumen — vision-first browser agent with self-healing replay.": (C, ["radar:CATALOG", "automation:replay_with_checkpoints"]),
    "vercel-labs/agent-browser — fast accessibility-tree browser control.": (C, ["radar:CATALOG", "views:semantic_overlay"]),
    "pinchtab/pinchtab — persistent local browser control plane.": (C, ["radar:CATALOG", "capabilities:CompiledSiteCapability"]),
    "lightpanda-io/browser — agent-native headless browser.": (C, ["radar:CATALOG", "standing:WebObservation"]),
    "koala73/worldmonitor — ready-made global intelligence/data fusion surface.": (C, ["radar:CATALOG", "views:dynamic_cop"]),
    "bilawalsidhu/gods-eye-view — photorealistic open-source spatial-intelligence globe.": (C, ["radar:CATALOG", "views:coverage_map"]),
    "tidwall/tile38 — realtime geospatial database + geofencing.": (C, ["radar:CATALOG", "spatial:SemanticMap"]),
    "organicmaps/organicmaps + Project-OSRM/osrm-backend — offline map/search/routing lane.": (C, ["radar:CATALOG", "emergency:PlaybookLibrary"]),
    "roboflow/supervision — reusable CV tracking/event primitives.": (C, ["radar:CATALOG", "providers:zone_crossings"]),
    "cpaczek/skylight — excellent Pi 5 reference project for physical-world fusion.": (C, ["radar:CATALOG", "spatial:PointingLoop"]),
    "wiedehopf/readsb + wiedehopf/tar1090 — local aircraft receiver/data/history stack.": (C, ["radar:CATALOG", "providers:parse_readsb"]),
    "jvde-github/AIS-catcher — local AIS vessel receiving.": (C, ["radar:CATALOG", "providers:parse_ais_catcher"]),
    "SatDump/SatDump — local satellite downlink processing.": (C, ["radar:CATALOG"]),
    "thkruz/keeptrack.space — local/offline orbital world model.": (C, ["radar:CATALOG"]),
    "eclipse-zenoh/zenoh — unified pub/sub + store/query transport for Jarvis nodes.": (C, ["radar:CATALOG", "reliability:ReconciliationLedger"]),
    "bluenviron/mediamtx — realtime media router.": (C, ["radar:CATALOG", "providers:gateway_plan"]),
    "drasi-project/drasi-platform — change-data-processing engine.": (C, ["radar:CATALOG", "standing:StandingQueryEngine"]),
    "promptfoo/promptfoo — model/agent regression harness.": (C, ["radar:CATALOG", "evaluation:eval_matrix"]),
    "langfuse/langfuse — agent trace/evaluation observability.": (C, ["radar:CATALOG", "evaluation:TraceLedger"]),
    "Cua Bench (inside trycua/cua) — real task verification for computer use.": (I, ["capabilities:evaluate_task"]),
    # ---- New architectural ideas
    "Conversation/Execution Split.": (I, ["continuity:JobManager"]),
    "Direct-Observation Tier.": (I, ["providers:LOCAL", "providers:Observation"]),
    "Camera-Free Room Model.": (I, ["providers:room_presence"]),
    "Physical Sensor Gateway on Pi 5.": (I, ["providers:verify_sensor_report"]),
    "RF Reality Layer.": (I, ["providers:parse_readsb", "providers:parse_ais_catcher", "providers:parse_rtl433"]),
    "Predict -> Point -> Verify -> Calibrate loop.": (I, ["spatial:PointingLoop"]),
    "Compiled Website Capability.": (I, ["capabilities:CompiledSiteCapability"]),
    "Capability Evidence Ledger.": (I, ["reliability:capability_claim"]),
    "Standing Query Reality Engine.": (I, ["standing:StandingQueryEngine"]),
    "Offline World Core.": (I, ["reliability:DependencyMap", "emergency:PlaybookLibrary", "providers:parse_readsb"]),
    "Model-independent Interaction Bus.": (I, ["capabilities:CapabilityBus"]),
    # ---- Gemma 4
    "Benchmark Gemma 4 12B Unified on the RTX 5080 as a general local-intelligence candidate.": (H, ["evaluation:promotion_decision"]),
    "Do not replace deterministic systems with it.": (I, ["capabilities:route_model"]),
    "Possible role:": (I, ["capabilities:route_model", "capabilities:ModelLane"]),
    "Vision bake-off:": (H, ["evaluation:score_vision"]),
    "Audio understanding experiment:": (H, ["evaluation:eval_matrix"]),
    "User Belief Model experiment:": (I, ["belief:UserBeliefModel"]),
    "Jarvis-specific acceptance harness:": (H, ["evaluation:summarize_runs", "evaluation:promotion_decision"]),
    "Promotion rule:": (H, ["evaluation:promotion_decision"]),
    # ---- Epistemic claim types
    "stable": (I, ["epistemics:STABLE"]),
    "user-supplied": (I, ["epistemics:USER_SUPPLIED"]),
    "local-observed": (I, ["epistemics:LOCAL_OBSERVED"]),
    "externally-verified": (I, ["epistemics:EXTERNALLY_VERIFIED"]),
    "inferred": (I, ["epistemics:INFERRED"]),
    "current-unverified": (I, ["epistemics:CURRENT_UNVERIFIED"]),
    "Epistemic Freshness Gate:": (I, ["epistemics:route_claim", "epistemics:lint_answer"]),
    "User Belief Model:": (I, ["belief:UserBeliefModel"]),
    # ---- HORUS Ambient Commentary
    "Delivery:": (I, ["humor:HumorEngine", "humor:PRIVATE_DEVICES"]),
    "Frequency:": (I, ["humor:HumorEngine"]),
    "Voice:": (I, ["humor:REPERTOIRE"]),
    "Humor mechanisms:": (I, ["humor:detect_triggers"]),
    "Canonical examples and triggers:": (I, ["humor:REPERTOIRE", "humor:detect_triggers"]),
    "Personalization:": (I, ["humor:HumorEngine"]),
    "Candidate pipeline:": (I, ["humor:HumorEngine"]),
    "Practical prototype:": (H, ["humor:evaluate_transcript"]),
    "Success criterion:": (H, ["humor:evaluate_transcript"]),
    "Modes:": (I, ["humor:MODES"]),
    "Output:": (I, ["humor:HumorEngine"]),
    "Timing:": (I, ["humor:HumorEngine"]),
    "Calibration:": (I, ["humor:HumorEngine"]),
    "Learning:": (I, ["humor:HumorEngine"]),
    "Prototype test:": (H, ["humor:evaluate_transcript"]),
}

# Ideas that appear in future.md prose (not as bold bullets) but were implemented.
PROSE_IDEAS: dict[str, tuple[str, list[str]]] = {
    "Unified ask-everything search with source/freshness disclosure": (I, ["memory:MemoryStore"]),
    "Cross-device continuation for general productivity": (I, ["continuity:Session"]),
    "Voice replacement acceptance test": (H, ["evaluation:score_tts", "evaluation:TTS_CORPUS"]),
    "Identity Resolver / evidence-debugging public research": (I, ["identity:IdentityGraph", "identity:research_receipt"]),
    "Epistemic Freshness Gate (core rule, routing, linter, receipts, TTLs)": (I, ["epistemics:verify_claim",
                                                                                 "epistemics:AdjudicationSequence"]),
    "Additional running-gag examples": (I, ["humor:REPERTOIRE"]),
}


def resolve(ref: str) -> Any:
    """Resolve a reference.  HORUS modules are imported; existing ``jarvis_mrb``
    modules are checked statically (they may need optional runtime dependencies)."""
    mod, _, attr = ref.partition(":")
    if mod.startswith("jarvis_mrb"):
        import ast
        from importlib.util import find_spec

        spec = find_spec(mod)
        if spec is None or spec.origin is None:
            raise ImportError(mod)
        if not attr:
            return spec.origin
        tree = ast.parse(open(spec.origin, encoding="utf-8").read())
        names = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        names |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
        if attr not in names:
            raise AttributeError(f"{mod} has no {attr}")
        return f"{spec.origin}:{attr}"
    module = importlib.import_module(f"jarvis_mrb.horus.{mod}")
    return getattr(module, attr) if attr else module


def summary() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for kind, _ in list(IDEAS.values()) + list(PROSE_IDEAS.values()):
        counts[kind] = counts.get(kind, 0) + 1
    return {"ideas": len(IDEAS) + len(PROSE_IDEAS), "by_kind": counts}


def lookup(text: str) -> list[dict[str, Any]]:
    """Find mapped ideas whose title contains ``text`` (case-insensitive)."""
    t = text.lower()
    out = []
    for title, (kind, refs) in {**IDEAS, **PROSE_IDEAS}.items():
        if t in title.lower():
            out.append({"idea": title, "kind": kind, "implemented_by": refs})
    return out
