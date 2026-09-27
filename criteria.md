# criteria.md — Jarvis Reality Release Constitution

> **RELEASE STATUS: NOT COMPLETE**
>
> This file is the single authoritative definition of done for the Jarvis "revolutionary upgrade" / reality-and-agency convergence release.
>
> **The release is not done because code exists, a branch merged, a test double passed, a route returned 200, an LLM produced a plan, or a developer can demonstrate a subsystem from a terminal. It is done only when every required gate in this file passes on the actual deployed system, at one exact release-candidate Git SHA, using the real devices/services/providers specified here, and the promised behavior is observable through ordinary Jarvis use.**

Adopted in repository `US0RIS/Jarvis-for-MRB` on branch `jarvis/cloud-cognition-groq`, from baseline `be4017efa9b33bfdceebd7ebb74c112a7b365bb4`. The criteria commit itself necessarily changes the branch SHA. All release evidence must bind to the later frozen release-candidate SHA, not to this adoption baseline.

---

## 0. Authority and precedence

This file is the constitution for this release.

If another README, design document, PR description, comment, test name, UI label, or prior assistant statement conflicts with this file about whether the release is complete, **this file wins**.

Other documents may explain implementation details. They may make a gate stricter. They may not weaken, waive, reinterpret, or silently satisfy a gate in this file.

A claim that a feature is "implemented," "source-complete," "candidate-complete," "working in CI," "wired," "integrated," "supported," or "done" does **not** mean the corresponding release gate has passed.

### Fixed finish line

This release is intentionally fixed.

- `future.md` is an idea backlog, not release scope.
- New ideas discovered during this release do not become new release gates unless they repair or complete an already-promised capability.
- Conversely, an existing promised/shipped capability cannot be removed, relabeled, or narrowed merely to make the release pass unless the user explicitly chooses to remove it from the product.
- No new "revolutionary" feature work should begin merely to avoid finishing these gates.
- A defect discovered while running a gate is a defect in this release, not a reason to redefine the gate.

---

## 1. The rule that replaces "implemented"

For this release, a user-facing capability has exactly these maturity states:

1. **DESIGNED** — a document or architecture exists.
2. **SOURCE PRESENT** — executable implementation exists in the repository.
3. **SYNTHETIC PASS** — automated tests pass with mocks/fixtures/simulators.
4. **DEPLOYED** — the exact release-candidate build is installed/running on the real target devices.
5. **REAL PASS** — the capability has been invoked through the normal Jarvis path against real hardware/services/data and produced the expected observable result.
6. **RELEASED** — every required gate in this file has REAL PASS evidence at the same candidate SHA/environment.

Only state 5 counts as "the feature works" for purposes of this release. Only state 6 counts as "the revolutionary upgrade is done."

A feature may never be promoted from SOURCE PRESENT or SYNTHETIC PASS to REAL PASS by inference.

---

## 2. What "observable in the real world" means

A REAL gate passes only when a person using Jarvis normally can observe the promised effect or state without pretending that an internal software event is the outside world.

Examples:

- A Calendar write is real only after Google is independently read back and the expected event/change is present.
- A Mac/Windows app launch is real only after the target machine actually reports the expected process state; command acceptance alone is insufficient.
- A HomeKit light action is real only after the physical accessory changes and fresh accessory state is read back. The acceptance record must also include human confirmation that the actual light visibly changed.
- A public-camera observation is real only when a currently reachable, authorized public source returns actual media and Jarvis interprets that media with source/time/provenance attached.
- An APNs path is real only when the physical iPhone receives the notification while Jarvis is not merely foregrounded waiting for it.
- A persistent goal is real only when it survives an actual process/service restart and resumes without the user restating it.
- Proactivity is real only when Jarvis initiates the appropriate interruption without the user asking it to check.
- Cross-device continuity is real only when state or capability survives an actual device handoff/reconnect.
- Cloud cognition is real only when an actual Groq request occurs from the intended credential path and the fallback path is also exercised.
- "Verified" is forbidden when the evidence proves only dispatch, API acceptance, model output, or local intent.

Where the outside world cannot be independently observed, Jarvis must report `unverified`, `unknown`, `unavailable`, or an equally explicit uncertainty state. Honest uncertainty is a pass condition when uncertainty is the correct result. False certainty is always a failure.

---

## 3. Universal rules for every REAL gate

Unless a gate explicitly says otherwise, all of these rules apply.

### 3.1 Exact release candidate

Every REAL receipt must identify:

- full Git SHA;
- branch/ref used for the build;
- backend installation/environment fingerprint;
- iOS build identity where applicable;
- participating device IDs/labels;
- test start/end time;
- relevant provider/account class without storing secrets.

A source change after a REAL pass invalidates that pass unless the gate is rerun on the new SHA. No cherry-pick, manual patch, local uncommitted edit, or post-test hotfix may be hidden from the receipt.

### 3.2 Normal user path

A capability must be triggered the way the finished Jarvis product claims the user can trigger it.

For a user-facing behavior, the following **do not** satisfy a REAL gate:

- calling an internal Python function by hand;
- manually POSTing the target endpoint;
- editing SQLite directly;
- inserting a fake event row;
- running a hidden developer-only action in place of the user-facing interaction;
- manually performing an intermediate task Jarvis was supposed to perform;
- reading a log and claiming that the user-visible feature therefore worked.

CLI/diagnostic tools may set up the environment before a test and may inspect evidence after the user-facing behavior. They may not substitute for the behavior under test.

### 3.3 Real dependencies

REAL means real:

