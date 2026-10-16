# AirPods + public freshness gate: physical acceptance

Status: **not yet verified on the user's iPhone/AirPods.** The PR adds integration
code and automated tests; source-level checks do not establish working hardware.

## AirPods (test on a real iPhone)

Prerequisites: AirPods paired in iOS, microphone + Speech Recognition access granted,
Horus/Jarvis backend reachable, foreground app open.

1. In iOS Settings → Voice & Privacy, enable **Use Bluetooth hands-free microphone**
   and choose **AirPods**. Ensure the active route label names the AirPods rather
   than a Ray-Ban headset.
2. Say the wake phrase and a read-only command. Confirm the recognized transcript
   came from AirPods and response audio reached the selected AirPods.
3. While audio is playing, interrupt with a new request. Confirm playback stops
   promptly and the interruption is recognized.
4. With both AirPods and Ray-Bans connected, choose **AirPods**; restart listening
   and prove the active input is AirPods. Then choose **Ray-Ban Meta**, restart
   listening and prove the active input changed.
5. Disconnect the selected headset. On the next turn the system must select the
   built-in iPhone microphone, never the other connected headset by surprise.
   Confirm the warning/route label is truthful.
6. Switch **Use Bluetooth hands-free microphone** off. On the next turn, prove
   the iPhone microphone is used. Room/meeting mode also requires the phone mic.
7. Deny mic permission or temporarily disconnect Bluetooth. App must surface an
   error/degraded route, not claim AirPods microphone capture succeeded.
8. Test interruptions from an incoming call and an audio route change. The
   app must not crash or leave its microphone tap in a corrupted state.
9. Background/suspended tests are distinct. Do **not** claim that iOS will permit
   perpetual listening through AirPods when this app is suspended.
10. For renamed AirPods without the word "AirPods" in their system port name,
    choose Automatic with the Ray-Bans disconnected; the exact AirPods preference
    cannot infer a stable manufacturer identity from a custom port name.

AirPods gestures/Siri invocation are **not** integrated by this change. The
feature is headset audio I/O for the existing app, not control of Apple's private
earbud firmware or background execution privileges.

## Freshness routing (server tests)

- Verify a current public model announcement is sent to the actual configured
  web.search provider before either conversational model path is used.
- Remove the Serper key and repeat. An unavailable provider must be stated as
  unavailable; the model must not invent a negative answer from its prior.
- Challenge a previous denial: “How do you know they didn't post it?”
  Verify source search only if an unambiguous, nonprivate public referent exists
  in recent user history; otherwise ask for an account/link.
- Verify questions about private emails/files/calendar are **never** sent to
  public web search merely because they contain a date or product name.
- Inspect search receipt and answer grounding independently. The present PR
  enforces a bounded class of freshness **routes**; complete evidence-level
  entailment, per-claim TTL, and a universal post-generation linter remain future
  work. Search snippets alone are not proof of an announcement.

## Release gate

Do not mark AirPods or freshness routing **verified in production** until:
- Python regression CI passes;
- iOS simulator compilation passes;
- the hardware tests above pass with input/output route evidence;
- actual live-search and no-credentials paths pass.

If any test is not performed, describe that portion as implemented but unverified.
