import Foundation
import SwiftUI
import MWDATCore

@main
struct JarvisIOSApp: App {
    @StateObject private var appModel: JarvisAppModel
    @StateObject private var persistentPresence: PersistentPresenceController

    init() {
        do {
            try Wearables.configure()
        } catch {
            NSLog("[Jarvis] Failed to configure Meta Wearables SDK: \(error)")
        }

        let model = JarvisAppModel()
        _appModel = StateObject(wrappedValue: model)
        _persistentPresence = StateObject(
            wrappedValue: PersistentPresenceController(appModel: model)
        )
    }

    var body: some Scene {
        WindowGroup {
            MainView()
                .environmentObject(appModel)
                .environmentObject(persistentPresence)
                .task {
                    await persistentPresence.start()
                }
        }
    }
}