- real Windows backend;
- physical iPhone for iPhone behavior;
- a real paired Mac/Windows host for Mesh/Conductor behavior;
- real Google Calendar/Gmail where those services are required;
- real Groq for cloud-cognition acceptance;
- real public providers for World Armor/Reality Graph acceptance;
- real HomeKit accessory for Presence acceptance;
- real APNs delivery for closed-app notification acceptance.

Mocks, simulator-only runs, fixture providers, fake clocks, and synthetic SQLite rows remain valuable preflight but never satisfy a REAL gate.

### 3.4 No hidden choreography

After the user begins a scenario, human participation is limited to:

- approvals or denials Jarvis legitimately requests;
- genuine value judgments that cannot be inferred safely;
- performing an explicitly defined environmental change used to test replanning/failure;
- observing and recording a physical outcome.

The human may not tell Jarvis which internal tool to call next, manually transfer intermediate data, repair its plan, invoke the next backend endpoint, or otherwise act as Jarvis's orchestration layer.

### 3.5 Evidence before narrative

A gate is PASS only when its evidence exists. A prose explanation that the implementation "should" work does not count.

Required evidence should be machine-generated where possible and must include enough information to falsify the claim. Screenshots/video may supplement receipts but do not replace structured logs/readback.

### 3.6 Failure is a first-class test

Each capability family must be tested at least once under a meaningful failure/unavailable/revoked condition. Jarvis must fail closed, preserve truth, and avoid duplicate or unsafe retries.

### 3.7 Law, authorization, provider rights, and physical limits remain binding

This release does not require bypassing authentication, access controls, provider terms, private networks, device security, or applicable law.

If a source/action is not authorized or technically accessible, Jarvis must say so accurately. It may not fabricate access in order to pass a gate.

At the same time, an avoidable implementation limitation cannot be mislabeled "safety" or "law" merely to escape a promised capability.

---

## 4. Release evidence record

Each gate must have one acceptance record containing at least:

```text
gate_id:
result: PASS | FAIL | BLOCKED
candidate_sha:
environment_fingerprint:
started_at:
finished_at:
user_entry_surface:
literal_user_request:
devices:
real_services_or_providers:
preconditions:
expected_observable_result:
actual_observable_result:
external_readback_or_independent_evidence:
permission_or_grant_evidence:
failure_case_exercised:
artifacts:
notes:
```

`BLOCKED` is not PASS. A blocked external dependency keeps the release incomplete.

Every record must be retained long enough to audit the final release decision. Existing Agency/World Armor receipts may be reused only if they satisfy this file and match the exact final candidate SHA/environment.

---

## 5. Master gate ledger

All gates begin as **UNPROVEN**. Source code or old demonstrations do not pre-mark them passed.

| Gate | Capability | Required level | Initial status |
|---|---|---|---|
| C00 | Candidate integrity and deployment identity | SYNTHETIC + REAL | UNPROVEN |
| C01 | Feature inventory / truth audit | REAL audit | UNPROVEN |
| C02 | Ordinary Jarvis interaction path | REAL | UNPROVEN |
| C03 | Persistent world model and identity continuity | REAL | UNPROVEN |
| C04 | Persistent intentions across restart | REAL | UNPROVEN |
| C05 | Executive loop / closed-loop convergence | REAL | UNPROVEN |
| C06 | Authority, approval, denial, and resumption | REAL | UNPROVEN |
| C07 | Independent outcome verification and failure recovery | REAL | UNPROVEN |
| C08 | Replanning and dormant-goal wakeup | REAL | UNPROVEN |
| C09 | Proactivity and exception-based attention | REAL | UNPROVEN |
| C10 | Cross-source situational awareness | REAL | UNPROVEN |
| C11 | Deliberation, counterfactuals, and capability-gap honesty | SYNTHETIC + REAL | UNPROVEN |
| C12 | Cognitive routing: deterministic, local, Groq, fallback | REAL | UNPROVEN |
| C13 | Conductor: verified workstation action | REAL | UNPROVEN |
| C14 | Reality Mesh: actual cross-device presence/continuity | REAL | UNPROVEN |
| C15 | Reality Graph: live, provenance-bearing world state | REAL | UNPROVEN |
| C16 | World Armor: general lawful public-camera path | REAL | UNPROVEN |
| C17 | World Armor: shipped environmental/movement providers | REAL | UNPROVEN |
| C18 | Closed-app delivery and runtime resilience | REAL | UNPROVEN |
| C19 | Presence: real bounded physical actuation | REAL | UNPROVEN |
| C20 | Privacy, secrets, revocation, and fail-closed boundaries | SYNTHETIC + REAL | UNPROVEN |
| C21 | Long-run reliability / recovery soak | REAL | UNPROVEN |
| C22 | Unscripted revolutionary capstone | REAL | UNPROVEN |
| C01-S01 … C01-S16 | Shipped-capability scenarios (§7A) | REAL | UNPROVEN |

**Release condition: every row must be PASS.**

---

# 6. Gate definitions

## C00 — Candidate integrity and deployment identity

Purpose: prove that all later observations belong to one coherent release candidate rather than a mixture of branches, old installs, and local patches.

### Test

1. Freeze one release-candidate Git SHA.
2. Working tree must be clean.
3. Run the complete Python regression suite at that SHA.
4. Run all Agency acceptance preflight/synthetic tests.
5. Run World/World Armor diagnostics applicable to the enabled feature set.
6. Build the iOS app from the same SHA.
7. Install that build on the physical iPhone.
8. Install/start the backend from that SHA on the primary Windows host.
9. Confirm backend health reports the expected code/build identity.
10. Confirm schema/migrations/required local stores are current.
11. Confirm each real paired node used later identifies itself and is reachable.

