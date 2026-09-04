import SwiftUI
import MWDATCore

@main
struct JarvisIOSApp: App {
    @StateObject private var appModel: JarvisAppModel

    init() {
        do {
            try Wearables.configure()
        } catch {
            assertionFailure("Failed to configure Meta Wearables SDK: \(error)")
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
