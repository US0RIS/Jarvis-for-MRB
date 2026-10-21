"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const root = "/callless/v1/";
  const localKey = "horus.callless.access";
  const params = new URLSearchParams(location.search);
  const requestedName = (params.get("contact") || "").trim().toLowerCase();
  const CAPS = ["media-v1"];
  const RESTART_WINDOW_MS = 10000;     // one ICE restart, then end with reason "network"
  const STALE_TICKS = 3;               // seconds without new inbound audio packets => media lost
  let token = localStorage.getItem(localKey) || "";
  let myUser = null;
  let socket = null;
  let heartbeat = null;
  let reconnect = null;
  let peer = null;
  let localStream = null;
  let session = null;
  let mode = "login";
  let armedLocal = false;
  let monitor = null;
  let restartTimer = null;
  let audioCtx = null;
  let pendingCandidates = [];
  let contactCache = [];
  let iceServers = [{urls:"stun:stun.l.google.com:19302"}];
  const msg = (text) => { $("message").textContent = text || ""; };
  const state = (text) => { $("call-state").textContent = text; };
  const txt = (text) => { $("call-text").textContent = text; };
  const btn = (name, visible) => { $(name).hidden = !visible; };

  // ---- tones (synthesized; no audio assets) -------------------------------
  // WebAudio may be blocked until a user gesture; the visual cues never depend on it.
  function audio() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      if (!audioCtx) audioCtx = new Ctx();
      if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
      return audioCtx;
    } catch (_) { return null; }
  }
  function tone(sequence, type, gainLevel) {
    const ctx = audio();
    if (!ctx) return;
    let at = ctx.currentTime + 0.02;
    for (const [freq, seconds] of sequence) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(gainLevel, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(at); osc.stop(at + seconds + 0.02);
      at += seconds * 0.85;
    }
  }
  // Subtle rising pair: only ever played when the hub reports media_connected.
  const connectTone = () => tone([[660, 0.13], [880, 0.18]], "sine", 0.07);
  // Clearly different: lower, descending, three steps.
  const endTone = () => tone([[520, 0.16], [390, 0.16], [260, 0.30]], "triangle", 0.11);

  const END_TEXT = {
    hangup: (who) => who === "me" ? "You ended the conversation." : "The other person ended the conversation.",
    peer_left: () => "The other person left (their connection closed).",
    revoked: () => "Access was revoked.",
    unavailable: () => "Availability was closed.",
    network: () => "The network connection failed.",
    media: () => "Audio could not be established.",
    timeout: () => "Audio did not connect in time.",
    no_answer: () => "No answer.",
    declined: () => "The request was declined.",
    cancelled: () => "The request was cancelled.",
    error: () => "The conversation stopped because of an error."
  };

  async function api(method, path, body) {
    const headers = {"Accept":"application/json"};
    if (token) headers.Authorization = "Bearer " + token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(root + path, {method, headers, body:body === undefined ? undefined : JSON.stringify(body), cache:"no-store"});
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw Error(data.detail || "Request failed (" + response.status + ")");
    return data;
  }

  function renderLogin() {
    $("auth-panel").hidden = !!myUser;
    $("session-panel").hidden = !myUser;
    $("display-name-field").hidden = mode !== "register";
    $("display-name").required = mode === "register";
    $("auth-submit").textContent = mode === "register" ? "Register" : "Sign in";
    $("auth-mode").textContent = mode === "register" ? "I already have an account" : "Create an account";
    $("password").autocomplete = mode === "register" ? "new-password" : "current-password";
    if (myUser) $("my-identity").textContent = "@" + myUser.handle;
  }

  const STATUS_HELP = {
    open: "Contacts you grant Open can reach you without a ring, but only after you arm microphone consent in this tab. Contacts on Ask first still need your approval.",
    ask: "Every request needs your approval, even from contacts you granted Open.",
    closed: "Nobody can reach you. Requests are refused without saying why."
  };

  async function initSession(data) {
    myUser = data.user;
    token = data.token || token;
    localStorage.setItem(localKey, token);
    renderLogin();
    $("status").value = myUser.status;
    $("status-help").textContent = STATUS_HELP[myUser.status] || "";
    try {
      const result = await api("GET", "ice");
      if (Array.isArray(result.ice_servers)) iceServers = result.ice_servers;
    } catch (_) {}
    await refresh();
    openSocket();
  }

  function resolveRequested(contacts) {
    if (!requestedName) return null;
    const lowered = requestedName.replace(/^@/, "");
    const exact = contacts.filter((c) => !c.blocked && (c.handle === lowered || c.name.toLowerCase() === lowered || c.handle === lowered.replace(/\s+/g, "")));
    if (exact.length === 1) return exact[0].handle;
    const first = contacts.filter((c) => !c.blocked && c.name.toLowerCase().split(/\s+/)[0] === lowered);
    return first.length === 1 ? first[0].handle : null;
  }

  async function refresh() {
    if (!myUser) return;
    const {contacts} = await api("GET", "contacts");
    contactCache = contacts;
    const container = $("contacts");
    container.replaceChildren();
    const wanted = resolveRequested(contacts);
    if (requestedName && !wanted) msg("No single approved contact matches \"" + requestedName + "\".");
    if (!contacts.length) {
      const p = document.createElement("p");
      p.className = "description";
      p.textContent = "No approved contacts. Generate or redeem an invitation to connect.";
      container.append(p);
    }
    for (const item of contacts) {
      const row = document.createElement("div"); row.className = "contact";
      const info = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = item.name + "  @" + item.handle;
      const sub = document.createElement("div"); sub.className = "sub";
      sub.textContent = item.blocked ? "Blocked" : item.online ? "Online" : "Offline";
      info.append(title, sub);
      const controls = document.createElement("div"); controls.className = "controls";
      const connect = document.createElement("button");
      connect.textContent = wanted === item.handle ? "Connect to @" + item.handle : "Connect";
      // The hub decides; a closed or unavailable contact is refused without detail.
      connect.disabled = item.blocked || !item.online || !!session || !socket || socket.readyState !== WebSocket.OPEN;
      connect.addEventListener("click", () => call(item.handle));
      const grant = document.createElement("select");
      grant.setAttribute("aria-label", "What @" + item.handle + " may do when they request you");
      for (const [value, label] of [["ask", "They must ask"], ["open", "They may connect directly"], ["closed", "They cannot reach me"]]) {
        const option = document.createElement("option"); option.value = value; option.textContent = label;
        grant.append(option);
      }
      grant.value = item.my_grant;
      grant.addEventListener("change", async () => {
        try { await api("PUT", "grants", {handle:item.handle, level:grant.value}); msg("Access for @" + item.handle + " updated."); }
        catch (e) { msg(e.message); }
        await refresh().catch(() => {});
      });
      const block = document.createElement("button");
      block.textContent = item.blocked ? "Unblock" : "Block";
      block.addEventListener("click", async () => {
        try { await api("PUT", "block", {handle:item.handle, blocked:!item.blocked}); await refresh(); }
        catch (e) { msg(e.message); }
      });
      controls.append(connect, grant, block); row.append(info, controls); container.append(row);
      if (wanted === item.handle && !session) msg("Contact selected: @" + item.handle + ". Tap Connect to enable your microphone.");
    }
    loadRecent().catch(() => {});
  }

  async function loadRecent() {
    const {sessions} = await api("GET", "sessions/recent?limit=8");
    const list = $("recent");
    list.replaceChildren();
    if (!sessions.length) { const li = document.createElement("li"); li.textContent = "No conversations yet."; list.append(li); return; }
    for (const item of sessions) {
      const li = document.createElement("li");
      const when = item.requested_at ? new Date(item.requested_at * 1000).toLocaleString() : "";
      const timing = item.connect_ms != null ? " · audio live after " + (item.connect_ms / 1000).toFixed(1) + " s" : "";
      li.textContent = (item.direction === "outgoing" ? "To @" : "From @") + item.peer + " · " + item.state +
        (item.reason ? " (" + item.reason + ")" : "") + timing + " · " + when;
      list.append(li);
    }
  }

  function send(obj) {
    if (socket && socket.readyState === WebSocket.OPEN) { socket.send(JSON.stringify(obj)); return true; }
    return false;
  }

  function openSocket() {
    if (!token) return;
    if (socket) socket.close();
    clearTimeout(reconnect);
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(scheme + "//" + location.host + root + "socket");
    socket = ws;
    ws.addEventListener("open", () => {
      ws.send(JSON.stringify({type:"auth", token, caps:CAPS}));
      heartbeat = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:"ping"})); }, 25000);
    });
    ws.addEventListener("message", async (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { return; }
      try { await onMessage(data); } catch (e) { msg("Callless: " + e.message); }
    });
    ws.addEventListener("close", () => {
      clearInterval(heartbeat);
      $("connection").textContent = "Offline";
      $("connection").classList.remove("online");
      if (socket === ws && myUser) {
        // The signaling channel is gone, so the hub has already ended this session for the peer.
        if (session) conversationEnded("network", "me");
        setArmed(false, true);
        reconnect = setTimeout(openSocket, 3000);
      }
    });
  }

  async function onMessage(data) {
    if (data.type === "ready") {
      $("connection").textContent = "Online";
      $("connection").classList.add("online");
      if (armedLocal) send({type:"arm", armed:true});
      await refresh();
    } else if (data.type === "incoming") {
      if (session) return;
      session = {id:data.session_id, contact:data.from, role:"callee", state:data.state, access:data.access,
                 accepted:data.state === "authorized", reported:false, stale:0, lastPackets:0, toneDone:false,
                 restartTried:false, peerMuted:false, muted:false};
      hideEnded();
      showSession();
      await refresh();
      if (data.state === "authorized" && armedLocal) {
        // Granted Open and this tab was armed: connect without a ring. Microphone permission may still
        // need a tap on some browsers; join() falls back to a visible button in that case.
        txt("@" + data.from + " is connecting (you granted direct access). Starting your microphone.");
        join(true);
      } else if (data.state === "authorized") {
        txt("@" + data.from + " is allowed to connect directly, but this tab is not armed. Tap Join to enable your microphone.");
      } else {
        txt("@" + data.from + " wants to speak. Tap Join to accept and enable your microphone.");
      }
    } else if (data.type === "state" && session && data.session_id === session.id) {
      onHubState(data);
    } else if (data.type === "peer_muted" && session && data.session_id === session.id) {
      session.peerMuted = !!data.muted;
      $("peer-muted").hidden = !data.muted;
    } else if (data.type === "signal") {
      await signalReceived(data);
    } else if (data.type === "ended" && session && session.id === data.session_id) {
      conversationEnded(data.reason, "peer");
    } else if (data.type === "armed") {
      setArmed(!!data.armed, false);
    }
  }

  function showSession() {
    btn("hangup", true);
    $("hangup").textContent = session && session.role === "callee" && !session.accepted ? "Decline" : "Disconnect";
    btn("join", !!session && session.role === "callee" && !session.accepted ||
                !!session && session.role === "callee" && session.state === "authorized" && !peer);
    btn("mute", !!session && ["authorized", "signaling", "media_connected"].includes(session.state));
    state(stateLabel());
  }

  function stateLabel() {
    if (!session) return "Idle";
    return {
      requested: "Requesting", ringing: session.role === "caller" ? "Waiting for approval" : "Approval requested",
      authorized: "Authorized · not connected yet",
      signaling: "Negotiating audio · not live yet",
      media_connected: session.muted ? "Live audio · you are muted" : "Live audio"
    }[session.state] || session.state;
  }

  function onHubState(data) {
    const was = session.state;
    session.state = data.state;
    if (data.state === "media_connected") {
      clearTimeout(restartTimer);
      const seconds = data.connect_ms != null ? " Connected in " + (data.connect_ms / 1000).toFixed(1) + " s." : "";
      txt("Live audio with @" + session.contact + "." + seconds);
      if (!session.toneDone) { session.toneDone = true; connectTone(); }
    } else if (data.state === "signaling" && was === "media_connected") {
      txt("Audio from @" + session.contact + " was interrupted. Trying to recover.");
    } else if (data.state === "signaling") {
      txt("Negotiating audio with @" + session.contact + ". Not live yet.");
    } else if (data.state === "authorized") {
      txt(session.role === "caller" ? "@" + session.contact + " approved. Waiting for their microphone." : "Approved. Join to enable your microphone.");
    }
    showSession();
  }

  // ---- microphone / peer connection --------------------------------------
  async function mic() {
    if (!navigator.mediaDevices?.getUserMedia) throw Error("Microphone access requires HTTPS, or localhost.");
    if (!localStream) localStream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    return localStream;
  }

  // Arming records that THIS tab's user has consented to hands-free pickup for
  // contacts they granted Open. It needs a tap (browser permission prompt), then
  // releases the microphone again: nothing records or listens while idle.
  async function arm() {
    try {
      audio();
      const probe = await navigator.mediaDevices.getUserMedia({audio:true, video:false});
      probe.getTracks().forEach((track) => track.stop());
      if (!send({type:"arm", armed:true})) throw Error("Not connected to the hub.");
      armedLocal = true;
    } catch (e) { msg("Could not arm microphone consent: " + e.message); }
  }
  function setArmed(value, keepIntent) {
    if (!value && !keepIntent) armedLocal = false;
    const on = value && armedLocal;
    $("arm").textContent = on ? "Direct connections armed · tap to disarm" : "Arm direct connections for this tab";
    $("arm-help").textContent = on ? "Contacts you granted Open can connect without a ring while this tab stays open and online. Your microphone is idle until a conversation starts."
      : "Not armed: even contacts you granted Open will be asked for your approval.";
  }

  async function createPeer() {
    if (peer) return peer;
    const audioStream = await mic();
    const pc = new RTCPeerConnection({iceServers});
    peer = pc;
    for (const track of audioStream.getAudioTracks()) pc.addTrack(track, audioStream);
    pc.addEventListener("icecandidate", (event) => { if (event.candidate) sendSignal({type:"candidate", candidate:event.candidate.toJSON()}); });
    pc.addEventListener("track", (event) => {
      const element = $("remote-audio");
      element.srcObject = event.streams[0] || new MediaStream([event.track]);
      element.play().catch(() => {btn("enable-audio", true); msg("Tap Enable speaker audio to hear your contact.");});
    });
    pc.addEventListener("connectionstatechange", () => {
      if (peer !== pc || !session) return;
      // connected here only means the transport is up. Audio is reported by the monitor.
      if (pc.connectionState === "failed") recoverOrEnd("failed");
      else if (pc.connectionState === "disconnected") recoverOrEnd("disconnected");
    });
    startMonitor(pc);
    return pc;
  }

  function sendSignal(payload) {
    if (session) send({type:"signal", session_id:session.id, payload});
  }

  // Report media only after the peer connection is connected AND inbound audio
  // packets are actually arriving. Signaling alone is never reported as media.
  function startMonitor(pc) {
    clearInterval(monitor);
    monitor = setInterval(async () => {
      if (peer !== pc || !session) return;
      let packets = 0;
      try {
        (await pc.getStats()).forEach((report) => {
          if (report.type === "inbound-rtp" && (report.kind || report.mediaType) === "audio") packets += report.packetsReceived || 0;
        });
      } catch (_) { return; }
      const flowing = pc.connectionState === "connected" && packets > session.lastPackets;
      session.lastPackets = packets;
      if (flowing) {
        session.stale = 0;
        if (!session.reported) {
          session.reported = true;
          clearTimeout(restartTimer);
          send({type:"media", session_id:session.id, state:"connected"});
        }
      } else if (session.reported && !session.peerMuted && ++session.stale >= STALE_TICKS) {
        session.reported = false;
        send({type:"media", session_id:session.id, state:"lost"});
        recoverOrEnd("stalled");
      }
    }, 1000);
  }

  // One ICE restart inside a bounded window; if audio is not back, end as "network".
  function recoverOrEnd(why) {
    if (!session || !peer) return;
    if (session.reported && why === "disconnected") { session.reported = false; send({type:"media", session_id:session.id, state:"lost"}); }
    if (session.restartTried) {
      if (why === "failed" || why === "stalled") endSession("network");
      return;
    }
    session.restartTried = true;
    clearTimeout(restartTimer);
    const id = session.id;
    restartTimer = setTimeout(() => { if (session && session.id === id) endSession("network"); }, RESTART_WINDOW_MS);
    if (session.role === "caller") restartOffer().catch(() => endSession("network"));
    else sendSignal({type:"restart"});
  }
  async function restartOffer() {
    const pc = peer;
    if (!pc) return;
    const offer = await pc.createOffer({iceRestart:true});
    await pc.setLocalDescription(offer);
    sendSignal({type:"offer", sdp:pc.localDescription.sdp});
  }

  async function call(handle) {
    try {
      if (session) throw Error("Disconnect your current session first.");
      audio();   // the Connect tap authorizes sound and microphone use
      const result = await api("POST", "sessions", {target:handle});
      session = {id:result.session_id, contact:handle, role:"caller", state:result.state, accepted:result.state === "authorized",
                 reported:false, stale:0, lastPackets:0, toneDone:false, restartTried:false, peerMuted:false, muted:false};
      hideEnded();
      txt(result.state === "authorized"
        ? "Connecting to @" + handle + ". Waiting for their microphone; not live yet."
        : "Asking @" + handle + ". They must approve before anything connects.");
      showSession();
      await createPeer();
      await refresh();
    } catch (e) { msg(e.message); if (session) await endSession("hangup"); }
  }

  async function join(automatic) {
    if (!session || session.role !== "callee") return;
    const s = session;
    try {
      await createPeer();
      if (!s.accepted) await api("POST", "sessions/" + encodeURIComponent(s.id) + "/accept");
      if (session !== s) return;
      s.accepted = true;
      sendSignal({type:"ready"});
      txt("Connecting with @" + s.contact + ". Audio is not live yet.");
      showSession();
    } catch (e) {
      msg(automatic ? "Tap Join to enable your microphone (" + e.message + ")." : e.message);
      if (session === s) { btn("join", true); showSession(); }
    }
  }

  async function signalReceived(data) {
    if (!session || data.session_id !== session.id) return;
    const p = data.payload;
    if (!p || !["ready", "offer", "answer", "candidate", "restart"].includes(p.type)) return;
    if (p.type === "ready" && session.role === "caller") {
      const pc = await createPeer();
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      sendSignal({type:"offer", sdp:pc.localDescription.sdp});
    } else if (p.type === "restart" && session.role === "caller" && peer) {
      await restartOffer();
    } else if (p.type === "offer" && session.role === "callee") {
      const pc = await createPeer();
      await pc.setRemoteDescription({type:"offer", sdp:p.sdp});
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      sendSignal({type:"answer", sdp:pc.localDescription.sdp});
      while (pendingCandidates.length) await pc.addIceCandidate(pendingCandidates.shift());
    } else if (p.type === "answer" && session.role === "caller" && peer) {
      await peer.setRemoteDescription({type:"answer", sdp:p.sdp});
      while (pendingCandidates.length) await peer.addIceCandidate(pendingCandidates.shift());
    } else if (p.type === "candidate" && p.candidate) {
      if (peer?.remoteDescription) await peer.addIceCandidate(p.candidate);
      else pendingCandidates.push(p.candidate);
    }
  }

  // ---- ending -------------------------------------------------------------
  function hideEnded() { $("end-banner").hidden = true; $("end-banner").textContent = ""; }

  // Single place every end path goes through: hangup, peer left, revoked,
  // network failure, WebSocket loss. Shows the banner and plays the end tone.
  function conversationEnded(reason, who) {
    const s = session;
    if (!s) return;
    const text = (END_TEXT[reason] || END_TEXT.error)(who);
    teardown();
    const failed = reason === "network" || reason === "media" || reason === "timeout" || reason === "error";
    $("end-banner").textContent = "Conversation ended · " + text + (failed && !s.toneDone ? " Audio never went live." : "");
    $("end-banner").hidden = false;
    state("Ended"); txt("Conversation with @" + s.contact + " ended.");
    endTone();
    refresh().catch(() => {});
  }

  function teardown() {
    clearInterval(monitor); clearTimeout(restartTimer);
    if (peer) { peer.close(); peer = null; }
    if (localStream) { localStream.getTracks().forEach((track) => track.stop()); localStream = null; }
    $("remote-audio").srcObject = null;
    session = null; pendingCandidates = [];
    for (const name of ["join", "hangup", "enable-audio", "mute"]) btn(name, false);
    $("peer-muted").hidden = true;
    $("mute").textContent = "Mute";
  }

  async function endSession(reason) {
    const s = session;
    if (!s) return;
    send({type:"hangup", session_id:s.id, reason});
    const hubReason = ["hangup", "network", "media", "error"].includes(reason) ? reason : "hangup";
    conversationEnded(s.state === "requested" || s.state === "ringing" ? (s.role === "callee" ? "declined" : "cancelled") : hubReason, "me");
  }

  function toggleMute() {
    if (!session || !localStream) return;
    session.muted = !session.muted;
    localStream.getAudioTracks().forEach((track) => { track.enabled = !session.muted; });
    $("mute").textContent = session.muted ? "Unmute" : "Mute";
    send({type:"mute", session_id:session.id, muted:session.muted});
    state(stateLabel());
  }

  $("auth-mode").addEventListener("click", () => {mode = mode === "login" ? "register" : "login";renderLogin();});
  $("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault(); msg("");
    try {
      const data = await api("POST", mode === "register" ? "register" : "login", {
        handle:$("handle").value, password:$("password").value, name:$("display-name").value
      });
      $("password").value = "";
      await initSession(data);
    } catch(e) {msg(e.message);}
  });
  $("status").addEventListener("change", async () => {
    try {
      const {user} = await api("PUT", "presence", {status:$("status").value});
      myUser = user;
      $("status-help").textContent = STATUS_HELP[user.status] || "";
      msg("Status updated."); await refresh();
    } catch(e) {msg(e.message);}
  });
  $("arm").addEventListener("click", () => { if (armedLocal) { send({type:"arm", armed:false}); armedLocal = false; setArmed(false, false); } else arm(); });
  $("refresh").addEventListener("click", () => refresh().catch(e=>msg(e.message)));
  $("generate-invite").addEventListener("click", async () => {
    try {const result=await api("POST","invite");$("invite-code").textContent=result.code;msg("One-use invitation code. Expires in 15 minutes. New contacts start on \"They must ask\".");}
    catch(e){msg(e.message);}
  });
  $("accept-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {await api("POST","accept",{code:$("accept-code").value});$("accept-code").value="";await refresh();msg("Contact added.");}
    catch(e){msg(e.message);}
  });
  $("join").addEventListener("click", () => join(false));
  $("hangup").addEventListener("click", () => endSession("hangup"));
  $("mute").addEventListener("click", toggleMute);
  $("dismiss-ended").addEventListener("click", hideEnded);
  $("enable-audio").addEventListener("click", () => $("remote-audio").play().then(()=>btn("enable-audio",false)).catch(e=>msg(e.message)));
  $("logout").addEventListener("click", async () => {
    try {await api("POST","logout");} catch (_) {}
    if (socket) {const old = socket; socket=null; old.close();}
    clearTimeout(reconnect);clearInterval(heartbeat);
    teardown();localStorage.removeItem(localKey);token="";myUser=null;armedLocal=false;renderLogin();msg("Signed out.");
  });

  setArmed(false, false);
  renderLogin();
  if (token) api("GET","me").then(async data => initSession(data)).catch(() => {
    localStorage.removeItem(localKey);token="";myUser=null;renderLogin();
  });
})();