### PASS

- all relevant automated tests are green;
- iOS builds/signs/launches on the physical phone;
- Windows backend is running the frozen SHA;
- all later REAL receipts can be tied to this exact candidate;
- there is no uncommitted code used to make any demonstration work.

A new code commit after this gate requires C00 again and invalidates later same-SHA claims until rerun.

---

## C01 — Feature inventory / truth audit

Purpose: prevent another release where README/UI language promises more than the deployed product actually does.

### Test

On the frozen SHA, enumerate every capability that is any of:

- described in README/docs as implemented, working, shipping, supported, source-complete, candidate-complete, or current;
- exposed as an enabled user-facing control in the iPhone/iPad UI;
- exposed as a user-facing voice/text capability;
- exposed by a production endpoint intended for the app;
- relied upon by another in-scope feature.

For each capability, map it to exactly one of:

1. a REAL gate in this file; or
2. clearly labeled future/experimental/developer-only functionality that is not presented to the user as a finished capability.

### PASS

- no shipped/claimed user capability is orphaned from acceptance;
- no current UI advertises a capability that only exists on another branch or in a design doc;
- no README sentence turns SOURCE PRESENT into a deployed/verified claim;
- `future.md` ideas remain explicitly outside this release unless promoted;
- every capability promoted into the release has a concrete REAL test.

If a claimed capability is discovered without a test, C01 fails and the release remains incomplete until this file is amended and the new test passes.

The amendment in §7A adds scenario gates C01-S01 … C01-S16. C01 is PASS only when all of them are PASS on the frozen candidate.

---

## C02 — Ordinary Jarvis interaction path

Purpose: prove Jarvis works as Jarvis, not only as a collection of backend routes.

### Test

Using the physical iPhone/iPad Jarvis app and/or the supported voice path:

1. Ask a routine deterministic request that should not need a model.
2. Ask an ordinary conversational request that should use the local model.
3. Ask for a currently enabled real capability using natural language rather than its internal function name.
4. Ask, "What can you do right now?" or equivalent.

### PASS

- requests enter through the normal UI/voice interface;
- literal names, negations, time windows, and targets survive routing;
- the capability inventory answer reflects **actually enabled/reachable** capabilities, not everything mentioned in documentation;
- unavailable dependencies are called unavailable;
- no terminal/API/manual backend invocation is necessary to complete the user interaction.

---

## C03 — Persistent world model and identity continuity

Purpose: prove Jarvis maintains a durable model of the user's world rather than reconstructing everything from prompt context.

### Test

Create/use a real entity represented in at least three supported sources, such as Calendar, Gmail, a project/document/commitment, or explicitly enrolled phone/world state.

1. Resolve the observations into one stable entity where evidence supports that identity.
2. Store a durable fact/objective/relationship with provenance.
3. Introduce one conflicting or newer observation.
4. Restart the backend.
5. Query the entity again through ordinary Jarvis interaction.
6. Correct one fact explicitly as the user.

### PASS

- the same entity persists across restart;
- source provenance and observed time survive;
- conflicting evidence remains represented rather than silently overwritten;
- the user correction is durable and distinguishable from inference;
- strong conflicting identities are not incorrectly collapsed;
- Jarvis does not invent missing evidence.

---

## C04 — Persistent intentions across restart

Purpose: prove a goal remains Jarvis's responsibility after the conversation ends.

### Test

1. Through ordinary language, create one bounded goal with an observable success condition and at least one pending next step.
2. Allow Jarvis to perform or verify at least one piece of work on it.
3. Ensure at least one remaining step is pending, scheduled, blocked, or awaiting approval.
4. Restart the actual Jarvis backend/service.
5. Reopen/reconnect the physical iPhone without restating the objective.
6. Wait for or request the normal status surface.

### PASS

Jarvis restores:

- the exact goal;
- completed work/evidence;
- current plan;
- pending approvals;
- blocking conditions;
- next evaluation/wake state.

The user must not need to restate the goal or reconstruct its plan.

---

## C05 — Executive loop / closed-loop convergence

Purpose: prove Jarvis can pursue an outcome, not merely produce one-shot plans.

### Test

Use one real goal that requires **at least two distinct action → observation cycles**.

The loop must demonstrate:

```text
observe
-> compute desired-state gap
-> select feasible action
-> authorize
-> act
-> independently observe
-> update world state
-> evaluate goal
-> repeat if needed
-> stop when satisfied
```

### PASS

- at least two distinct non-read steps occur;
- after the first step, Jarvis explicitly recognizes the goal is still unsatisfied;
- a second action is selected without the user orchestrating it;
- independent observations reconcile both actions;
- Jarvis stops once success conditions are met;
- no further action occurs after satisfaction.

---

## C06 — Authority, approval, denial, and resumption

Purpose: prove increased agency does not mean silent authority expansion.

### Test

Use one active plan containing:

- at least one safe read;
- at least one protected external write/action;
- a second protected step that will be denied.

### PASS

- safe read proceeds under its normal policy;
- protected action stops at the real approval boundary;
- explicit approval resumes the **same persisted plan step**;
- the action is not recreated as a new unrelated conversational request;
- denial blocks that exact path and causes replan/blocked state as appropriate;
- neither Qwen nor Groq nor generated tools can bypass the permission engine;
- repeated prior approvals/preferences do not silently become blanket permission.

---

