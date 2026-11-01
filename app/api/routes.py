import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.schemas import ClientMessage
from app.core.config import settings
from app.core.llm import ChatSession

router = APIRouter()


@router.get("/health")
async def health():
    """Server run aagudha nu check panna."""
    return {
        "status": "ok",
        "assistant": settings.assistant_name,
        "model": settings.ollama_model,
    }


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    session = ChatSession()
    await ws.send_json({"type": "ready", "assistant": settings.assistant_name})

    try:
        while True:
            raw = await ws.receive_text()

            # 1. Message format check
            try:
                msg = ClientMessage.model_validate_json(raw)
            except ValidationError:
                await ws.send_json(
                    {"type": "error", "message": "Invalid message format"}
                )
                continue

            # 2. Reset command
            if msg.type == "reset":
                session.reset()
                await ws.send_json({"type": "reset_ok"})
                continue

            # 3. Empty text check
            if not msg.text.strip():
                await ws.send_json({"type": "error", "message": "Empty message"})
                continue

            # 4. LLM reply stream
            start = time.time()
            try:
                async for token in session.stream_reply(msg.text):
                    await ws.send_json({"type": "token", "text": token})
                await ws.send_json(
                    {"type": "done", "seconds": round(time.time() - start, 2)}
                )
            except Exception as exc:
                await ws.send_json({"type": "error", "message": f"LLM error: {exc}"})

    except WebSocketDisconnect:
        print("Client disconnected")