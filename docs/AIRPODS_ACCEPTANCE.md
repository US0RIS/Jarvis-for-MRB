# AirPods and iPhone acceptance checklist

**Purpose:** a step-by-step test script for a real iPhone and ordinary AirPods (or other Bluetooth headphones). It asks for what you see and hear, not how Horus is built.

**Status:** not run. Every row in the results table at the end is blank. Do not mark a row as passed unless you did the step on the device and saw the result. Write down the date, iPhone model, iOS version, AirPods model and the Horus build (the commit on the PR) at the top of your results.

**Before you start:** read [Earpiece](EARPIECE.md) once so you know what Horus is supposed to do. The checks below are written from a user's point of view.

---

## 0. Setup and evidence to keep

Keep these with your results: a screen recording of each test if you can, the screen text shown in Horus at the time, and the ledger output described in the diagnostics notes.

**Diagnostics you can collect without a computer:**
- Screenshot of the Horus screen, including the status line under the big button.
- Screenshot of Settings → Callless and the AI Provider section if something is wrong with the connection.

**Diagnostics that need a computer:** request the server's `/proactive/ledger` endpoint with the same `Authorization: Bearer <token>` header the app uses (for example with `curl`). It is JSON, not a web page. It shows, for each alert or briefing, whether Horus spoke it live (`live_state`) and what Apple's push service said (`push_state`). Possible push states are `queued`, `accepted_by_apns`, `rejected_by_apns`, `delivery_unknown`, `not_configured` and `failed`. **`accepted_by_apns` is not proof that the phone got the alert.** Only the state `device_acknowledged` would mean that, and no code path sets it yet.

---