## C07 — Independent outcome verification and failure recovery

Purpose: eliminate "API returned success, therefore done."

### Test A — verified real effect

Perform one consequential real action for which an independent external readback exists, such as an approved Calendar write, supported workstation action, or HomeKit action.

### Test B — ambiguity/failure

Induce a real failure, timeout, unreachable target, revoked permission, or non-verifiable outcome.

### PASS

For A:

- action attempt is persisted;
- expected observable result is defined before verification;
- a distinct verifier obtains fresh external evidence;
- status becomes verified only after that evidence;
- the owning goal/plan sees the verification.

For B:

- Jarvis records failed/timed_out/unverified accurately;
- it does not blindly retry an ambiguous protected action;
- it can answer a later "did that work?" from stored action state/evidence;
- recovery/replan occurs without fabricating success.

---

## C08 — Replanning and dormant-goal wakeup

Purpose: prove Jarvis adapts when reality changes while retaining the user's objective.

### Test A — replan

1. Begin a plan with at least one already-completed valid step.
2. Change a relevant real external fact so the planned next path is no longer feasible/optimal.
3. Do not restate the objective.

### Test B — dormant wake

1. Create a goal blocked on a real observable condition.
2. Jarvis must place it in an explicit dormant/watch state.
3. Change the exact blocking condition using real evidence.

### PASS

- Jarvis notices the relevant change;
- stale plan is invalidated with causal evidence;
- valid completed work is preserved;
- replacement plan names the prior plan/cause;
- dormant goal wakes from the matching condition, not an unrelated event;
- newly feasible next action is surfaced/executed according to existing authority.

---

## C09 — Proactivity and exception-based attention

Purpose: prove Jarvis can notice what matters without becoming notification spam.

### Test

During a controlled period:

1. generate at least five low-value state changes that remain queryable;
2. generate one genuinely interrupt-worthy event for an enrolled goal/watch;
3. present that same high-value observation twice or through duplicate delivery;
4. do not ask Jarvis to "check" for the event.

### PASS

- low-value changes do not interrupt;
- the high-value event produces one bounded proactive intervention;
- duplicate evidence does not produce a second interruption;
- the reason, evidence, timestamp, goal/watch, and confidence are inspectable;
- if the user is in a configured busy/driving/meeting context, deferral behavior is correct;
- proactivity never silently expands action permissions.

At least one proactive event must be delivered when the app is not sitting foregrounded on the relevant screen; C18 defines the closed-app delivery requirement.

---

## C10 — Cross-source situational awareness

Purpose: prove Jarvis can assemble a situation rather than merely list disconnected records.

### Test

Use a real imminent event/project that has relevant data in multiple sources.

Ask a natural-language question equivalent to:

> "Anything I need to know before I go in?"

### PASS

The answer correctly selects the situation and joins only justified context, including where available:

- exact Calendar event;
- participants/entities;
- active project/objective;
- pending commitments/tasks;
- relevant recent Gmail/doc evidence;
- fresh enrolled Guardian/Reality/World evidence;
- uncertainty and unavailable-source status.

Requirements:

- every material claim has source/provenance internally available;
- stale evidence is labeled;
- unrelated sensitive tasks are not pulled in because they are merely urgent;
- missing phone-local/location data is reported as missing, not treated as reassuring;
- no read-only briefing silently triggers external action.

---

## C11 — Deliberation, counterfactuals, and capability-gap honesty

Purpose: prove deeper reasoning exists without hiding uncertainty or inventing tools.

### Test A — real disagreement

Use a real ambiguous decision/research task. Production workers must independently cover evidence, counterexample/skepticism, feasibility, and cost/risk.

### Test B — counterfactual persistence

Create at least two plausible branches with different assumptions and preserve them after one is selected.

### Test C — missing capability

Give Jarvis an objective that needs one capability that is genuinely unavailable.

### PASS

- workers execute independently and their provenance exists before synthesis;
- at least one material disagreement survives into the record;
- counterfactual branches retain assumptions, expected outcomes, uncertainty, reversibility, and "what would change the choice";
- selecting a branch does not grant action permission;
- a missing capability is named explicitly;
- Jarvis does not fabricate that a tool/provider exists;
- if a narrow adapter is safely synthesized, it remains disabled until the real security/enable boundary is crossed.

---

## C12 — Cognitive routing: deterministic, local, Groq, and fallback

Purpose: prove the heterogeneous cognition hierarchy works on actual hardware/services.

### Test

Using the physical app and real backend:

1. issue one request that should use a deterministic capability;
2. issue one ordinary request that should remain local;
3. issue one genuinely difficult harmless reasoning request that deterministic routing sends to Groq;
4. inspect authenticated routing telemetry;
5. verify the Groq credential is stored through the intended iPhone/iPad Keychain flow;
6. force or induce a real cloud failure/unavailability and repeat a request;
7. use a cloud response that proposes a protected tool/action.

### PASS

- each request routes to the intended tier for an inspectable reason;
- a real Groq request succeeds using the configured device credential path;
- backend never receives/stores the normal iPhone Keychain Groq secret;
- compiled cloud context is minimized and a seeded credential-like secret is redacted;
- cloud outage/auth/rate/malformed-output path falls back to local Jarvis without making the whole system unusable;
- cloud proposal is treated as untrusted proposal data;
- protected action still crosses C06 authority and C07 verification;
- no free-tier quota or provider availability is fabricated.

---

## C13 — Conductor: verified workstation action

Purpose: prove Jarvis can extend agency into a real computer through bounded, auditable control.

### Test

