(() => {
  "use strict";

  const TARGET_RATE = 16000;     // Whisper ku 16 kHz thevai
  const SPEECH_RMS = 0.015;      // idhukku mela sathham irundha "pesuraan"
  const SILENCE_MS = 1200;       // pesi mudinju 1.2 sec silence na auto stop
  const NO_SPEECH_MS = 7000;     // 7 sec pesaama irundha cancel
  const MAX_RECORD_MS = 30000;

  const $ = (id) => document.getElementById(id);
  const el = {
    chat: $("chat"), form: $("form"), text: $("text"), send: $("send"), mic: $("mic"),
    meter: $("meter-fill"), voice: $("voice"), reset: $("reset"), status: $("status"),
    title: $("title"), install: $("install"), settingsBtn: $("settings-btn"),
    dialog: $("dialog"), token: $("token"), saveToken: $("save-token"), cancelToken: $("cancel-token"),
  };

  const state = {
    ws: null, connected: false, busy: false, recording: false,
    retry: 0, assistant: "Nova", rec: null, audio: null, installEvent: null,
  };

  // ---------- UI helpers (innerHTML use pannala, textContent mattum: LLM text la HTML irundhaalum safe) ----------
  function setStatus(text, kind) {
    el.status.textContent = text;
    el.status.className = "pill " + (kind || "");
  }

  function updateControls() {
    el.text.disabled = !state.connected;
    el.send.disabled = !state.connected || state.busy;
    el.mic.disabled = !state.connected || (state.busy && !state.recording);
    el.reset.disabled = !state.connected;
  }

  function addMessage(role, text, meta) {
    const box = document.createElement("div");
    box.className = "msg " + role;
    box.appendChild(document.createTextNode(text));
    if (meta) {
      const small = document.createElement("span");
      small.className = "meta";
      small.textContent = meta;
      box.appendChild(small);
    }
    el.chat.appendChild(box);
    el.chat.scrollTop = el.chat.scrollHeight;
    return box;
  }

  function addSteps(box, steps) {
    if (!steps || steps.length < 2) return;
    const chips = document.createElement("div");
    chips.className = "chips";
    for (const step of steps) {
      const chip = document.createElement("span");
      chip.className = "chip " + step.status;
      chip.textContent = `${step.index}. ${step.route || "?"}`;
      chips.appendChild(chip);
    }
    box.appendChild(chips);
  }

  function send(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(obj));
  }

  // ---------- Notifications ----------
  function ensureNotifications() {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }

  function notify(text) {
    if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
    const options = { body: text, icon: "/static/icons/icon-192.png", tag: "nova-alert" };
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then((reg) => reg.showNotification(state.assistant, options));
    } else {
      new Notification(state.assistant, options);
    }
  }

  // ---------- Audio playback (server la irundhu WAV varum) ----------
  function playAudio(buffer) {
    const url = URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
    if (state.audio) state.audio.pause();
    const audio = new Audio(url);
    state.audio = audio;
    audio.onended = audio.onerror = () => URL.revokeObjectURL(url);
    audio.play().catch(() => addMessage("system", "Audio play aagala. Page la oru dhadavai click pannittu thirumba try pannu."));
  }

  // ---------- WebSocket ----------
  function connect() {
    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    const ws = new WebSocket(scheme + location.host + "/ws/assistant");
    ws.binaryType = "arraybuffer";
    state.ws = ws;
    setStatus("connecting...", "warn");

    ws.onopen = () => {
      if (state.ws !== ws) return;
      ws.send(JSON.stringify({ type: "auth", token: localStorage.getItem("nova.token") || "" }));
    };

    ws.onmessage = (event) => {
      if (state.ws !== ws) return;
      if (typeof event.data === "string") {
        try { handleJson(JSON.parse(event.data)); } catch (error) { console.error(error); }
      } else {
        playAudio(event.data);
      }
    };

    ws.onclose = (event) => {
      if (state.ws !== ws) return;   // manual reconnect panna pazhaya socket close ah ignore
      state.connected = false;
      state.busy = false;
      if (state.recording) stopRecording(false);
      updateControls();

      if (event.code === 4401) {
        setStatus("token thappu", "bad");
        if (!el.dialog.open) el.dialog.showModal();
        return;
      }
      if (event.code === 4403) {
        setStatus("origin allowed illa", "bad");
        return;
      }
      state.retry = Math.min(state.retry + 1, 6);
      setStatus("disconnected, retry...", "bad");
      setTimeout(() => { if (state.ws === ws) connect(); }, 1000 * state.retry);
    };
  }

  function reconnectNow() {
    const old = state.ws;
    state.ws = null;
    if (old) old.close();
    state.retry = 0;
    connect();
  }

  function handleJson(msg) {
    switch (msg.type) {
      case "ready":
        state.connected = true;
        state.retry = 0;
        state.assistant = msg.assistant || "Nova";
        el.title.textContent = state.assistant;
        document.title = state.assistant;
        setStatus("connected", "ok");
        send({ type: "settings", voice_reply: el.voice.checked });
        updateControls();
        break;
      case "status": {
        const labels = { transcribing: "kekkudhu...", thinking: "yosikkudhu...", speaking: "pesudhu...", idle: "connected" };
        state.busy = msg.state !== "idle";
        setStatus(labels[msg.state] || msg.state, msg.state === "idle" ? "ok" : "warn");
        updateControls();
        break;
      }
      case "transcript":
        if (msg.text) addMessage("user", msg.text, "voice");
        else addMessage("system", "(edhuvum kekkala, thirumba try pannu)");
        break;
      case "reply": {
        const routes = [...new Set((msg.steps || []).map((s) => s.route).filter(Boolean))].join(", ");
        const box = addMessage("nova", msg.text, `${routes || "chat"} | ${(msg.ms / 1000).toFixed(1)}s`);
        addSteps(box, msg.steps);
        break;
      }
      case "alert":
        addMessage("alert", msg.text, msg.late ? "(nee illaadha neram)" : "");
        notify(msg.text);
        break;
      case "reset_ok":
        el.chat.replaceChildren();
        addMessage("system", "Memory (idha chat oda) clear aachu.");
        break;
      case "error":
        addMessage("system", msg.message || "Error");
        state.busy = false;
        updateControls();
        break;
      default:
        break;
    }
  }

  // ---------- Text input ----------
  el.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = el.text.value.trim();
    if (!text || state.busy || !state.connected) return;
    ensureNotifications();
    addMessage("user", text);
    el.text.value = "";
    state.busy = true;
    updateControls();
    send({ type: "text", text });
  });

  el.reset.addEventListener("click", () => send({ type: "reset" }));
  el.voice.addEventListener("change", () => send({ type: "settings", voice_reply: el.voice.checked }));

  // ---------- Mic ----------
  function downsample(rec, input) {
    const ratio = rec.ctx.sampleRate / TARGET_RATE;
    const merged = new Float32Array(rec.pending.length + input.length);
    merged.set(rec.pending, 0);
    merged.set(input, rec.pending.length);

    const outLength = Math.floor(merged.length / ratio);
    const out = new Int16Array(outLength);
    for (let i = 0; i < outLength; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), merged.length);
      let sum = 0;
      for (let j = start; j < end; j++) sum += merged[j];
      const value = sum / Math.max(end - start, 1);
      out[i] = Math.max(-1, Math.min(1, value)) * 32767;
    }
    rec.pending = merged.slice(Math.floor(outLength * ratio));
    return out;
  }

  function handleChunk(rec, samples) {
    if (!state.recording || state.rec !== rec) return;
    const now = performance.now();

    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    const rms = Math.sqrt(sum / samples.length);
    el.meter.style.width = Math.min(100, rms * 600) + "%";

    if (rms > SPEECH_RMS) {
      rec.heardSpeech = true;
      rec.lastVoiceAt = now;
    }

    const pcm = downsample(rec, samples);
    if (pcm.length && state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(pcm.buffer);

    if (rec.heardSpeech && now - rec.lastVoiceAt > SILENCE_MS) stopRecording(true);
    else if (!rec.heardSpeech && now - rec.startedAt > NO_SPEECH_MS) stopRecording(false);
    else if (now - rec.startedAt > MAX_RECORD_MS) stopRecording(true);
  }

  async function startRecording() {
    if (!state.connected || state.busy || state.recording) return;
    if (!navigator.mediaDevices || !window.isSecureContext) {
      addMessage("system", "Mic ku HTTPS illa localhost venum. (Phone la http://IP:8010 la mic work aagaadhu.)");
      return;
    }
    ensureNotifications();
    if (state.audio) state.audio.pause();   // Nova pesittu irundha, adhu mic la pidikka koodaadhu

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const ctx = new AudioContext();
      if (ctx.state === "suspended") await ctx.resume();
      await ctx.audioWorklet.addModule("/static/pcm-worklet.js");

      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "pcm-capture");
      const mute = ctx.createGain();           // worklet process aaga destination ku connect pannanum, aana sathham varaama mute
      mute.gain.value = 0;
      source.connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);

      const rec = {
        stream, ctx, source, node, mute, pending: new Float32Array(0),
        startedAt: performance.now(), lastVoiceAt: 0, heardSpeech: false,
      };
      state.rec = rec;
      state.recording = true;
      node.port.onmessage = (event) => handleChunk(rec, event.data);

      send({ type: "audio_start" });
      el.mic.classList.add("recording");
      setStatus("kekkudhu... pesu", "warn");
      updateControls();
    } catch (error) {
      addMessage("system", "Mic open aagala: " + error.message);
    }
  }

  function stopRecording(sendIt) {
    const rec = state.rec;
    if (!rec) return;
    state.rec = null;
    state.recording = false;
    rec.node.port.onmessage = null;
    try {
      rec.source.disconnect();
      rec.node.disconnect();
      rec.mute.disconnect();
    } catch (error) { /* already disconnected */ }
    rec.stream.getTracks().forEach((track) => track.stop());
    rec.ctx.close();

    el.meter.style.width = "0%";
    el.mic.classList.remove("recording");
    send({ type: sendIt ? "audio_end" : "audio_cancel" });
    if (sendIt) state.busy = true;
    else setStatus("connected", "ok");
    updateControls();
  }

  function toggleMic() {
    if (state.recording) stopRecording(true);
    else startRecording();
  }

  el.mic.addEventListener("click", toggleMic);

  // Space = mic toggle (input / button focus la illa na mattum)
  document.addEventListener("keydown", (event) => {
    if (event.code === "Space" && document.activeElement === document.body && !el.dialog.open) {
      event.preventDefault();
      toggleMic();
    }
  });

  // ---------- Settings (token) ----------
  el.settingsBtn.addEventListener("click", () => {
    el.token.value = localStorage.getItem("nova.token") || "";
    el.dialog.showModal();
  });
  el.cancelToken.addEventListener("click", () => el.dialog.close());
  el.saveToken.addEventListener("click", () => {
    localStorage.setItem("nova.token", el.token.value.trim());
    el.dialog.close();
    reconnectNow();
  });

  // ---------- PWA install + service worker ----------
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installEvent = event;
    el.install.hidden = false;
  });
  el.install.addEventListener("click", async () => {
    if (!state.installEvent) return;
    state.installEvent.prompt();
    await state.installEvent.userChoice;
    state.installEvent = null;
    el.install.hidden = true;
  });
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  // Electron / vera shells ku (global shortcut)
  window.nova = { toggleMic };

  updateControls();
  connect();
})();