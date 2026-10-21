"""Static wiring checks for the AirPods-first Instant Earpiece / interruptible conversation flow.

These tests read the Swift sources: no Swift compiler or iPhone exists in this
environment, so real AirPods HFP routing, barge-in echo behavior, the Action Button
and latency remain device-acceptance items (see ios/README.md).
"""
from __future__ import annotations

import plistlib
import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_IOS = _ROOT / "ios" / "JarvisIOS"


def _read(name: str) -> str:
    return (_IOS / name).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


class AudioRouteAndInterruptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recognizer = _read("SpeechRecognizer.swift")
        self.synth = _read("SpeechSynthesizer.swift")
        self.model = _read("JarvisAppModel.swift")
        self.cues = _read("AmbientCuePlayer.swift")

    def test_old_device_unavailable_stops_private_speech_immediately(self) -> None:
        handler = _between(self.recognizer, "private func handleRouteChange(", "private func preferredBluetoothInput")
        self.assertIn("AVAudioSessionRouteChangeReasonKey", handler)
        self.assertIn("AVAudioSessionRouteChangePreviousRouteKey", handler)
        self.assertIn("reason == .oldDeviceUnavailable", handler)
        self.assertIn("previousWasPrivate", handler)
        self.assertIn("privateOutputLost = true", handler)
        self.assertIn("onPrivateOutputLost?()", handler)
        # Only headphone / Bluetooth ports count as private.
        ports = _between(self.recognizer, "private static func isPrivatePort", "func prepareForVoice")
        for port in (".headphones", ".bluetoothA2DP", ".bluetoothHFP", ".bluetoothLE"):
            self.assertIn(port, ports)
        # The route-change observer feeds the handler.
        self.assertIn("self.handleRouteChange(note)", self.recognizer)
        # The app model stops speech and capture, and explains why on screen.
        lost = _between(self.model, "private func handlePrivateOutputLost()", "private func handlePrivateOutputRestored()")
        self.assertIn("speechSynthesizer.stopSpeakingForPrivateRouteLoss()", lost)
        self.assertIn("cancelPushToTalk()", lost)
        self.assertIn("Headphones disconnected", lost)
        self.assertIn("audioRouteManager.onPrivateOutputLost", self.model)

    def test_speech_and_cues_never_continue_on_loudspeaker_after_route_loss(self) -> None:
        self.assertIn("private func refuseSpeechAfterPrivateRouteLoss() -> Bool", self.synth)
        self.assertEqual(self.synth.count("guard !refuseSpeechAfterPrivateRouteLoss() else { return }"), 2)
        self.assertIn("lastInterruptionKind = .routeLost", self.synth)
        self.assertIn("guard !audioRouteManager.privateOutputLost else { return }", self.cues)
        # A conscious user override is the only way back without reconnecting.
        self.assertIn("func allowSpeakerOutputAfterLoss()", self.recognizer)
        main = _read("MainView.swift")
        self.assertIn("Speak on iPhone speaker instead", main)
        self.assertIn("route.privateOutputLost", main)

    def test_interruption_and_media_services_reset_recovery(self) -> None:
        self.assertIn("AVAudioSession.interruptionNotification", self.recognizer)
        self.assertIn("type == .began", self.recognizer)
        self.assertIn("type == .ended", self.recognizer)
        self.assertIn("AVAudioSession.mediaServicesWereResetNotification", self.recognizer)
        reset = self.recognizer[self.recognizer.index("mediaResetTask = Task"):]
        self.assertIn("self.audioEngine = AVAudioEngine()", reset)
        self.assertIn("self.tapInstalled = false", reset)
        self.assertIn("func resetAfterMediaServicesReset()", self.synth)
        self.assertIn("bargeInAudioEngine = AVAudioEngine()", self.synth)
        began = _between(self.model, "private func handleAudioSessionInterruption(", "private func handleAudioSessionInterruptionEnded")
        self.assertIn("stopSpeakingForSystemInterruption()", began)
        self.assertIn("resetAfterMediaServicesReset()", began)
        self.assertIn("cancelPushToTalk()", began)
        # The microphone is never re-opened automatically after an interruption.
        ended = _between(self.model, "private func handleAudioSessionInterruptionEnded", "func noteSceneLeftForeground()")
        self.assertNotIn("beginListening", ended)
        self.assertNotIn("startListening", ended)

    def test_session_modes_for_bluetooth_input_and_output(self) -> None:
        prepare = _between(self.recognizer, "func prepareForVoice(", "func prepareForRoomCapture")
        self.assertIn(".playAndRecord", prepare)
        self.assertIn(".allowBluetoothHFP", prepare)
        self.assertIn(".allowBluetoothA2DP", prepare)
        self.assertIn(".notifyOthersOnDeactivation", prepare)
        self.assertIn("setPreferredInput(bluetoothInput)", prepare)
        self.assertIn("setPreferredInput(builtInInput)", prepare)
        room = _between(self.recognizer, "func prepareForRoomCapture", "func releaseOneShotVoiceSession")
        self.assertIn(".allowBluetoothA2DP", room)


class MicrophoneReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recognizer = _read("SpeechRecognizer.swift")
        self.model = _read("JarvisAppModel.swift")

    def test_recognizer_stops_engine_removes_tap_and_session_deactivates(self) -> None:
        stop = _between(self.recognizer, "private func stopAudioOnly(", "private func removeInputTapIfNeeded")
        self.assertIn("audioEngine.stop()", stop)
        self.assertIn("removeInputTapIfNeeded()", stop)
        self.assertIn("request?.endAudio()", stop)
        self.assertIn("isActive = false", stop)
        self.assertIn("audioEngine.inputNode.removeTap(onBus: 0)", self.recognizer)
        release = _between(self.recognizer, "func releaseOneShotVoiceSession()", "func refresh()")
        self.assertIn("setActive(", release)
        self.assertIn("false, options: .notifyOthersOnDeactivation", release)

    def test_every_close_path_releases_the_session(self) -> None:
        helper = _between(self.model, "private func releaseMicrophone(", "private func playCue(")
        self.assertIn("audioRouteManager.releaseOneShotVoiceSession()", helper)
        self.assertIn('playCue("listening_end", prepareRoute: false)', helper)
        for fn, nxt in (
            ("func cancelPushToTalk()", "func stopListeningAndSend()"),
            ("func stopListeningAndSend()", "func configureHomeGeofence()"),
            ("private func endConversationFollowUp(", "func speakFrontendResponseIfEnabled"),
        ):
            self.assertIn("releaseMicrophone(", _between(self.model, fn, nxt), fn)
        # Idle also releases the hands-free (call-quality) Bluetooth route.
        self.assertIn("scheduleSessionRelease(afterMilliseconds: 900)", self.model)
        can_release = _between(self.model, "private var canReleaseVoiceSession", "private func scheduleSessionRelease")
        for guard in ("!isListening", "!speechRecognizer.isActive", "!speechSynthesizer.isSpeaking", "!isSending", "!handsFreeEnabled"):
            self.assertIn(guard, can_release)

    def test_single_stop_control_closes_everything(self) -> None:
        stop = _between(self.model, "func stopEverything()", "private static func isVoiceInterruption")
        self.assertIn("invalidateInFlightTurn()", stop)
        self.assertIn("cancelPushToTalk()", stop)
        self.assertIn("followUpTask?.cancel()", stop)
        main = _read("MainView.swift")
        self.assertIn("appModel.stopEverything()", main)

    def test_scene_exit_closes_capture_and_followups(self) -> None:
        app = _read("JarvisIOSApp.swift")
        self.assertIn("appModel.noteSceneLeftForeground()", app)
        self.assertIn("if phase != .active && appModel.isListening && !appModel.handsFreeEnabled", app)
        scene = _between(self.model, "func noteSceneLeftForeground()", "// MARK: - Context sent with each command")
        self.assertIn("followUpTask?.cancel()", scene)
        self.assertIn("cancelPushToTalk()", scene)


class TurnGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = _read("JarvisAppModel.swift")
        self.client = _read("JarvisAPIClient.swift")

    def test_monotonic_turn_id_invalidates_in_flight_work(self) -> None:
        invalidate = _between(self.model, "private func invalidateInFlightTurn()", "private func beginTurn()")
        self.assertIn("currentTurnID += 1", invalidate)
        self.assertIn("inFlightStreamHandle.cancel?()", invalidate)
        self.assertIn("speechSynthesizer.stopSpeaking()", invalidate)
        self.assertEqual(len(re.findall(r"currentTurnID \+= 1", self.model)), 1)
        # New turn, Action Button / push to talk, Stop all go through it.
        self.assertIn("let id = invalidateInFlightTurn()", self.model)
        activate = _between(self.model, "func activatePushToTalk() async", "private func beginListening(")
        self.assertIn("invalidateInFlightTurn()", activate)
        self.assertIn("guard !isListening && !speechRecognizer.isActive else { return }", activate)
        self.assertIn("let turnID = beginTurn()", self.model)
        # The old "drop the second command while sending" guard is gone.
        self.assertNotIn("guard !isSending else { return }", self.model)

    def test_late_results_are_dropped(self) -> None:
        route = self.model[self.model.index("private func performCommand("):self.model.index("private static func isConnectivityError")]
        self.assertIn("if !isCurrentTurn(turnID) { break }", route)
        self.assertGreaterEqual(route.count("guard isCurrentTurn(turnID) else { return }"), 4)
        # No recording / fallback request for a stale turn.
        self.assertLess(
            route.index("guard isCurrentTurn(turnID) else { return }"),
            route.index('recordTurn(role: "assistant", text: fullResponse'),
        )
        catch_start = route.index("} catch {\n            // A superseded or cancelled stream")
        self.assertLess(
            route.index("guard isCurrentTurn(turnID) else { return }", catch_start),
            route.index("try await client.command(requestText, context: requestContext)"),
        )
        # Late synthesized audio and local-handler results are dropped too.
        chunk = _between(self.model, "private func speakQwenChunk(", "private func speakOneResponse(")
        self.assertEqual(chunk.count("if let turnID, !isCurrentTurn(turnID) { return true }"), 2)
        local = _between(self.model, "private func finishLocalResponse(", "private static func calllessRecipient")
        self.assertIn("guard isCurrentTurn(turnID) else { return }", local)
        self.assertEqual(route.count("fromHandsFree: fromHandsFree, turnID: turnID, channel: effectiveChannel,"), 15)
        # The finished-turn bookkeeping cannot clobber a newer turn.
        self.assertIn("if isCurrentTurn(turnID) {\n                isSending = false", route)

    def test_stream_request_is_really_aborted(self) -> None:
        self.assertIn("final class JarvisStreamCancelHandle", self.client)
        self.assertIn("cancelHandle?.cancel = { task.cancel() }", self.client)
        self.assertIn("continuation.onTermination = { @Sendable _ in task.cancel() }", self.client)
        self.assertIn("(error as? URLError)?.code == .cancelled", self.client)

    def test_spoken_stop_commands_are_handled_locally(self) -> None:
        synth = _read("SpeechSynthesizer.swift")
        for phrase in ('"stop"', '"cancel"', '"never mind"', '"be quiet"'):
            self.assertIn(phrase, synth)
        handler = _between(self.model, "private func handleSpokenStopIfApplicable", "private func applyEarpieceState")
        self.assertIn("EarpieceVoiceCommands.isCancelCommand(text)", handler)
        self.assertIn("responseRequestsConfirmation(lastResponse)", handler)
        # A cancel said over a confirmation prompt still reaches the backend.
        after = _between(self.model, "private func scheduleAfterTurn(", "private func conversationFollowUpAllowed")
        self.assertIn('performCommand("cancel", fromHandsFree: false, channel: .voice)', after)
        self.assertIn("responseRequestsConfirmation(response)", after)


class BargeInEchoGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.synth = _read("SpeechSynthesizer.swift")
        self.recognizer = _read("SpeechRecognizer.swift")

    def test_barge_in_only_on_private_route_or_voice_processing_session(self) -> None:
        policy = _between(self.recognizer, "var bargeInPolicy: BargeInPolicy", "/// Explicit user choice")
        self.assertIn("if isPrivateOutput { return .fullConversation }", policy)
        self.assertIn("AVAudioSession.sharedInstance().mode == .voiceChat", policy)
        self.assertIn("return .disabled", policy)
        self.assertIn("guard audioRouteManager.bargeInPolicy != .disabled else { return }", self.synth)

    def test_echo_and_minimum_evidence_guards(self) -> None:
        decide = _between(self.synth, "private func shouldBargeIn(", "private func isLikelyEcho(")
        self.assertIn("isLikelyEcho(heard)", decide)
        self.assertIn("Self.minimumBargeInWords", decide)
        self.assertIn("Self.minimumTwoWordBargeInDuration", decide)
        self.assertIn("policy == .fullConversation", decide)
        self.assertIn("static let minimumBargeInWords = 3", self.synth)
        self.assertIn("static let minimumTwoWordBargeInDuration: TimeInterval = 0.35", self.synth)
        helper = _between(self.synth, "static func isLikelyEcho(heard:", "@MainActor\nfinal class SpeechSynthesizer")
        self.assertIn("overlap", helper)
        # Single stray words ("no", "what") no longer interrupt.
        self.assertNotIn('"what", "why", "how"', self.synth)

    def test_barge_in_keeps_reading_partials_while_it_settles(self) -> None:
        self.assertIn("guard let self, self.isSpeaking || self.didBargeIn, let result else { return }", self.synth)
        self.assertIn("guard !Task.isCancelled else { return }", self.synth)

    def test_barge_in_outcome_becomes_the_next_turn(self) -> None:
        model = _read("JarvisAppModel.swift")
        after = _between(model, "private func scheduleAfterTurn(", "private func conversationFollowUpAllowed")
        self.assertIn("case .utterance:", after)
        self.assertIn("BargeInBuffer.take()", after)
        self.assertIn("performCommand(carried, fromHandsFree: false", after)
        self.assertIn("!handsFreeEnabled", after)


class ConversationModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = _read("JarvisAppModel.swift")
        self.settings = _read("SettingsStore.swift")

    def test_optional_off_by_default_and_visible(self) -> None:
        self.assertIn('conversationModeEnabled = defaults.object(forKey: "jarvis.conversationModeEnabled") as? Bool ?? false', self.settings)
        self.assertIn("$settings.conversationModeEnabled", _read("SettingsView.swift"))
        main = _read("MainView.swift")
        self.assertIn("$settings.conversationModeEnabled", main)
        self.assertIn("appModel.conversationFollowUpActive", main)
        self.assertIn("microphone open for a follow-up", main)

    def test_window_is_bounded_and_foreground_only(self) -> None:
        self.assertIn("static let conversationFollowUpWindow: TimeInterval = 8", self.model)
        self.assertIn("static let conversationModeMaxTurns = 12", self.model)
        allowed = _between(self.model, "private func conversationFollowUpAllowed", "private func openConversationFollowUp")
        for guard in (
            "settings.conversationModeEnabled",
            "settings.speakResponses",
            "channel != .text",
            "!handsFreeEnabled",
            "UIApplication.shared.applicationState == .active",
            "!audioRouteManager.privateOutputLost",
            "conversationTurnCount < Self.conversationModeMaxTurns",
        ):
            self.assertIn(guard, allowed)
        monitor = _between(self.model, "private func monitorPushToTalk()", "func cancelPushToTalk()")
        self.assertIn("elapsed >= Self.conversationFollowUpWindow", monitor)
        self.assertIn('endConversationFollowUp(message: "No follow-up heard', monitor)
        self.assertIn("!settings.conversationModeEnabled", monitor)
        # The original push-to-talk bounds are untouched; short commands may send sooner.
        self.assertIn("(spoken ? 90 : 15)", monitor)
        self.assertIn("now.timeIntervalSince(updated) >= 2.3", monitor)
        self.assertIn("Self.commandSilenceWindow(for: speechRecognizer.transcript)", monitor)
        # Opening re-checks eligibility after the speaker tail delay.
        opened = _between(self.model, "private func openConversationFollowUp", "private func endConversationFollowUp")
        self.assertIn("Task.sleep(for: .milliseconds(450))", opened)
        self.assertIn("conversationFollowUpAllowed(channel: .conversation)", opened)
        self.assertIn("beginListening(conversation: true)", opened)

    def test_follow_up_uses_conversation_channel_and_drops_self_echo(self) -> None:
        send = _between(self.model, "func stopListeningAndSend()", "func configureHomeGeofence()")
        self.assertIn("wasConversationFollowUp ? .conversation : .voice", send)
        self.assertIn("EarpieceVoiceCommands.isLikelyEcho(heard: text, spoken: lastResponse)", send)

    def test_same_session_id_is_sent_with_every_command(self) -> None:
        client = _read("JarvisAPIClient.swift")
        body = _between(client, "private func commandBody(", "func command(")
        self.assertIn('"session_id": sessionID', body)
        self.assertIn('body["context"] = context', body)
        self.assertIn("conversationSessionID", self.model)


class ContextChannelAndLocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = _read("JarvisAppModel.swift")
        self.client = _read("JarvisAPIClient.swift")

    def test_channel_values_match_backend_contract(self) -> None:
        synth = _read("SpeechSynthesizer.swift")
        enum = _between(synth, "enum VoiceChannel", "/// Single user-visible state")
        for case in ("case voice", "case conversation", "case text"):
            self.assertIn(case, enum)
        self.assertIn('"channel": channel.rawValue', self.model)
        self.assertIn("func sendCommand(_ text: String, channel: VoiceChannel = .text)", self.model)
        self.assertIn("channel ?? (fromHandsFree ? .voice : .text)", self.model)
        self.assertIn("wasConversationFollowUp ? .conversation : .voice", self.model)
        stream = _between(self.client, "func streamCommandEvents(", "private func recoverFromEmptyStream")
        self.assertIn("commandBody(text, context: context)", stream)
        self.assertIn("context: context", stream)

    def test_location_only_when_authorized_and_fresh(self) -> None:
        build = _between(self.model, "static func commandContext(", "// MARK: - After a spoken turn")
        for key in ('"latitude"', '"longitude"', '"location_accuracy_m"', '"location_captured_at"'):
            self.assertIn(key, build)
        self.assertIn("ISO8601DateFormatter().string(from: fix.timestamp)", build)
        self.assertIn("age <= maximumLocationFixAge", build)
        self.assertIn("static let maximumLocationFixAge: TimeInterval = 600", self.model)
        # Only a channel is sent when there is no fix.
        self.assertLess(build.index('["channel": channel.rawValue]'), build.index('context["latitude"]'))
        fix = _between(self.model, "private func recentLocationFix()", "static func commandContext(")
        self.assertIn(".authorizedAlways, .authorizedWhenInUse", fix)
        self.assertIn("default:\n            return nil", fix)
        # No new location manager, no new request or prompt on the voice path.
        for forbidden in ("CLLocationManager()", "requestWhenInUseAuthorization", "requestLocation(", "startUpdatingLocation"):
            self.assertNotIn(forbidden, self.model[self.model.index("// MARK: - Earpiece turn control"):self.model.index("func speakFrontendResponseIfEnabled")])
        sensors = _read("FrontendIntelligence.swift")
        provider = _between(sensors, "appModel.recentLocationProvider = {", "// The Action Button intent posts")
        self.assertIn("settings.localSensorContextEnabled", provider)
        self.assertIn("recentAuthorizedFix(maxAge: 600)", provider)
        fix_source = _between(sensors, "func recentAuthorizedFix(", "private func start()")
        self.assertIn("isLocationAuthorized", fix_source)
        self.assertNotIn("requestWhenInUseAuthorization", fix_source)


