import Contacts
import CryptoKit
import EventKit
import Foundation
import SwiftUI
import UIKit
import UserNotifications

// MARK: - Milestone data models

struct LocalContextCapsule: Identifiable, Codable, Equatable {
    let id: UUID
    let createdAt: Date
    var title: String
    let mode: String
    let personName: String
    let ocrText: String
    let lastHeard: String
    let lastJarvisResponse: String
    let clipboardExcerpt: String
    let latitude: Double?
    let longitude: Double?

    init(
        id: UUID = UUID(),
        createdAt: Date = Date(),
        title: String,
        mode: String,
        personName: String,
        ocrText: String,
        lastHeard: String,
        lastJarvisResponse: String,
        clipboardExcerpt: String,
        latitude: Double?,
        longitude: Double?
    ) {
        self.id = id
        self.createdAt = createdAt
        self.title = title
        self.mode = mode
        self.personName = personName
        self.ocrText = ocrText
        self.lastHeard = lastHeard
        self.lastJarvisResponse = lastJarvisResponse
        self.clipboardExcerpt = clipboardExcerpt
        self.latitude = latitude
        self.longitude = longitude
    }

    var searchableText: String {
        [title, mode, personName, ocrText, lastHeard, lastJarvisResponse, clipboardExcerpt]
            .joined(separator: " ")
    }

    var compactDescription: String {
        var parts: [String] = []
        if !personName.isEmpty { parts.append("with \(personName)") }
        if !ocrText.isEmpty { parts.append("visible text: \(String(ocrText.replacingOccurrences(of: "\n", with: " ").prefix(120)))") }
        if !lastHeard.isEmpty { parts.append("heard: \(String(lastHeard.prefix(120)))") }
        if !lastJarvisResponse.isEmpty { parts.append("Jarvis: \(String(lastJarvisResponse.replacingOccurrences(of: "\n", with: " ").prefix(120)))") }
        if parts.isEmpty { parts.append("mode \(mode)") }
        return parts.joined(separator: " • ")
    }
}

struct LocalContactLink: Codable, Equatable {
    let personID: UUID
    let contactIdentifier: String
    let linkedAt: Date
}

struct LocalTimerRecord: Identifiable, Codable, Equatable {
    let id: UUID
    let createdAt: Date
    let fireAt: Date
    let label: String
    let notificationIdentifier: String

    init(
        id: UUID = UUID(),
        createdAt: Date = Date(),
        fireAt: Date,
        label: String,
        notificationIdentifier: String
    ) {
        self.id = id
        self.createdAt = createdAt
        self.fireAt = fireAt
        self.label = label
        self.notificationIdentifier = notificationIdentifier
    }

    var remaining: TimeInterval { fireAt.timeIntervalSinceNow }
}

struct LocalMemorySearchResult: Identifiable, Equatable {
    let id: String
    let source: String
    let title: String
    let detail: String
    let timestamp: Date
    let symbol: String
}

// MARK: - Encrypted milestone storage

private enum LocalIntelligenceSecureStore {
    private static let keyAccount = "jarvis.localIntelligence.storageKey.v1"

    static func load<T: Decodable>(_ type: T.Type, account: String, fallback: T) -> T {
        do {
            let url = try fileURL(account: account)
            guard FileManager.default.fileExists(atPath: url.path) else { return fallback }
            let combined = try Data(contentsOf: url)
            let sealed = try AES.GCM.SealedBox(combined: combined)
            let plain = try AES.GCM.open(sealed, using: key())
            return (try? JSONDecoder().decode(type, from: plain)) ?? fallback
        } catch {
            return fallback
        }
    }

    static func save<T: Encodable>(_ value: T, account: String) {
        do {
            let plain = try JSONEncoder().encode(value)
            let sealed = try AES.GCM.seal(plain, using: key())
            guard let combined = sealed.combined else { return }
            let url = try fileURL(account: account)
            try combined.write(to: url, options: [.atomic, .completeFileProtection])
        } catch {
            // Persistence failure must never break the foreground assistant.
        }
    }

    private static func key() -> SymmetricKey {
        if let existing = KeychainStore.readData(keyAccount), existing.count == 32 {
            return SymmetricKey(data: existing)
        }
        let generated = SymmetricKey(size: .bits256)
        let data = generated.withUnsafeBytes { Data($0) }
        KeychainStore.saveData(data, account: keyAccount)
        return generated
    }

    private static func fileURL(account: String) throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appendingPathComponent("JarvisLocalIntelligence", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true, attributes: nil)
        let digest = SHA256.hash(data: Data(account.utf8)).map { String(format: "%02x", $0) }.joined()
        return base.appendingPathComponent(digest + ".sealed")
    }
}

// MARK: - Deterministic local utilities

private enum DeterministicUtilityEngine {
    private struct UnitDefinition {
        let dimension: String
        let factorToBase: Double
        let display: String
    }

    static func answer(_ raw: String, now: Date = Date()) -> String? {
        let cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }

        if let result = timeAnswer(cleaned, now: now) { return result }
        if let result = dateAnswer(cleaned, now: now) { return result }
        if let result = percentageAnswer(cleaned) { return result }
        if let result = unitConversionAnswer(cleaned) { return result }
        if let result = arithmeticAnswer(cleaned) { return result }
        if let result = daysUntilAnswer(cleaned, now: now) { return result }
        return nil
    }

    private static func timeAnswer(_ raw: String, now: Date) -> String? {
        let n = normalize(raw)
        let timePhrases = ["what time is it", "what's the time", "what is the time", "time in "]
        guard timePhrases.contains(where: { n.contains($0) }) else { return nil }

        var location = ""
        if let range = n.range(of: " in ", options: .backwards) {
            location = String(n[range.upperBound...]).trimmingCharacters(in: CharacterSet.punctuationCharacters.union(.whitespaces))
        }

        let aliases: [String: String] = [
            "dc": "America/New_York",
            "washington dc": "America/New_York",
            "washington d.c": "America/New_York",
            "washington d.c.": "America/New_York",
            "new york": "America/New_York",
            "nyc": "America/New_York",
            "boston": "America/New_York",
            "miami": "America/New_York",
            "chicago": "America/Chicago",
            "dallas": "America/Chicago",
            "houston": "America/Chicago",
            "denver": "America/Denver",
            "phoenix": "America/Phoenix",
            "los angeles": "America/Los_Angeles",
            "la": "America/Los_Angeles",
            "san francisco": "America/Los_Angeles",
            "seattle": "America/Los_Angeles",
            "honolulu": "Pacific/Honolulu",
            "london": "Europe/London",
            "paris": "Europe/Paris",
            "berlin": "Europe/Berlin",
            "rome": "Europe/Rome",
            "tokyo": "Asia/Tokyo",
            "seoul": "Asia/Seoul",
            "hong kong": "Asia/Hong_Kong",
            "singapore": "Asia/Singapore",
            "sydney": "Australia/Sydney",
            "melbourne": "Australia/Melbourne",
            "dubai": "Asia/Dubai",
            "delhi": "Asia/Kolkata",
            "mumbai": "Asia/Kolkata",
        ]

        let zone: TimeZone
        let label: String
        if location.isEmpty {
            zone = .current
            label = "here"
        } else if let identifier = aliases[location], let mapped = TimeZone(identifier: identifier) {
            zone = mapped
            label = location.uppercased() == "DC" ? "DC" : location.split(separator: " ").map { $0.capitalized }.joined(separator: " ")
        } else if let direct = TimeZone(identifier: location) {
            zone = direct
            label = location
        } else {
            return nil
        }

        let formatter = DateFormatter()
        formatter.timeZone = zone
        formatter.dateFormat = "h:mm a"
        return "It's \(formatter.string(from: now)) in \(label), sir."
    }

    private static func dateAnswer(_ raw: String, now: Date) -> String? {
        let n = normalize(raw)
        guard n == "what day is it"
                || n == "what day is it?"
                || n == "what is today's date"
                || n == "what's today's date"
                || n == "what is the date"
                || n == "what's the date" else { return nil }
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d, yyyy"
        return "Today is \(formatter.string(from: now)), sir."
    }

    private static func percentageAnswer(_ raw: String) -> String? {
        let pattern = #"(?i)(?:what is\s+)?([+-]?\d+(?:\.\d+)?)\s*%\s+of\s+([+-]?\d+(?:\.\d+)?)"#
        guard let groups = capture(pattern, in: raw, groups: 2),
              let percent = Double(groups[0]),
              let value = Double(groups[1]) else { return nil }
        return "\(format(percent))% of \(format(value)) is \(format(percent * value / 100))."
    }

    private static func arithmeticAnswer(_ raw: String) -> String? {
        var expression = raw.lowercased()
        for prefix in ["what is ", "what's ", "calculate ", "compute "] where expression.hasPrefix(prefix) {
            expression = String(expression.dropFirst(prefix.count))
            break
        }
        expression = expression
            .replacingOccurrences(of: "multiplied by", with: "*")
            .replacingOccurrences(of: "times", with: "*")
            .replacingOccurrences(of: "divided by", with: "/")
            .replacingOccurrences(of: "over", with: "/")
            .replacingOccurrences(of: "plus", with: "+")
            .replacingOccurrences(of: "minus", with: "-")
            .replacingOccurrences(of: "to the power of", with: "^")
            .trimmingCharacters(in: CharacterSet(charactersIn: " ?.!"))

        guard expression.range(of: #"^[0-9+\-*/^().\s]+$"#, options: .regularExpression) != nil,
              expression.rangeOfCharacter(from: .decimalDigits) != nil,
              let value = evaluate(expression) else { return nil }
        return "\(format(value))."
    }

    private static func unitConversionAnswer(_ raw: String) -> String? {
        let pattern = #"(?i)^\s*(?:convert\s+)?([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z°/\. ]+?)\s+(?:in|to)\s+([a-zA-Z°/\. ]+?)\s*[?!.]*\s*$"#
        guard let groups = capture(pattern, in: raw, groups: 3), let value = Double(groups[0]) else { return nil }
        let fromKey = canonicalUnit(groups[1])
        let toKey = canonicalUnit(groups[2])

        if ["c", "f", "k"].contains(fromKey), ["c", "f", "k"].contains(toKey) {
            let celsius: Double
            switch fromKey {
            case "f": celsius = (value - 32) * 5 / 9
            case "k": celsius = value - 273.15
            default: celsius = value
            }
            let result: Double
            switch toKey {
            case "f": result = celsius * 9 / 5 + 32
            case "k": result = celsius + 273.15
            default: result = celsius
            }
            return "\(format(value))°\(fromKey.uppercased()) is \(format(result))°\(toKey.uppercased())."
        }

        guard let from = unitDefinition(fromKey), let to = unitDefinition(toKey), from.dimension == to.dimension else { return nil }
        let base = value * from.factorToBase
        let result = base / to.factorToBase
        return "\(format(value)) \(from.display) is \(format(result)) \(to.display)."
    }

    private static func daysUntilAnswer(_ raw: String, now: Date) -> String? {
        let n = normalize(raw)
        guard let range = n.range(of: "how many days until ") else { return nil }
        let targetText = String(n[range.upperBound...]).trimmingCharacters(in: CharacterSet.punctuationCharacters.union(.whitespaces))
        guard let target = detectDate(targetText, relativeTo: now) else { return nil }
        let start = Calendar.current.startOfDay(for: now)
        let end = Calendar.current.startOfDay(for: target)
        guard let days = Calendar.current.dateComponents([.day], from: start, to: end).day else { return nil }
        if days == 0 { return "That's today, sir." }
        if days > 0 { return "There are \(days) day\(days == 1 ? "" : "s") until then, sir." }
        return "That was \(-days) day\(-days == 1 ? "" : "s") ago, sir."
    }

    private static func canonicalUnit(_ raw: String) -> String {
        let n = raw.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: ".", with: "")
        let aliases: [String: String] = [
            "meter": "m", "meters": "m", "metre": "m", "metres": "m", "m": "m",
            "kilometer": "km", "kilometers": "km", "kilometre": "km", "kilometres": "km", "km": "km",
            "centimeter": "cm", "centimeters": "cm", "cm": "cm",
            "millimeter": "mm", "millimeters": "mm", "mm": "mm",
            "mile": "mi", "miles": "mi", "mi": "mi",
            "yard": "yd", "yards": "yd", "yd": "yd",
            "foot": "ft", "feet": "ft", "ft": "ft",
            "inch": "in", "inches": "in", "in": "in",
            "kilogram": "kg", "kilograms": "kg", "kg": "kg",
            "gram": "g", "grams": "g", "g": "g",
            "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
            "ounce": "oz", "ounces": "oz", "oz": "oz",
            "liter": "l", "liters": "l", "litre": "l", "litres": "l", "l": "l",
            "milliliter": "ml", "milliliters": "ml", "ml": "ml",
            "cup": "cup", "cups": "cup",
            "gallon": "gal", "gallons": "gal", "gal": "gal",
            "mph": "mph", "miles per hour": "mph",
            "kph": "kph", "km/h": "kph", "kilometers per hour": "kph",
            "m/s": "mps", "meters per second": "mps",
            "c": "c", "°c": "c", "celsius": "c",
            "f": "f", "°f": "f", "fahrenheit": "f",
            "k": "k", "kelvin": "k",
        ]
        return aliases[n] ?? n
    }

    private static func unitDefinition(_ key: String) -> UnitDefinition? {
        let values: [String: UnitDefinition] = [
            "m": .init(dimension: "length", factorToBase: 1, display: "m"),
            "km": .init(dimension: "length", factorToBase: 1000, display: "km"),
            "cm": .init(dimension: "length", factorToBase: 0.01, display: "cm"),
            "mm": .init(dimension: "length", factorToBase: 0.001, display: "mm"),
            "mi": .init(dimension: "length", factorToBase: 1609.344, display: "miles"),
            "yd": .init(dimension: "length", factorToBase: 0.9144, display: "yards"),
            "ft": .init(dimension: "length", factorToBase: 0.3048, display: "feet"),
            "in": .init(dimension: "length", factorToBase: 0.0254, display: "inches"),
            "kg": .init(dimension: "mass", factorToBase: 1, display: "kg"),
            "g": .init(dimension: "mass", factorToBase: 0.001, display: "g"),
            "lb": .init(dimension: "mass", factorToBase: 0.45359237, display: "lb"),
            "oz": .init(dimension: "mass", factorToBase: 0.028349523125, display: "oz"),
            "l": .init(dimension: "volume", factorToBase: 1, display: "L"),
            "ml": .init(dimension: "volume", factorToBase: 0.001, display: "mL"),
            "cup": .init(dimension: "volume", factorToBase: 0.2365882365, display: "US cups"),
            "gal": .init(dimension: "volume", factorToBase: 3.785411784, display: "US gallons"),
            "mps": .init(dimension: "speed", factorToBase: 1, display: "m/s"),
            "kph": .init(dimension: "speed", factorToBase: 0.2777777778, display: "km/h"),
            "mph": .init(dimension: "speed", factorToBase: 0.44704, display: "mph"),
        ]
        return values[key]
    }

    private enum Token {
        case number(Double)
        case op(Character)
        case left
        case right
    }

    private static func evaluate(_ expression: String) -> Double? {
        guard let tokens = tokenize(expression) else { return nil }
        var output: [Token] = []
        var operators: [Token] = []

        func precedence(_ op: Character) -> Int {
            switch op {
            case "^": return 3
            case "*", "/": return 2
            case "+", "-": return 1
            default: return 0
            }
        }

        for token in tokens {
            switch token {
            case .number:
                output.append(token)
            case .op(let op):
                while let last = operators.last {
                    guard case .op(let top) = last else { break }
                    let shouldPop = op == "^" ? precedence(top) > precedence(op) : precedence(top) >= precedence(op)
                    if shouldPop { output.append(operators.removeLast()) } else { break }
                }
                operators.append(token)
            case .left:
                operators.append(token)
            case .right:
                var foundLeft = false
                while let last = operators.popLast() {
                    if case .left = last { foundLeft = true; break }
                    output.append(last)
                }
                if !foundLeft { return nil }
            }
        }
        while let last = operators.popLast() {
            if case .left = last { return nil }
            output.append(last)
        }

        var stack: [Double] = []
        for token in output {
            switch token {
            case .number(let value): stack.append(value)
            case .op(let op):
                guard stack.count >= 2 else { return nil }
                let rhs = stack.removeLast()
                let lhs = stack.removeLast()
                let result: Double
                switch op {
                case "+": result = lhs + rhs
                case "-": result = lhs - rhs
                case "*": result = lhs * rhs
                case "/": guard rhs != 0 else { return nil }; result = lhs / rhs
                case "^": result = pow(lhs, rhs)
                default: return nil
                }
                guard result.isFinite else { return nil }
                stack.append(result)
            default: return nil
            }
        }
        return stack.count == 1 ? stack[0] : nil
    }

    private static func tokenize(_ expression: String) -> [Token]? {
        let chars = Array(expression)
        var result: [Token] = []
        var index = 0
        var expectingValue = true

        while index < chars.count {
            let char = chars[index]
            if char.isWhitespace { index += 1; continue }
            if char == "(" { result.append(.left); expectingValue = true; index += 1; continue }
            if char == ")" { result.append(.right); expectingValue = false; index += 1; continue }
            if "+-*/^".contains(char), !(char == "-" && expectingValue) {
                result.append(.op(char)); expectingValue = true; index += 1; continue
            }

            var number = ""
            if char == "-" && expectingValue {
                number.append(char)
                index += 1
            }
            var hasDigit = false
            var hasDot = false
            while index < chars.count {
                let c = chars[index]
                if c.isNumber { hasDigit = true; number.append(c); index += 1; continue }
                if c == ".", !hasDot { hasDot = true; number.append(c); index += 1; continue }
                break
            }
            guard hasDigit, let value = Double(number) else { return nil }
            result.append(.number(value))
            expectingValue = false
        }
        return result
    }

    private static func detectDate(_ text: String, relativeTo now: Date) -> Date? {
        let lower = text.lowercased()
        if lower == "today" { return now }
        if lower == "tomorrow" { return Calendar.current.date(byAdding: .day, value: 1, to: now) }

        if let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.date.rawValue) {
            let range = NSRange(text.startIndex..., in: text)
            if let match = detector.firstMatch(in: text, options: [], range: range), let date = match.date {
                return date
            }
        }

        let formats = ["MMMM d yyyy", "MMMM d, yyyy", "MMM d yyyy", "MMM d, yyyy", "M/d/yyyy", "M/d/yy", "MMMM d", "MMM d"]
        for format in formats {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.dateFormat = format
            if let parsed = formatter.date(from: text) {
                if format == "MMMM d" || format == "MMM d" {
                    var components = Calendar.current.dateComponents([.month, .day], from: parsed)
                    components.year = Calendar.current.component(.year, from: now)
                    if let candidate = Calendar.current.date(from: components) {
                        if candidate < Calendar.current.startOfDay(for: now) {
                            components.year = (components.year ?? 0) + 1
                            return Calendar.current.date(from: components)
                        }
                        return candidate
                    }
                }
                return parsed
            }
        }
        return nil
    }

    private static func capture(_ pattern: String, in text: String, groups: Int) -> [String]? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
        var values: [String] = []
        for index in 1...groups {
            guard let range = Range(match.range(at: index), in: text) else { return nil }
            values.append(String(text[range]))
        }
        return values
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased().replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func format(_ value: Double) -> String {
        if abs(value.rounded() - value) < 0.0000001 { return String(Int(value.rounded())) }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 6
        formatter.minimumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }
}

