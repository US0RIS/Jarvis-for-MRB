import Foundation
import MapKit
import SwiftUI

// Phase 1 is a user-enrolled, one-shot evidence instrument. There is no
// background camera, AIS, aircraft tracker, worker or actuation path here.
struct ArmorCapabilities: Decodable {
    struct Provider: Decodable, Identifiable {
        let id: String
        let kind: String
        let coverage: String
    }
    let enabled: Bool
    let mode: String
    let sourceState: String
    let scheduledWatches: Bool?
    let watchRunnerAutoStarted: Bool?
    let cameraCollection: Bool?
    let windyGlobalCatalogConfigured: Bool?
    let providers: [Provider]
    enum CodingKeys: String, CodingKey {
        case enabled, mode, providers
        case sourceState = "source_state"
        case scheduledWatches = "scheduled_watches"
        case watchRunnerAutoStarted = "watch_runner_auto_started"
        case cameraCollection = "camera_collection"
        case windyGlobalCatalogConfigured = "windy_global_catalog_configured"
    }
}

struct ArmorPublicPageMediaCandidate: Decodable, Identifiable {
    let url: String
    let source: String
    let sameOrigin: Bool
    var id: String { url }
    enum CodingKeys: String, CodingKey {
        case url, source
        case sameOrigin = "same_origin"
    }
}

struct ArmorPublicPageMedia: Decodable {
    let status: String
    let candidates: [ArmorPublicPageMediaCandidate]
    let qualifier: String
}

struct ArmorPublicCamera: Decodable, Identifiable {
    let id: String
    let title: String
    let provider: String
    let latitude: Double
    let longitude: Double
    let imageURL: String?
    let streamURL: String?
    let providerDetailURL: String?
    let sourceNote: String?
    enum CodingKeys: String, CodingKey {
        case id, title, provider, latitude, longitude
        case imageURL = "image_url"
        case streamURL = "stream_url"
        case providerDetailURL = "provider_detail_url"
        case sourceNote = "source_note"
    }
}

struct ArmorPublicCameraProviderStatus: Decodable, Identifiable {
    let provider: String
    let status: String
    let keyRequired: String?
    var id: String { provider }
    enum CodingKeys: String, CodingKey {
        case provider, status
        case keyRequired = "key_required"
    }
}

struct ArmorPublicCameraDiscovery: Decodable {
    let cameras: [ArmorPublicCamera]
    let providerStatuses: [ArmorPublicCameraProviderStatus]
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case cameras, qualifier
        case providerStatuses = "provider_statuses"
    }
}

struct ArmorCameraReceipt: Decodable, Identifiable {
    let id: String
    let investigationID: String
    let cameraRef: String
    let provider: String
    let title: String
    let mediaKind: String
    let sourceDisplay: String
    let condition: String?
    let classification: String?
    let description: String
    let imageSHA256: String
    let retrievedAt: String
    let captureTime: String?
    let receivedAt: String
    let spatialBasis: String
    let changeState: String
    enum CodingKeys: String, CodingKey {
        case id, provider, title, condition, classification, description
        case investigationID = "investigation_id"
        case cameraRef = "camera_ref"
        case mediaKind = "media_kind"
        case sourceDisplay = "source_display"
        case imageSHA256 = "image_sha256"
        case retrievedAt = "retrieved_at"
        case captureTime = "capture_time"
        case receivedAt = "received_at"
        case spatialBasis = "spatial_basis"
        case changeState = "change_state"
    }
}

struct ArmorCameraReceiptList: Decodable {
    let cameraReceipts: [ArmorCameraReceipt]
    let sourceCoverage: String
    enum CodingKeys: String, CodingKey {
        case cameraReceipts = "camera_receipts"
        case sourceCoverage = "source_coverage"
    }
}

struct ArmorPlatformSource: Decodable, Identifiable {
    let id: String
    let label: String
    let kind: String
    let sourceDisplay: String
    let sceneGoal: String
    let grantClass: String
    let termsReference: String
    let state: String
    let cadenceSeconds: Int
    let checkCount: Int
    let sampleBudget: Int?
    let consentExpiresAt: String?
    let lastCheckedAt: String?
    let lastOutcome: String?
    let authorizedAutomatedAccess: Bool
    let retentionDays: Int
    let permissionVerifiedByJarvis: Bool
    enum CodingKeys: String, CodingKey {
        case id, label, kind, state
        case sourceDisplay = "source_display"
        case sceneGoal = "scene_goal"
        case grantClass = "grant_class"
        case termsReference = "terms_reference"
        case cadenceSeconds = "cadence_seconds"
        case checkCount = "check_count"
        case sampleBudget = "sample_budget"
        case consentExpiresAt = "consent_expires_at"
        case lastCheckedAt = "last_checked_at"
        case lastOutcome = "last_outcome"
        case authorizedAutomatedAccess = "authorized_automated_access"
        case retentionDays = "retention_days"
        case permissionVerifiedByJarvis = "permission_verified_by_jarvis"
    }
}

struct ArmorPlatformSourcePage: Decodable {
    let sources: [ArmorPlatformSource]
    let nextOffset: Int?
    let total: Int
    enum CodingKeys: String, CodingKey {
        case sources, total
        case nextOffset = "next_offset"
    }
}

struct ArmorPlatformObservation: Decodable, Identifiable {
    let id: String
    let seq: Int
    let sourceID: String
    let description: String
    let conditionStatus: String?
    let sceneGoal: String
    let sourceCaptureAt: String?
    let receivedAt: String
    let changeKind: String
    enum CodingKeys: String, CodingKey {
        case id, seq, description
        case sourceID = "source_id"
        case conditionStatus = "condition_status"
        case sceneGoal = "scene_goal"
        case sourceCaptureAt = "source_capture_at"
        case receivedAt = "received_at"
        case changeKind = "change_kind"
    }
}

struct ArmorPlatformEvidencePage: Decodable {
    let observations: [ArmorPlatformObservation]
    let nextAfterSeq: Int?
    enum CodingKeys: String, CodingKey {
        case observations
        case nextAfterSeq = "next_after_seq"
    }
}

struct ArmorPlatformNotice: Decodable, Identifiable {
    let id: String
    let sourceID: String
    let summary: String
    let createdAt: String
    enum CodingKeys: String, CodingKey {
        case id, summary
        case sourceID = "source_id"
        case createdAt = "created_at"
    }
}

struct ArmorPlatformNoticesPage: Decodable {
    let notices: [ArmorPlatformNotice]
}

struct ArmorPlatformCheck: Decodable {
    let status: String
    let sourceID: String
    let modelCalls: Int?
    let changeKind: String?
    let noticeCreated: Bool?
    enum CodingKeys: String, CodingKey {
        case status
        case sourceID = "source_id"
        case modelCalls = "model_calls"
        case changeKind = "change_kind"
        case noticeCreated = "notice_created"
    }
}

struct ArmorPlatformForget: Decodable {
    let deleted: Int
}

struct ArmorPlatformPlan: Decodable {
    let available: Int
    let automated: Int
    let proposedHostConcurrency: Int
    let providerEntitlementIndependentlyVerified: Bool
    let remoteDistributedWorkers: Bool
    enum CodingKeys: String, CodingKey {
        case available, automated
        case proposedHostConcurrency = "proposed_host_concurrency"
        case providerEntitlementIndependentlyVerified =
             "provider_entitlement_independently_verified"
        case remoteDistributedWorkers = "remote_distributed_workers"
    }
}

struct ArmorLiveEvent: Decodable, Identifiable {
    let seq: Int
    let eventID: String
    let kind: String
    let subsystem: String
    let sourceID: String?
    let status: String
    let priority: String
    let createdAt: String
    let summary: String
    var id: Int { seq }
    enum CodingKeys: String, CodingKey {
        case seq, kind, subsystem, status, priority, summary
        case eventID = "event_id"
        case sourceID = "source_id"
        case createdAt = "created_at"
    }
}

struct ArmorLiveEventsPage: Decodable {
    let events: [ArmorLiveEvent]
    let nextSeq: Int
    let oldestSeq: Int?
    let latestSeq: Int?
    let replayGap: Bool?
    let truncated: Bool
    let retentionDays: Int
    enum CodingKeys: String, CodingKey {
        case events, truncated
        case nextSeq = "next_seq"
        case oldestSeq = "oldest_seq"
        case latestSeq = "latest_seq"
        case replayGap = "replay_gap"
        case retentionDays = "retention_days"
    }
}

struct ArmorLiveStatus: Decodable {
    let running: Bool
    let enabled: Bool
    let autostartEnabled: Bool
    let heartbeatAt: String?
    let heartbeatAgeSeconds: Double?
    let cycleCount: Int
    let lastCycleMS: Int?
    let lastError: String
    let journalEvents: Int
    let latestSeq: Int
    enum CodingKeys: String, CodingKey {
        case running, enabled
        case autostartEnabled = "autostart_enabled"
        case heartbeatAt = "heartbeat_at"
        case heartbeatAgeSeconds = "heartbeat_age_seconds"
        case cycleCount = "cycle_count"
        case lastCycleMS = "last_cycle_ms"
        case lastError = "last_error"
        case journalEvents = "journal_events"
        case latestSeq = "latest_seq"
    }
}

struct ArmorDistributedWorker: Decodable, Identifiable {
    struct Metrics: Decodable {
        let activeRequests: Int
        let capacity: Int
        let normalizedLoad: Double
        enum CodingKeys: String, CodingKey {
            case capacity
            case activeRequests = "active_requests"
            case normalizedLoad = "normalized_load"
        }
    }
    struct DispatchHealth: Decodable {
        let successCount: Int?
        let failureCount: Int?
        let consecutiveFailures: Int?
        let cooldownUntil: String?
        enum CodingKeys: String, CodingKey {
            case successCount = "success_count"
            case failureCount = "failure_count"
            case consecutiveFailures = "consecutive_failures"
            case cooldownUntil = "cooldown_until"
        }
    }
    let id: String
    let status: String
    let capabilities: [String]
    let observedAt: String?
    let workerMetrics: Metrics?
    let dispatchHealth: DispatchHealth?
    enum CodingKeys: String, CodingKey {
        case id, status, capabilities
        case observedAt = "observed_at"
        case workerMetrics = "worker_metrics"
        case dispatchHealth = "dispatch_health"
    }
}

struct ArmorDistributedWorkers: Decodable {
    let workers: [ArmorDistributedWorker]
    let networkDiscovery: Bool
    let controller: String
    let credentialDelegation: Bool
    let remoteArbitraryRPC: Bool
    let workerRegistry: String?
    let workerCountCap: Int?
    enum CodingKeys: String, CodingKey {
        case workers, controller
        case networkDiscovery = "network_discovery"
        case credentialDelegation = "credential_delegation"
        case remoteArbitraryRPC = "remote_arbitrary_rpc"
        case workerRegistry = "worker_registry"
        case workerCountCap = "worker_count_cap"
    }
}

struct ArmorMovementSource: Decodable, Identifiable {
    let id: String
    let label: String
    let kind: String
    let grantClass: String
    let termsReference: String
    let authorizedAutomatedAccess: Bool
    let providerMinIntervalSeconds: Int
    let cadenceSeconds: Int
    let retentionDays: Int
    let state: String
    let latitude: Double?
    let longitude: Double?
    let radiusKM: Double?
    let globalScope: Bool
    let checkCount: Int
    let lastCheckedAt: String?
    let lastOutcome: String?
    enum CodingKeys: String, CodingKey {
        case id, label, kind, state, latitude, longitude
        case grantClass = "grant_class"
        case termsReference = "terms_reference"
        case authorizedAutomatedAccess = "authorized_automated_access"
        case providerMinIntervalSeconds = "provider_min_interval_seconds"
        case cadenceSeconds = "cadence_seconds"
        case retentionDays = "retention_days"
        case radiusKM = "radius_km"
        case globalScope = "global_scope"
        case checkCount = "check_count"
        case lastCheckedAt = "last_checked_at"
        case lastOutcome = "last_outcome"
    }
}

struct ArmorMovementSourcePage: Decodable {
    let sources: [ArmorMovementSource]
    let nextOffset: Int?
    let total: Int
    enum CodingKeys: String, CodingKey {
        case sources, total
        case nextOffset = "next_offset"
    }
}

struct ArmorMovementEntity: Decodable, Identifiable {
    let seq: Int
    let entityID: String
    let entityType: String
    let observedAt: String
    let providerTime: String?
    let latitude: Double
    let longitude: Double
    let altitudeM: Double?
    let velocityMPS: Double?
    let headingDeg: Double?
    let sourceName: String
    let lastName: String?
    let lastCallsign: String?
    let distanceKM: Double?
    var id: String { entityID }
    enum CodingKeys: String, CodingKey {
        case seq, latitude, longitude
        case entityID = "entity_id"
        case entityType = "entity_type"
        case observedAt = "observed_at"
        case providerTime = "provider_time"
        case altitudeM = "altitude_m"
        case velocityMPS = "velocity_mps"
        case headingDeg = "heading_deg"
        case sourceName = "source_name"
        case lastName = "last_name"
        case lastCallsign = "last_callsign"
        case distanceKM = "distance_km"
    }
}

struct ArmorMovementNearbyPage: Decodable {
    let entities: [ArmorMovementEntity]
    let nextAfterSeq: Int?
    enum CodingKeys: String, CodingKey {
        case entities
        case nextAfterSeq = "next_after_seq"
    }
}

struct ArmorMovementCollectReceipt: Decodable {
    let status: String
    let sourceID: String
    let entitiesSeen: Int?
    let observationsSaved: Int?
    let providerNote: String?
    enum CodingKeys: String, CodingKey {
        case status
        case sourceID = "source_id"
        case entitiesSeen = "entities_seen"
        case observationsSaved = "observations_saved"
        case providerNote = "provider_note"
    }
}

struct ArmorWatch: Decodable, Identifiable {
    let id: String
    let investigationID: String
    let createdAt: String
    let expiresAt: String
    let nextDueAt: String
    let intervalMinutes: Int
    let maxChecks: Int
    let checkCount: Int
    let state: String
    let collecting: Bool
    let lastCheckedAt: String?
    let lastOutcome: String?
    let lastChangeState: String?
    let attentionKind: String?
    let attentionThreshold: Double?
    let attentionCooldownMinutes: Int?
    let notificationsEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case id, state, collecting
        case investigationID = "investigation_id"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
        case nextDueAt = "next_due_at"
        case intervalMinutes = "interval_minutes"
        case maxChecks = "max_checks"
        case checkCount = "check_count"
        case lastCheckedAt = "last_checked_at"
        case lastOutcome = "last_outcome"
        case lastChangeState = "last_change_state"
        case attentionKind = "attention_kind"
        case attentionThreshold = "attention_threshold"
        case attentionCooldownMinutes = "attention_cooldown_minutes"
        case notificationsEnabled = "notifications_enabled"
    }
}