class TextFallbackTests(unittest.TestCase):
    def test_denied_or_restricted_permissions_fall_back_to_typing(self) -> None:
        recognizer = _read("SpeechRecognizer.swift")
        self.assertIn("case .restricted:", recognizer)
        self.assertIn("case .denied:", recognizer)
        self.assertIn("static func isPermissionError(_ error: Error) -> Bool", recognizer)
        model = _read("JarvisAppModel.swift")
        failure = _between(model, "private func handleVoiceStartFailure", "/// A single Action Button press")
        self.assertIn("SpeechRecognizer.isPermissionError(error)", failure)
        self.assertIn("textFallbackReason", failure)
        self.assertIn("Voice unavailable", failure)
        self.assertIn("textFallbackReason = nil", model)
        main = _read("MainView.swift")
        self.assertIn("appModel.textFallbackReason", main)
        self.assertIn("UIApplication.openSettingsURLString", main)
        # The text field remains the first control of the card.
        card = _between(main, "private var commandCard", "private var personalNotecardCard")
        self.assertLess(card.index("TextField("), card.index("EarpieceStatusView"))


class CueVocabularyAndEntryPointTests(unittest.TestCase):
    def test_small_cue_vocabulary(self) -> None:
        cues = _read("AmbientCuePlayer.swift")
        for cue in ('case "listening_start":', 'case "listening_end":', 'case "error":', 'case "warning":', 'case "response_complete":'):
            self.assertIn(cue, cues)
        self.assertIn("prepareRoute: Bool = true", cues)
        model = _read("JarvisAppModel.swift")
        self.assertIn('playCue("listening_start", prepareRoute: false)', model)
        self.assertIn('playCue("error")', model)
        self.assertIn("guard settings.ambientCuesEnabled else { return }", model)

    def test_action_button_is_one_action_and_posts_immediately(self) -> None:
        shortcuts = _read("JarvisShortcuts.swift")
        self.assertIn('FrontendActionMailbox.post("talk")', shortcuts)
        self.assertIn("static let horusShortcutActionPosted", shortcuts)
        frontend = _read("FrontendIntelligence.swift")
        self.assertIn("NotificationCenter.default.post(name: .horusShortcutActionPosted, object: nil)", frontend)
        self.assertIn("NotificationCenter.default.notifications(named: .horusShortcutActionPosted)", frontend)

    def test_state_is_derived_from_real_state(self) -> None:
        model = _read("JarvisAppModel.swift")
        self.assertIn("Publishers.CombineLatest3($isListening, $isSending, speechSynthesizer.$isSpeaking)", model)
        synth = _read("SpeechSynthesizer.swift")
        for state in ("case idle", "case listening", "case thinking", "case speaking"):
            self.assertIn(state, synth)


class NoNewBackgroundCaptureTests(unittest.TestCase):
    def test_background_modes_unchanged_and_no_new_capture_entry(self) -> None:
        with (_IOS / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        # Baseline set before the earpiece work. "audio" pre-exists for spoken output and
        # cue playback; it is not used to keep the microphone open, and nothing was added.
        self.assertEqual(
            sorted(info["UIBackgroundModes"]),
            ["audio", "bluetooth-peripheral", "external-accessory", "location"],
        )
        self.assertNotIn("voip", info["UIBackgroundModes"])
        self.assertIn("NSMicrophoneUsageDescription", info)
        self.assertIn("NSSpeechRecognitionUsageDescription", info)

    def test_conversation_mode_never_listens_without_foreground_check(self) -> None:
        model = _read("JarvisAppModel.swift")
        # The only automatic listening entry is guarded by conversationFollowUpAllowed.
        for match in re.finditer(r"beginListening\(conversation: true\)", model):
            window = model[max(0, match.start() - 400):match.start()]
            self.assertIn("conversationFollowUpAllowed(channel: .conversation)", window)
        self.assertEqual(len(re.findall(r"beginListening\(conversation: true\)", model)), 1)

    def test_cues_and_intent_do_not_open_the_microphone(self) -> None:
        self.assertNotIn("startListening", _read("AmbientCuePlayer.swift"))
        self.assertNotIn("startListening", _read("JarvisShortcuts.swift"))


if __name__ == "__main__":
    unittest.main()