## 1. Initial setup

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 1.1 | Install the Horus build on the iPhone. Open the app. | App opens to the main screen with a Push to Talk control. | Opens with no crash. | Crash, or blank screen. | Screenshot. |
| 1.2 | Settings → **Jarvis Server**: enter the home/LAN URL (and Tailscale URL if you use it). | Fields save. | Values stay after you leave and return to Settings. | Values reset. | Screenshot. |
| 1.3 | Check the connection (the app's status line or the first request). | Horus answers a simple question such as "What time is it?" | You hear or read a correct local time. | No answer, or a timeout. | Screenshot and the exact text. |
| 1.4 | Ask "Horus, what can you do?" | A short, spoken answer with no invented features. | No claim of camera vision or background listening. | Claims a camera, always-on listening or a feature you can't see. | Transcript. |
| 1.5 | Settings → **Callless**: leave the hub URL empty, then open **Open Callless**. | Opens the browser Callless page (or says the URL is not set). | Honest behavior either way. | Crash. | Screenshot. |

---

## 2. Action Button, audio routing and private audio

Put AirPods in your ears and connect them to the iPhone first.

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 2.1 | Assign the **Talk to Horus** shortcut to the Action Button (Settings → Action Button). Press the Action Button once. | Horus starts listening within about one second. A short "listening" cue plays in the AirPods or on the phone. Status shows **Listening**. | You see Listening, and the cue is audible. | Nothing happens, or it needs two presses. | Screen recording of the press; timestamp. |
| 2.2 | Say "What's on my calendar today?" then stop talking. | Status shows **Thinking**, then **Speaking**. The answer is spoken into the AirPods, not the phone speaker. | The answer is heard in the AirPods; the phone does not speak aloud. | Answer comes out of the iPhone speaker, or never comes. | Note where you heard it. Time from the moment you stopped talking to the first word. |
| 2.3 | When the answer ends, do nothing for ten seconds. | Status returns to **Idle**. The microphone indicator in the status bar goes away. | The orange microphone dot is off in Idle. | Dot stays on in Idle. | Screenshot showing the status bar. |
| 2.4 | Choose the iPhone microphone instead of the AirPods mic (if your build exposes that setting). Repeat 2.2. | The reply still comes out of the AirPods. | Reply is in the AirPods. | Reply comes out of the phone speaker. | Note the setting used. |
| 2.5 | Deny microphone permission (Settings → Privacy → Microphone → Horus, off). Press the Action Button. | Horus says or shows that microphone access is off and offers typing. | Typed input still works; a reason is shown. | Crash, silent failure, or it keeps trying. | Screenshot of the message. |
| 2.6 | Turn speech recognition off for Horus (Settings → Privacy → Speech Recognition). Press the button. | Same as 2.5, with a message about speech recognition. | Message names the setting and typing works. | Crash or silent failure. | Screenshot. |
| 2.7 | Restore permissions. Press the button, say nothing, wait. | Horus returns to Idle after the silence window. | Idle appears without you pressing anything. | Listening continues indefinitely. | Time it. |

---

## 3. Conversation: interruption, follow-ups, cancellation

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 3.1 | Ask a question with a long answer, e.g. "Give me my briefing." While Horus is speaking, say "Stop." | Speech stops within about half a second. Status returns to Idle or Listening. | Speech stops; no further words are spoken from that answer. | Speech continues for several seconds, or Horus answers its own words. | Time to silence (estimate from the recording). |
| 3.2 | Ask "What's on my calendar tomorrow?" Then say "Just the afternoon." | Horus answers with only afternoon events. It does not re-read the whole day. | Afternoon events only. | Full list again, or an unrelated answer. | Transcript. |
| 3.3 | Follow 3.2 with "The first one." | Horus gives details of the first afternoon event. | Correct event. | Wrong event or nothing. | Transcript. |
| 3.4 | Say "Never mind" during a reply. | Speech stops. Horus does not send "never mind" as a new request. | Nothing new is said. | A new answer starts. | Transcript. |
| 3.5 | Say "Remind me to" and stop, mid-sentence. | Horus asks you to finish the sentence. | It asks you to finish. | It guesses a reminder. | Transcript. |
| 3.6 | Turn on **Conversation mode (foreground follow-ups)** in Settings. Ask a question. After the answer, speak a follow-up within 8 seconds. | Status shows "Conversation mode: microphone open for a follow-up". Your follow-up is answered. | Follow-up works; the countdown is visible. | No follow-up window, or the mic stays open after the countdown. | Screen recording. |
| 3.7 | With Conversation mode on, ask a question, then stay silent for the whole countdown. | Mic closes; status returns to Idle. | Idle after about 8 seconds. | Mic stays open. | Time it. |
| 3.8 | With Conversation mode on, ask a question, then switch to another app before the answer finishes. | Horus stops listening and does not reopen the mic in the background. | No listening while the app is in the background. | Mic indicator on in the other app. | Screenshot of the status bar. |
| 3.9 | Ask a question, and while Horus is thinking (before any speech), press **Stop**. | Thinking ends. Nothing is spoken afterwards. Notice says the request may already have reached the server. | Silence after Stop. | A late answer is spoken. | Screenshot of the notice. |

---

## 4. Memory: store, correct, recall, restart

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 4.1 | Say "Remember I put my passport in the top drawer of my desk." | "Got it." | Confirmation spoken or shown. | No confirmation, or a request to add a camera. | Transcript. |
| 4.2 | Say "Where's my passport?" | "You last told me your passport was in the top drawer of your desk…" It says it was a report from you. | Correct place; says it was reported. | Says it "sees" or "saw" the passport. | Transcript. |
| 4.3 | Say "I moved my passport into my suitcase." | "Got it… not the top drawer … anymore." | Confirmation mentions the move. | Still gives the drawer. | Transcript. |
| 4.4 | Say "Where's my passport?" again. | Suitcase only. | Suitcase is the answer. | Drawer, or both. | Transcript. |
| 4.5 | Say "Where was it before?" | The drawer, with the time it was reported. | Earlier place returned. | Nothing or the current place. | Transcript. |
| 4.6 | Ask "Where are my sunglasses?" (never stored). | An honest unknown: "I don't have any record…". | No invented location. | Any location. | Transcript. |
| 4.7 | Force-close Horus, reopen it, and ask "Where's my passport?" | Still "suitcase". | Answer survives the restart. | Forgotten. | Transcript. |
| 4.8 | Say "Forget where I put my passport." | Confirmation. Asking again gives the unknown answer. | Record gone. | Still remembered. | Transcript. |

---

## 5. Situational awareness with public data

Use a place you can verify. Test each question once.

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 5.1 | Turn on location for Horus (Settings → Privacy → Location Services → Horus, While Using). Say "Anything interesting happening around me?" | Short spoken answer that names the place as "around you". | Answer uses your current position. | Answers for another city, or no place. | Transcript. |
| 5.2 | Say "Tell me more." | Lists sources, when each was checked, and "Location came from your iPhone". | Each source is named with its freshness. | No sources, or a source not in the answer. | Transcript. |
| 5.3 | Turn location off for Horus. Ask 5.1 again. | Horus says it doesn't know where you are and asks you to allow location or name a saved place. | No answer guessed for a place. | Any answer about "around you". | Transcript. |
| 5.4 | Save your home: stand at home, say "Save this place as home." Then ask "Is anything unusual happening near home?" | "near home" in the answer. | Named place used. | Uses your current position instead. | Transcript. |
| 5.5 | Ask "What's happening in the airspace around here?" | Aircraft count, labelled as OpenSky coverage-limited, with no flight numbers. | No flight identities. | Flight numbers or identities. | Transcript. |
| 5.6 | Ask a question while the backend cannot reach public data (e.g. turn off the server). | "I couldn't reach any of my sources… That's not an all-clear." | Honest outage message. | "All clear" or "nothing happening". | Transcript. |

---

## 6. Proactive alerts: watch, notification, cancel, quiet and snooze

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 6.1 | Say "Watch for new severe weather alerts near home for the next three hours." | Horus confirms the official source, end time and how to cancel. It also says if its background checker is not running. | Confirmation matches reality. | Says it is monitoring when the checker is off. | Transcript. |
| 6.2 | Say "What are you watching?" | The watch is listed with its end time. | Listed. | Missing. | Transcript. |
| 6.3 | When a real alert occurs (only if one is actually issued for your area), check the app and your phone. | Horus speaks the alert if the app is open. If the app is closed, a notification appears on the lock screen (if the server has push configured). | Alert appears and shows its source. | Alert without a source, or an alert for an old event. | Screenshot of the notification; `/proactive/ledger` entry. |
| 6.4 | In the ledger, look at the push state for 6.3. | `accepted_by_apns` (Apple accepted) or `not_configured`. **Do not** count `accepted_by_apns` as "I received it." | You state only what you saw on the phone. | You report receipt based on the ledger alone. | Ledger snippet. |
| 6.5 | Tell the phone "Why did you tell me that?" | The rule, score and source for that alert. | Explanation matches the alert. | Unrelated answer. | Transcript. |
| 6.6 | Say "Cancel the weather watch." Then wait through a new check period. | Confirmation. No further alerts. | No new alerts. | An alert after cancellation. | Note times. |
| 6.7 | Say "Snooze briefings for an hour." Then "Set quiet hours from 10 pm to 7 am." | Confirmations. Briefings do not speak during the snooze or quiet hours. | Silence in those windows. | Speech during quiet hours. | Time log. |
| 6.8 | Say "Turn briefings back on." | Confirmation; briefings resume. | Resumed. | Still snoozed. | Transcript. |

---

## 7. Callless: two real people, two real devices

Both people need a Horus account and the Callless page. Use two phones, on different networks if possible (for example one on Wi-Fi and one on cellular). Browsers need a tap to allow the microphone.

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 7.1 | Both people register and add each other as contacts. Person A sets Person B's grant to **Open**. Person B does not change anything. | Contacts list shows the grants you set. | Each sees their own grant. | Grants swapped or missing. | Screenshot of each contacts list. |
| 7.2 | Both people press **Arm direct connections for this tab** and allow the microphone when asked. | Status shows armed. | Both armed. | Mic permission never requested. | Screenshot. |
| 7.3 | Person A asks to connect to Person B (Open grant). With an Ask grant instead, Person B must tap **Join conversation**. | Person B hears a connection tone and sees the conversation start. Both sides show connecting, then **connected** only after both can hear. | Both sides hear each other. | "Connected" while one side hears nothing. | Time from request to both hearing audio (use a stopwatch and a recording). |
| 7.4 | Speak from both phones. | Each person hears the other clearly. | Two-way audio works. | One-way audio. | Note what you hear. |
| 7.5 | Person A presses **Mute**, then **Unmute**. Person B should see the muted state both times. | Person B sees Person A is muted; Person A's voice stops. | Mute consistent on both sides. | Mute state disagrees. | Screenshot. |
| 7.6 | Person A presses **Disconnect**. | Both sides hear a distinct end tone and see "Conversation ended". | Both see the ending. | One side keeps connected. | Screenshot both sides. |
| 7.7 | Person B changes A's grant to **Closed**, then A tries to connect. | A is refused with "Contact is not currently reachable." | Refusal with no reason given. | Connection succeeds. | Screenshot. |
| 7.8 | Start a conversation (grant Open). Then Person B revokes access during the call. | The call ends for both people with a visible reason. | Call ends. | Call continues. | Screenshot both sides. |
| 7.9 | Start a call, then turn Person A's Wi-Fi off for 15 seconds, then back on. | One automatic reconnection attempt. If it fails, the call ends on both sides with "network". | Honest ending. | Stuck "connecting" forever. | Note the time. |
| 7.10 | Person A opens the sessions list of another user (if you can get their session ID). | Not found. | "Session not found." | The session details show. | Screenshot. |

---

## 8. Failure conditions

| # | Action | Expected result | Pass when | Fail when | Collect |
|---|---|---|---|---|---|
| 8.1 | No network on the phone (airplane mode, Wi-Fi off). Ask a question. | Honest error: it could not reach Horus. No invented answer. | Error stated. | Made-up answer. | Screenshot. |
| 8.2 | Remove the AirPods (put them in the case) while Horus is speaking. | Speech stops at once. Status says headphones disconnected. Speech does not continue from the phone speaker. | Silence from the phone speaker. | Speech continues from the phone. | Recording (listen for sound from the phone). |
| 8.3 | Put the AirPods back in and wait. | Notice says headphones reconnected. Horus speaks again on the next reply. | Reconnect notice and speech return. | Speech never returns without a restart. | Screenshot. |
| 8.4 | Turn off the Horus server, then ask a question. | Honest "can't reach Horus" message. | Clear message. | Silent failure. | Screenshot. |
| 8.5 | Background the app while Horus is speaking (press Home). | Speech stops or continues only as iOS allows; the microphone is never opened in the background. | Microphone indicator off in background. | Indicator on in background. | Screenshot. |
| 8.6 | Interrupt with a phone call during a reply. | Speech stops; after the call Horus does not reopen the mic on its own. | No automatic listening after the call. | Automatic listening. | Note what happened. |
| 8.7 | Restart the iPhone. Open Horus. Ask a question. | Works after the normal launch. | Works. | Fails until reinstall. | Note the time. |

---

## Results

| Section | Test | Date | Device / iOS / AirPods / build | Result (pass / fail / not run) | Notes or evidence link |
|---|---|---|---|---|---|
| 1 | 1.1–1.5 | | | not run | |
| 2 | 2.1–2.7 | | | not run | |
| 3 | 3.1–3.9 | | | not run | |
| 4 | 4.1–4.8 | | | not run | |
| 5 | 5.1–5.6 | | | not run | |
| 6 | 6.1–6.8 | | | not run | |
| 7 | 7.1–7.10 | | | not run | |
| 8 | 8.1–8.7 | | | not run | |
