import ActivityKit
import SwiftUI
import WidgetKit

struct JarvisLiveActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var mode: String
        var detail: String
        var progress: Double
        var endsAt: Date?
        var badge: String
    }

    var sessionID: String
}

struct JarvisLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: JarvisLiveActivityAttributes.self) { context in
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: symbol(for: context.state.mode))
                    .font(.title3)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(context.state.mode)
                            .font(.headline)
                            .lineLimit(1)
                        if !context.state.badge.isEmpty {
                            Text(context.state.badge)
                                .font(.caption2.bold())
                        }
                    }
                    Text(context.state.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                    if let endsAt = context.state.endsAt {
                        Text(timerInterval: Date()...endsAt, countsDown: true)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 4)
            }
            .padding(.horizontal)
            .activityBackgroundTint(.black.opacity(0.88))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: symbol(for: context.state.mode))
                        .font(.title3)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.mode)
                        .font(.headline)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if let endsAt = context.state.endsAt {
                        Text(timerInterval: Date()...endsAt, countsDown: true)
                            .font(.caption2.monospacedDigit())
                            .frame(width: 48)
                    } else if !context.state.badge.isEmpty {
                        Text(context.state.badge)
                            .font(.caption2.bold())
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(context.state.detail)
                            .font(.caption)
                            .lineLimit(2)
                        if context.state.progress > 0 {
                            ProgressView(value: context.state.progress)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } compactLeading: {
                Image(systemName: symbol(for: context.state.mode))
            } compactTrailing: {
                if let endsAt = context.state.endsAt {
                    Text(timerInterval: Date()...endsAt, countsDown: true)
                        .font(.caption2.monospacedDigit())
                        .frame(width: 36)
                } else if !context.state.badge.isEmpty {
                    Text(context.state.badge.prefix(3))
                        .font(.caption2.bold())
                } else {
                    Image(systemName: "circle.fill")
                        .font(.caption2)
                }
            } minimal: {
                Image(systemName: symbol(for: context.state.mode))
            }
            .keylineTint(.white)
        }
    }

    private func symbol(for mode: String) -> String {
        let lower = mode.lowercased()
        if lower.contains("room") || lower.contains("meeting") { return "waveform" }
        if lower.contains("verification") { return "checkmark.shield" }
        if lower.contains("attention") || lower.contains("warning") { return "exclamationmark.triangle" }
        if lower.contains("action") { return "bolt" }
        return "circle.hexagongrid"
    }
}

@main
struct JarvisLiveActivityWidgetBundle: WidgetBundle {
    var body: some Widget {
        JarvisLiveActivityWidget()
    }
}
