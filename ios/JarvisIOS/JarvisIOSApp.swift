import Foundation
import SwiftUI
import MWDATCore

@main
struct JarvisIOSApp: App {
    @StateObject private var appModel: JarvisAppModel

    init() {
        do {
            try Wearables.configure()
        } catch {
            // Meta's current sample apps deliberately log configuration failures
            // instead of trapping. A debug assertion here causes an installed
            // development build to terminate immediately on launch, which hides
            // the actual SDK error and makes the rest of Jarvis unusable.
            NSLog("[Jarvis] Failed to configure Meta Wearables SDK: \(error)")
        }
        _appModel = StateObject(wrappedValue: JarvisAppModel())
    }

    var body: some Scene {
        WindowGroup {
            MainView()
                .environmentObject(appModel)
        }
    }
}
