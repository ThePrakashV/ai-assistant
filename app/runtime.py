import asyncio
import time

import numpy as np
from fastapi import WebSocket

from app.agent.graph import NovaAgent
from app.core.config import settings
from app.memory.long_term import get_long_term
from app.orchestrator.orchestrator import TaskOrchestrator
from app.security.audit import audit_event
from app.security.speaker import get_gate
from app.skills.context import SkillContext
from app.skills.scheduler import Scheduler
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech

SAMPLE_RATE = 16000
MIN_AUDIO_SECONDS = 0.3
MAX_PENDING_ALERTS = 20


class ClientConnection:
    """Oru browser / phone connection. Send panrathu lock kulla (rendu per ore neram la ezhudhaadhu)."""

    def __init__(self, ws: WebSocket, actor: str = "web") -> None:
        self.ws = ws
        self.actor = actor            # audit log la "yaaru" nu kaattum (web:<ip>)
        self.voice_reply = True
        self._lock = asyncio.Lock()

    async def send_json(self, data: dict) -> None:
        async with self._lock:
            await self.ws.send_json(data)

    async def send_audio(self, wav: bytes) -> None:
        # Header + audio bytes rendum onnaa pogum (naduvula vera message vara koodaadhu)
        async with self._lock:
            await self.ws.send_json({"type": "audio", "format": "wav"})
            await self.ws.send_bytes(wav)


class AssistantRuntime:
    """Kitchen. Models + agent + scheduler oru dhadavai load aagum, ellaa clients share pannum."""

    def __init__(self) -> None:
        self.ready = False
        self.clients: set[ClientConnection] = set()
        self.pending_alerts: list[str] = []   # yaarum connect aagala na alerts inga irukkum
        self.stt: SpeechToText | None = None
        self.tts: TextToSpeech | None = None
        self.scheduler: Scheduler | None = None
        self.agent: NovaAgent | None = None
        self.orchestrator: TaskOrchestrator | None = None
        self.request_lock: asyncio.Lock | None = None

    # ---------- Startup / shutdown ----------
    async def start(self) -> None:
        print("[Server] Models load aagudhu (30-90 sec edukkum)...")
        self.stt = await asyncio.to_thread(SpeechToText)
        self.tts = await asyncio.to_thread(TextToSpeech)
        await asyncio.to_thread(get_long_term)

        self.scheduler = Scheduler()
        ctx = SkillContext(tts=self.tts, scheduler=self.scheduler)
        self.agent = await asyncio.to_thread(NovaAgent, "web", ctx)
        self.orchestrator = await asyncio.to_thread(TaskOrchestrator, self.agent)

        self.request_lock = asyncio.Lock()
        self.scheduler.start(self.broadcast_alert)
        self.ready = True
        audit_event(
            "server.start",
            encrypt_at_rest=settings.encrypt_at_rest,
            offline_mode=settings.offline_mode,
            token_required=bool(settings.api_token),
            speaker_mode=settings.speaker_mode,
        )
        print(f"[Server] {settings.assistant_name} ready. (speaker_mode={settings.speaker_mode})")

    async def stop(self) -> None:
        audit_event("server.stop")
        if self.scheduler and self.scheduler._task:
            self.scheduler._task.cancel()

    # ---------- Requests ----------
    async def handle_text(self, client: ClientConnection, text: str, source: str = "web") -> None:
        async with self.request_lock:
            await self._process(client, text, source)

    async def handle_audio(self, client: ClientConnection, pcm: bytes) -> None:
        """16 kHz int16 mono PCM -> (voice verify) -> text -> agent."""
        samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) < SAMPLE_RATE * MIN_AUDIO_SECONDS:
            await client.send_json({"type": "transcript", "text": ""})
            await client.send_json({"type": "status", "state": "idle"})
            return

        async with self.request_lock:
            # Voice biometrics: Whisper ku munnaadi. Un kural illa na transcribe kooda pannaadhu
            if settings.speaker_mode == "enforce":
                await client.send_json({"type": "status", "state": "verifying"})
                verdict = await asyncio.to_thread(get_gate().check, samples, "web")
                if not verdict.allowed:
                    await client.send_json({"type": "error", "message": verdict.message})
                    await client.send_json({"type": "status", "state": "idle"})
                    return

            await client.send_json({"type": "status", "state": "transcribing"})
            result = await asyncio.to_thread(self.stt.transcribe, samples)
            text = result["text"]
            await client.send_json({"type": "transcript", "text": text})
            if not text:
                await client.send_json({"type": "status", "state": "idle"})
                return
            await self._process(client, text, "web-voice")

    async def _process(self, client: ClientConnection, text: str, source: str) -> None:
        """request_lock hold panna nilamai la mattum call pannanum."""
        await client.send_json({"type": "status", "state": "thinking"})
        started = time.perf_counter()
        task = await self.orchestrator.handle(text, source=source)
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        # Audit: metadata mattum (route, status, ms). User text AUDIT_LOG_TEXT=true na mattum
        detail = {
            "source": source,
            "task_id": task.id,
            "status": task.status,
            "routes": ",".join(step.route or "?" for step in task.steps),
            "steps": len(task.steps),
            "ms": elapsed_ms,
            "text_len": len(text),
        }
        if settings.audit_log_text:
            detail["text"] = text
        audit_event("request", actor=client.actor, **detail)

        reply = task.reply or "Sorry, I have nothing to say."
        await client.send_json(
            {
                "type": "reply",
                "text": reply,
                "task_id": task.id,
                "status": task.status,
                "ms": elapsed_ms,
                "steps": [
                    {"index": s.index, "text": s.text, "route": s.route, "status": s.status}
                    for s in task.steps
                ],
            }
        )

        # Text modhalil, kural apparam (text varra varaikkum wait pannaadha)
        if client.voice_reply:
            await client.send_json({"type": "status", "state": "speaking"})
            wav = await asyncio.to_thread(self.tts.synthesize_wav, reply)
            if wav:
                await client.send_audio(wav)
        await client.send_json({"type": "status", "state": "idle"})

    # ---------- Timer / reminder alerts ----------
    async def broadcast_alert(self, message: str) -> None:
        print(f"[ALERT] {message}")
        if not self.clients:
            self.pending_alerts = (self.pending_alerts + [message])[-MAX_PENDING_ALERTS:]
            return

        wav = await asyncio.to_thread(self.tts.synthesize_wav, message)
        for client in list(self.clients):
            try:
                await client.send_json({"type": "alert", "text": message})
                if wav and client.voice_reply:
                    await client.send_audio(wav)
            except Exception:
                self.clients.discard(client)

    async def flush_pending_alerts(self, client: ClientConnection) -> None:
        pending, self.pending_alerts = self.pending_alerts, []
        for message in pending:
            await client.send_json({"type": "alert", "text": message, "late": True})


runtime = AssistantRuntime()