struct ArmorNotice: Decodable, Identifiable {
    let id: String
    let watchID: String
    let investigationID: String
    let sampleID: String
    let source: String
    let kind: String
    let sourceKey: String
    let observedAt: String?
    let receivedAt: String
    let createdAt: String
    let summary: String
    let observationID: String?
    let readAt: String?
    enum CodingKeys: String, CodingKey {
        case id, source, kind, summary
        case watchID = "watch_id"
        case investigationID = "investigation_id"
        case sampleID = "sample_id"
        case sourceKey = "source_key"
        case observedAt = "observed_at"
        case receivedAt = "received_at"
        case createdAt = "created_at"
        case observationID = "observation_id"
        case readAt = "read_at"
    }
}

struct ArmorNoticeList: Decodable {
    let notices: [ArmorNotice]
    let unreadCount: Int
    let delivery: String
    enum CodingKeys: String, CodingKey {
        case notices, delivery
        case unreadCount = "unread_count"
    }
}

struct ArmorNoticeForgetReceipt: Decodable {
    let deleted: Int
}

struct ArmorWatchForgetReceipt: Decodable {
    let deleted: Int
}

struct ArmorWatchList: Decodable {
    let watches: [ArmorWatch]
    let runnerAutoStarted: Bool
    enum CodingKeys: String, CodingKey {
        case watches
        case runnerAutoStarted = "runner_auto_started"
    }
}

struct ArmorInvestigation: Decodable, Identifiable {
    let id: String
    let label: String
    let latitude: Double
    let longitude: Double
    let radiusKM: Double
    let expiresAt: String
    let sampleCount: Int
    enum CodingKeys: String, CodingKey {
        case id, label, latitude, longitude
        case radiusKM = "radius_km"
        case expiresAt = "expires_at"
        case sampleCount = "sample_count"
    }
}

struct ArmorInvestigationList: Decodable {
    let investigations: [ArmorInvestigation]
    let setupRequired: Bool
    enum CodingKeys: String, CodingKey {
        case investigations
        case setupRequired = "setup_required"
    }
}

struct ArmorCreated: Decodable {
    let id: String
    let label: String
}

struct ArmorCoverage: Decodable {
    let status: String
    let checkedAt: String
    let reportedCount: Int
    let scope: String
    let adapterMode: String
    enum CodingKeys: String, CodingKey {
        case status, scope
        case checkedAt = "checked_at"
        case reportedCount = "reported_count"
        case adapterMode = "adapter_mode"
    }
}

struct ArmorValues: Decodable {
    let usAQI: Double?
    let event: String?
    let headline: String?
    let severity: String?
    let magnitude: Double?
    let place: String?
    let reviewed: Bool?
    let sourceURL: String?
    let latitude: Double?
    let longitude: Double?
    enum CodingKeys: String, CodingKey {
        case event, headline, severity, magnitude, place, reviewed
        case latitude, longitude
        case usAQI = "us_aqi"
        case sourceURL = "source_url"
    }
    var brief: String {
        if let usAQI {
            return "Modelled US AQI: " + String(format: "%.1f", usAQI)
        }
        if let magnitude {
            return "USGS reported M" + String(format: "%.1f", magnitude)
                + " • " + (place ?? "Unspecified location")
        }
        if let event {
            return event + " • " + (headline ?? "No headline")
                + " • " + (severity ?? "Unknown severity")
        }
        return "Source reported a structured observation."
    }
}

struct ArmorObservation: Decodable, Identifiable {
    let id: String
    let source: String
    let kind: String
    let observedAt: String?
    let publishedAt: String?
    let receivedAt: String
    let revision: Int
    let lineage: String
    let geometryBasis: String
    let adapterMode: String?
    let sampleCoverageStatus: String?
    let sampleCoverageCheckedAt: String?
    let values: ArmorValues
    enum CodingKeys: String, CodingKey {
        case id, source, kind, revision, lineage, values
        case observedAt = "observed_at"
        case publishedAt = "published_at"
        case receivedAt = "received_at"
        case geometryBasis = "geometry_basis"
        case adapterMode = "adapter_mode"
        case sampleCoverageStatus = "sample_coverage_status"
        case sampleCoverageCheckedAt = "sample_coverage_checked_at"
    }
}

struct ArmorSampleMoment: Decodable, Identifiable {
    struct SourceCoverage: Decodable {
        let status: String
        let reportedCount: Int
        enum CodingKeys: String, CodingKey {
            case status
            case reportedCount = "reported_count"
        }
    }
    let id: String
    let receivedAt: String
    let adapterMode: String
    let sourceCoverage: [String: SourceCoverage]?
    var coverageSummary: String {
        let labels = [
            ("openmeteo_model", "AQI"),
            ("nws_point_alerts", "NWS"),
            ("usgs_earthquakes", "USGS")
        ]
        return labels.map { entry in
            let (source, label) = entry
            return label + " " + (sourceCoverage?[source]?.status ?? "not checked")
        }.joined(separator: " · ")
    }
    enum CodingKeys: String, CodingKey {
        case id
        case receivedAt = "received_at"
        case adapterMode = "adapter_mode"
        case sourceCoverage = "source_coverage"
    }
}

struct ArmorReplay: Decodable {
    struct Region: Decodable {
        let id: String
        let label: String
        let latitude: Double
        let longitude: Double
    }
    let investigation: Region
    let asKnownAt: String
    let observationCount: Int
    let sampleTimeline: [ArmorSampleMoment]?
    let observations: [ArmorObservation]
    let coverage: [String: ArmorCoverage]
    let mode: String
    let unknownIsNotAllClear: Bool
    enum CodingKeys: String, CodingKey {
        case investigation, observations, coverage, mode
        case asKnownAt = "as_known_at"
        case observationCount = "observation_count"
        case sampleTimeline = "sample_timeline"
        case unknownIsNotAllClear = "unknown_is_not_all_clear"
    }
}

struct ArmorChangeReport: Decodable {
    struct CoverageChange: Decodable {
        let source: String
        let before: String
        let after: String
    }
    struct AQIChange: Decodable {
        let before: Double
        let after: Double
        let delta: Double
        let beforeModelAt: String
        let afterModelAt: String
        enum CodingKeys: String, CodingKey {
            case before, after, delta
            case beforeModelAt = "before_model_at"
            case afterModelAt = "after_model_at"
        }
    }
    struct RecordChange: Decodable, Identifiable {
        let source: String
        let kind: String
        let recordKey: String
        let receivedAt: String
        let observedAt: String?
        let after: ArmorValues
        let note: String
        var id: String { source + ":" + kind + ":" + recordKey }
        enum CodingKeys: String, CodingKey {
            case source, kind, after, note
            case recordKey = "record_key"
            case receivedAt = "received_at"
            case observedAt = "observed_at"
        }
    }
    let comparison: String
    let sourceChanges: [CoverageChange]
    let modelledAirQualityChange: AQIChange?
    let sourceRecordChanges: [RecordChange]
    let sourcesWithoutComparableCoverage: [String]?
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case comparison, qualifier
        case sourceChanges = "source_changes"
        case modelledAirQualityChange = "modelled_air_quality_change"
        case sourceRecordChanges = "source_record_changes"
        case sourcesWithoutComparableCoverage = "sources_without_comparable_coverage"
    }
}

struct ArmorCorrelationReport: Decodable {
    struct Window: Decodable {
        let start: String
        let end: String
    }
    struct Region: Decodable {
        let latitude: Double
        let longitude: Double
        let radiusKM: Double
        let geometryBasis: String
        enum CodingKeys: String, CodingKey {
            case latitude, longitude
            case radiusKM = "radius_km"
            case geometryBasis = "geometry_basis"
        }
    }
    struct Coverage: Decodable {
        let status: String
        let scope: String
    }
    struct Link: Decodable, Identifiable {
        let firstObservationID: String
        let secondObservationID: String
        let firstSource: String
        let secondSource: String
        let firstSourceTime: String
        let secondSourceTime: String
        let separationSeconds: Int
        let spatialBasis: String
        let note: String
        var id: String { firstObservationID + ":" + secondObservationID }
        enum CodingKeys: String, CodingKey {
            case note
            case firstObservationID = "first_observation_id"
            case secondObservationID = "second_observation_id"
            case firstSource = "first_source"
            case secondSource = "second_source"
            case firstSourceTime = "first_source_time"
            case secondSourceTime = "second_source_time"
            case separationSeconds = "separation_seconds"
            case spatialBasis = "spatial_basis"
        }
    }
    let queryID: String
    let observationWindow: Window
    let queryRegion: Region
    let spatiallyIndeterminateObservations: [ArmorObservation]
    let timedObservations: [ArmorObservation]
    let degradedObservations: [ArmorObservation]
    let receiptTimeOnlyObservations: [ArmorObservation]
    let candidateLinks: [Link]
    let sourceCoverage: [String: Coverage]
    let mode: String
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case mode, qualifier
        case queryID = "query_id"
        case observationWindow = "observation_window"
        case queryRegion = "query_region"
        case spatiallyIndeterminateObservations = "spatially_indeterminate_observations"
        case timedObservations = "timed_observations"
        case degradedObservations = "degraded_observations"
        case receiptTimeOnlyObservations = "receipt_time_only_observations"
        case candidateLinks = "candidate_links"
        case sourceCoverage = "source_coverage"
    }
}

struct ArmorEvidenceGraph: Decodable {
    struct Edge: Decodable, Identifiable {
        let id: String
        let type: String
        let from: String
        let to: String
        let assertion: String
        let causal: Bool
    }
    struct Hypothesis: Decodable, Identifiable {
        let id: String
        let status: String
        let type: String
        let claim: String
        let supportingObservationIDs: [String]
        let contradictingObservationIDs: [String]
        let independentLineageCount: Int
        let spatialPrecision: String
        let assumptions: [String]
        let missingEvidence: [String]
        let alternativeExplanations: [String]
        let prohibitedConclusion: String
        enum CodingKeys: String, CodingKey {
            case id, status, type, claim, assumptions
            case supportingObservationIDs = "supporting_observation_ids"
            case contradictingObservationIDs = "contradicting_observation_ids"
            case independentLineageCount = "independent_lineage_count"
            case spatialPrecision = "spatial_precision"
            case missingEvidence = "missing_evidence"
            case alternativeExplanations = "alternative_explanations"
            case prohibitedConclusion = "prohibited_conclusion"
        }
    }
    let queryID: String
    let nodes: [ArmorObservation]
    let edges: [Edge]
    let hypotheses: [Hypothesis]
    let unavailableOrUncheckedSources: [String]
    let receiptTimeOnlyCount: Int
    let degradedObservationCount: Int
    let spatiallyIndeterminateCount: Int
    let qualifier: String
    enum CodingKeys: String, CodingKey {
        case nodes, edges, hypotheses, qualifier
        case queryID = "query_id"
        case unavailableOrUncheckedSources = "unavailable_or_unchecked_sources"
        case receiptTimeOnlyCount = "receipt_time_only_count"
        case degradedObservationCount = "degraded_observation_count"
        case spatiallyIndeterminateCount = "spatially_indeterminate_count"
    }
}

struct ArmorSampleReceipt: Decodable {
    let newObservations: Int
    let receivedAt: String
    let mode: String
    enum CodingKeys: String, CodingKey {
        case mode
        case newObservations = "new_observations"
        case receivedAt = "received_at"
    }
}

struct ArmorForgetReceipt: Decodable {
    let deleted: Int
    let qualifier: String?
}

struct ArmorPushStatus: Decodable {
    let enabled: Bool
    let providerConfigured: Bool
    let registeredDevices: Int
    let pending: Int
    let dead: Int
    let sentRetained: Int
    let oldestPendingAt: String?
    let maxPending: Int
    let maxAttempts: Int
    let deliverySemantics: String

    enum CodingKeys: String, CodingKey {
        case enabled, pending, dead
        case providerConfigured = "provider_configured"
        case registeredDevices = "registered_devices"
        case sentRetained = "sent_retained"
        case oldestPendingAt = "oldest_pending_at"
        case maxPending = "max_pending"
        case maxAttempts = "max_attempts"
        case deliverySemantics = "delivery_semantics"
    }
}

struct ArmorPushRegistration: Decodable {
    let deviceID: String
    let tokenHash: String
    let enabled: Bool
    let pushTransportEnabled: Bool
    let providerConfigured: Bool
    let tokenReflected: Bool

    enum CodingKeys: String, CodingKey {
        case enabled
        case deviceID = "device_id"
        case tokenHash = "token_hash"
        case pushTransportEnabled = "push_transport_enabled"
        case providerConfigured = "provider_configured"
        case tokenReflected = "token_reflected"
    }
}

struct ArmorPushUnregister: Decodable {
    let disabled: Bool
}

struct ArmorFullStatus: Decodable {
    struct Layers: Decodable {
        let realityBrowser: String
        let syntheticSenses: String
        let causalDebugger: String
        let parallelExistence: String
        let presence: String

        enum CodingKeys: String, CodingKey {
            case realityBrowser = "reality_browser"
            case syntheticSenses = "synthetic_senses"
            case causalDebugger = "causal_debugger"
            case parallelExistence = "parallel_existence"
            case presence
        }
    }

    let enabled: Bool
    let layers: Layers
    let registeredWorkers: Int
    let activePresenceGrants: Int
    let pendingPresenceReceipts: Int
    let qualifier: String

    enum CodingKeys: String, CodingKey {
        case enabled, layers, qualifier
        case registeredWorkers = "registered_workers"
        case activePresenceGrants = "active_presence_grants"
        case pendingPresenceReceipts = "pending_presence_receipts"
    }
}

struct ArmorRealityBrowser: Decodable {
    struct Item: Decodable, Identifiable {
        let id: String
        let time: String?
        let timeBasis: String
        let kind: String?
        let subsystem: String
        let sourceID: String?
        let status: String?
        let priority: String
        let summary: String
        let synthetic: Bool

        enum CodingKeys: String, CodingKey {
            case id, time, kind, subsystem, status, priority, summary, synthetic
            case timeBasis = "time_basis"
            case sourceID = "source_id"
        }
    }

    let timeline: [Item]
    let nextSeq: Int
    let latestSeq: Int
    let replayGap: Bool
    let missingTimeIsUnknown: Bool
    let interpolationPerformed: Bool

    enum CodingKeys: String, CodingKey {
        case timeline
        case nextSeq = "next_seq"
        case latestSeq = "latest_seq"
        case replayGap = "replay_gap"
        case missingTimeIsUnknown = "missing_time_is_unknown"
        case interpolationPerformed = "interpolation_performed"
    }
}

