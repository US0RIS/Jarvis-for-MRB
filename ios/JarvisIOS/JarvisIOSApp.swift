import Foundation
import SwiftUI
import MWDATCore

@main
struct JarvisIOSApp: App {
    @StateObject private var appModel: JarvisAppModel
    @StateObject private var persistentPresence: PersistentPresenceController
    @StateObject private var meetingCapture: MeetingCaptureController
    @StateObject private var frontendIntelligence: FrontendIntelligenceController
    @StateObject private var knownPeople: KnownPeopleController

    init() {
        do {
            try Wearables.configure()
        } catch {
            NSLog("[Jarvis] Failed to configure Meta Wearables SDK: \(error)")
        }

        let model = JarvisAppModel()
        let presence = PersistentPresenceController(appModel: model)
        let meeting = MeetingCaptureController(appModel: model)
        let frontend = FrontendIntelligenceController(appModel: model)
        let people = KnownPeopleController()
        frontend.attach(persistentPresence: presence, meetingCapture: meeting)

        _appModel = StateObject(wrappedValue: model)
        _persistentPresence = StateObject(wrappedValue: presence)
        _meetingCapture = StateObject(wrappedValue: meeting)
        _frontendIntelligence = StateObject(wrappedValue: frontend)
        _knownPeople = StateObject(wrappedValue: people)
    }

    var body: some Scene {
        WindowGroup {
            MainView()
                .environmentObject(appModel)
                .environmentObject(persistentPresence)
                .environmentObject(meetingCapture)
                .environmentObject(frontendIntelligence)
                .environmentObject(knownPeople)
                .task {
                    await persistentPresence.start()
                    await frontendIntelligence.start()
                    await knownPeople.start(appModel: appModel)
                }
        }
    }
}