From the normal supported Jarvis interaction, target one actually paired workstation.

1. Request one exact supported low-risk app launch.
2. Cross the real grant/confirmation boundary required by that path.
3. Observe the target workstation.
4. Exercise replay/expiry or wrong-target failure.
5. Request one unsupported arbitrary command/shell action.

### PASS

- correct exact host is targeted;
- action grant is short-lived/use-bounded as designed;
- target OS actually attempts the allowed launch;
- fresh process observation distinguishes observed from unverified;
- replay/expired/wrong-target request fails closed;
- unsupported arbitrary shell/command does not become available through model wording;
- user does not need to run a command manually on the target machine to complete the action.

---

## C14 — Reality Mesh: actual cross-device presence and continuity

Purpose: prove Jarvis's cross-device fabric exists outside documentation.

### Test

With physical iPhone/iPad, Windows host, and at least one configured real Mac:

1. check connected nodes;
2. confirm live device status comes from the actual node;
3. start an authorized view-only screen session;
4. observe a current screen change on the remote machine appear in a later snapshot;
5. stop/revoke the session;
6. repeat an access attempt after expiry/revocation;
7. disconnect the node/network and reconnect it.

If the candidate exposes exact app-launch buttons through Mesh, exercise one on each platform claimed as supported.

### PASS

- no device is reported online merely because it is configured;
- current real snapshots are viewable only during the permitted session;
- session expiry/revocation stops further viewing;
- unavailable node is reported unavailable rather than stale/online;
- reconnection restores status without manual database repair;
- enabled app launch produces real OS/process evidence;
- no hidden general remote shell, keyboard/mouse, clipboard, or file-transfer capability is implied unless separately implemented and accepted.

---

## C15 — Reality Graph: live provenance-bearing world state

Purpose: prove the graph represents real observations, not caller-supplied labels dressed up as reality.

### Test

Create one real bounded mission/situation containing at least:

- a real place/entity;
- at least two independent supported observation sources;
- freshness timestamps;
- one change over time.

Query the mission through the user-facing Jarvis path.

### PASS

- graph entities/edges preserve actual source identity and observation time;
- freshness/staleness is explicit;
- the answer is deterministic/model-free where the known query path claims it is;
- a source label supplied by a client is not treated as proof of authenticity;
- correlation is not upgraded to causation;
- missing courier/traffic/camera/provider evidence remains missing rather than inferred;
- Reality Graph itself does not silently gain purchasing/messaging/device authority.

---

## C16 — World Armor: general lawful public-camera path

Purpose: prove "remote eyes" means a general source platform rather than one hard-coded demo.

### Required real campaign

Use at least **three currently reachable, lawful public camera/media sources** satisfying all of the following:

- at least two distinct publishers/provider mechanisms;
- at least two geographic regions;
- at least one source enrolled as an exact public media/page source that was **not hard-coded as a special named demo**;
- at least one source that fails, goes stale, is unavailable, or is intentionally stopped during the campaign.

For each successful source:

1. enroll the exact source and its access/terms declaration through the intended UI/API path;
2. obtain actual current media;
3. run the intended bounded perception question/watch;
4. preserve source identity, check time, and uncertainty;
5. view the resulting evidence through Jarvis;
6. exercise pause/stop;
7. exercise forget/delete where supported.

### PASS

- actual public media is fetched from the enrolled source;
- private/link-local/reserved destinations and redirects are rejected according to policy;
- no credentials are guessed/bypassed;
- supported direct JPEG/PNG/WebP/MJPEG/HLS paths work where the source actually publishes them;
- page inspection either discovers a literal usable media source or honestly reports that the dynamic/protected format needs a provider adapter;
- one arbitrary supported-format source outside the fixed catalog works end-to-end;
- stale/offline source is not presented as live;
- perception is framed as visible evidence, not confirmed crime/disaster/person identity;
- identical frames do not manufacture repeated new physical events;
- stop/forget prevents prohibited later collection/retention;
- the UI does not claim universal CCTV access merely because some global places have no supported source.

**Important:** if the product claims a stronger phrase such as "any arbitrary public camera works," this gate fails unless that stronger claim is actually demonstrated across the access/format classes the product claims. The alternative is to make the user-facing claim precise and truthful before release, not to pretend unsupported formats are covered.

---

## C17 — World Armor: shipped environmental/movement providers

Purpose: prove each world-data integration currently advertised as operational reaches its real provider.

### Test

From the C01 inventory, list every World Armor / external-evidence provider the candidate claims as currently implemented and user-available (for example NWS, USGS, modelled air data, OpenSky, AIS if and only if the frozen candidate actually ships it, and any other promoted provider).

For **every provider in that shipped list**:

1. make one real provider request through normal Jarvis functionality;
2. record provider/source timestamp and coverage;
3. observe one real unavailable/no-data/degraded case somewhere in the campaign;
4. confirm provider facts enter the relevant World Armor/Reality Graph surface with correct provenance.

### PASS

- every advertised provider is exercised against the real external service;
- no provider is counted because a mock test passed;
- coverage gaps remain gaps;
- movement data is not silently converted into identity/surveillance claims beyond the provider data;
- an adapter being coded but not authorized/configured is labeled unavailable rather than working.

This gate is intentionally inventory-driven so later promoted provider features cannot escape real acceptance by being omitted from a static list here.

---

## C18 — Closed-app delivery and runtime resilience

Purpose: prove Jarvis remains present when the foreground app is not babysitting it.

### Test A — physical APNs delivery