struct ArmorSyntheticSenses: Decodable {
    struct Signal: Decodable, Identifiable {
        let id: String
        let label: String
        let value: Double
        let unit: String
        let derived: Bool
        let worldFact: Bool
        let interpretation: String

        enum CodingKeys: String, CodingKey {
            case id, label, value, unit, derived, interpretation
            case worldFact = "world_fact"
        }
    }

    let signals: [Signal]
    let eventCount: Int
    let replayGap: Bool
    let derivedOnly: Bool

    enum CodingKeys: String, CodingKey {
        case signals
        case eventCount = "event_count"
        case replayGap = "replay_gap"
        case derivedOnly = "derived_only"
    }
}

struct ArmorCausalDebugger: Decodable {
    struct Report: Decodable, Identifiable {
        var id: String { hypothesisID }
        let hypothesisID: String
        let claimUnderTest: String
        let status: String
        let supportingObservationIDs: [String]
        let contradictingObservationIDs: [String]
        let independentLineageCount: Int
        let missingEvidence: [String]
        let alternativeExplanations: [String]
        let causalConclusion: Bool
        let interventionPerformed: Bool

        enum CodingKeys: String, CodingKey {
            case hypothesisID = "hypothesis_id"
            case claimUnderTest = "claim_under_test"
            case status
            case supportingObservationIDs = "supporting_observation_ids"
            case contradictingObservationIDs = "contradicting_observation_ids"
            case independentLineageCount = "independent_lineage_count"
            case missingEvidence = "missing_evidence"
            case alternativeExplanations = "alternative_explanations"
            case causalConclusion = "causal_conclusion"
            case interventionPerformed = "intervention_performed"
        }
    }

    let reports: [Report]
    let causalClaims: Int
    let externalActions: Int
    let qualifier: String

    enum CodingKeys: String, CodingKey {
        case reports, qualifier
        case causalClaims = "causal_claims"
        case externalActions = "external_actions"
    }
}

struct ArmorParallelExistence: Decodable {
    let runID: String
    let durationMS: Int
    let parallelTaskCount: Int
    let okCount: Int
    let degradedCount: Int
    let remoteAuthorityExpansion: Bool
    let externalActions: Int

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case durationMS = "duration_ms"
        case parallelTaskCount = "parallel_task_count"
        case okCount = "ok_count"
        case degradedCount = "degraded_count"
        case remoteAuthorityExpansion = "remote_authority_expansion"
        case externalActions = "external_actions"
    }
}

struct ArmorPresenceGrant: Decodable, Identifiable {
    let id: String
    let actuatorKind: String
    let targetID: String
    let targetLabel: String
    let createdAt: String
    let expiresAt: String
    let state: String
    let maxUses: Int
    let useCount: Int
    let remainingUses: Int

    enum CodingKeys: String, CodingKey {
        case id, state
        case actuatorKind = "actuator_kind"
        case targetID = "target_id"
        case targetLabel = "target_label"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
        case maxUses = "max_uses"
        case useCount = "use_count"
        case remainingUses = "remaining_uses"
    }
}

struct ArmorPresenceReceipt: Decodable, Identifiable {
    let id: String
    let grantID: String
    let requestedAt: String
    let completedAt: String?
    let requestedState: Int
    let status: String
    let verificationBasis: String
    let message: String
    let physicalEffectVerified: Bool?

    enum CodingKeys: String, CodingKey {
        case id, status, message
        case grantID = "grant_id"
        case requestedAt = "requested_at"
        case completedAt = "completed_at"
        case requestedState = "requested_state"
        case verificationBasis = "verification_basis"
        case physicalEffectVerified = "physical_effect_verified"
    }
}

struct ArmorPresenceState: Decodable {
    let grants: [ArmorPresenceGrant]
    let receipts: [ArmorPresenceReceipt]
}

struct ArmorPresenceDispatchReceipt: Decodable {
    let requestID: String
    let grantID: String
    let status: String
    let verificationBasis: String
    let physicalEffectVerified: Bool
    let requestedState: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case requestID = "request_id"
        case grantID = "grant_id"
        case verificationBasis = "verification_basis"
        case physicalEffectVerified = "physical_effect_verified"
        case requestedState = "requested_state"
    }
}

struct ArmorPresenceRevoke: Decodable {
    let grantID: String
    let revoked: Bool

    enum CodingKeys: String, CodingKey {
        case grantID = "grant_id"
        case revoked
    }
}

struct WorldArmorView: View {
    @EnvironmentObject private var appModel: JarvisAppModel
    @Environment(\.scenePhase) private var scenePhase

    @State private var capabilities: ArmorCapabilities?
    @State private var investigations: [ArmorInvestigation] = []
    @State private var watches: [ArmorWatch] = []
    @State private var watchInterval = 60
    @State private var watchChecks = 6
    @State private var watchLifetime = 6
    @State private var attentionKind = "off"
    @State private var attentionAQI = 100.0
    @State private var attentionMagnitude = 4.0
    @State private var attentionCooldown = 60
    @State private var notices: [ArmorNotice] = []
    @State private var unreadNotices = 0
    @State private var hasNoticeBaseline = false
    @State private var seenNoticeIDs: Set<String> = []
    @State private var showAttentionBanner = false
    @State private var attentionBannerText = ""
    @State private var foregroundAttentionOptIn = false
    @State private var publicCameras: [ArmorPublicCamera] = []
    @State private var cameraProviders: [ArmorPublicCameraProviderStatus] = []
    @State private var cameraReceipts: [ArmorCameraReceipt] = []
    @State private var selectedCameraRef = ""
    @State private var publicCameraURL = ""
    @State private var publicPageMedia: [ArmorPublicPageMediaCandidate] = []
    @State private var cameraCondition = ""
    @State private var cameraWatch: ExternalWatchSummary?
    @State private var cameraWatchImportID = ""
    @State private var cameraStatus = "No public camera requested."
    @State private var platformSources: [ArmorPlatformSource] = []
    @State private var platformTotal = 0
    @State private var platformNextOffset: Int?
    @State private var platformKind = "public_https"
    @State private var platformLocator = ""
    @State private var platformLabel = "Public camera"
    @State private var platformGoal = ""
    @State private var platformTerms = ""
    @State private var platformGrantClass = "public_publisher"
    @State private var platformAutomated = false
    @State private var platformCadence = "60"
    @State private var platformMinInterval = "0"
    @State private var platformRetentionDays = "30"
    @State private var platformLatitude = ""
    @State private var platformLongitude = ""
    @State private var platformActiveID: String?
    @State private var platformEvidence: [ArmorPlatformObservation] = []
    @State private var platformNotices: [ArmorPlatformNotice] = []
    @State private var platformCombinedSummary = ""
    @State private var platformStatus = "No source registry check performed."
    @State private var movementSources: [ArmorMovementSource] = []
    @State private var movementTotal = 0
    @State private var movementNextOffset: Int?
    @State private var movementKind = "opensky_region"
    @State private var movementLabel = "Public movement region"
    @State private var movementTerms = ""
    @State private var movementGrantClass = "public_publisher"
    @State private var movementAutomated = false
    @State private var movementCadence = "60"
    @State private var movementMinInterval = "0"
    @State private var movementRetention = "7"
    @State private var movementLatitude = "34.0500"
    @State private var movementLongitude = "-118.2500"
    @State private var movementRadius = "80"
    @State private var movementEntities: [ArmorMovementEntity] = []
    @State private var movementEntityType = ""
    @State private var movementStatus = "No movement source queried."
    @State private var distributedWorkers: [ArmorDistributedWorker] = []
    @State private var pushStatus: ArmorPushStatus?
    @State private var fullScopeStatus: ArmorFullStatus?
    @State private var realityBrowser: ArmorRealityBrowser?
    @State private var syntheticSenses: ArmorSyntheticSenses?
    @State private var causalDebugger: ArmorCausalDebugger?
    @State private var parallelExistence: ArmorParallelExistence?
    @State private var presenceState: ArmorPresenceState?
    @State private var liveFabricStatus: ArmorLiveStatus?
    @State private var liveEvents: [ArmorLiveEvent] = []
    @State private var selectedID: String?
    @State private var label = "Selected corridor"
    @State private var latitude = "34.12000"
    @State private var longitude = "-118.16000"
    @State private var radius = "30"
    @State private var asKnownAt = ""
    @State private var replayResult: ArmorReplay?
    @State private var changes: ArmorChangeReport?
    @State private var correlations: ArmorCorrelationReport?
    @State private var evidenceGraph: ArmorEvidenceGraph?
    @State private var sampleTimes: [ArmorSampleMoment] = []
    @State private var correlationWindowHours = 6
    @State private var correlationQueryRadiusKM = 30.0
    @State private var correlationEnd = Date()
    @State private var busy = false
    @State private var confirmForget = false
    @State private var status = "World Armor is off until enabled on your Jarvis backend."

    private var client: JarvisAPIClient {
        JarvisAPIClient(
            baseURL: appModel.settings.baseURL,
            fallbackBaseURL: appModel.settings.fallbackBaseURL,
            apiToken: appModel.settings.apiToken,
            sessionID: appModel.settings.conversationSessionID
        )
    }

