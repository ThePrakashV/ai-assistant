import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from plotly.offline import get_plotlyjs

from app.monitor.metrics import (
    build_figures,
    service_health,
    summarize,
    system_stats,
    task_payload,
)
from app.orchestrator.store import TaskStore

router = APIRouter()

# Dashboard server read-only. Redis la irundhu voice / text scripts la run aana tasks ah paakkum.
_store = TaskStore()
_DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "monitor" / "dashboard.html"
_plotly_js: str | None = None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return _DASHBOARD_FILE.read_text(encoding="utf-8")


@router.get("/dashboard/plotly.js")
async def plotly_js():
    """Plotly.js pip package la irundhu thaane serve pannurom (CDN / internet thevai illa)."""
    global _plotly_js
    if _plotly_js is None:
        _plotly_js = get_plotlyjs()
    return Response(
        _plotly_js,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/monitor")
async def monitor():
    now = time.time()
    tasks = _store.recent(60)
    stats = system_stats()
    return {
        "now": now,
        "summary": summarize(tasks, now),
        "tasks": [task_payload(task, now) for task in tasks[:15]],
        "figures": build_figures(tasks, stats, now),
        "stats": stats,
        "health": await service_health(_store),
    }


@router.get("/api/tasks")
async def list_tasks(limit: int = 20):
    now = time.time()
    return [task_payload(task, now) for task in _store.recent(min(limit, 100))]


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = _store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_payload(task, time.time())


@router.post("/api/tasks/clear")
async def clear_tasks():
    _store.clear()
    return {"cleared": True}