1. configure real APNs credentials/entitlements for the candidate build;
2. register the physical iPhone through the actual app toggle;
3. place the app in background/closed state appropriate to the supported design;
4. generate one real qualifying warning/urgent event;
5. verify delivery on the physical phone;
6. generate a duplicate/retry condition.

### Test B — process recovery

1. with an opted-in live World Armor/watch process running, terminate/crash the supervised child/thread in the supported configuration;
2. verify guard/watchdog recovery;
3. temporarily remove network/provider availability and restore it;
4. restart the Windows service.

### PASS

- a real notification appears on the physical phone without foreground polling;
- APNs acceptance is not called physical-world verification of the underlying event;
- duplicate delivery is bounded/deduplicated at the user level;
- invalid/revoked token handling behaves correctly;
- live journal survives notification transport failure;
- watcher/supervisor restarts after the tested failure;
- goals/watches remain coherent after service restart;
- no duplicate protected actions occur due to recovery.

---

## C19 — Presence: real bounded physical actuation

Purpose: prove Jarvis can cause one safe, authorized physical-world change while preserving strict authority.

### Test

Using one exact HomeKit light already present in the physical iPhone's Apple Home catalog:

1. establish the exact short-lived/use-bounded grant through the intended Jarvis flow;
2. request the supported state change;
3. observe backend dispatch status;
4. allow the physical iPhone to execute the local HomeKit write;
5. obtain fresh HomeKit accessory readback;
6. have the human physically observe the actual light state change;
7. exhaust/expire/revoke the grant;
8. attempt the action again.

### PASS

- target is exact and preauthorized;
- initial dispatch remains unverified until readback;
- accessory readback matches expected state;
- the human records that the physical light visibly changed;
- expired/revoked grant prevents another actuation;
- failure/unreachable accessory produces failed/unverified status rather than success;
- locks, garage doors, arbitrary URLs, robots, or other unaccepted actuators do not become implicitly authorized.

If additional physical actuators are promoted into the release, C01 requires adding an equally concrete physical acceptance scenario before release.

---

## C20 — Privacy, secrets, revocation, and fail-closed boundaries

Purpose: prove that making Jarvis more powerful has not quietly made it less trustworthy.

### Real/synthetic campaign

Exercise at least:

1. wrong/missing Jarvis bearer credential;
2. revoked/expired action grant;
3. disabled feature flag;
4. private/link-local public-camera target;
5. malformed/oversized/redirecting external media response;
6. seeded API-key/password/bearer/private-key-like string in cloud candidate context;
7. wrong paired-node ID/token;
8. user revocation/stop while external I/O is in flight.

### PASS

- requests fail closed;
- secret-like material is not placed into logs, Reality Graph, analytics, or cloud context contrary to policy;
- cloud redaction is demonstrated on the real compile path;
- device/provider tokens are not returned to inappropriate clients;
- stop/revoke wins over late network completion;
- a model cannot widen a grant;
- a source "terms_reference" is never described as Jarvis having legally verified permission;
- no private network scan, credential guessing, surveillance identity extraction, or access-control bypass is required for any accepted feature.

---

## C21 — Long-run reliability / recovery soak

Purpose: catch the class of failures that only appear when Jarvis is treated as a persistent system.

### Test

Run the frozen candidate for at least **24 continuous hours** on the real primary deployment with the actual enabled feature set.

During the soak:

- keep at least one persistent goal active;
- keep at least one permitted watch/collector active;
- background and foreground the phone multiple times;
- perform at least one network disconnect/reconnect;
- restart one paired node;
- allow normal provider/API failures to occur rather than replacing them with fixtures;
- perform at least one approved action and verification;
- inspect database/outbox/resource growth.

### PASS

- backend remains/recoverably becomes healthy;
- no manual database repair is needed;
- active goal survives;
- watches do not silently die;
- duplicate notifications/actions remain bounded;
- resource/DB/outbox growth respects documented bounds;
- reconnecting devices restore truthful state;
- no secret leakage or permission widening appears;
- the system can still perform an ordinary Jarvis interaction at the end of the soak.

Any crash/hang/data corruption/silent watcher death that requires developer intervention is a failure until fixed and the soak is repeated on the new candidate SHA.

---

# 7. C22 — The unscripted revolutionary capstone

This is the release's decisive test.

Its purpose is to prove the system has become a **general, persistent agency layer** rather than a collection of individually demoable features.

## Selection rule

The exact capstone objective must be chosen **after the release candidate is frozen**.

It may not be:

- copied from an automated test fixture;
- the exact scenario used while implementing the feature;
- a developer-authored sequence of tool calls;
- a disguised checklist telling Jarvis which subsystem to invoke next.

The user supplies one ordinary-language bounded objective that is lawful, safe, and achievable using capabilities already in the release.

## The objective must naturally require all of the following

1. **Persistent intention** — it cannot finish in one immediate response.
2. **Private context** — at least one real supported private source such as Calendar/Gmail/world state.
3. **Live external/world evidence** — at least one real public/provider/device observation.
4. **Capability composition** — at least three distinct capability families must be selected and combined by Jarvis itself.
5. **A protected real action** — at least one external write/device action that crosses the proper approval boundary.
6. **Independent verification** — the action's outcome must be observed independently.
7. **A reality change** — during the run, one relevant external fact is changed or becomes unavailable so the original plan must adapt.
8. **Proactivity** — Jarvis must surface at least one material development without being asked to check.
9. **Continuity** — the run must survive either a real backend restart or a real device handoff/reconnect.
10. **Completion evidence** — Jarvis must know when the objective is satisfied and stop.