    private var selected: ArmorInvestigation? {
        investigations.first { $0.id == selectedID }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                heading
                sourceConsole
                fullScopeConsole
                liveFabricConsole
                movementConsole
                enrollment
                saved
                if let selected {
                    selectedRegion(selected)
                    actions
                    standingWatches
                    attentionInbox
                    publicCameraWorkbench
                    if let changes { changePanel(changes) }
                    temporalQueryPanel
                    if let correlations { correlationPanel(correlations) }
                    if let evidenceGraph { hypothesisPanel(evidenceGraph) }
                    if let replayResult { replayPanel(replayResult) }
                }
            }
            .padding()
        }
        .navigationTitle("World Armor")
        .navigationBarTitleDisplayMode(.inline)
        .task { await refresh() }
        .task(id: selectedID) { await pollAttentionInbox() }
        .onChange(of: selectedID) { _, _ in
            publicCameras = []
            cameraProviders = []
            cameraReceipts = []
            selectedCameraRef = ""
            publicCameraURL = ""
            publicPageMedia = []
            cameraWatch = nil
        }
        .alert("World Armor attention", isPresented: $showAttentionBanner) {
            Button("View inbox") { showAttentionBanner = false }
        } message: {
            Text(attentionBannerText)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                replayResult = nil
                changes = nil
                correlations = nil
                evidenceGraph = nil
                sampleTimes = []
                platformEvidence = []
                platformNotices = []
                platformActiveID = nil
                platformCombinedSummary = ""
                movementEntities = []
                notices = []
                unreadNotices = 0
                seenNoticeIDs = []
                hasNoticeBaseline = false
                showAttentionBanner = false
                publicCameras = []
                cameraProviders = []
                cameraReceipts = []
                selectedCameraRef = ""
                publicCameraURL = ""
                publicPageMedia = []
                cameraWatch = nil
                status = "Sensitive investigation evidence hidden while app is inactive."
            }
        }
        .confirmationDialog(
            "Forget this investigation and all of its local evidence?",
            isPresented: $confirmForget,
            titleVisibility: .visible
        ) {
            Button("Forget saved investigation", role: .destructive) {
                Task { await forgetSelected() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the stored region and its samples. It cannot "
                 + "erase source-provider records or independent backups.")
        }
    }

    private var heading: some View {
        GroupBox("World Armor • event instrument") {
            VStack(alignment: .leading, spacing: 8) {
                Text("Explicitly save one region, sample three existing public "
                     + "provider families on demand, replay source receipts, "
                     + "and inspect source-qualified changes.")
                Text("No private-camera access, person tracking, arbitrary "
                     + "remote commands, autonomous action or guaranteed global coverage.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let capabilities {
                    Text(capabilities.enabled
                         ? "Backend feature enabled • one-shot collection only"
                         : "Backend feature OFF • set JARVIS_WORLD_ARMOR_ENABLED=1")
                        .font(.subheadline.weight(.medium))
                    ForEach(capabilities.providers) { provider in
                        Text(provider.id + " • " + provider.coverage)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(status)
                    .font(.caption)
                    .accessibilityIdentifier("world-armor-status")
                Button(busy ? "Working…" : "Refresh status") {
                    Task { await refresh() }
                }
                .buttonStyle(.bordered)
                .disabled(busy)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var enrollment: some View {
        GroupBox("1 · Enroll a bounded region") {
            VStack(alignment: .leading, spacing: 9) {
                TextField("Label", text: $label)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    TextField("Latitude", text: $latitude)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Longitude", text: $longitude)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Radius km", text: $radius)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.decimalPad)
                        .frame(maxWidth: 110)
                }
                Text("Coordinate entry is deliberate: no GPS, contacts, "
                     + "Calendar or MapKit place match is read automatically. "
                     + "Region expires after 24 hours.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Button("Create investigation") {
                    Task { await create() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true)
            }
        }
    }

    private var saved: some View {
        GroupBox("2 · Saved investigations") {
            VStack(alignment: .leading, spacing: 9) {
                if investigations.isEmpty {
                    Text("None enrolled. No automatic world collection.")
                        .font(.caption)
                }
                ForEach(investigations) { entry in
                    Button {
                        selectedID = entry.id
                        correlationQueryRadiusKM = entry.radiusKM
                        asKnownAt = ""
                        replayResult = nil
                        changes = nil
                        correlations = nil
                        evidenceGraph = nil
                        sampleTimes = []
                        status = "Selected " + entry.label
                        Task { await replay() }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(entry.label).font(.subheadline.weight(.medium))
                                Text("\(entry.sampleCount) samples • "
                                     + String(format: "%.2f, %.2f", entry.latitude, entry.longitude)
                                     + " • \(entry.radiusKM) km")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: selectedID == entry.id
                                  ? "checkmark.circle.fill" : "circle")
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func selectedRegion(_ entry: ArmorInvestigation) -> some View {
        GroupBox("Selected region • \(entry.label)") {
            VStack(alignment: .leading, spacing: 8) {
                Map(initialPosition: .region(MKCoordinateRegion(
                    center: CLLocationCoordinate2D(
                        latitude: entry.latitude, longitude: entry.longitude
                    ),
                    span: MKCoordinateSpan(
                        latitudeDelta: max(0.02, entry.radiusKM / 55.0),
                        longitudeDelta: max(0.02, entry.radiusKM / 55.0)
                    )
                ))) {
                    Marker(entry.label, coordinate: CLLocationCoordinate2D(
                        latitude: entry.latitude, longitude: entry.longitude
                    ))
                    MapCircle(
                        center: CLLocationCoordinate2D(
                            latitude: entry.latitude, longitude: entry.longitude
                        ),
                        radius: max(1, min(entry.radiusKM, correlationQueryRadiusKM)) * 1_000
                    )
                    .foregroundStyle(Color.blue.opacity(0.10))
                    if let correlations {
                        ForEach(correlations.timedObservations) { observation in
                            if observation.source == "usgs_earthquakes",
                               let eventLat = observation.values.latitude,
                               let eventLon = observation.values.longitude {
                                Marker(
                                    observation.values.magnitude.map {
                                        "USGS M" + String(format: "%.1f", $0)
                                    } ?? "USGS report",
                                    coordinate: CLLocationCoordinate2D(
                                        latitude: eventLat, longitude: eventLon
                                    )
                                )
                                .tint(.orange)
                            }
                        }
                    }
                }
                .frame(height: 230)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("Map of explicitly saved investigation region")
                Text("The circle is your requested radial search area, NOT "
                     + "verified sensor coverage or a surveyed boundary. "
                     + "Map tiles may be requested from Apple.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Expires: " + entry.expiresAt)
                    .font(.caption2)
            }
        }
    }

    private var actions: some View {
        GroupBox("3 · Observe, rewind and compare") {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Button("Observe once") { Task { await observe() } }
                        .buttonStyle(.borderedProminent)
                    Button("Compare last two") { Task { await compare() } }
                        .buttonStyle(.bordered)
                }
                .disabled(busy || capabilities?.enabled != true)
                if !sampleTimes.isEmpty {
                    Menu("Rewind to a retained receipt") {
                        Button("Latest saved evidence") { asKnownAt = "" }
                        ForEach(sampleTimes) { item in
                            Button(item.receivedAt + " • " + item.adapterMode
                                   + " • " + item.coverageSummary) {
                                asKnownAt = item.receivedAt
                                Task { await replay() }
                            }
                        }
                    }
                    .disabled(busy || capabilities?.enabled != true)
                }
                TextField("Optional as-known-at ISO time (UTC or offset)", text: $asKnownAt)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                HStack {
                    Button("Replay retained evidence") { Task { await replay() } }
                        .buttonStyle(.bordered)
                        .disabled(busy || capabilities?.enabled != true)
                    Button("Forget", role: .destructive) {
                        confirmForget = true
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                Text("Two samples cannot establish continuous monitoring. "
                     + "An unavailable provider cannot imply nothing happened.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // The MapKit center is a user-enrolled query scope, NOT an event location.
    // These queries never fetch providers, enroll watches or operate machines.
    private var standingWatches: some View {
        GroupBox("4 · Explicit standing watches") {
            VStack(alignment: .leading, spacing: 9) {
                Text("The selected public region can be checked by the "
                     + "separate, explicitly started Jarvis host runner. "
                     + "Enrolling a watch does NOT start that process or "
                     + "contact providers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if capabilities?.scheduledWatches != true {
                    Text("Host standing-watch opt-in is OFF. Existing grants "
                         + "remain visible for Stop or investigation Forget.")
                        .font(.caption)
                }
                HStack {
                    Picker("Every", selection: $watchInterval) {
                        Text("30 min").tag(30)
                        Text("60 min").tag(60)
                        Text("2 hours").tag(120)
                        Text("6 hours").tag(360)
                    }
                    .pickerStyle(.menu)
                    Stepper("Max \(watchChecks) checks", value: $watchChecks,
                            in: 1...12)
                }
                Stepper("Expire after \(watchLifetime) hours",
                        value: $watchLifetime, in: 1...24)
                Picker("Evidence attention", selection: $attentionKind) {
                    Text("No notices").tag("off")
                    Text("Modelled AQI threshold crossing")
                        .tag("modelled_aqi_threshold_crossed")
                    Text("New USGS report").tag("new_usgs_report")
                    Text("New NWS alert").tag("new_nws_alert")
                }
                .pickerStyle(.menu)
                if attentionKind == "modelled_aqi_threshold_crossed" {
                    Stepper("Modelled AQI: \(Int(attentionAQI))",
                            value: $attentionAQI, in: 50...300, step: 25)
                }
                if attentionKind == "new_usgs_report" {
                    Stepper("Reported magnitude: \(attentionMagnitude.formatted())",
                            value: $attentionMagnitude, in: 2.5...8, step: 0.5)
                }
                if attentionKind != "off" {
                    Picker("Notice cooldown", selection: $attentionCooldown) {
                        Text("30 minutes").tag(30)
                        Text("60 minutes").tag(60)
                        Text("2 hours").tag(120)
                        Text("6 hours").tag(360)
                    }
                    .pickerStyle(.menu)
                }
                Button("Enroll bounded watch") {
                    Task { await enrollWatch() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true
                          || capabilities?.scheduledWatches != true)
                Text("Host runner requires separate local opt-in. Typed "
                     + "rules save source-qualified INBOX notices, NOT "
                     + "remote push or emergency alerts. First sampled "
                     + "evidence establishes the baseline; no external actions.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                ForEach(watches.filter { $0.investigationID == selectedID }) { item in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(item.state.uppercased()
                             + " · \(item.checkCount)/\(item.maxChecks) checks"
                             + " · every \(item.intervalMinutes) min")
                            .font(.subheadline.weight(.medium))
                        Text("Next scheduled: " + item.nextDueAt
                             + " · expires " + item.expiresAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let outcome = item.lastOutcome {
                            Text("Last receipt: " + outcome)
                                .font(.caption2)
                        }
                        if let kind = item.attentionKind, kind != "off" {
                            Text("Attention: " + kind.replacingOccurrences(
                                of: "_", with: " "
                            ) + " · cooldown \(item.attentionCooldownMinutes ?? 60) min")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        if let difference = item.lastChangeState {
                            Text("Source comparison: " + difference
                                 .replacingOccurrences(of: "_", with: " "))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        HStack {
                            if item.state == "active" {
                                Button("Pause") {
                                    Task { await changeWatch(item.id, action: "pause") }
                                }
                                .disabled(busy || capabilities?.scheduledWatches != true)
                            }
                            if item.state == "paused" {
                                Button("Resume") {
                                    Task { await changeWatch(item.id, action: "resume") }
                                }
                                .disabled(busy || capabilities?.scheduledWatches != true)
                            }
                            if item.state == "active" || item.state == "paused" {
                                Button("Stop permanently", role: .destructive) {
                                    Task { await changeWatch(item.id, action: "stop") }
                                }
                                .disabled(busy)
                            } else {
                                Button("Forget watch", role: .destructive) {
                                    Task { await forgetWatch(item.id) }
                                }
                                .disabled(busy)
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(8)
                    .background(.thinMaterial,
                                in: RoundedRectangle(cornerRadius: 10))
                }
                Button("Refresh watch receipts") {
                    Task { await refreshWatches() }
                }
                .disabled(busy)
            }
        }
    }

    private var attentionInbox: some View {
        GroupBox("5 · Evidence attention inbox · \(unreadNotices) unread") {
            VStack(alignment: .leading, spacing: 9) {
                Toggle("In-app banners while World Armor is open",
                       isOn: $foregroundAttentionOptIn)
                Text("Private inbox only. In-app banners require this view "
                     + "to be open and active. No remote push, background "
                     + "wake, emergency dispatch or all-clear.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Button("Refresh attention inbox") {
                    Task { await refreshNotices(alertOnNew: false) }
                }
                .disabled(busy)
                ForEach(notices) { notice in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(notice.summary)
                            .font(.subheadline.weight(
                                notice.readAt == nil ? .semibold : .regular
                            ))
                        Text(notice.source + " · received " + notice.receivedAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let observed = notice.observedAt {
                            Text("Source/model time: " + observed)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("Source event time unavailable; receipt only.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        HStack {
                            if notice.readAt == nil {
                                Button("Mark read") {
                                    Task { await changeNotice(notice.id, action: "read") }
                                }
                            }
                            Button("Forget notice", role: .destructive) {
                                Task { await changeNotice(notice.id, action: "forget") }
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(busy)
                    }
                    .padding(8)
                    .background(.thinMaterial,
                                in: RoundedRectangle(cornerRadius: 10))
                }
                if notices.isEmpty {
                    Text("No retained notices. This does not establish safety.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var fullScopeConsole: some View {
        GroupBox("World Armor v8 · full suit") {
            VStack(alignment: .leading, spacing: 10) {
                if let fullScopeStatus {
                    HStack {
                        Text(fullScopeStatus.enabled ? "Full-scope layer enabled" : "Full-scope layer disabled")
                            .font(.headline)
                        Spacer()
                        Text("\(fullScopeStatus.registeredWorkers) workers")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Group {
                        Text("Reality Browser · \(fullScopeStatus.layers.realityBrowser)")
                        Text("Synthetic Senses · \(fullScopeStatus.layers.syntheticSenses)")
                        Text("Causal Debugger · \(fullScopeStatus.layers.causalDebugger)")
                        Text("Parallel Existence · \(fullScopeStatus.layers.parallelExistence)")
                        Text("Presence · \(fullScopeStatus.layers.presence)")
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    Text(fullScopeStatus.qualifier)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                } else {
                    Text("Full-scope status not checked.")
                        .font(.headline)
                }

                HStack {
                    Button("Refresh full suit") {
                        Task { await refreshFullScope(runAnalysis: false) }
                    }
                    .buttonStyle(.bordered)
                    Button("Run parallel analysis") {
                        Task { await refreshFullScope(runAnalysis: true) }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .disabled(busy)

                if let parallelExistence {
                    Text("Parallel Existence: \(parallelExistence.okCount)/\(parallelExistence.parallelTaskCount) "
                         + "tasks healthy · \(parallelExistence.durationMS) ms"
                         + (parallelExistence.degradedCount > 0
                            ? " · \(parallelExistence.degradedCount) degraded" : ""))
                        .font(.caption)
                }

                if let syntheticSenses {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Synthetic Senses")
                            .font(.subheadline.weight(.semibold))
                        ForEach(syntheticSenses.signals.prefix(5)) { signal in
                            Text(signal.label + ": "
                                 + String(format: "%.2f", signal.value)
                                 + " " + signal.unit)
                                .font(.caption)
                        }
                        Text("Derived signals are explicitly synthetic; they are not direct world facts.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                if let realityBrowser {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Reality Browser")
                            .font(.subheadline.weight(.semibold))
                        ForEach(realityBrowser.timeline.suffix(8).reversed()) { item in
                            Text((item.time ?? "time unknown") + " · " + item.summary)
                                .font(.caption2)
                                .lineLimit(2)
                        }
                        if realityBrowser.replayGap {
                            Text("Replay gap: retained history does not cover the saved cursor.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                if let causalDebugger {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Causal Debugger")
                            .font(.subheadline.weight(.semibold))
                        if causalDebugger.reports.isEmpty {
                            Text("No bounded candidate hypothesis in the selected window.")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        ForEach(causalDebugger.reports.prefix(3)) { report in
                            Text(report.claimUnderTest)
                                .font(.caption)
                            Text("Mechanism: " + report.status
                                 + " · causal conclusion: "
                                 + (report.causalConclusion ? "yes" : "no"))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Divider()
                Text("Presence · authorized physical embodiment")
                    .font(.subheadline.weight(.semibold))
                Text("Each tap creates a short-lived one-use World Armor grant for one exact Apple Home light. "
                     + "The iPhone performs the HomeKit write and posts fresh accessory readback separately.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if appModel.homeEnvironment.lights.isEmpty {
                    Button("Discover Apple Home lights") {
                        appModel.homeEnvironment.discover()
                    }
                    .buttonStyle(.bordered)
                } else {
                    ForEach(appModel.homeEnvironment.lights.prefix(8)) { light in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(light.name)
                                    .font(.caption)
                                Text(light.room + (light.reachable ? "" : " · unreachable"))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("On") {
                                Task {
                                    await runPresence(
                                        lightID: light.id,
                                        label: light.name,
                                        desiredOn: true
                                    )
                                }
                            }
                            Button("Off") {
                                Task {
                                    await runPresence(
                                        lightID: light.id,
                                        label: light.name,
                                        desiredOn: false
                                    )
                                }
                            }
                            .disabled(!light.reachable || busy)
                        }
                    }
                }
                if let recent = presenceState?.receipts.first {
                    Text("Latest Presence receipt: " + recent.status
                         + " · " + recent.message)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var liveFabricConsole: some View {
        GroupBox("World Armor v7 · live fabric") {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    if let liveFabricStatus {
                        Text(liveFabricStatus.running ? "Supervisor running" : "Supervisor stopped")
                            .font(.headline)
                        Spacer()
                        Text("\(liveFabricStatus.journalEvents) retained events")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Live fabric status not checked")
                            .font(.headline)
                    }
                }
                if let liveFabricStatus {
                    Text("cycles \(liveFabricStatus.cycleCount)"
                         + (liveFabricStatus.lastCycleMS.map { " · last \($0) ms" } ?? "")
                         + (liveFabricStatus.heartbeatAgeSeconds.map {
                             " · heartbeat " + String(format: "%.0f", $0) + "s ago"
                         } ?? ""))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if !liveFabricStatus.lastError.isEmpty {
                        Text("Degraded: " + liveFabricStatus.lastError)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Toggle(
                    "Notifications for warning/urgent World Armor events",
                    isOn: Binding(
                        get: { appModel.settings.worldArmorLiveAlertsEnabled },
                        set: { appModel.settings.worldArmorLiveAlertsEnabled = $0 }
                    )
                )
                Text("The durable journal replays missed events after reconnect. "
                     + "When APNs credentials and this signed app's push entitlement "
                     + "are configured, warning/urgent events can also arrive while "
                     + "the app is closed. In-app/local delivery remains a fallback.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let pushStatus {
                    Group {
                        Text(pushStatus.providerConfigured
                             ? "Closed-app APNs · provider configured"
                             : "Closed-app APNs · provider not configured")
                        Text("Devices \(pushStatus.registeredDevices) · pending \(pushStatus.pending)")
                        if pushStatus.dead > 0 {
                            Text("Dead deliveries \(pushStatus.dead)")
                        }
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
                HStack {
                    Button("Start live supervisor") {
                        Task { await setLiveSupervisor(running: true) }
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Stop") {
                        Task { await setLiveSupervisor(running: false) }
                    }
                    .buttonStyle(.bordered)
                    Button("Refresh") {
                        Task { await refreshLiveFabric() }
                    }
                    .buttonStyle(.bordered)
                }
                .disabled(busy)
                ForEach(liveEvents.prefix(12)) { event in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(event.summary)
                            .font(.caption)
                        Text("#\(event.seq) · \(event.subsystem) · "
                             + event.priority + " · " + event.createdAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                if liveEvents.isEmpty {
                    Text("No retained live events yet.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var movementConsole: some View {
        GroupBox("World Armor v3 · planetary movement graph") {
            VStack(alignment: .leading, spacing: 9) {
                HStack {
                    Text("Observation workers · \(distributedWorkers.count)")
                        .font(.headline)
                    Button("Refresh workers") {
                        Task { await refreshDistributedWorkers() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                ForEach(distributedWorkers) { worker in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(worker.id + " · " + worker.status + " · "
                             + worker.capabilities.joined(separator: ", "))
                            .font(.caption2)
                        if let metrics = worker.workerMetrics {
                            Text("load "
                                 + String(format: "%.2f", metrics.normalizedLoad)
                                 + " · active \(metrics.activeRequests)/\(metrics.capacity)"
                                 + (worker.dispatchHealth?.cooldownUntil != nil
                                    ? " · cooling down" : ""))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Text("Workers only run typed read-only observation tasks. "
                     + "The controller schedules by capability, reported load, "
                     + "capacity and recent failures while retaining grants, "
                     + "cadence, normalization and evidence authority. Opening "
                     + "this app does not start the distributed runner.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Public aircraft and vessel state becomes typed movement "
                     + "evidence: entity → position → heading/speed → source "
                     + "time → bounded local history. Transport identifiers "
                     + "are not treated as people, owners or passenger records.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Picker("Movement provider", selection: $movementKind) {
                    Text("OpenSky · selected region").tag("opensky_region")
                    Text("OpenSky · provider-global").tag("opensky_global")
                    Text("AISStream · selected region").tag("aisstream_region")
                }
                .pickerStyle(.menu)
                TextField("Source label", text: $movementLabel)
                Picker("Declared source permission",
                       selection: $movementGrantClass) {
                    Text("Publisher/public data terms").tag("public_publisher")
                    Text("My API/license contract").tag("api_contract")
                    Text("Owned or explicitly authorized").tag("owned_or_authorized")
                }
                .pickerStyle(.menu)
                TextField("Provider terms / permission reference (required)",
                          text: $movementTerms)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Toggle("I have permission for automated polling",
                       isOn: $movementAutomated)
                if movementAutomated {
                    HStack {
                        TextField("Cadence sec", text: $movementCadence)
                            .keyboardType(.numberPad)
                        TextField("Provider minimum sec",
                                  text: $movementMinInterval)
                            .keyboardType(.numberPad)
                    }
                }
                TextField("Derived track retention days",
                          text: $movementRetention)
                    .keyboardType(.numberPad)
                if movementKind != "opensky_global" {
                    HStack {
                        TextField("Latitude", text: $movementLatitude)
                            .keyboardType(.numbersAndPunctuation)
                        TextField("Longitude", text: $movementLongitude)
                            .keyboardType(.numbersAndPunctuation)
                        TextField("Radius km", text: $movementRadius)
                            .keyboardType(.decimalPad)
                    }
                } else {
                    Text("Provider-global OpenSky can consume more provider "
                         + "credits and bandwidth. Jarvis does not impose a "
                         + "smaller artificial geography, but the provider's "
                         + "actual terms, quota and host resources still govern.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                HStack {
                    Button("Enroll movement source") {
                        Task { await enrollMovementSource() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(busy || movementTerms.isEmpty)
                    Button("Refresh sources") {
                        Task { await refreshMovementSources() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                Text("Enrolled movement sources · \(movementTotal)")
                    .font(.headline)
                ForEach(movementSources) { source in
                    movementSourceRow(source)
                }
                if movementNextOffset != nil {
                    Button("Load more movement sources") {
                        Task { await loadMoreMovementSources() }
                    }
                    .disabled(busy)
                }
                Divider()
                Text("Query retained latest movement near a point")
                    .font(.subheadline.weight(.medium))
                Picker("Entity type", selection: $movementEntityType) {
                    Text("Aircraft + vessels").tag("")
                    Text("Aircraft").tag("aircraft")
                    Text("Vessels").tag("vessel")
                }
                .pickerStyle(.segmented)
                Button("Show retained movement near entered point") {
                    Task { await queryNearbyMovement() }
                }
                .buttonStyle(.bordered)
                .disabled(busy)
                ForEach(movementEntities) { entity in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(
                            (entity.lastName ?? entity.lastCallsign
                             ?? entity.entityID)
                            + " · " + entity.entityType
                        )
                        .font(.subheadline.weight(.medium))
                        Text(
                            "\(entity.latitude.formatted()), "
                            + "\(entity.longitude.formatted())"
                            + (entity.distanceKM != nil
                               ? " · \(entity.distanceKM!.formatted()) km"
                               : "")
                        )
                        .font(.caption)
                        Text(
                            "Source time: "
                            + (entity.providerTime ?? entity.observedAt)
                            + " · " + entity.sourceName
                        )
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    }
                    Divider()
                }
                Text(movementStatus)
                    .font(.caption)
                Text("No owner/passenger/crew inference. No missing track "
                     + "is treated as evidence that an area is clear. "
                     + "AISStream requires a server-side API key; OpenSky "
                     + "coverage and quota are provider-dependent.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func movementSourceRow(
        _ source: ArmorMovementSource
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(source.label + " · " + source.kind)
                .font(.subheadline.weight(.medium))
            Text(
                source.globalScope
                ? "global provider scope"
                : "\(source.latitude?.formatted() ?? "?"), "
                  + "\(source.longitude?.formatted() ?? "?")"
                  + " · \(source.radiusKM?.formatted() ?? "?") km"
            )
            .font(.caption)
            Text(
                "\(source.checkCount) checks · "
                + (source.cadenceSeconds > 0
                   ? "every \(source.cadenceSeconds)s"
                   : "manual only")
                + " · retain \(source.retentionDays)d"
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
            HStack {
                Button("Collect now") {
                    Task { await collectMovementSource(source.id) }
                }
                .disabled(busy || source.state != "active")
                Button(source.state == "active" ? "Pause" : "Resume") {
                    Task {
                        await changeMovementSource(
                            source.id,
                            action: source.state == "active"
                                ? "pause" : "resume"
                        )
                    }
                }
                .disabled(busy || source.state == "stopped")
                Button("Stop", role: .destructive) {
                    Task {
                        await changeMovementSource(
                            source.id, action: "stop"
                        )
                    }
                }
                .disabled(busy || source.state == "stopped")
            }
            .buttonStyle(.bordered)
            Button("Forget movement source + local track history",
                   role: .destructive) {
                Task { await forgetMovementSource(source.id) }
            }
            .buttonStyle(.bordered)
            .disabled(busy)
        }
        .padding(8)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }

    private var sourceConsole: some View {
        GroupBox("World Armor v2 · open observation platform") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Persistent, explicitly enrolled source grants. No fixed "
                     + "camera count or 72-hour watch expiry. Each camera has "
                     + "its own access terms, polling cadence and retention. "
                     + "A public website is not automatically permission "
                     + "for continuous scraping or recording.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("Source label", text: $platformLabel)
                Picker("Source adapter", selection: $platformKind) {
                    Text("Exact public HTTPS media").tag("public_https")
                    Text("Exact public HTTP media · insecure").tag("public_http")
                    Text("Caltrans catalog ID").tag("caltrans")
                    Text("Windy Webcams ID").tag("windy")
                }
                .pickerStyle(.menu)
                TextField("Public media URL or official camera ID",
                          text: $platformLocator)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Goal: e.g., is the road visibly flooded?",
                          text: $platformGoal)
                Picker("Declared source permission", selection: $platformGrantClass) {
                    Text("Publisher's public media").tag("public_publisher")
                    Text("My API/license contract").tag("api_contract")
                    Text("Owned or explicitly authorized").tag("owned_or_authorized")
                }
                .pickerStyle(.menu)
                TextField("Publisher terms or permission reference (required)",
                          text: $platformTerms)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Toggle("I have permission for automated polling",
                       isOn: $platformAutomated)
                if platformAutomated {
                    TextField("Check cadence in seconds",
                              text: $platformCadence)
                        .keyboardType(.numberPad)
                    TextField("Publisher's minimum interval (seconds)",
                              text: $platformMinInterval)
                        .keyboardType(.numberPad)
                }
                TextField("Keep derived evidence for days",
                          text: $platformRetentionDays)
                    .keyboardType(.numberPad)
                HStack {
                    TextField("Camera latitude (optional)",
                              text: $platformLatitude)
                        .keyboardType(.numbersAndPunctuation)
                    TextField("Camera longitude (optional)",
                              text: $platformLongitude)
                        .keyboardType(.numbersAndPunctuation)
                }
                if platformKind == "public_http" {
                    Text("HTTP is unencrypted and vulnerable to tampering. "
                         + "Enroll only this exact publicly accessible "
                         + "feed after checking publisher terms. "
                         + "Jarvis still blocks private IP destinations.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text("An entered camera point is operator-reported; "
                     + "it is not the camera's verified viewing footprint. "
                     + "Permissions are recorded but not independently "
                     + "certified by Jarvis. Raw frames are not archived.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                HStack {
                    Button("Enroll this exact source") {
                        Task { await enrollPlatformSource() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(busy || platformLocator.isEmpty
                              || platformTerms.isEmpty)
                    Button("Preflight active sources") {
                        Task { await planPlatformSources() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                HStack {
                    Text("Enrolled sources · \(platformTotal)")
                        .font(.headline)
                    Button("Refresh") {
                        Task { await refreshPlatformSources() }
                    }
                    .disabled(busy)
                }
                ForEach(platformSources) { source in
                    platformSourceRow(source)
                }
                if platformNextOffset != nil {
                    Button("Load more sources") {
                        Task { await loadMorePlatformSources() }
                    }
                    .disabled(busy)
                }
                if let id = platformActiveID {
                    Text("Evidence for " + String(id.prefix(8)))
                        .font(.subheadline.weight(.medium))
                    ForEach(platformEvidence) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(event.description)
                            Text("Model classification: "
                                 + (event.conditionStatus ?? "scene only"))
                                .font(.caption)
                            Text("Jarvis received: " + event.receivedAt
                                 + " · publisher capture time "
                                 + (event.sourceCaptureAt ?? "unknown"))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(event.changeKind.replacingOccurrences(
                                of: "_", with: " "
                            ))
                                .font(.caption2)
                        }
                        Divider()
                    }
                    ForEach(platformNotices) { notice in
                        Text("Watch notice: " + notice.summary)
                            .font(.caption)
                    }
                    if platformEvidence.isEmpty {
                        Text("No retained observations for this selected source.")
                            .font(.caption)
                    }
                }
                if let regionID = selectedID {
                    Button("Co-display cameras with selected region evidence") {
                        Task { await inspectCombinedPlatformEvidence(regionID) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                    if !platformCombinedSummary.isEmpty {
                        Text(platformCombinedSummary).font(.caption)
                    }
                }
                Text(platformStatus)
                    .font(.caption)
                Text("Host collector is not started by opening this view. "
                     + "Remote distributed workers and closed-app push "
                     + "have not been enabled.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func platformSourceRow(
        _ source: ArmorPlatformSource
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(source.label + " · " + source.kind)
                .font(.subheadline.weight(.medium))
            Text(source.sourceDisplay + " · " + source.state)
                .font(.caption)
            Text(source.sceneGoal.isEmpty
                 ? "General environmental scene description"
                 : "Observation goal: " + source.sceneGoal)
                .font(.caption)
            Text("\(source.checkCount) checks · "
                 + (source.cadenceSeconds > 0
                    ? "every \(source.cadenceSeconds)s"
                    : "manual only")
                 + " · retain \(source.retentionDays)d")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if let outcome = source.lastOutcome {
                Text("Last source outcome: " + outcome)
                    .font(.caption2)
            }
            HStack {
                Button("Inspect") {
                    Task { await observePlatformSource(source.id) }
                }
                .disabled(busy || source.state != "active")
                Button("Evidence") {
                    Task { await readPlatformEvidence(source.id) }
                }
                .disabled(busy)
                Button(source.state == "active" ? "Pause" : "Resume") {
                    Task {
                        await changePlatformSource(
                            source.id,
                            action: source.state == "active"
                                ? "pause" : "resume"
                        )
                    }
                }
                .disabled(busy || source.state == "stopped")
            }
            .buttonStyle(.bordered)
            HStack {
                Button("Stop", role: .destructive) {
                    Task { await changePlatformSource(source.id, action: "stop") }
                }
                .disabled(busy || source.state == "stopped")
                Button("Forget + erase evidence", role: .destructive) {
                    Task { await forgetPlatformSource(source.id) }
                }
                .disabled(busy)
            }
            .buttonStyle(.bordered)
        }
        .padding(8)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }

    private var publicCameraWorkbench: some View {
        GroupBox("6 · Public camera evidence · worldwide when configured") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Search opt-in Windy Webcams v3 (requires your API key) "
                     + "and Caltrans highway cameras in California. "
                     + "Alternatively paste ONE directly published public HTTPS "
                     + "image, MJPEG or unencrypted HLS address. No private "
                     + "camera scanning or guessed RTSP endpoints.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Find public cameras in this region") {
                    Task { await discoverRegionCameras() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true)
                ForEach(cameraProviders) { provider in
                    Text(provider.provider + " · " + provider.status
                         + (provider.keyRequired != nil
                            ? " · optional API key needed" : ""))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text("Provider coverage varies; camera location is not "
                     + "its verified viewing footprint.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                ForEach(publicCameras) { camera in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(camera.title + " · " + camera.provider)
                            .font(.subheadline.weight(.medium))
                        Button(selectedCameraRef == camera.id
                               ? "Selected · " + camera.id
                               : "Select this camera") {
                            selectedCameraRef = camera.id
                            publicCameraURL = ""
                        }
                        .buttonStyle(.bordered)
                        Button("Prepare persistent source grant for this camera") {
                            selectedCameraRef = camera.id
                            publicCameraURL = ""
                            platformKind = camera.id.hasPrefix("windy-")
                                ? "windy" : "caltrans"
                            platformLocator = camera.id
                            platformLabel = camera.title
                            platformLatitude = String(camera.latitude)
                            platformLongitude = String(camera.longitude)
                            platformStatus = "Source selected; review publisher "
                                + "access rights and terms at the source "
                                + "console before enrolling."
                        }
                        .buttonStyle(.bordered)
                        if selectedCameraRef == camera.id {
                            if let image = camera.imageURL,
                               let url = URL(string: image),
                               url.scheme == "https" {
                                AsyncImage(url: url) { phase in
                                    if let image = phase.image {
                                        image.resizable().scaledToFit()
                                    } else {
                                        Text("Publisher still unavailable; "
                                             + "not proof of a live feed.")
                                            .font(.caption2)
                                    }
                                }
                                .frame(maxHeight: 180)
                            }
                            if let link = camera.providerDetailURL,
                               let url = URL(string: link),
                               url.scheme == "https" {
                                Link("View publisher's camera page",
                                     destination: url)
                                    .font(.caption2)
                            }
                            if let note = camera.sourceNote {
                                Text(note)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .padding(8)
                    .background(.thinMaterial,
                                in: RoundedRectangle(cornerRadius: 10))
                }
                TextField("Exact public HTTPS still, MJPEG or HLS media URL",
                          text: $publicCameraURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Prepare this public media as persistent source") {
                    platformKind = "public_https"
                    platformLocator = publicCameraURL
                    platformLabel = "Selected public camera media"
                    platformLatitude = ""
                    platformLongitude = ""
                    platformStatus = "Source selected with UNKNOWN "
                        + "geography. Review exact publisher rights "
                        + "and permitted cadence before enrollment."
                }
                .buttonStyle(.bordered)
                .disabled(publicCameraURL.isEmpty)
                Text("An ordinary webcam webpage is not necessarily an "
                     + "image/stream URL. Passwords, signed access tokens, "
                     + "local IPs and private URLs are not accepted in this field.")
                Button("Find public image/stream links on this webpage") {
                    Task { await discoverPageMedia() }
                }
                .buttonStyle(.bordered)
                .disabled(busy || publicCameraURL.isEmpty)
                ForEach(publicPageMedia) { candidate in
                    Button("Choose " + candidate.source
                           + (candidate.sameOrigin ? "" : " · external media host")) {
                        publicCameraURL = candidate.url
                        selectedCameraRef = ""
                        publicPageMedia = []
                    }
                    .buttonStyle(.bordered)
                    .font(.caption)
                }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Picker("Observe", selection: $cameraCondition) {
                    Text("Describe visible scene").tag("")
                    Text("Obvious visible smoke").tag("smoke_visible")
                    Text("Apparent road congestion").tag("road_congestion")
                }
                .pickerStyle(.menu)
                HStack {
                    Button("Inspect one frame + retain evidence") {
                        Task { await inspectSelectedPublicCamera() }
                    }
                    .disabled(
                        busy || capabilities?.enabled != true
                        || (selectedCameraRef.isEmpty
                            && publicCameraURL.isEmpty)
                    )
                    Button("Watch exact camera · 3h") {
                        Task { await enrollExactCameraWatch() }
                    }
                    .disabled(
                        busy || capabilities?.enabled != true
                        || (selectedCameraRef.isEmpty
                            && publicCameraURL.isEmpty)
                    )
                }
                .buttonStyle(.bordered)
                if let watched = cameraWatch {
                    Text("External camera watch: " + watched.id
                         + " (separate, explicitly enrolled backend ledger)")
                        .font(.caption2)
                    Button("Stop this camera watch", role: .destructive) {
                        Task { await stopExactCameraWatch(watched.id) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                TextField("Personal camera watch ID to import",
                          text: $cameraWatchImportID)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                HStack {
                    Button("Check exact watch now + import one frame") {
                        Task { await checkAndImportCameraWatch() }
                    }
                    Button("Import saved watch frame (no network)") {
                        Task { await importSavedCameraWatch() }
                    }
                }
                .buttonStyle(.bordered)
                .disabled(busy || cameraWatchImportID.isEmpty)
                Text(cameraStatus)
                    .font(.caption)
                Divider()
                Text("Saved camera receipts • \(cameraReceipts.count)"
                     + " · no footage archive or verified capture time")
                    .font(.subheadline.weight(.medium))
                Button("Refresh retained camera evidence") {
                    Task { await refreshCameraEvidence() }
                }
                .disabled(busy)
                ForEach(cameraReceipts) { receipt in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(receipt.title + " · " + receipt.provider)
                            .font(.subheadline.weight(.medium))
                        Text(receipt.description)
                        Text("Condition: " + (receipt.classification ?? "not requested")
                             + " · " + receipt.changeState.replacingOccurrences(
                                of: "_", with: " "
                             ))
                            .font(.caption2)
                        Text("Received: " + receipt.receivedAt
                             + " · publisher capture time unknown")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(receipt.spatialBasis.replacingOccurrences(
                            of: "_", with: " "
                        ))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Button("Forget camera receipt", role: .destructive) {
                            Task { await forgetCameraEvidence(receipt.id) }
                        }
                        .buttonStyle(.bordered)
                        .disabled(busy)
                    }
                    .padding(8)
                    .background(.thinMaterial,
                                in: RoundedRectangle(cornerRadius: 10))
                }
                Text("Retained camera evidence is receipt-time-only and "
                     + "does not assert physical event onset, identify people, "
                     + "or silently enter timestamped AQI/NWS/USGS correlation. "
                     + "Webcams provided by Windy.com where configured.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var temporalQueryPanel: some View {
        GroupBox("4 · Investigate retained evidence across time") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Compare source-observed times in this selected region. "
                     + "The current providers do not report exact shared "
                     + "event footprints, so matches are temporal candidates only.")
                    .font(.caption)
                Text("Narrowed search radius: "
                     + "\(correlationQueryRadiusKM.formatted()) km")
                    .font(.subheadline.weight(.medium))
                Slider(
                    value: $correlationQueryRadiusKM,
                    in: 1...(selected?.radiusKM ?? 30),
                    step: 1
                )
                .accessibilityLabel("Historical evidence query radius in kilometers")
                Text("The radius cannot exceed the region you enrolled. "
                     + "Exact earthquake epicenters are used only when "
                     + "present in the official source.")
                    .font(.caption2)
                Picker("Observation window", selection: $correlationWindowHours) {
                    ForEach([6, 24, 72], id: \.self) { hours in
                        Text("Previous \(hours) hours").tag(hours)
                    }
                }
                .pickerStyle(.segmented)
                DatePicker(
                    "Window ends",
                    selection: $correlationEnd,
                    in: ...Date(),
                    displayedComponents: [.date, .hourAndMinute]
                )
                Button(busy ? "Querying…" : "Correlate saved sources") {
                    Task { await correlateSavedEvidence() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || capabilities?.enabled != true)
                Text("Read-only query; observation and receipt timestamps "
                     + "remain distinct. No new sensor checks occur.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func correlationPanel(_ report: ArmorCorrelationReport) -> some View {
        GroupBox("Temporal relationship candidates • not causal findings") {
            VStack(alignment: .leading, spacing: 9) {
                Text("Region \(report.queryRegion.latitude.formatted()), "
                     + "\(report.queryRegion.longitude.formatted()) "
                     + "• \(report.queryRegion.radiusKM.formatted()) km query radius")
                    .font(.subheadline.weight(.medium))
                Text("Query: " + report.queryID)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                Text("Observed-time window: "
                     + report.observationWindow.start + " → "
                     + report.observationWindow.end)
                    .font(.caption)
                Text(report.mode + " • \(report.timedObservations.count) timestamped "
                     + "source records; \(report.receiptTimeOnlyObservations.count) "
                     + "receipt-only records")
                    .font(.caption)
                ForEach(report.sourceCoverage.keys.sorted(), id: \.self) { source in
                    if let coverage = report.sourceCoverage[source] {
                        Text(source + " • " + coverage.status + " • " + coverage.scope)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Divider()
                Text("Event-time coincidence candidates: "
                     + "\(report.candidateLinks.count)")
                    .font(.headline)
                if report.candidateLinks.isEmpty {
                    Text("No eligible independent-source event-time pairs "
                         + "in these retained samples. Not an all-clear.")
                        .font(.caption)
                }
                ForEach(report.candidateLinks) { link in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(link.firstSource + " ↔ " + link.secondSource)
                            .font(.subheadline.weight(.medium))
                        Text("\(link.separationSeconds) seconds apart in reported "
                             + "source time")
                        Text(link.firstSourceTime + " → " + link.secondSourceTime)
                            .font(.caption2)
                        Text(link.note)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(8)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
                if !report.degradedObservations.isEmpty {
                    Text("\(report.degradedObservations.count) retained source "
                         + "record(s) are visible but excluded from correlation "
                         + "because their producing sample was not status=ok.")
                        .font(.caption)
                }
                if !report.receiptTimeOnlyObservations.isEmpty {
                    Divider()
                    Text("Received-only • source event times unavailable")
                        .font(.headline)
                    ForEach(report.receiptTimeOnlyObservations.prefix(25)) { row in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(row.source + " • " + row.values.brief)
                            Text("Jarvis received: " + row.receivedAt
                                 + " • source event time UNKNOWN")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                if !report.spatiallyIndeterminateObservations.isEmpty {
                    Text("Location unknown in narrowed query: "
                         + "\(report.spatiallyIndeterminateObservations.count) "
                         + "retained earthquake reports excluded from exact "
                         + "radius matching.")
                        .font(.caption)
                }
                Text(report.qualifier)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func hypothesisPanel(_ graph: ArmorEvidenceGraph) -> some View {
        GroupBox("Evidence graph • candidate explanations") {
            VStack(alignment: .leading, spacing: 9) {
                Text("\(graph.nodes.count) evidence node(s) • "
                     + "\(graph.edges.count) typed edge(s) • "
                     + "\(graph.hypotheses.count) unverified hypothesis candidate(s)")
                    .font(.subheadline.weight(.medium))
                Text("Query: " + graph.queryID)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                if graph.degradedObservationCount > 0 {
                    Text("\(graph.degradedObservationCount) degraded observation(s) "
                         + "remain inspectable but cannot support a hypothesis.")
                        .font(.caption)
                }
                if !graph.unavailableOrUncheckedSources.isEmpty {
                    Text("Unavailable/unchecked: "
                         + graph.unavailableOrUncheckedSources.joined(separator: ", "))
                        .font(.caption)
                }
                ForEach(graph.hypotheses) { hypothesis in
                    DisclosureGroup(hypothesis.claim) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Status: " + hypothesis.status
                                 + " • independent lineages: "
                                 + String(hypothesis.independentLineageCount))
                                .font(.caption)
                            Text("Spatial precision: " + hypothesis.spatialPrecision)
                                .font(.caption2)
                            if !hypothesis.missingEvidence.isEmpty {
                                Text("Still needed")
                                    .font(.caption.weight(.semibold))
                                ForEach(hypothesis.missingEvidence, id: \.self) {
                                    Text("• " + $0).font(.caption2)
                                }
                            }
                            if !hypothesis.alternativeExplanations.isEmpty {
                                Text("Alternatives")
                                    .font(.caption.weight(.semibold))
                                ForEach(hypothesis.alternativeExplanations, id: \.self) {
                                    Text("• " + $0).font(.caption2)
                                }
                            }
                            Text(hypothesis.prohibitedConclusion)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.top, 4)
                    }
                    .padding(8)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 9))
                }
                if graph.hypotheses.isEmpty {
                    Text("No cross-source hypothesis candidate is supported "
                         + "by these retained, timestamped observations.")
                        .font(.caption)
                }
                Text(graph.qualifier)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func changePanel(_ report: ArmorChangeReport) -> some View {
        GroupBox("Observed differences, not assumed causes") {
            VStack(alignment: .leading, spacing: 8) {
                Text(report.comparison.replacingOccurrences(of: "_", with: " "))
                    .font(.headline)
                if let air = report.modelledAirQualityChange {
                    Text("Modelled AQI: \(air.before.formatted()) → "
                         + "\(air.after.formatted()); Δ \(air.delta.formatted())")
                    Text("Model times: " + air.beforeModelAt + " → " + air.afterModelAt)
                        .font(.caption2)
                }
                ForEach(report.sourceChanges.indices, id: \.self) { index in
                    let row = report.sourceChanges[index]
                    Text(row.source + " coverage: " + row.before + " → " + row.after)
                        .font(.caption)
                }
                ForEach(report.sourceRecordChanges) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.source + " · " + row.kind.replacingOccurrences(
                            of: "_", with: " "))
                            .font(.subheadline.weight(.medium))
                        Text(row.after.brief)
                        Text(row.note + " • received " + row.receivedAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                if report.sourceRecordChanges.isEmpty
                    && report.modelledAirQualityChange == nil
                    && report.sourceChanges.isEmpty {
                    Text("No detectable difference in these retained samples. "
                         + "This is not an all-clear.")
                        .font(.caption)
                }
                Text(report.qualifier)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func replayPanel(_ report: ArmorReplay) -> some View {
        GroupBox("Retained source evidence • as known then") {
            VStack(alignment: .leading, spacing: 9) {
                Text("As known at " + report.asKnownAt)
                    .font(.subheadline.weight(.medium))
                Text(report.mode + " • \(report.observationCount) latest "
                     + "source-key records • not a complete world history")
                    .font(.caption)
                ForEach(report.coverage.keys.sorted(), id: \.self) { source in
                    if let coverage = report.coverage[source] {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source + " • " + coverage.status)
                                .font(.subheadline.weight(.medium))
                            Text("Reported count \(coverage.reportedCount) • "
                                 + "checked " + coverage.checkedAt)
                                .font(.caption2)
                            Text(coverage.scope)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Divider()
                ForEach(report.observations.prefix(60)) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.source + " • revision \(row.revision)"
                             + " • " + (row.adapterMode ?? "unknown source mode"))
                            .font(.subheadline.weight(.medium))
                        Text(row.values.brief)
                        Text("Source observation: "
                             + (row.observedAt ?? "unknown")
                             + " • Jarvis received " + row.receivedAt)
                            .font(.caption2)
                        Text("Producing-sample coverage: "
                             + (row.sampleCoverageStatus ?? "unknown")
                             + (row.sampleCoverageCheckedAt.map { " • checked " + $0 } ?? ""))
                            .font(.caption2)
                        Text(row.geometryBasis)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Divider()
                }
                Text("No source observation or no matching events "
                     + "never proves an area is safe or fully observed.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func fullScopeWindow() -> (String, String) {
        let end = correlationEnd
        let start = end.addingTimeInterval(
            -Double(correlationWindowHours) * 3_600
        )
        let formatter = ISO8601DateFormatter()
        return (formatter.string(from: start), formatter.string(from: end))
    }

    private func refreshFullScope(runAnalysis: Bool) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            async let fullStatusRequest = client.worldArmorFullStatus()
            async let presenceRequest = client.worldArmorPresence()
            async let browserRequest = client.worldArmorRealityBrowser(
                afterSeq: max(0, (liveFabricStatus?.latestSeq ?? 0) - 100),
                limit: 100
            )
            async let sensesRequest = client.worldArmorSyntheticSenses(
                afterSeq: max(0, (liveFabricStatus?.latestSeq ?? 0) - 100),
                limit: 100
            )
            let (newStatus, newPresence, newBrowser, newSenses) = try await (
                fullStatusRequest, presenceRequest, browserRequest, sensesRequest
            )
            fullScopeStatus = newStatus
            presenceState = newPresence
            realityBrowser = newBrowser
            syntheticSenses = newSenses

            if runAnalysis {
                let cutoff = asKnownAt.trimmingCharacters(in: .whitespacesAndNewlines)
                if let selectedID {
                    let (start, end) = fullScopeWindow()
                    async let causalRequest = client.worldArmorCausalDebugger(
                        investigationID: selectedID,
                        startAt: start,
                        endAt: end,
                        asKnownAt: cutoff.isEmpty ? nil : cutoff
                    )
                    async let parallelRequest = client.worldArmorParallelExistence(
                        afterSeq: max(0, (liveFabricStatus?.latestSeq ?? 0) - 100),
                        startAt: start,
                        endAt: end,
                        investigationID: selectedID,
                        asKnownAt: cutoff.isEmpty ? nil : cutoff
                    )
                    let (newCausal, newParallel) = try await (
                        causalRequest, parallelRequest
                    )
                    causalDebugger = newCausal
                    parallelExistence = newParallel
                    realityBrowser = try await client.worldArmorRealityBrowser(
                        afterSeq: max(0, (liveFabricStatus?.latestSeq ?? 0) - 100),
                        limit: 200,
                        startAt: start,
                        endAt: end,
                        investigationID: selectedID,
                        asKnownAt: cutoff.isEmpty ? nil : cutoff
                    )
                } else {
                    causalDebugger = nil
                    parallelExistence = try await client.worldArmorParallelExistence(
                        afterSeq: max(0, (liveFabricStatus?.latestSeq ?? 0) - 100)
                    )
                }
            }
            status = runAnalysis
                ? "Full World Armor analysis completed."
                : "Full World Armor interfaces refreshed."
        } catch {
            status = "Full World Armor unavailable: " + error.localizedDescription
        }
    }

    private func runPresence(
        lightID: UUID, label: String, desiredOn: Bool
    ) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let grant = try await client.worldArmorPresenceGrant(
                targetID: lightID,
                targetLabel: label,
                lifetimeSeconds: 120,
                maxUses: 1
            )
            let dispatch = try await client.worldArmorPresenceDispatch(
                grantID: grant.id,
                desiredOn: desiredOn
            )
            status = "Presence request #" + String(dispatch.requestID.prefix(8))
                + " dispatched; awaiting separate HomeKit readback."
            try? await Task.sleep(for: .milliseconds(500))
            presenceState = try? await client.worldArmorPresence()
        } catch {
            status = "Presence blocked: " + error.localizedDescription
        }
    }

    private func refresh() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            capabilities = try await client.worldArmorCapabilities()
            // Listing and forgetting retained regions remains available after
            // collection is disabled; no new provider request is issued here.
            investigations = try await client.worldArmorInvestigations().investigations
            watches = (try? await client.worldArmorWatches())?.watches ?? []
            if let page = try? await client.worldArmorPlatformSources() {
                platformSources = page.sources
                platformNextOffset = page.nextOffset
                platformTotal = page.total
            }
            if let movement = try? await client.worldArmorMovementSources() {
                movementSources = movement.sources
                movementNextOffset = movement.nextOffset
                movementTotal = movement.total
            }
            if let fabric = try? await client.worldArmorDistributedWorkers() {
                distributedWorkers = fabric.workers
            }
            pushStatus = try? await client.worldArmorPushStatus()
            if let live = try? await client.worldArmorLiveStatus() {
                liveFabricStatus = live
                if let page = try? await client.worldArmorLiveEvents(
                    afterSeq: max(0, live.latestSeq - 25), limit: 25
                ) {
                    liveEvents = Array(page.events.reversed())
                }
            }
            if let current = selectedID {
                let response = try? await client.worldArmorNotices(
                    investigationID: current
                )
                notices = response?.notices ?? []
                unreadNotices = response?.unreadCount ?? 0
                seenNoticeIDs = Set(notices.map { $0.id })
                hasNoticeBaseline = true
                cameraReceipts = (try? await client.worldArmorCameraReceipts(
                    investigationID: current
                ))?.cameraReceipts ?? []
            }
            if !investigations.contains(where: { $0.id == selectedID }) {
                selectedID = nil
                replayResult = nil
                changes = nil
                correlations = nil
                evidenceGraph = nil
                sampleTimes = []
                notices = []
                unreadNotices = 0
                seenNoticeIDs = []
                hasNoticeBaseline = false
            }
            if capabilities?.enabled == true {
                status = "Source registry integrated, not proof that live "
                    + "feeds or your installed devices have been checked."
            } else {
                replayResult = nil
                changes = nil
                correlations = nil
                evidenceGraph = nil
                sampleTimes = []
                status = "Backend OFF: collection and replay disabled. "
                    + "Previously saved locations remain visible for deletion."
            }
        } catch {
            capabilities = nil
            replayResult = nil
            changes = nil
            correlations = nil
            evidenceGraph = nil
            sampleTimes = []
            status = "World Armor unavailable: " + error.localizedDescription
        }
    }

    private func refreshLiveFabric() async {
        do {
            let live = try await client.worldArmorLiveStatus()
            liveFabricStatus = live
            let page = try await client.worldArmorLiveEvents(
                afterSeq: max(0, live.latestSeq - 25), limit: 25
            )
            liveEvents = Array(page.events.reversed())
            pushStatus = try? await client.worldArmorPushStatus()
        } catch {
            status = "Live fabric unavailable: " + error.localizedDescription
        }
    }

    private func setLiveSupervisor(running: Bool) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            liveFabricStatus = running
                ? try await client.worldArmorLiveStart()
                : try await client.worldArmorLiveStop()
            let live = liveFabricStatus
            if let live {
                let page = try await client.worldArmorLiveEvents(
                    afterSeq: max(0, live.latestSeq - 25), limit: 25
                )
                liveEvents = Array(page.events.reversed())
            }
        } catch {
            status = "Could not change live supervisor: " + error.localizedDescription
        }
    }

    private func pollAttentionInbox() async {
        guard let current = selectedID else { return }
        while !Task.isCancelled && selectedID == current {
            if scenePhase == .active && !busy {
                await refreshNotices(alertOnNew: true)
            }
            do {
                try await Task.sleep(for: .seconds(60))
            } catch {
                break
            }
        }
    }

    private func refreshNotices(alertOnNew: Bool) async {
        guard let current = selectedID else { return }
        do {
            let response = try await client.worldArmorNotices(
                investigationID: current
            )
            guard selectedID == current, scenePhase == .active else { return }
            let newItems = response.notices.filter {
                !seenNoticeIDs.contains($0.id) && $0.readAt == nil
            }
            notices = response.notices
            unreadNotices = response.unreadCount
            seenNoticeIDs = Set(response.notices.map { $0.id })
            if hasNoticeBaseline && alertOnNew && foregroundAttentionOptIn,
               let first = newItems.first {
                attentionBannerText = first.summary
                showAttentionBanner = true
            }
            hasNoticeBaseline = true
        } catch {
            // Offline/unknown never means all-clear. Keep the prior inbox
            // and prior seen IDs instead of pretending delivery succeeded.
            if hasNoticeBaseline {
                status = "Attention inbox unavailable: "
                    + error.localizedDescription
            }
        }
    }

    private func changeNotice(_ id: String, action: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            if action == "read" {
                _ = try await client.worldArmorNoticeRead(id)
            } else {
                _ = try await client.worldArmorNoticeForget(id)
            }
            await refreshNotices(alertOnNew: false)
        } catch {
            status = "Notice update failed: " + error.localizedDescription
        }
    }

    private func refreshDistributedWorkers() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let fabric = try await client.worldArmorDistributedWorkers()
            distributedWorkers = fabric.workers
            movementStatus = "Worker fabric refreshed; no provider job dispatched."
        } catch {
            distributedWorkers = []
            movementStatus = "Worker fabric unavailable: "
                + error.localizedDescription
        }
    }

    private func refreshMovementSources() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorMovementSources()
            movementSources = page.sources
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementStatus = "Movement registry refreshed; no provider queried."
        } catch {
            movementStatus = "Movement registry unavailable: "
                + error.localizedDescription
        }
    }

    private func loadMoreMovementSources() async {
        guard !busy, let cursor = movementNextOffset else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorMovementSources(
                offset: cursor
            )
            movementSources.append(contentsOf: page.sources)
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementStatus = "Loaded \(movementSources.count) of "
                + "\(movementTotal) movement sources."
        } catch {
            movementStatus = "Movement pagination unavailable: "
                + error.localizedDescription
        }
    }

    private func enrollMovementSource() async {
        guard !busy else { return }
        guard let retention = Int(movementRetention), retention >= 1,
              let minimum = Int(movementMinInterval), minimum >= 0 else {
            movementStatus = "Enter positive retention and a valid provider interval."
            return
        }
        let cadence: Int
        if movementAutomated {
            guard let entered = Int(movementCadence),
                  entered >= max(minimum, 1) else {
                movementStatus = "Scheduled cadence must meet provider terms."
                return
            }
            cadence = entered
        } else {
            cadence = 0
        }
        var lat: Double?
        var lon: Double?
        var radiusKM: Double?
        if movementKind != "opensky_global" {
            guard let parsedLat = Double(movementLatitude),
                  let parsedLon = Double(movementLongitude),
                  let parsedRadius = Double(movementRadius),
                  parsedRadius > 0 else {
                movementStatus = "Enter a valid movement region."
                return
            }
            lat = parsedLat
            lon = parsedLon
            radiusKM = parsedRadius
        }
        busy = true
        defer { busy = false }
        do {
            let source = try await client.worldArmorMovementEnroll(
                label: movementLabel,
                kind: movementKind,
                grantClass: movementGrantClass,
                termsReference: movementTerms,
                automated: movementAutomated,
                providerMinIntervalSeconds: minimum,
                cadenceSeconds: cadence,
                retentionDays: retention,
                latitude: lat, longitude: lon, radiusKM: radiusKM
            )
            let page = try await client.worldArmorMovementSources()
            movementSources = page.sources
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementStatus = "Enrolled " + source.label
                + ". Collection is still local-host/user initiated."
        } catch {
            movementStatus = "Movement source enrollment blocked: "
                + error.localizedDescription
        }
    }

    private func collectMovementSource(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorMovementCollect(id)
            let page = try await client.worldArmorMovementSources()
            movementSources = page.sources
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementStatus = "Provider status: " + receipt.status
                + " · entities \(receipt.entitiesSeen ?? 0)"
                + " · new track points \(receipt.observationsSaved ?? 0). "
                + (receipt.providerNote ?? "")
        } catch {
            movementStatus = "Movement collection unavailable: "
                + error.localizedDescription
        }
    }

    private func changeMovementSource(
        _ id: String, action: String
    ) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let source = try await client.worldArmorMovementTransition(
                id, action: action
            )
            let page = try await client.worldArmorMovementSources()
            movementSources = page.sources
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementStatus = source.label + " is " + source.state + "."
        } catch {
            movementStatus = "Movement transition unavailable: "
                + error.localizedDescription
        }
    }

    private func forgetMovementSource(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await client.worldArmorMovementForget(id)
            let page = try await client.worldArmorMovementSources()
            movementSources = page.sources
            movementTotal = page.total
            movementNextOffset = page.nextOffset
            movementEntities = []
            movementStatus = "Movement source and its local track history forgotten."
        } catch {
            movementStatus = "Movement forget unavailable: "
                + error.localizedDescription
        }
    }

    private func queryNearbyMovement() async {
        guard !busy,
              let lat = Double(movementLatitude),
              let lon = Double(movementLongitude),
              let radius = Double(movementRadius),
              radius > 0 else {
            movementStatus = "Enter a valid point and movement radius."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorMovementNearby(
                latitude: lat, longitude: lon, radiusKM: radius,
                entityType: movementEntityType
            )
            movementEntities = page.entities
            movementStatus = "Showing \(page.entities.count) latest retained "
                + "public movement states. Missing entities do not prove "
                + "the area is clear."
        } catch {
            movementStatus = "Movement query unavailable: "
                + error.localizedDescription
        }
    }

    private func refreshPlatformSources() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorPlatformSources()
            platformSources = page.sources
            platformTotal = page.total
            platformNextOffset = page.nextOffset
            platformStatus = "Source register refreshed. No camera fetched."
        } catch {
            platformStatus = "Source register unavailable: "
                + error.localizedDescription
        }
    }

    private func loadMorePlatformSources() async {
        guard !busy, let cursor = platformNextOffset else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorPlatformSources(
                offset: cursor
            )
            platformSources.append(contentsOf: page.sources)
            platformTotal = page.total
            platformNextOffset = page.nextOffset
            platformStatus = "Loaded \(platformSources.count) of "
                + "\(platformTotal) enrolled sources."
        } catch {
            platformStatus = "Source pagination unavailable: "
                + error.localizedDescription
        }
    }

    private func enrollPlatformSource() async {
        guard !busy else { return }
        guard let retention = Int(platformRetentionDays),
              retention >= 1 else {
            platformStatus = "Enter positive derived-evidence retention days."
            return
        }
        guard let publisherMinimum = Int(platformMinInterval),
              publisherMinimum >= 0 else {
            platformStatus = "Enter the source's permitted minimum interval."
            return
        }
        let cadence: Int
        if platformAutomated {
            guard let entered = Int(platformCadence),
                  entered >= max(publisherMinimum, 1) else {
                platformStatus = "Polling cadence must meet source permissions."
                return
            }
            cadence = entered
        } else {
            cadence = 0
        }
        let latText = platformLatitude.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let lonText = platformLongitude.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        if latText.isEmpty != lonText.isEmpty {
            platformStatus = "Provide both camera coordinates or neither."
            return
        }
        let lat = latText.isEmpty ? nil : Double(latText)
        let lon = lonText.isEmpty ? nil : Double(lonText)
        if !latText.isEmpty && (lat == nil || lon == nil) {
            platformStatus = "Camera coordinates must be numeric."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let enrolled = try await client.worldArmorPlatformEnroll(
                label: platformLabel, kind: platformKind,
                locator: platformLocator,
                grantClass: platformGrantClass,
                termsReference: platformTerms,
                automated: platformAutomated,
                sourceMinIntervalSeconds: publisherMinimum,
                cadenceSeconds: cadence,
                retentionDays: retention, goal: platformGoal,
                latitude: lat, longitude: lon
            )
            let page = try await client.worldArmorPlatformSources()
            platformSources = page.sources
            platformTotal = page.total
            platformNextOffset = page.nextOffset
            platformStatus = "Source " + enrolled.id
                + " enrolled with exact declared rights. Host runner "
                + "requires explicit start; no camera was fetched."
        } catch {
            platformStatus = "Source enrollment blocked: "
                + error.localizedDescription
        }
    }

    private func planPlatformSources() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let preflight = try await client.worldArmorPlatformPlan()
            platformStatus = "\(preflight.available) eligible sources; "
                + "\(preflight.automated) explicitly permitted for scheduled "
                + "checks. Suggested host batch "
                + "\(preflight.proposedHostConcurrency). Permissions not "
                + "independently verified; remote workers unavailable."
        } catch {
            platformStatus = "Source plan unavailable: "
                + error.localizedDescription
        }
    }

    private func observePlatformSource(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorPlatformObserve(id)
            let page = try await client.worldArmorPlatformSources()
            platformSources = page.sources
            platformNextOffset = page.nextOffset
            platformTotal = page.total
            let records = try await client.worldArmorPlatformEvidence(
                sourceID: id
            )
            platformActiveID = id
            platformEvidence = records.observations
            platformNotices = try await client.worldArmorPlatformNotices(
                sourceID: id
            ).notices
            platformStatus = "Source check: " + receipt.status
                + "; model calls \(receipt.modelCalls ?? 0). "
                + "Identical published images skip redundant model passes."
        } catch {
            platformStatus = "Source observation unavailable: "
                + error.localizedDescription
        }
    }

    private func readPlatformEvidence(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.worldArmorPlatformEvidence(
                sourceID: id
            )
            platformActiveID = id
            platformEvidence = page.observations
            platformNotices = try await client.worldArmorPlatformNotices(
                sourceID: id
            ).notices
            platformStatus = "Loaded derived evidence, not publisher footage. "
                + "Source capture times remain unverified."
        } catch {
            platformStatus = "Evidence unavailable: "
                + error.localizedDescription
        }
    }

    private func changePlatformSource(
        _ id: String, action: String
    ) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let item = try await client.worldArmorPlatformTransition(
                id, action: action
            )
            let page = try await client.worldArmorPlatformSources()
            platformSources = page.sources
            platformTotal = page.total
            platformNextOffset = page.nextOffset
            platformStatus = "Source " + item.label + " is " + item.state
                + ". Leased observations cannot save after stop/pause."
        } catch {
            platformStatus = "Source transition unavailable: "
                + error.localizedDescription
        }
    }

    private func forgetPlatformSource(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorPlatformForget(id)
            let page = try await client.worldArmorPlatformSources()
            platformSources = page.sources
            platformTotal = page.total
            platformNextOffset = page.nextOffset
            if platformActiveID == id {
                platformActiveID = nil
                platformEvidence = []
                platformNotices = []
            }
            platformStatus = receipt.deleted > 0
                ? "Source and all its local text/hash evidence forgotten."
                : "Selected source was already absent."
        } catch {
            platformStatus = "Forget source unavailable: "
                + error.localizedDescription
        }
    }

    private func inspectCombinedPlatformEvidence(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let data = try await client.worldArmorCombinedCameraEvidence(
                investigationID: id
            )
            let cameras = (data["camera_observations"]
                           as? [[String: Any]]) ?? []
            let environmental = (data["environmental_observations"]
                                 as? [[String: Any]]) ?? []
            let unlocated = (data["enrolled_camera_location_unknown_source_ids"]
                             as? [String]) ?? []
            platformCombinedSummary =
                "\(cameras.count) camera receipts near the selected "
                + "region's camera points and \(environmental.count) "
                + "environmental source observations; "
                + "\(unlocated.count) camera sources have unknown geography. "
                + "These are CO-DISPLAYED, not correlated by fabricated "
                + "camera capture times or verified view cones."
        } catch {
            platformCombinedSummary =
                "Combined evidence unavailable: " + error.localizedDescription
        }
    }

    private func discoverPageMedia() async {
        guard !busy, !publicCameraURL.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.worldArmorPageMedia(
                publicCameraURL.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            publicPageMedia = result.candidates
            cameraStatus = "Found \(result.candidates.count) possible "
                + "public image or HLS links. Select one explicitly; "
                + "a thumbnail may not be a camera view."
        } catch {
            publicPageMedia = []
            cameraStatus = "Page link discovery unavailable: "
                + error.localizedDescription
        }
    }

    private func discoverRegionCameras() async {
        guard let region = selected, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.worldArmorDiscoverCameras(
                latitude: region.latitude, longitude: region.longitude,
                radiusKM: region.radiusKM
            )
            guard selectedID == region.id else { return }
            publicCameras = result.cameras
            cameraProviders = result.providerStatuses
            cameraStatus = "Found \(publicCameras.count) directory cameras. "
                + "Incomplete catalogs do not mean no cameras exist."
        } catch {
            cameraStatus = "Camera discovery unavailable: "
                + error.localizedDescription
        }
    }

    private func inspectSelectedPublicCamera() async {
        guard let regionID = selectedID, !busy else { return }
        let direct = publicCameraURL.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let reference = direct.isEmpty ? selectedCameraRef : ""
        guard !reference.isEmpty || !direct.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.worldArmorInspectCamera(
                investigationID: regionID,
                cameraRef: reference, publicURL: direct,
                condition: cameraCondition
            )
            guard selectedID == regionID else { return }
            let history = try await client.worldArmorCameraReceipts(
                investigationID: regionID
            )
            cameraReceipts = history.cameraReceipts
            cameraStatus = "One published frame inspected at "
                + result.retrievedAt + ". Capture time unverified. "
                + "No raw image retained."
        } catch {
            cameraStatus = "Public frame not retained: "
                + error.localizedDescription
        }
    }

    private func enrollExactCameraWatch() async {
        guard !busy else { return }
        let direct = publicCameraURL.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        var config: [String: Any] = ["condition": cameraCondition]
        if !direct.isEmpty {
            config["public_url"] = direct
        } else if selectedCameraRef.hasPrefix("caltrans-") {
            config["camera_id"] = selectedCameraRef
        } else if selectedCameraRef.hasPrefix("windy-") {
            config["camera_ref"] = selectedCameraRef
        } else {
            cameraStatus = "Select a camera or exact public media URL."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let created = try await client.createExternalWatch(
                kind: "camera", label: "World Armor public camera",
                config: config, seconds: 1800, scope: "personal",
                expiresHours: 3
            )
            cameraWatch = created
            cameraWatchImportID = created.id
            cameraStatus = "Separate exact camera watch enrolled for "
                + "3 hours; host must run. Its history does not "
                + "automatically enter this World Armor region."
        } catch {
            cameraStatus = "Camera watch enrollment blocked: "
                + error.localizedDescription
        }
    }

    private func stopExactCameraWatch(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await client.stopExternalWatch(id, scope: "personal")
            cameraWatch = nil
            cameraStatus = "Exact external camera watch stopped."
        } catch {
            cameraStatus = "Camera watch stop failed: "
                + error.localizedDescription
        }
    }

    private func checkAndImportCameraWatch() async {
        guard let regionID = selectedID, !busy else { return }
        let id = cameraWatchImportID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !id.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            let checked = try await client.checkExternalWatch(
                id, scope: "personal"
            )
            guard checked.status == "ok" else {
                cameraStatus = "Camera watch source check: " + checked.status
                    + ". No evidence imported."
                return
            }
            let imported = try await client.worldArmorImportCameraWatch(
                investigationID: regionID, watchID: id
            )
            let history = try await client.worldArmorCameraReceipts(
                investigationID: regionID
            )
            cameraReceipts = history.cameraReceipts
            cameraStatus = "Imported one exact watch source report at "
                + imported.retrievedAt + ". Publisher capture time unknown."
        } catch {
            cameraStatus = "Check/import unavailable: " + error.localizedDescription
        }
    }

    private func importSavedCameraWatch() async {
        guard let regionID = selectedID, !busy else { return }
        let id = cameraWatchImportID.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !id.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            let imported = try await client.worldArmorImportCameraWatch(
                investigationID: regionID, watchID: id
            )
            let history = try await client.worldArmorCameraReceipts(
                investigationID: regionID
            )
            cameraReceipts = history.cameraReceipts
            cameraStatus = "Imported one prior exact watch report at "
                + imported.retrievedAt + ". No new provider request."
        } catch {
            cameraStatus = "Saved watch import unavailable: "
                + error.localizedDescription
        }
    }

    private func refreshCameraEvidence() async {
        guard let regionID = selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.worldArmorCameraReceipts(
                investigationID: regionID
            )
            guard selectedID == regionID, scenePhase == .active else { return }
            cameraReceipts = result.cameraReceipts
            cameraStatus = "Loaded stored camera receipts; no new provider "
                + "request or background stream."
        } catch {
            cameraStatus = "Camera evidence unavailable: "
                + error.localizedDescription
        }
    }

    private func forgetCameraEvidence(_ id: String) async {
        guard let regionID = selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await client.worldArmorForgetCameraReceipt(id)
            let history = try await client.worldArmorCameraReceipts(
                investigationID: regionID
            )
            cameraReceipts = history.cameraReceipts
            cameraStatus = "Local camera text/hash receipt forgotten."
        } catch {
            cameraStatus = "Forget camera receipt failed: "
                + error.localizedDescription
        }
    }

    private func refreshWatches() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            watches = try await client.worldArmorWatches().watches
            investigations = try await client.worldArmorInvestigations().investigations
            status = "Showing persisted watch state; this is not a provider check."
        } catch {
            status = "Watch readback unavailable: " + error.localizedDescription
        }
    }

    private func enrollWatch() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await client.worldArmorWatchCreate(
                selectedID, intervalMinutes: watchInterval,
                maxChecks: watchChecks, lifetimeHours: watchLifetime,
                attentionKind: attentionKind,
                attentionThreshold: attentionKind == "modelled_aqi_threshold_crossed"
                    ? attentionAQI : attentionKind == "new_usgs_report"
                        ? attentionMagnitude : nil,
                attentionCooldownMinutes: attentionCooldown
            )
            watches = try await client.worldArmorWatches().watches
            status = "Watch enrolled. The separate local host runner must "
                + "be started explicitly; no provider check has happened yet."
        } catch {
            status = "Watch enrollment blocked: " + error.localizedDescription
        }
    }

    private func forgetWatch(_ id: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.worldArmorWatchForget(id)
            watches = try await client.worldArmorWatches().watches
            status = result.deleted > 0
                ? "Watch grant forgotten; region samples remain until region Forget."
                : "Watch grant was already absent."
        } catch {
            status = "Watch Forget failed: " + error.localizedDescription
        }
    }

    private func changeWatch(_ id: String, action: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await client.worldArmorWatchTransition(id, action: action)
            watches = try await client.worldArmorWatches().watches
            status = action == "stop"
                ? "Watch revoked. In-flight collection cannot retain evidence "
                    + "after revocation; past samples remain until region Forget."
                : "Watch " + action + " confirmed by backend."
        } catch {
            status = "Watch transition failed: " + error.localizedDescription
        }
    }

    private func create() async {
        guard !busy else { return }
        guard let lat = Double(latitude), let lon = Double(longitude),
              let radiusKM = Double(radius) else {
            status = "Enter valid numeric coordinates and radius."
            return
        }
        busy = true
        defer { busy = false }
        do {
            let made = try await client.worldArmorCreate(
                label: label, latitude: lat, longitude: lon, radiusKM: radiusKM
            )
            investigations = try await client.worldArmorInvestigations().investigations
            watches = (try? await client.worldArmorWatches())?.watches ?? []
            selectedID = made.id
            correlationQueryRadiusKM = radiusKM
            replayResult = nil
            changes = nil
            correlations = nil
            evidenceGraph = nil
            sampleTimes = []
            asKnownAt = ""
            status = "Created an expiring region. No provider checked yet."
        } catch {
            status = "Create blocked: " + error.localizedDescription
        }
    }

    private func observe() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorObserve(selectedID)
            investigations = try await client.worldArmorInvestigations().investigations
            watches = (try? await client.worldArmorWatches())?.watches ?? []
            replayResult = try await client.worldArmorReplay(
                selectedID, asKnownAt: nil
            )
            sampleTimes = replayResult?.sampleTimeline ?? []
            asKnownAt = ""
            changes = nil
            correlations = nil
            evidenceGraph = nil
            status = "Received \(receipt.newObservations) new source records "
                + "at " + receipt.receivedAt + ". Read coverage before "
                + "drawing conclusions."
        } catch {
            status = "Observation failed: " + error.localizedDescription
        }
    }

    private func replay() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let cutoff = asKnownAt.trimmingCharacters(in: .whitespacesAndNewlines)
            replayResult = try await client.worldArmorReplay(
                selectedID, asKnownAt: cutoff.isEmpty ? nil : cutoff
            )
            correlations = nil
            evidenceGraph = nil
            if cutoff.isEmpty {
                sampleTimes = replayResult?.sampleTimeline ?? []
            }
            status = "Viewing retained evidence, not issuing provider requests."
        } catch {
            status = "Replay blocked: " + error.localizedDescription
        }
    }

    private func compare() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            changes = try await client.worldArmorChanges(selectedID)
            status = "Compared the two latest saved receipts. "
                + "No inference of causation or absence."
        } catch {
            status = "Comparison blocked: " + error.localizedDescription
        }
    }

    private func correlateSavedEvidence() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let end = correlationEnd
            let start = end.addingTimeInterval(
                -Double(correlationWindowHours) * 3_600
            )
            let formatter = ISO8601DateFormatter()
            let cutoff = asKnownAt.trimmingCharacters(in: .whitespacesAndNewlines)
            async let correlationRequest = client.worldArmorCorrelate(
                selectedID,
                startAt: formatter.string(from: start),
                endAt: formatter.string(from: end),
                asKnownAt: cutoff.isEmpty ? nil : cutoff,
                radiusKM: correlationQueryRadiusKM
            )
            async let graphRequest = client.worldArmorHypotheses(
                selectedID,
                startAt: formatter.string(from: start),
                endAt: formatter.string(from: end),
                asKnownAt: cutoff.isEmpty ? nil : cutoff,
                radiusKM: correlationQueryRadiusKM
            )
            let (newCorrelations, newGraph) = try await (
                correlationRequest, graphRequest
            )
            correlations = newCorrelations
            evidenceGraph = newGraph
            status = "Read-only evidence graph complete. Inspect source time, "
                + "spatial limits, alternatives and missing evidence."
        } catch {
            correlations = nil
            evidenceGraph = nil
            status = "Correlation unavailable: " + error.localizedDescription
        }
    }

    private func forgetSelected() async {
        guard let selectedID, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let receipt = try await client.worldArmorForget(selectedID)
            replayResult = nil
            changes = nil
            correlations = nil
            evidenceGraph = nil
            sampleTimes = []
            investigations = try await client.worldArmorInvestigations().investigations
            self.selectedID = nil
            status = "Removed \(receipt.deleted) investigation. "
                + "External source records and backups were not erased."
        } catch {
            status = "Forget blocked: " + error.localizedDescription
        }
    }
}