// MARK: - Native Calendar / Reminders / Contacts bridge

@MainActor
final class NativePersonalDataBridge: ObservableObject {
    @Published private(set) var calendarStatus = "Not requested"
    @Published private(set) var remindersStatus = "Not requested"
    @Published private(set) var contactsStatus = "Not requested"

    private let eventStore = EKEventStore()
    private let contactStore = CNContactStore()

    func requestCalendarAccess() async -> Bool {
        let status = EKEventStore.authorizationStatus(for: .event)
        if status == .fullAccess || status == .authorized {
            calendarStatus = "Full access"
            return true
        }
        if status == .denied || status == .restricted {
            calendarStatus = "Denied"
            return false
        }
        do {
            let granted = try await eventStore.requestFullAccessToEvents()
            calendarStatus = granted ? "Full access" : "Denied"
            return granted
        } catch {
            calendarStatus = "Unavailable: \(error.localizedDescription)"
            return false
        }
    }

    func requestRemindersAccess() async -> Bool {
        let status = EKEventStore.authorizationStatus(for: .reminder)
        if status == .fullAccess || status == .authorized {
            remindersStatus = "Full access"
            return true
        }
        if status == .denied || status == .restricted {
            remindersStatus = "Denied"
            return false
        }
        do {
            let granted = try await eventStore.requestFullAccessToReminders()
            remindersStatus = granted ? "Full access" : "Denied"
            return granted
        } catch {
            remindersStatus = "Unavailable: \(error.localizedDescription)"
            return false
        }
    }

    func requestContactsAccess() async -> Bool {
        let status = CNContactStore.authorizationStatus(for: .contacts)
        if status == .authorized {
            contactsStatus = "Authorized"
            return true
        }
        if status == .denied || status == .restricted {
            contactsStatus = "Denied"
            return false
        }
        let granted = await withCheckedContinuation { continuation in
            contactStore.requestAccess(for: .contacts) { granted, _ in
                continuation.resume(returning: granted)
            }
        }
        contactsStatus = granted ? "Authorized" : "Denied"
        return granted
    }

    func events(from start: Date, to end: Date, limit: Int = 10) async -> [EKEvent] {
        guard await requestCalendarAccess() else { return [] }
        let predicate = eventStore.predicateForEvents(withStart: start, end: end, calendars: nil)
        return Array(eventStore.events(matching: predicate).sorted { $0.startDate < $1.startDate }.prefix(max(1, min(limit, 20))))
    }

    func nextEvent() async -> EKEvent? {
        let now = Date()
        return await events(from: now, to: now.addingTimeInterval(14 * 86_400), limit: 20)
            .first(where: { $0.endDate > now })
    }