## Human constraint

After the initial objective, the user may only:

- approve or deny protected actions;
- answer genuine value questions;
- perform the one defined real-world perturbation;
- physically observe outcomes.

The user may **not**:

- tell Jarvis which tool to call;
- manually invoke an endpoint;
- copy data between subsystems;
- restart a failed internal step by hand;
- tell Jarvis that an action succeeded when an independent observation exists;
- repair the plan.

## PASS

A single causal trace shows:

```text
ordinary user objective
-> persistent desired state
-> real observations/private context
-> Jarvis-selected composition of capabilities
-> plan
-> protected action boundary
-> action
-> independent outcome verification
-> changed reality
-> autonomous replan
-> proactive user-facing intervention
-> continuity across restart/handoff
-> independently evidenced satisfaction
-> automatic stop
```

The user must be able to experience this as **one Jarvis task**, not as a developer walking through twelve demos.

If every preceding gate passes but C22 fails, the revolutionary upgrade is **not done**.

---

## 7A. C01 appendix — shipped-capability acceptance scenarios

*Amendment adopted 2026-09-27 under C01 ("this file is amended and the new test passes"). The user decided that every
capability previously presented to them as implemented or current is in release scope. It gets a REAL test and may
not be relabelled to pass. The only exceptions are the internal mechanisms listed at the end. This amendment adds
tests. It weakens no gate.*

Each scenario below is a REAL gate with its own acceptance record (gate IDs `C01-S01` … `C01-S16`).
§3 applies in full:
- the current frozen candidate SHA;
- normal user surfaces only;
- real devices and services;
- at least one failure case per scenario.

Each scenario record also needs a human attestation of what was observed. **C01 passes only when every C01-Sxx
record is PASS on the frozen candidate** and the inventory in `CAPABILITY_INVENTORY.md` has no orphan.

| ID | Scenario (one real session) | Capabilities covered (Feature Guide ids / docs) | PASS requires | Failure case |
|---|---|---|---|---|
| C01-S01 | Hands-free voice conversation of at least 10 turns on the iPhone | wake, followup, barge, dictation, vocab, quiet-speech, local-alias, audio-hud, response-done-tone, sir-dedupe, empty-stream-recovery, kokoro, whisper, context-discipline, episodic | Wake word starts a turn. A follow-up within 5 s needs no wake word. Speaking over Jarvis interrupts it. A long dictated email body is not cut off. A custom vocabulary word is recognized. The Kokoro voice is heard, and a whisper response when requested. The done tone plays. No duplicated "sir". A reference from 3 turns earlier resolves. | Kill the TTS server mid-session: Jarvis falls back audibly, without a silent failure. |
| C01-S02 | Ray-Ban Meta glasses session | Gen 1 audio route, welcome-back, passive-vision, live-scene recall ("what can you see?"), spatial last-seen, camera-master, local-visual-cache, fast-perception, visual-change | Audio routes through the glasses. Put the glasses back on: greeting. "What can you see?" describes the current fresh scene. "Where did I last see my keys?" answers from a real sighting. The Stop Camera master switch stops frames. | Camera stopped: vision questions report no fresh frames instead of describing stale ones. |
| C01-S03 | iPhone-only intelligence with the backend unreachable, then reachable | offline-brain, local-first-router, deterministic-utilities, stable-local-brain, native-calendar-local, native-reminders-local, local-timers, native-contacts-local, context-capsules, unified-local-memory, local-route-telemetry, quality-shield, semantic-audit, capability-receipts, packs-tab, offline-queue, no-write-replay, diagnostics, auto-recovery | Backend off: a time/unit question, a native Calendar read, a Reminder created (visible in Reminders.app), a timer, a Contacts lookup, a stable factual question all answered on the phone. An email request is staged offline, **not** sent. Backend on: auto-recovery reconnects; the staged write is **not** replayed without confirmation. Packs/receipts/telemetry show the routes taken. | The backend outage itself. |
| C01-S04 | On-device perception and audio | audio-memory, sound-analysis, translation, ocr, qr | "What did I just say?" recalls recent speech. A doorbell/alarm sound is classified. A phrase is translated on-device. OCR of a printed page. A QR code decoded. | Airplane mode: all still work, or say explicitly that they are unavailable. |
| C01-S05 | People and personal inventory | known-people, person-brief, encounter-capture, inventory, inventory-lastseen, inventory-alert | Enroll one consenting person. Jarvis recognizes them later and gives a pre-conversation brief. Post-encounter capture is saved. An enrolled item is matched with last-seen time and place, and a knowledge-triggered item note fires. | A non-enrolled face is not identified. Unenrollment removes the person from future matches. |
| C01-S06 | Privacy and interruption controls | privacy-mode, privacy-zone, incident, modes, smart-interrupt, context-reminders, event-timeline, camera-privacy-pack | Guest/privacy mode suppresses personal data. Entering a configured privacy zone disables capture. An encrypted incident capture is created and viewable. Conversation modes change behavior. A contextual reminder fires in context. The event timeline shows the session. | Inside the privacy zone a camera request is refused. |
| C01-S07 | Local executive tools | goals, waiting, routine, intent-radar, knowledge-graph, clipboard, local-receipts | Create a goal and a waiting-on item. A routine proposal appears after repeated behavior. Intent radar surfaces a relevant item. Knowledge-graph query answers. Clipboard intelligence acts on copied text. Local receipts list the actions. | Delete a waiting-on item: it no longer surfaces. |
| C01-S08 | iOS integration | shortcuts (App Intents / Action Button), share-text | An Action Button / Shortcuts invocation reaches Jarvis. Text shared from another app is processed. | Invoke while the backend is down: the result reports offline honestly. |
| C01-S09 | Windows PC and automation | pc-app, browser, desktop-context, jobs, briefing, background, prewarm, resources, audio-damping, journal, expenses, meeting, meeting-offline, unified-search | Launch and close a Windows app (process verified). Focus a browser tab. "What am I working on?" is correct. A scheduled reminder fires at its time and a recurring one is created. A briefing is generated. A background task completes. Resource status is shown. Audio damping lowers media during speech. A daily journal and an expense from a real receipt. Start/finish meeting notes (online and offline). Unified search finds an email and an event. | Close the browser: tab control reports unavailable instead of claiming success. |
| C01-S10 | Connectivity failover | tailscale failover (LAN → Tailscale) | Away from home, requests succeed via Tailscale automatically. Back home, LAN is used again. | Both paths down: the app says unreachable and queues nothing consequential. |
| C01-S11 | Mission Control and navigation | appointment journey mission, Maps handoff, GPS arrival, turn-by-turn navigation | For a real appointment: the mission starts, the Maps handoff opens the correct destination, arrival is observed by GPS, and navigation commands work. | Location permission revoked: arrival is reported unknown, never assumed. |
| C01-S12 | Life Fabric | deadlines, handoffs, assets, friction log, readiness, what-if | Create a deadline, a handoff and an asset. Readiness reflects them. A friction entry is logged. A what-if returns minutes saved with provenance. Retire/forget works. | A forgotten record no longer appears after restart. |
| C01-S13 | Reality Lens and World Armor analysis surfaces | Reality Lens sense/compare/remember; Synthetic Senses; Causal Debugger; Parallel Existence; two-region comparison | Reality Lens senses a real place and remembers it for 30 days. Each v8 surface runs once on real retained evidence. The two-region comparison compares two enrolled regions with provenance. | An unsupported region shows unknown/unavailable providers, never an all-clear. |
| C01-S14 | Personal Notecard and Health context | Personal Notecard (address, relationships), optional Apple Health context | Store the home address and one relationship; Jarvis uses them in an answer. With Health opt-in, a Health-derived context appears in a relevant answer. | Health permission revoked: no Health data is used or claimed. |
| C01-S15 | Camera-free ambient physical actuation (second actuation path per C19) | arrival- and doorbell-triggered pre-enrolled HomeKit light | A real away→home arrival turns on the enrolled light, with fresh HomeKit readback and human observation. A real doorbell sound triggers the enrolled doorbell light. | The first at-home fix after launch, a stale geofence, or a revoked enrollment produces no actuation. |
| C01-S16 | Guardian surfaces | Counterfactual Guardian, Goal Guardian deadline/warning loops | An enrolled objective with a real deadline produces an evidence-backed warning at the right time. Snooze and revoke work. | Revoked enrollment: no further warnings. |

