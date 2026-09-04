import SwiftUI

@main
struct JarvisIOSApp: App {
    @StateObject private var appModel = JarvisAppModel()

    var body: some Scene {
        WindowGroup {
            MainView()
                .environmentObject(appModel)
        }
    }
}