    func daySummary(offset: Int) async -> String {
        guard let date = Calendar.current.date(byAdding: .day, value: offset, to: Date()) else {
            return "I couldn't resolve that day locally."
        }
        let start = Calendar.current.startOfDay(for: date)
        let end = Calendar.current.date(byAdding: .day, value: 1, to: start) ?? start.addingTimeInterval(86_400)
        let items = await events(from: start, to: end, limit: 12)
        let dayName = offset == 0 ? "today" : (offset == 1 ? "tomorrow" : date.formatted(date: .abbreviated, time: .omitted))
        guard !items.isEmpty else { return "You have no events on your iPhone calendars \(dayName), sir." }
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return "Your iPhone calendars show \(items.count) event\(items.count == 1 ? "" : "s") \(dayName): " + items.map { event in
            if event.isAllDay { return "\(event.title ?? "Untitled event") all day" }
            return "\(event.title ?? "Untitled event") at \(formatter.string(from: event.startDate))"
        }.joined(separator: "; ") + "."
    }

    func nextEventSummary() async -> String {
        guard await requestCalendarAccess() else { return "Calendar access is not available on this iPhone, sir." }
        guard let event = await nextEvent() else { return "I don't see an upcoming event in the next two weeks on your iPhone calendars, sir." }
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE 'at' h:mm a"
        return "Your next iPhone calendar event is \(event.title ?? "Untitled event"), \(formatter.string(from: event.startDate)), sir."
    }

    func createReminder(title: String, dueAt: Date?) async -> String {
        guard await requestRemindersAccess() else { return "Reminders access is not available on this iPhone, sir." }
        guard let calendar = eventStore.defaultCalendarForNewReminders() else { return "I couldn't find a writable default Reminders list, sir." }
        let reminder = EKReminder(eventStore: eventStore)
        reminder.title = title
        reminder.calendar = calendar
        if let dueAt {
            reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: dueAt)
            reminder.alarms = [EKAlarm(absoluteDate: dueAt)]
        }
        do {
            try eventStore.save(reminder, commit: true)
            if let dueAt {
                let formatter = DateFormatter()
                formatter.dateFormat = "EEE MMM d 'at' h:mm a"
                return "I added that to Apple Reminders for \(formatter.string(from: dueAt)), sir."
            }
            return "I added that to Apple Reminders, sir."
        } catch {
            return "I couldn't save that reminder: \(error.localizedDescription)"
        }
    }

    func contacts(matching query: String, limit: Int = 5) async -> [CNContact] {
        guard await requestContactsAccess() else { return [] }
        let keys: [CNKeyDescriptor] = [
            CNContactIdentifierKey as CNKeyDescriptor,
            CNContactGivenNameKey as CNKeyDescriptor,
            CNContactFamilyNameKey as CNKeyDescriptor,
            CNContactOrganizationNameKey as CNKeyDescriptor,
            CNContactPhoneNumbersKey as CNKeyDescriptor,
            CNContactEmailAddressesKey as CNKeyDescriptor,
        ]
        do {
            let predicate = CNContact.predicateForContacts(matchingName: query)
            return Array(try contactStore.unifiedContacts(matching: predicate, keysToFetch: keys).prefix(max(1, min(limit, 10))))
        } catch {
            contactsStatus = "Lookup failed: \(error.localizedDescription)"
            return []
        }
    }

    func contact(identifier: String) async -> CNContact? {
        guard await requestContactsAccess() else { return nil }
        let keys: [CNKeyDescriptor] = [
            CNContactIdentifierKey as CNKeyDescriptor,
            CNContactGivenNameKey as CNKeyDescriptor,
            CNContactFamilyNameKey as CNKeyDescriptor,
            CNContactOrganizationNameKey as CNKeyDescriptor,
            CNContactPhoneNumbersKey as CNKeyDescriptor,
            CNContactEmailAddressesKey as CNKeyDescriptor,
        ]
        return try? contactStore.unifiedContact(withIdentifier: identifier, keysToFetch: keys)
    }

    static func displayName(_ contact: CNContact) -> String {
        let joined = [contact.givenName, contact.familyName].filter { !$0.isEmpty }.joined(separator: " ")
        if !joined.isEmpty { return joined }
        if !contact.organizationName.isEmpty { return contact.organizationName }
        return "Unnamed contact"
    }

    static func summary(_ contact: CNContact) -> String {
        let name = displayName(contact)
        let phones = contact.phoneNumbers.prefix(3).map { $0.value.stringValue }
        let emails = contact.emailAddresses.prefix(3).map { String($0.value) }
        var parts = [name]
        if !contact.organizationName.isEmpty, contact.organizationName.caseInsensitiveCompare(name) != .orderedSame {
            parts.append(contact.organizationName)
        }
        if !phones.isEmpty { parts.append("phone " + phones.joined(separator: ", ")) }
        if !emails.isEmpty { parts.append("email " + emails.joined(separator: ", ")) }
        return parts.joined(separator: " • ")
    }
}

// MARK: - Local-first routing, quality shield, memory center

@MainActor
final class LocalIntelligenceMilestoneController: ObservableObject {
    @Published var localFirstEnabled: Bool { didSet { defaults.set(localFirstEnabled, forKey: "jarvis.milestone.localFirst") } }
    @Published var simpleOnDeviceAnswersEnabled: Bool { didSet { defaults.set(simpleOnDeviceAnswersEnabled, forKey: "jarvis.milestone.simpleOnDevice") } }
    @Published var nativeCalendarEnabled: Bool { didSet { defaults.set(nativeCalendarEnabled, forKey: "jarvis.milestone.calendar") } }
    @Published var nativeRemindersEnabled: Bool { didSet { defaults.set(nativeRemindersEnabled, forKey: "jarvis.milestone.reminders") } }
    @Published var nativeContactsEnabled: Bool { didSet { defaults.set(nativeContactsEnabled, forKey: "jarvis.milestone.contacts") } }

    @Published private(set) var lastRoute = "Not used yet"
    @Published private(set) var locallyHandledCount = 0
    @Published private(set) var capsules: [LocalContextCapsule]
    @Published private(set) var contactLinks: [LocalContactLink]
    @Published private(set) var timers: [LocalTimerRecord]
    @Published private(set) var lastMemorySearch = ""

    let nativeData = NativePersonalDataBridge()

    private static let capsulesAccount = "jarvis.localIntelligence.capsules.v1"
    private static let contactLinksAccount = "jarvis.localIntelligence.contactLinks.v1"
    private static let timersAccount = "jarvis.localIntelligence.timers.v1"

    private let defaults = UserDefaults.standard
    private unowned let appModel: JarvisAppModel
    private unowned let frontend: FrontendIntelligenceController
    private unowned let knownPeople: KnownPeopleController
    private unowned let power: LocalPowerFeaturesController
    private unowned let productivity: LocalProductivityController
    private var started = false