**Internal mechanisms (not user capabilities, labelled as such, no separate gate):** capability-packs registry,
capability-router, readonly-composer, lazy-pack-activation, routing-regressions harness, compact-context-packets.
They are exercised implicitly by C01-S03, C02 and C12.
**Declared limitations** (Feature Guide "Known Limits") claim no capability and need no gate.

---

## 8. Release decision

The release may be called complete only when all of the following are true simultaneously:

- C00–C22 are PASS;
- all REAL evidence is bound to the same frozen candidate SHA/environment, except where a gate explicitly records a separate physical node build identity;
- the feature inventory has no unaccepted shipped claims;
- no required gate is BLOCKED;
- no known defect invalidates a receipt;
- the 24-hour soak passed after the final code change;
- C22 passed after the code freeze;
- the final full Agency/release validation runs **after** the qualifying REAL receipts, not before them.

Existing command where applicable:

```powershell
jarvis-agency-release-check --full
```

That command is necessary where its contract applies. It is not sufficient by itself to satisfy this constitution.

### Forbidden completion language before the above is true

Do not describe the release as:

- done;
- complete;
- revolutionary upgrade delivered;
- fully implemented;
- fully working;
- deployed and verified;
- production-ready;

unless C00–C22 are actually PASS.

Permitted language before then should be precise, e.g.:

- "source implementation exists";
- "synthetic tests pass";
- "deployed but C18 is unverified";
- "C16 passed on two of three required real camera sources";
- "blocked on physical HomeKit acceptance";
- "release remains incomplete."

---

## 9. Change-control rule

After this file exists:

1. Every engineering change for this release must close a failed/unproven gate, make a gate more falsifiable, or repair a regression preventing a gate from passing.
2. Adding a new feature does not excuse failing an old gate.
3. If a new user-facing capability is nevertheless promoted into this release, update C01 and add its REAL test **before calling the capability implemented**.
4. Any code change after a REAL test invalidates whichever receipts may be affected; when uncertain, rerun.
5. C22 is always rerun after the final code freeze.
6. Future conceptual work belongs in `future.md` until this release is actually complete.

---

## 10. The standard

The standard for this release is deliberately simple:

> **If the user cannot experience the capability on the real Jarvis system, it is not finished.**
>
> **If Jarvis cannot prove an external action worked, it did not work yet.**
>
> **If Jarvis needs the developer to orchestrate the supposedly autonomous workflow, it is not autonomous yet.**
>
> **If an advertised capability has not survived its real failure case, it is not accepted yet.**
>
> **If any required gate remains unproven, the release is not done.**

This file exists so that "we built it" can never again be substituted for "you can use it."
