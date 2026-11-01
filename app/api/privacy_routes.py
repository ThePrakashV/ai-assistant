import asyncio
import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.runtime import runtime
from app.security import privacy
from app.security.access import throttle
from app.security.audit import audit_event, get_audit

router = APIRouter()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
LOCAL_HOSTS = {"127.0.0.1", "::1"}


def require_access(request: Request) -> str:
    """Privacy / audit API ku vaasal. Origin + custom header + token + rate limit."""
    ip = request.client.host if request.client else "unknown"
    actor = f"web:{ip}"

    wait = throttle.blocked_for(ip)
    if wait:
        raise HTTPException(429, f"Romba thappa try pannitaa. {wait} sec apparam.")

    # Vera website la irundhu vandha browser request ah block (CSRF). Browser Origin header anuppum
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host", ""):
        audit_event("api.origin_blocked", actor=actor, path=request.url.path)
        raise HTTPException(403, "Origin allowed illa")

    # Custom header: vera site la irundhu indha header add panna browser CORS preflight kekkum (namma allow pannala)
    if request.headers.get("x-nova-request") != "1":
        raise HTTPException(403, "X-Nova-Request header venum")

    if settings.api_token:
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not secrets.compare_digest(supplied.encode(), settings.api_token.encode()):
            locked = throttle.fail(ip)
            audit_event("auth.lockout" if locked else "auth.fail", actor=actor, channel="api")
            raise HTTPException(401, "Token thappu")
        throttle.ok(ip)
    elif ip not in LOCAL_HOSTS:
        raise HTTPException(403, "API_TOKEN illaama idhu localhost la mattum work aagum")

    return actor


def _require_ready() -> None:
    if not runtime.ready:
        raise HTTPException(503, "Server innum ready aagala")


class DeleteRequest(BaseModel):
    scopes: list[str]
    confirm: str


class OfflineRequest(BaseModel):
    enabled: bool


@router.get("/privacy")
async def privacy_page():
    # Page shell mattum. Data ellam token venum API la irundhu varum
    return FileResponse(WEB_DIR / "privacy.html", headers={"Cache-Control": "no-cache"})


@router.get("/api/privacy/inventory")
async def inventory(actor: str = Depends(require_access)):
    _require_ready()
    return await asyncio.to_thread(privacy.inventory, runtime)


@router.get("/api/privacy/export")
async def export(actor: str = Depends(require_access)):
    _require_ready()
    data = await asyncio.to_thread(privacy.export_data, runtime)
    audit_event("data.export", actor=actor)
    return data


@router.post("/api/privacy/delete")
async def delete(body: DeleteRequest, actor: str = Depends(require_access)):
    _require_ready()
    if body.confirm != "DELETE":
        raise HTTPException(400, "Confirm la DELETE nu type pannanum")
    counts = await asyncio.to_thread(privacy.delete_data, runtime, body.scopes, actor)
    return {"deleted": counts}


@router.post("/api/privacy/offline")
async def set_offline(body: OfflineRequest, actor: str = Depends(require_access)):
    settings.offline_mode = body.enabled   # server restart varaikkum (permanent venum na .env la OFFLINE_MODE)
    audit_event("settings.change", actor=actor, offline_mode=body.enabled)
    return {"offline_mode": settings.offline_mode}


@router.get("/api/security/audit")
async def audit_recent(limit: int = Query(30, ge=1, le=200), actor: str = Depends(require_access)):
    return {"entries": await asyncio.to_thread(get_audit().recent, limit)}


@router.get("/api/security/audit/verify")
async def audit_verify(actor: str = Depends(require_access)):
    return await asyncio.to_thread(get_audit().verify)