    init(
        appModel: JarvisAppModel,
        frontend: FrontendIntelligenceController,
        knownPeople: KnownPeopleController,
        power: LocalPowerFeaturesController,
        productivity: LocalProductivityController
    ) {
        self.appModel = appModel
        self.frontend = frontend
        self.knownPeople = knownPeople
        self.power = power
        self.productivity = productivity
        localFirstEnabled = defaults.object(forKey: "jarvis.milestone.localFirst") as? Bool ?? true
        simpleOnDeviceAnswersEnabled = defaults.object(forKey: "jarvis.milestone.simpleOnDevice") as? Bool ?? true
        nativeCalendarEnabled = defaults.object(forKey: "jarvis.milestone.calendar") as? Bool ?? true
        nativeRemindersEnabled = defaults.object(forKey: "jarvis.milestone.reminders") as? Bool ?? true
        nativeContactsEnabled = defaults.object(forKey: "jarvis.milestone.contacts") as? Bool ?? true
        capsules = LocalIntelligenceSecureStore.load([LocalContextCapsule].self, account: Self.capsulesAccount, fallback: [])
        contactLinks = LocalIntelligenceSecureStore.load([LocalContactLink].self, account: Self.contactLinksAccount, fallback: [])
        timers = LocalIntelligenceSecureStore.load([LocalTimerRecord].self, account: Self.timersAccount, fallback: [])
        pruneTimers()
    }

    func start() async {
        guard !started else { return }
        started = true

        // Start last so this becomes the outermost local command layer. It gets the
        // first chance to answer deterministic/native questions, then delegates to
        // Known People, Power Features, Productivity, and finally the PC backend.
        let previousHandler = appModel.frontendCommandHandler
        appModel.frontendCommandHandler = { [weak self] command in
            guard let self else { return await previousHandler?(command) }

            if self.localFirstEnabled,
               let local = await self.handleMilestoneCommand(command) {
                self.recordRoute("iPhone local-first")
                return local
            }

            if let inherited = await previousHandler?(command) {
                return inherited
            }

            if self.localFirstEnabled,
               self.simpleOnDeviceAnswersEnabled,
               Self.isSimpleStableQuestion(command),
               let answer = await self.power.offlineBrain.respond(
                    to: command,
                    context: self.smallLocalContextForModel()
               ), !answer.isEmpty {
                self.recordRoute("iPhone Apple model • backend bypassed")
                return answer
            }
            return nil
        }
    }

    func stop() {
        started = false
    }

    private func recordRoute(_ route: String) {
        lastRoute = route
        locallyHandledCount += 1
    }

    private func handleMilestoneCommand(_ raw: String) async -> String? {
        if let deterministic = DeterministicUtilityEngine.answer(raw) {
            return deterministic
        }

        let n = Self.normalize(raw)

        if n == "local intelligence status" || n == "local first status" || n == "quality shield status" {
            return "Local-first routing is \(localFirstEnabled ? "on" : "off"). I've handled \(locallyHandledCount) requests locally in this app session. Last route: \(lastRoute)."
        }

        if n.contains("remember this context") || n.contains("save this context") || n.contains("save a context capsule") {
            return saveContextCapsule()
        }
        if n == "show saved contexts" || n == "list saved contexts" || n == "what context did i save" {
            return capsuleSummary()
        }
        if n == "forget last context" || n == "delete last context capsule" {
            return deleteLastCapsule()
        }
        if n.hasPrefix("search local memory for ") {
            let query = String(n.dropFirst("search local memory for ".count))
            return await answerFromLocalMemory(query)
        }
        if n.hasPrefix("what do you remember locally about ") {
            let query = String(n.dropFirst("what do you remember locally about ".count))
            return await answerFromLocalMemory(query)
        }

        if nativeCalendarEnabled {
            if Self.isNextEventRequest(n) { return await nativeData.nextEventSummary() }
            if Self.isTodayCalendarRequest(n) { return await nativeData.daySummary(offset: 0) }
            if Self.isTomorrowCalendarRequest(n) { return await nativeData.daySummary(offset: 1) }
        }

        if nativeRemindersEnabled, let reminder = Self.parseReminder(raw) {
            return await nativeData.createReminder(title: reminder.title, dueAt: reminder.dueAt)
        }

        if let timer = Self.parseTimer(raw) {
            return await createTimer(seconds: timer.seconds, label: timer.label)
        }
        if n == "how much time is left" || n == "how much time is left on my timer" || n == "timer status" {
            return timerStatus()
        }
        if n == "cancel timer" || n == "cancel my timer" || n == "stop timer" {
            return await cancelSoonestTimer()
        }

        if nativeContactsEnabled, let contactQuery = Self.parseContactQuery(raw, currentPerson: knownPeople.currentPerson()?.name) {
            return await contactAnswer(query: contactQuery)
        }
        if n == "link known people to contacts" || n == "link my known people to contacts" {
            return await linkKnownPeopleToContacts()
        }

        return nil
    }

    // MARK: Context capsules

    @discardableResult
    func saveContextCapsule(title requestedTitle: String = "") -> String {
        let person = knownPeople.currentPerson()?.name ?? ""
        let ocr = String(frontend.localOCRText.prefix(1800))
        let clipboard = String(productivity.clipboardText().prefix(1600))
        let coordinate = frontend.sensors.coordinate
        let title: String
        if !requestedTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            title = String(requestedTitle.trimmingCharacters(in: .whitespacesAndNewlines).prefix(120))
        } else if !person.isEmpty {
            title = "Context with \(person)"
        } else if !ocr.isEmpty {
            title = "Visible context: \(String(ocr.replacingOccurrences(of: "\n", with: " ").prefix(60)))"
        } else {
            title = "Saved context"
        }

