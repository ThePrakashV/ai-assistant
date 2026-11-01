import asyncio
import json
import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.api.privacy_routes import router as privacy_router
from app.core.config import settings
from app.runtime import ClientConnection, runtime
from app.security.access import throttle
from app.security.audit import audit_event

router = APIRouter()
router.include_router(privacy_router)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
AUTH_TIMEOUT = 5.0
NO_CACHE = {"Cache-Control": "no-cache"}


# ===================== Pages =====================
@router.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html", headers=NO_CACHE)


@router.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json", headers=NO_CACHE)


@router.get("/sw.js")
async def service_worker():
    # Root la irundhu serve pannanum (scope = "/"). /static/sw.js na scope /static/ mattum aagidum
    return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript", headers=NO_CACHE)


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "ready": runtime.ready,
        "assistant": settings.assistant_name,
        "clients": len(runtime.clients),
    }


# ===================== Security helpers =====================
def _origin_allowed(ws: WebSocket) -> bool:
    """Browser vera website la irundhu vandha (Origin != Host) block. Electron / scripts ku Origin illa, allow."""
    origin = ws.headers.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == ws.headers.get("host", "")


def _token_ok(token: str) -> bool:
    if not settings.api_token:
        return True
    return secrets.compare_digest(token.encode(), settings.api_token.encode())


# ===================== WebSocket =====================
@router.websocket("/ws/assistant")
async def assistant_ws(ws: WebSocket):
    await ws.accept()
    ip = ws.client.host if ws.client else "unknown"
    actor = f"web:{ip}"

    # 0. Rate limit: thappa token adikkadi vandha block
    wait = throttle.blocked_for(ip)
    if wait:
        await ws.send_json({"type": "error", "code": "rate_limited",
                            "message": f"Romba thappa token try pannitaa. {wait} sec apparam try pannu."})
        await ws.close(code=4429)
        return

    # 1. Origin check
    if not _origin_allowed(ws):
        audit_event("ws.origin_blocked", actor=actor, origin=ws.headers.get("origin", ""))
        await ws.close(code=4403)
        return

    # 2. Auth: modhal message {"type":"auth","token":"..."} (token URL la varaadhu, logs la theriyaadhu)
    try:
        first = await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT)
        auth = json.loads(first)
        if not isinstance(auth, dict) or auth.get("type") != "auth":
            raise ValueError("auth expected")
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, RuntimeError):
        try:
            await ws.close(code=4400)
        except RuntimeError:
            pass
        return

    if not _token_ok(str(auth.get("token", ""))):
        locked = throttle.fail(ip)
        audit_event("auth.lockout" if locked else "auth.fail", actor=actor, channel="ws")
        await ws.send_json({"type": "error", "code": "unauthorized", "message": "Token thappu."})
        await ws.close(code=4401)
        return

    throttle.ok(ip)
    client = ClientConnection(ws, actor)
    runtime.clients.add(client)
    audit_event("ws.connect", actor=actor)
    audio = bytearray()
    recording = False
    max_bytes = settings.max_audio_seconds * 16000 * 2

    try:
        await client.send_json(
            {
                "type": "ready",
                "assistant": settings.assistant_name,
                "memory_backend": runtime.agent.session.short.backend,
                "token_required": bool(settings.api_token),
            }
        )
        await runtime.flush_pending_alerts(client)

        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break

            # Binary = mic audio (16 kHz int16 PCM)
            if message.get("bytes") is not None:
                if recording and len(audio) < max_bytes:
                    audio.extend(message["bytes"][: max_bytes - len(audio)])
                continue

            raw = message.get("text")
            if raw is None:
                continue

            try:
                data = json.loads(raw)
                kind = data.get("type")
            except (ValueError, AttributeError):
                await client.send_json({"type": "error", "message": "Invalid message"})
                continue

            try:
                if kind == "text":
                    text = str(data.get("text", "")).strip()[:1000]
                    if text:
                        await runtime.handle_text(client, text)
                elif kind == "audio_start":
                    audio.clear()
                    recording = True
                elif kind == "audio_cancel":
                    audio.clear()
                    recording = False
                elif kind == "audio_end":
                    recording = False
                    pcm = bytes(audio)
                    audio.clear()
                    await runtime.handle_audio(client, pcm)
                elif kind == "settings":
                    client.voice_reply = bool(data.get("voice_reply", True))
                elif kind == "reset":
                    runtime.agent.session.reset()
                    audit_event("history.reset", actor=actor)
                    await client.send_json({"type": "reset_ok"})
                elif kind == "ping":
                    await client.send_json({"type": "pong"})
            except (WebSocketDisconnect, RuntimeError):
                raise
            except Exception as exc:  # oru request fail aanaalum connection nirkaadhu
                print(f"[Server] error: {type(exc).__name__}: {exc}")
                await client.send_json({"type": "error", "message": "Edho thappu aachu. Thirumba try pannu."})
                await client.send_json({"type": "status", "state": "idle"})

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        runtime.clients.discard(client)
        audit_event("ws.disconnect", actor=actor)