"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const root = "/callless/v1/";
  const localKey = "horus.callless.access";
  const requestedContact = new URLSearchParams(location.search).get("contact")?.toLowerCase() || "";
  let token = localStorage.getItem(localKey) || "";
  let myUser = null;
  let socket = null;
  let heartbeat = null;
  let reconnect = null;
  let peer = null;
  let localStream = null;
  let session = null;
  let mode = "login";
  let iceServers = [{urls:"stun:stun.l.google.com:19302"}];
  const msg = (text) => { $("message").textContent = text || ""; };
  const state = (text) => { $("call-state").textContent = text; };
  const txt = (text) => { $("call-text").textContent = text; };
  const btn = (name, visible) => { $(name).hidden = !visible; };

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

  async function initSession(data) {
    myUser = data.user;
    token = data.token || token;
    localStorage.setItem(localKey, token);
    renderLogin();
    $("status").value = myUser.status;
    $("status-help").textContent = myUser.status === "open" ? "Approved contacts can reach you while this page is connected." :
      myUser.status === "ask" ? "Requests need explicit approval." : "Not receiving connections.";
    try {
      const result = await api("GET", "ice");
      if (Array.isArray(result.ice_servers)) iceServers = result.ice_servers;
    } catch (_) {}
    await refresh();
    openSocket();
  }

  async function refresh() {
    if (!myUser) return;
    const {contacts} = await api("GET", "contacts");
    const container = $("contacts");
    container.replaceChildren();
    if (!contacts.length) {
      const p = document.createElement("p");
      p.className = "description";
      p.textContent = "No approved contacts. Generate or redeem an invitation to connect.";
      container.append(p);
      return;
    }
    for (const item of contacts) {
      const row = document.createElement("div"); row.className = "contact";
      const info = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = item.name + "  @" + item.handle;
      const sub = document.createElement("div"); sub.className = "sub";
      sub.textContent = item.blocked ? "Blocked" : item.online ? (item.status === "closed" ? "Closed" : item.status === "ask" ? "Ask first · online" : "Open · online") : "Offline";
      info.append(title, sub);
      const controls = document.createElement("div"); controls.className = "controls";
      const connect = document.createElement("button");
      connect.textContent = requestedContact === item.handle ? "Connect to @" + item.handle : "Connect";
      connect.disabled = item.blocked || !item.online || item.status === "closed" || !!session || !socket || socket.readyState !== WebSocket.OPEN;
      connect.addEventListener("click", () => call(item.handle));
      const block = document.createElement("button");
      block.textContent = item.blocked ? "Unblock" : "Block";
      block.addEventListener("click", async () => {
        try { await api("PUT", "block", {handle:item.handle, blocked:!item.blocked}); await refresh(); }
        catch (e) { msg(e.message); }
      });
      controls.append(connect, block); row.append(info, controls); container.append(row);
      if (requestedContact === item.handle) msg("Contact selected: @" + item.handle + ". Tap Connect to activate your microphone.");
    }
  }

  function openSocket() {
    if (!token) return;
    if (socket) socket.close();
    clearTimeout(reconnect);
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(scheme + "//" + location.host + root + "socket");
    socket = ws;
    ws.addEventListener("open", () => {
      ws.send(JSON.stringify({type:"auth", token}));
      heartbeat = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:"ping"})); }, 25000);
    });
    ws.addEventListener("message", async (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { return; }
      if (data.type === "ready") {
        $("connection").textContent = "Online";
        $("connection").classList.add("online");
        await refresh();
      } else if (data.type === "incoming") {
        if (session) return;
        session = {id:data.session_id, contact:data.from, role:"callee", accepted:data.status === "connected"};
        state(data.status === "connected" ? "Connected · microphone not active" : "Approval requested");
        txt("@" + data.from + " wants to speak. Tap Join to enable your microphone.");
        btn("join", true); btn("hangup", true); await refresh();
      } else if (data.type === "accepted") {
        if (session && session.id === data.session_id) {
          state("Connected · waiting for microphone");
          txt("Waiting for your contact to join.");
        }
      } else if (data.type === "signal") {
        try { await signalReceived(data); } catch (e) { msg("Audio negotiation failed: " + e.message); }
      } else if (data.type === "ended" && session && session.id === data.session_id) {
        cleanup("The other person disconnected.");
      }
    });
    ws.addEventListener("close", () => {
      clearInterval(heartbeat);
      $("connection").textContent = "Offline";
      $("connection").classList.remove("online");
      if (socket === ws && myUser) {
        if (session) cleanup("Connection was lost.");
        reconnect = setTimeout(openSocket, 3000);
      }
    });
  }

  function sendSignal(payload) {
    if (socket && socket.readyState === WebSocket.OPEN && session) {
      socket.send(JSON.stringify({type:"signal",session_id:session.id,payload}));
    }
  }

  async function mic() {
    if (!navigator.mediaDevices?.getUserMedia) throw Error("Microphone access requires HTTPS, or localhost.");
    if (!localStream) localStream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    return localStream;
  }

  async function createPeer() {
    if (peer) return peer;
    const audio = await mic();
    const pc = new RTCPeerConnection({iceServers});
    peer = pc;
    for (const track of audio.getAudioTracks()) pc.addTrack(track,audio);
    pc.addEventListener("icecandidate", (event) => { if (event.candidate) sendSignal({type:"candidate", candidate:event.candidate.toJSON()}); });
    pc.addEventListener("track", (event) => {
      const element = $("remote-audio");
      element.srcObject = event.streams[0] || new MediaStream([event.track]);
      element.play().catch(() => {btn("enable-audio", true); msg("Tap Enable speaker audio to hear your contact.");});
    });
    pc.addEventListener("connectionstatechange", () => {
      if (peer !== pc) return;
      if (pc.connectionState === "connected") { state("Live audio"); txt("Speaking with @" + session?.contact); }
      if (pc.connectionState === "failed") { state("Media connection failed"); msg("Try a TURN server or check network permissions."); }
    });
    return pc;
  }

  async function call(handle) {
    try {
      if (session) throw Error("Disconnect your current session first.");
      const result = await api("POST","sessions",{target:handle});
      session = {id:result.session_id, contact:handle, role:"caller", accepted:result.status === "connected"};
      state(result.status === "connected" ? "Connecting" : "Awaiting approval");
      txt("Connecting to @" + handle + ". The other person must activate their microphone.");
      btn("hangup",true);
      // The outbound user's explicit Connect click authorizes microphone use.
      await createPeer();
      await refresh();
    } catch (e) { msg(e.message); if(session) await hangup(); }
  }

  async function join() {
    if (!session || session.role !== "callee") return;
    try {
      const s = session;
      // Explicit user gesture is required on incoming browser audio.
      await createPeer();
      if (!s.accepted) await api("POST","sessions/"+encodeURIComponent(s.id)+"/accept");
      if (session !== s) return;
      s.accepted = true;
      btn("join",false);
      state("Connected · establishing audio");
      txt("Connecting with @" + s.contact);
      sendSignal({type:"ready"});
      await refresh();
    } catch (e) { msg(e.message); }
  }

  async function signalReceived(data) {
    if (!session || data.session_id !== session.id) return;
    const p = data.payload;
    if (!p || !["ready","offer","answer","candidate"].includes(p.type)) return;
    if (p.type === "ready" && session.role === "caller") {
      const pc = await createPeer();
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      sendSignal({type:"offer",sdp:pc.localDescription.sdp});
    } else if (p.type === "offer" && session.role === "callee") {
      const pc = await createPeer();
      await pc.setRemoteDescription({type:"offer",sdp:p.sdp});
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      sendSignal({type:"answer",sdp:pc.localDescription.sdp});
      while (pendingCandidates.length) await pc.addIceCandidate(pendingCandidates.shift());
    } else if (p.type === "answer" && session.role === "caller" && peer) {
      await peer.setRemoteDescription({type:"answer",sdp:p.sdp});
      while (pendingCandidates.length) await peer.addIceCandidate(pendingCandidates.shift());
    } else if (p.type === "candidate" && p.candidate) {
      if (peer?.remoteDescription) await peer.addIceCandidate(p.candidate);
      else pendingCandidates.push(p.candidate);
    }
  }
  let pendingCandidates = [];

  function cleanup(message) {
    if (peer) {peer.close(); peer=null;}
    if (localStream) {localStream.getTracks().forEach((track)=>track.stop());localStream=null;}
    $("remote-audio").srcObject=null;
    session=null; pendingCandidates=[];
    state("Idle"); txt(message || "Choose a contact to connect.");
    btn("join",false);btn("hangup",false);btn("enable-audio",false);
    refresh().catch(() => {});
  }

  async function hangup() {
    const id = session?.id;
    if (id) {
      if(socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"hangup",session_id:id}));
      // Deliberately no retry of an action if the signaling channel is offline.
    }
    cleanup("Disconnected.");
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
      const {user} = await api("PUT","presence",{status:$("status").value});
      myUser = user;
      $("status-help").textContent = user.status === "open" ? "Reachable by approved contacts while online. Microphone idle until a conversation." :
        user.status === "ask" ? "You'll receive an approval request." : "Unavailable for new connections.";
      if (user.status === "closed" && session) cleanup("Availability closed.");
      msg("Status updated."); await refresh();
    } catch(e) {msg(e.message);}
  });
  $("refresh").addEventListener("click", () => refresh().catch(e=>msg(e.message)));
  $("generate-invite").addEventListener("click", async () => {
    try {const result=await api("POST","invite");$("invite-code").textContent=result.code;msg("One-use invitation code. Expires in 15 minutes.");}
    catch(e){msg(e.message);}
  });
  $("accept-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {await api("POST","accept",{code:$("accept-code").value});$("accept-code").value="";await refresh();msg("Contact added.");}
    catch(e){msg(e.message);}
  });
  $("join").addEventListener("click", join);
  $("hangup").addEventListener("click", hangup);
  $("enable-audio").addEventListener("click", () => $("remote-audio").play().then(()=>btn("enable-audio",false)).catch(e=>msg(e.message)));
  $("logout").addEventListener("click", async () => {
    try {await api("POST","logout");} catch (_) {}
    if (socket) {socket.close();socket=null;}
    clearTimeout(reconnect);clearInterval(heartbeat);
    cleanup();localStorage.removeItem(localKey);token="";myUser=null;renderLogin();msg("Signed out.");
  });

  renderLogin();
  if (token) api("GET","me").then(async data => initSession(data)).catch(() => {
    localStorage.removeItem(localKey);token="";myUser=null;renderLogin();
  });
})();