        let capsule = LocalContextCapsule(
            title: title,
            mode: power.mode.rawValue,
            personName: person,
            ocrText: ocr,
            lastHeard: String(appModel.lastHeardCommand.prefix(1200)),
            lastJarvisResponse: String(appModel.lastResponse.prefix(1800)),
            clipboardExcerpt: clipboard,
            latitude: coordinate?.latitude,
            longitude: coordinate?.longitude
        )
        capsules.append(capsule)
        if capsules.count > 100 { capsules.removeFirst(capsules.count - 100) }
        persistCapsules()
        return "Saved a private local context capsule, sir. \(capsule.compactDescription)"
    }

    func deleteCapsule(_ capsule: LocalContextCapsule) {
        capsules.removeAll { $0.id == capsule.id }
        persistCapsules()
    }

    private func deleteLastCapsule() -> String {
        guard let last = capsules.last else { return "There are no saved context capsules, sir." }
        capsules.removeLast()
        persistCapsules()
        return "Deleted the most recent context capsule, \(last.title), sir."
    }

    private func capsuleSummary() -> String {
        let recent = capsules.suffix(6)
        guard !recent.isEmpty else { return "You have no saved context capsules, sir." }
        return recent.reversed().map { "\($0.title) — \($0.compactDescription)" }.joined(separator: "\n")
    }

    private func persistCapsules() {
        LocalIntelligenceSecureStore.save(capsules, account: Self.capsulesAccount)
    }

    // MARK: Timers

    private func createTimer(seconds: TimeInterval, label: String) async -> String {
        let bounded = max(1, min(seconds, 7 * 86_400))
        do {
            let center = UNUserNotificationCenter.current()
            _ = try await center.requestAuthorization(options: [.alert, .sound])
            let content = UNMutableNotificationContent()
            content.title = "Jarvis Timer"
            content.body = label.isEmpty ? "Timer complete." : "\(label) complete."
            content.sound = .default
            let identifier = "jarvis.localTimer.\(UUID().uuidString)"
            let request = UNNotificationRequest(
                identifier: identifier,
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: bounded, repeats: false)
            )
            try await center.add(request)
            let record = LocalTimerRecord(fireAt: Date().addingTimeInterval(bounded), label: label, notificationIdentifier: identifier)
            timers.append(record)
            if timers.count > 30 { timers.removeFirst(timers.count - 30) }
            persistTimers()
            return "Timer set for \(Self.durationDescription(bounded)), sir. It will alert through an iPhone notification even without the PC."
        } catch {
            return "I couldn't schedule the local timer: \(error.localizedDescription)"
        }
    }

    private func timerStatus() -> String {
        pruneTimers()
        guard let next = timers.filter({ $0.fireAt > Date() }).sorted(by: { $0.fireAt < $1.fireAt }).first else {
            return "There is no active local Jarvis timer, sir."
        }
        return "The next local timer has about \(Self.durationDescription(max(0, next.remaining))) remaining, sir."
    }

    private func cancelSoonestTimer() async -> String {
        pruneTimers()
        guard let next = timers.filter({ $0.fireAt > Date() }).sorted(by: { $0.fireAt < $1.fireAt }).first else {
            return "There is no active local Jarvis timer to cancel, sir."
        }
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [next.notificationIdentifier])
        timers.removeAll { $0.id == next.id }
        persistTimers()
        return "Cancelled the next local timer, sir."
    }

    private func pruneTimers() {
        let cutoff = Date().addingTimeInterval(-3600)
        timers.removeAll { $0.fireAt < cutoff }
        LocalIntelligenceSecureStore.save(timers, account: Self.timersAccount)
    }

    private func persistTimers() {
        LocalIntelligenceSecureStore.save(timers, account: Self.timersAccount)
    }

    // MARK: Contacts bridge

    private func contactAnswer(query: String) async -> String {
        if let person = knownPeople.currentPerson(),
           person.name.compare(query, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame,
           let link = contactLinks.first(where: { $0.personID == person.id }),
           let contact = await nativeData.contact(identifier: link.contactIdentifier) {
            return NativePersonalDataBridge.summary(contact)
        }

        let contacts = await nativeData.contacts(matching: query, limit: 5)
        guard !contacts.isEmpty else { return "I couldn't find a matching iPhone contact for \(query), sir." }
        if contacts.count == 1 { return NativePersonalDataBridge.summary(contacts[0]) }

        let exact = contacts.filter {
            NativePersonalDataBridge.displayName($0).compare(query, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
        }
        if exact.count == 1 { return NativePersonalDataBridge.summary(exact[0]) }
        return "I found multiple matching iPhone contacts: " + contacts.map { NativePersonalDataBridge.displayName($0) }.joined(separator: ", ") + ". Please be more specific."
    }

    @discardableResult
    func linkKnownPeopleToContacts() async -> String {
        guard nativeContactsEnabled else { return "The native Contacts bridge is disabled." }
        guard await nativeData.requestContactsAccess() else { return "Contacts access is not available on this iPhone, sir." }
        var linked = 0
        var ambiguous: [String] = []
        var updated = contactLinks

        for person in knownPeople.people {
            let matches = await nativeData.contacts(matching: person.name, limit: 8)
            let exact = matches.filter {
                NativePersonalDataBridge.displayName($0).compare(person.name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
            }
            if exact.count == 1, let contact = exact.first {
                updated.removeAll { $0.personID == person.id }
                updated.append(LocalContactLink(personID: person.id, contactIdentifier: contact.identifier, linkedAt: Date()))
                linked += 1
            } else if matches.count == 1, let contact = matches.first {
                updated.removeAll { $0.personID == person.id }
                updated.append(LocalContactLink(personID: person.id, contactIdentifier: contact.identifier, linkedAt: Date()))
                linked += 1
            } else if matches.count > 1 {
                ambiguous.append(person.name)
            }
        }
        contactLinks = updated
        LocalIntelligenceSecureStore.save(contactLinks, account: Self.contactLinksAccount)
        var response = "Linked \(linked) enrolled Known People profile\(linked == 1 ? "" : "s") to iPhone Contacts."
        if !ambiguous.isEmpty { response += " I left ambiguous matches unlinked: \(ambiguous.joined(separator: ", "))." }
        return response
    }

    // MARK: Unified local memory

    func memoryResults(query rawQuery: String) -> [LocalMemorySearchResult] {
        let query = Self.normalize(rawQuery)
        let tokens = query.split(separator: " ").map(String.init).filter { $0.count >= 2 }
        var results: [LocalMemorySearchResult] = []

        func matches(_ text: String) -> Bool {
            if tokens.isEmpty { return true }
            let lower = text.lowercased()
            return tokens.allSatisfy { lower.contains($0) }
                || tokens.filter { lower.contains($0) }.count >= max(1, (tokens.count + 1) / 2)
        }

        for capsule in capsules where matches(capsule.searchableText) {
            results.append(.init(
                id: "capsule-\(capsule.id)", source: "Context Capsule", title: capsule.title,
                detail: capsule.compactDescription, timestamp: capsule.createdAt, symbol: "archivebox.fill"
            ))
        }
        for turn in appModel.conversationLog where matches(turn.text) {
            results.append(.init(
                id: "conversation-\(turn.id)", source: "Conversation", title: turn.role == "user" ? "You" : "Jarvis",
                detail: String(turn.text.prefix(1200)), timestamp: turn.timestamp, symbol: "bubble.left.and.bubble.right.fill"
            ))
        }
        for person in knownPeople.people where matches(person.name + " " + person.notes) {
            results.append(.init(
                id: "person-\(person.id)", source: "Known Person", title: person.name,
                detail: person.notes.isEmpty ? "Explicitly enrolled Known People profile" : person.notes,
                timestamp: person.enrolledAt, symbol: "person.crop.circle"
            ))
        }
        for event in power.events where matches(event.title + " " + event.detail) {
            results.append(.init(
                id: "event-\(event.id)", source: "Local Event", title: event.title,
                detail: event.detail, timestamp: event.timestamp, symbol: "clock.arrow.circlepath"
            ))
        }
        for encounter in power.encounters where matches(encounter.personName + " " + encounter.summary + " " + encounter.transcriptExcerpt) {
            results.append(.init(
                id: "encounter-\(encounter.id)", source: "Encounter", title: encounter.personName,
                detail: encounter.summary.isEmpty ? encounter.transcriptExcerpt : encounter.summary,
                timestamp: encounter.endedAt, symbol: "person.2.wave.2"
            ))
        }
        for item in power.inventory where matches(item.name + " " + item.note) {
            results.append(.init(
                id: "inventory-\(item.id)", source: "Inventory", title: item.name,
                detail: item.note.isEmpty ? "Private enrolled inventory item" : item.note,
                timestamp: item.lastSeenAt ?? .distantPast, symbol: "shippingbox.fill"
            ))
        }
        for goal in productivity.goals where matches(goal.title + " " + goal.nextAction + " " + goal.note) {
            results.append(.init(
                id: "goal-\(goal.id)", source: "Goal", title: goal.title,
                detail: goal.nextAction.isEmpty ? goal.note : "Next: \(goal.nextAction)",
                timestamp: goal.createdAt, symbol: "scope"
            ))
        }
        for item in productivity.waitingItems where matches(item.person + " " + item.item) {
            results.append(.init(
                id: "waiting-\(item.id)", source: "Waiting On", title: item.person.isEmpty ? "Waiting item" : item.person,
                detail: item.item, timestamp: item.createdAt, symbol: "hourglass"
            ))
        }
        for receipt in productivity.receipts where matches(receipt.action + " " + receipt.detail) {
            results.append(.init(
                id: "receipt-\(receipt.id)", source: "Action Receipt", title: receipt.action,
                detail: receipt.detail, timestamp: receipt.timestamp, symbol: "checkmark.seal.fill"
            ))
        }

        return Array(results.sorted { $0.timestamp > $1.timestamp }.prefix(100))
    }

    private func answerFromLocalMemory(_ query: String) async -> String {
        let results = memoryResults(query: query)
        lastMemorySearch = query
        guard !results.isEmpty else { return "I couldn't find anything matching that in the iPhone's local Jarvis memory, sir." }

        let packet = results.prefix(10).map {
            "[\($0.source)] \($0.title): \($0.detail)"
        }.joined(separator: "\n")

        if simpleOnDeviceAnswersEnabled,
           let answer = await power.offlineBrain.respond(
                to: "Answer this local-memory question using ONLY the records below. If the records do not establish an answer, say so. Question: \(query)\n\nRecords:\n\(packet)",
                context: "These are the user's private local Jarvis records. Do not invent missing facts."
           ), !answer.isEmpty {
            return answer
        }
        return packet
    }

    private func smallLocalContextForModel() -> String {
        var lines = ["Conversation mode: \(power.mode.rawValue)."]
        if let person = knownPeople.currentPerson() { lines.append("Current explicitly enrolled person match: \(person.name) (advisory).") }
        if !appModel.lastResponse.isEmpty { lines.append("Immediately previous Jarvis response: \(String(appModel.lastResponse.prefix(900)))") }
        return lines.joined(separator: "\n")
    }

    // MARK: Routing heuristics

    private static func isSimpleStableQuestion(_ raw: String) -> Bool {
        let n = " " + normalize(raw) + " "
        guard n.count <= 520 else { return false }

        let backendOrFreshness = [
            " latest ", " breaking ", " news ", " weather ", " forecast ", " score ", " standings ",
            " stock ", " price ", " traffic ", " live ", " right now online ", " search ", " google ",
            " look up ", " browse ", " website ", " web ", " current president ", " current ceo ",
            " my email ", " my inbox ", " gmail ", " my pc ", " my computer ", " browser tab ",
            " file on ", " document on ", " open ", " launch ", " close ", " quit ", " send ",
            " reply ", " forward ", " create ", " delete ", " remove ", " run ", " execute ",
            " turn on ", " turn off ", " schedule ", " book ", " buy ", " call ", " text ",
            " what can you see ", " what am i looking at ", " clipboard ",
        ]
        if backendOrFreshness.contains(where: { n.contains($0) }) { return false }
        if n.contains(" my ") && !n.contains(" my name mean ") { return false }

        let prefixes = [
            " what is ", " what's ", " what are ", " explain ", " define ", " why does ", " why do ",
            " why is ", " how does ", " how do ", " how is ", " compare ", " tell me about ",
        ]
        return prefixes.contains(where: { n.hasPrefix($0) }) || normalize(raw).hasSuffix("?")
    }

    private static func isNextEventRequest(_ n: String) -> Bool {
        ["what's next on my calendar", "what is next on my calendar", "next calendar event", "next meeting", "what's my next meeting", "what is my next meeting"].contains(n)
    }

    private static func isTodayCalendarRequest(_ n: String) -> Bool {
        n.contains("calendar today") || n.contains("schedule today") || n.contains("meetings today") || n == "what do i have today" || n == "what's on my calendar today"
    }

    private static func isTomorrowCalendarRequest(_ n: String) -> Bool {
        n.contains("calendar tomorrow") || n.contains("schedule tomorrow") || n.contains("meetings tomorrow") || n == "what do i have tomorrow" || n == "what's on my calendar tomorrow" || n == "what meetings do i have tomorrow"
    }

    private static func parseReminder(_ raw: String) -> (title: String, dueAt: Date?)? {
        let lower = raw.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard lower.hasPrefix("remind me ") else { return nil }

        if let groups = regexCapture(#"(?i)^remind me in\s+(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days)\s+to\s+(.+)$"#, raw, groups: 3),
           let amount = Double(groups[0]) {
            let seconds = amount * multiplier(for: groups[1])
            return (groups[2].trimmingCharacters(in: .whitespacesAndNewlines), Date().addingTimeInterval(seconds))
        }

        guard let toRange = lower.range(of: "remind me to ") else { return nil }
        var title = String(raw[toRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
        var due: Date?

        if let groups = regexCapture(#"(?i)\s+in\s+(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days)\s*[.!?]*$"#, title, groups: 2),
           let amount = Double(groups[0]) {
            due = Date().addingTimeInterval(amount * multiplier(for: groups[1]))
            title = title.replacingOccurrences(of: #"(?i)\s+in\s+\d+\s+(second|seconds|minute|minutes|hour|hours|day|days)\s*[.!?]*$"#, with: "", options: .regularExpression)
        } else if let resolved = parseNaturalDueDate(title) {
            due = resolved.date
            title = resolved.cleanedTitle
        }

        title = title.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
        guard !title.isEmpty else { return nil }
        return (title, due)
    }

    private static func parseNaturalDueDate(_ title: String) -> (date: Date, cleanedTitle: String)? {
        let lower = title.lowercased()
        var dayOffset: Int?
        if lower.contains(" tomorrow") || lower.hasPrefix("tomorrow") { dayOffset = 1 }
        else if lower.contains(" today") || lower.hasPrefix("today") { dayOffset = 0 }
        guard let offset = dayOffset else { return nil }

        let base = Calendar.current.date(byAdding: .day, value: offset, to: Date()) ?? Date()
        var components = Calendar.current.dateComponents([.year, .month, .day], from: base)
        if let groups = regexCapture(#"(?i)\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b"#, title, groups: 3) {
            var hour = Int(groups[0]) ?? 9
            let minute = Int(groups[1]) ?? 0
            let ampm = groups[2].lowercased()
            if ampm == "pm" && hour < 12 { hour += 12 }
            if ampm == "am" && hour == 12 { hour = 0 }
            components.hour = max(0, min(hour, 23))
            components.minute = max(0, min(minute, 59))
        } else {
            components.hour = 9
            components.minute = 0
        }
        guard let date = Calendar.current.date(from: components) else { return nil }
        var cleaned = title.replacingOccurrences(of: #"(?i)\s*\b(today|tomorrow)\b\s*"#, with: " ", options: .regularExpression)
        cleaned = cleaned.replacingOccurrences(of: #"(?i)\s*\bat\s+\d{1,2}(?::\d{2})?\s*(am|pm)?\b\s*"#, with: " ", options: .regularExpression)
        return (date, cleaned.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func parseTimer(_ raw: String) -> (seconds: TimeInterval, label: String)? {
        guard let groups = regexCapture(#"(?i)^(?:set|start)\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+(?:\.\d+)?)\s+(second|seconds|minute|minutes|hour|hours)(?:\s+(?:for|called|named)\s+(.+))?[.!?]*$"#, raw.trimmingCharacters(in: .whitespacesAndNewlines), groups: 3),
              let amount = Double(groups[0]) else { return nil }
        return (amount * multiplier(for: groups[1]), groups[2].trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func parseContactQuery(_ raw: String, currentPerson: String?) -> String? {
        let n = normalize(raw)
        if let currentPerson,
           ["what's their phone number", "what is their phone number", "what's their email", "what is their email", "their contact info"].contains(n) {
            return currentPerson
        }
        let patterns = [
            #"(?i)^what(?:'s| is)\s+(.+?)(?:'s|’s)\s+(?:phone number|email|contact info)[?!.]*$"#,
            #"(?i)^(?:show|give me)\s+(?:the\s+)?contact info for\s+(.+?)[?!.]*$"#,
            #"(?i)^look up\s+(.+?)\s+in (?:my )?contacts[?!.]*$"#,
        ]
        for pattern in patterns {
            if let groups = regexCapture(pattern, raw, groups: 1) { return groups[0].trimmingCharacters(in: .whitespacesAndNewlines) }
        }
        return nil
    }

    private static func multiplier(for unit: String) -> Double {
        let u = unit.lowercased()
        if u.hasPrefix("second") { return 1 }
        if u.hasPrefix("minute") { return 60 }
        if u.hasPrefix("hour") { return 3600 }
        if u.hasPrefix("day") { return 86_400 }
        return 1
    }

    private static func durationDescription(_ seconds: TimeInterval) -> String {
        let rounded = max(0, Int(seconds.rounded()))
        if rounded >= 3600 {
            let h = rounded / 3600
            let m = (rounded % 3600) / 60
            return m == 0 ? "\(h) hour\(h == 1 ? "" : "s")" : "\(h) hour\(h == 1 ? "" : "s") \(m) minute\(m == 1 ? "" : "s")"
        }
        if rounded >= 60 {
            let m = rounded / 60
            let s = rounded % 60
            return s == 0 ? "\(m) minute\(m == 1 ? "" : "s")" : "\(m) minute\(m == 1 ? "" : "s") \(s) seconds"
        }
        return "\(rounded) second\(rounded == 1 ? "" : "s")"
    }

    private static func regexCapture(_ pattern: String, _ text: String, groups: Int) -> [String]? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
        var values: [String] = []
        for index in 1...groups {
            let nsRange = match.range(at: index)
            if nsRange.location == NSNotFound { values.append(""); continue }
            guard let range = Range(nsRange, in: text) else { values.append(""); continue }
            values.append(String(text[range]))
        }
        return values
    }

    private static func normalize(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
    }
}

// MARK: - Milestone UI

struct LocalIntelligenceMilestoneView: View {
    @EnvironmentObject private var intelligence: LocalIntelligenceMilestoneController
    @EnvironmentObject private var appModel: JarvisAppModel
    @EnvironmentObject private var knownPeople: KnownPeopleController
    @State private var memoryQuery = ""
    @State private var capsuleTitle = ""

    var body: some View {
        NavigationStack {
            List {
                Section("Local-first reliability") {
                    Toggle("Local-first routing", isOn: $intelligence.localFirstEnabled)
                    Toggle("Use Apple on-device model for simple stable questions", isOn: $intelligence.simpleOnDeviceAnswersEnabled)
                    LabeledContent("Last route", value: intelligence.lastRoute)
                    LabeledContent("Handled locally this session", value: String(intelligence.locallyHandledCount))
                    Text("Deterministic time/date, arithmetic, percentages and unit conversion are handled before the PC. Stable explanatory questions can use Apple's on-device model. Requests that clearly need current web data, private PC data or external actions continue to the backend.")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Section("Native iPhone data") {
                    Toggle("Read iPhone calendars locally", isOn: $intelligence.nativeCalendarEnabled)
                    Toggle("Create Apple Reminders locally", isOn: $intelligence.nativeRemindersEnabled)
                    Toggle("Use iPhone Contacts locally", isOn: $intelligence.nativeContactsEnabled)
                    LabeledContent("Calendar", value: intelligence.nativeData.calendarStatus)
                    LabeledContent("Reminders", value: intelligence.nativeData.remindersStatus)
                    LabeledContent("Contacts", value: intelligence.nativeData.contactsStatus)
                    HStack {
                        Button("Calendar Access") { Task { _ = await intelligence.nativeData.requestCalendarAccess() } }
                        Button("Reminders Access") { Task { _ = await intelligence.nativeData.requestRemindersAccess() } }
                    }
                    Button("Contacts Access") { Task { _ = await intelligence.nativeData.requestContactsAccess() } }
                    if !knownPeople.people.isEmpty {
                        Button("Link Known People to Contacts by name") {
                            Task { appModel.lastResponse = await intelligence.linkKnownPeopleToContacts() }
                        }
                    }
                }

                Section("Context Capsules") {
                    TextField("Optional capsule title", text: $capsuleTitle)
                    Button("Save current context") {
                        appModel.lastResponse = intelligence.saveContextCapsule(title: capsuleTitle)
                        capsuleTitle = ""
                    }
                    NavigationLink("Search all local Jarvis memory") {
                        LocalMemoryCenterView()
                    }
                    if intelligence.capsules.isEmpty {
                        Text("No saved capsules yet.").foregroundStyle(.secondary)
                    } else {
                        ForEach(intelligence.capsules.suffix(4).reversed()) { capsule in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(capsule.title).font(.headline)
                                Text(capsule.compactDescription).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                            }
                        }
                    }
                }

                Section("Local timers") {
                    let active = intelligence.timers.filter { $0.fireAt > Date() }.sorted { $0.fireAt < $1.fireAt }
                    if active.isEmpty {
                        Text("No active local timers.").foregroundStyle(.secondary)
                    } else {
                        ForEach(active) { timer in
                            LabeledContent(timer.label.isEmpty ? "Jarvis timer" : timer.label) {
                                Text(timer.fireAt, style: .timer).monospacedDigit()
                            }
                        }
                    }
                    Text("These are Jarvis local-notification timers, not Clock.app timers. They do not require the PC.")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Section("Quick verification") {
                    verificationRow("What time is it in DC?", note: "Should say the time directly; it must not inspect Clock.app.")
                    verificationRow("What is 17 times 24?", note: "Should answer 408 locally.")
                    verificationRow("Convert 5 miles to kilometers", note: "Should convert locally.")
                    verificationRow("What meetings do I have tomorrow?", note: "Uses EventKit/iPhone Calendar if access is granted.")
                    verificationRow("Set a timer for 2 minutes", note: "Schedules a local iPhone notification.")
                    verificationRow("Remember this context", note: "Creates an encrypted local context capsule.")
                }

                Section("Milestone boundary") {
                    Text("This milestone does not modify the Windows backend. It does not enable the pending backend conversational live-scene fix, does not intercept third-party iPhone notifications, and does not add a Dynamic Island/Control Center extension target. Those require separate deployment or extension work.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Local Intelligence")
        }
    }

    @ViewBuilder
    private func verificationRow(_ prompt: String, note: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(prompt).font(.headline)
            Text(note).font(.caption).foregroundStyle(.secondary)
            Button("Run") { Task { await appModel.sendCommand(prompt) } }
                .buttonStyle(.bordered)
        }
        .padding(.vertical, 2)
    }
}

struct LocalMemoryCenterView: View {
    @EnvironmentObject private var intelligence: LocalIntelligenceMilestoneController
    @State private var query = ""

    var body: some View {
        List {
            let results = intelligence.memoryResults(query: query)
            if results.isEmpty {
                ContentUnavailableView("No local matches", systemImage: "magnifyingglass", description: Text("Search conversations, people, encounters, goals, waiting items, inventory, events, action receipts and context capsules."))
            } else {
                ForEach(results) { result in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Label(result.source, systemImage: result.symbol)
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            if result.timestamp != .distantPast {
                                Text(result.timestamp, style: .date).font(.caption2).foregroundStyle(.tertiary)
                            }
                        }
                        Text(result.title).font(.headline)
                        Text(result.detail).font(.callout).textSelection(.enabled).lineLimit(8)
                    }
                    .padding(.vertical, 3)
                }
            }
        }
        .navigationTitle("Local Memory")
        .searchable(text: $query, prompt: "Search private local Jarvis memory")
    }
}
