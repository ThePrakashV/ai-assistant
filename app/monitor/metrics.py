import json
import time

import httpx
import plotly.graph_objects as go
import psutil

from app.core.config import settings
from app.orchestrator.models import StepRecord, TaskRecord
from app.orchestrator.store import TaskStore

psutil.cpu_percent(None)  # modhal call prime pannum. Apparam varra calls nijamaana CPU % kudukkum

STATUS_COLORS = {
    "done": "#2ecc71",
    "running": "#f1c40f",
    "failed": "#e74c3c",
    "pending": "#7f8c8d",
}
_BASE_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=30),
)

_health_cache: dict = {"at": 0.0, "ollama": {"ok": False, "models": []}}


# ===================== Numbers =====================
def system_stats() -> dict:
    ram = psutil.virtual_memory()
    return {
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / 1e9, 1),
        "ram_total_gb": round(ram.total / 1e9, 1),
        "cpu_percent": psutil.cpu_percent(None),
    }


def step_duration_ms(step: StepRecord, now: float) -> float:
    if step.started and step.ended:
        return (step.ended - step.started) * 1000
    if step.started:
        return (now - step.started) * 1000  # innum run aagitu irukku
    return 0.0


def task_duration_ms(task: TaskRecord, now: float) -> float:
    end = task.ended or now
    return (end - task.created) * 1000


def task_payload(task: TaskRecord, now: float) -> dict:
    data = task.model_dump()
    data["duration_ms"] = round(task_duration_ms(task, now))
    for raw, step in zip(data["steps"], task.steps):
        raw["duration_ms"] = round(step_duration_ms(step, now))
    return data


def summarize(tasks: list[TaskRecord], now: float) -> dict:
    done = sum(1 for t in tasks if t.status == "done")
    failed = sum(1 for t in tasks if t.status in ("partial", "failed"))
    running = sum(1 for t in tasks if t.status in ("planning", "running"))
    finished = [t for t in tasks if t.ended]
    completed = done + failed
    return {
        "total": len(tasks),
        "done": done,
        "failed": failed,
        "running": running,
        "success_rate": round(done / completed * 100) if completed else None,
        "avg_task_ms": round(sum(task_duration_ms(t, now) for t in finished) / len(finished)) if finished else None,
    }


async def service_health(store: TaskStore) -> dict:
    """Redis + Ollama status. Ollama check 5 sec ku oru dhadavai mattum (cache)."""
    now = time.time()
    if now - _health_cache["at"] > 5:
        ollama = {"ok": False, "models": []}
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(f"{settings.ollama_base_url}/api/ps")
                response.raise_for_status()
                models = [
                    {"name": m.get("name"), "size_gb": round(m.get("size", 0) / 1e9, 1)}
                    for m in response.json().get("models", [])
                ]
                ollama = {"ok": True, "models": models}
        except httpx.HTTPStatusError:
            ollama = {"ok": True, "models": []}  # server irukku, /api/ps support illa
        except Exception:
            pass
        _health_cache.update({"at": now, "ollama": ollama})

    return {"store": store.backend, "ollama": _health_cache["ollama"]}


# ===================== Plotly figures =====================
def _fig_json(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def _empty_figure(message: str, title: str, height: int) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color="#8b98a5"))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=title,
        height=height,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _timeline_figure(tasks: list[TaskRecord], now: float) -> go.Figure:
    recent = [t for t in tasks if t.steps][:6]  # puthu tasks modhalil
    if not recent:
        return _empty_figure("Innum tasks illa. test_orchestrator.py run pannu.", "Step timeline", 340)

    t0 = min((step.started or task.created) for task in recent for step in task.steps)
    groups: dict[str, dict[str, list]] = {
        status: {"y": [], "x": [], "base": [], "text": []} for status in STATUS_COLORS
    }

    for task in recent:
        for step in task.steps:
            start = step.started or task.created
            width = max(step_duration_ms(step, now) / 1000, 0.05)
            label = f"{task.id[:4]}.{step.index} {step.route or '...'}"
            group = groups[step.status]
            group["y"].append(label)
            group["x"].append(width)
            group["base"].append(start - t0)
            group["text"].append(f"{step.text}<br>{step.status} | {width:.2f}s")

    fig = go.Figure()
    for status, group in groups.items():
        if group["y"]:
            fig.add_trace(
                go.Bar(
                    name=status,
                    orientation="h",
                    y=group["y"],
                    x=group["x"],
                    base=group["base"],
                    marker_color=STATUS_COLORS[status],
                    hovertext=group["text"],
                    hoverinfo="text",
                )
            )
    fig.update_layout(
        **_BASE_LAYOUT,
        title="Step timeline (parallel steps onnaa overlap aagum)",
        height=340,
        barmode="overlay",
        xaxis_title="seconds",
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def _route_durations(tasks: list[TaskRecord]) -> dict[str, list[float]]:
    durations: dict[str, list[float]] = {}
    for task in tasks:
        for step in task.steps:
            if step.status in ("done", "failed") and step.started and step.ended:
                durations.setdefault(step.route or "unknown", []).append((step.ended - step.started) * 1000)
    return durations


def _latency_figure(durations: dict[str, list[float]]) -> go.Figure:
    if not durations:
        return _empty_figure("Data illa", "Average step time (ms)", 260)
    routes = list(durations)
    averages = [round(sum(values) / len(values)) for values in durations.values()]
    fig = go.Figure(go.Bar(x=routes, y=averages, marker_color="#3498db"))
    fig.update_layout(**_BASE_LAYOUT, title="Average step time (ms)", height=260)
    return fig


def _usage_figure(durations: dict[str, list[float]]) -> go.Figure:
    if not durations:
        return _empty_figure("Data illa", "Skill usage", 260)
    fig = go.Figure(
        go.Pie(labels=list(durations), values=[len(v) for v in durations.values()], hole=0.5)
    )
    fig.update_layout(**_BASE_LAYOUT, title="Skill usage", height=260)
    return fig


def _gauge_figure(title: str, value: float) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": "%"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#3498db"},
                "steps": [
                    {"range": [0, 60], "color": "#1e3a2f"},
                    {"range": [60, 85], "color": "#4a3d12"},
                    {"range": [85, 100], "color": "#4a1f1f"},
                ],
            },
        )
    )
    fig.update_layout(**_BASE_LAYOUT, title=title, height=260)
    return fig


def build_figures(tasks: list[TaskRecord], stats: dict, now: float) -> dict:
    durations = _route_durations(tasks)
    return {
        "timeline": _fig_json(_timeline_figure(tasks, now)),
        "latency": _fig_json(_latency_figure(durations)),
        "usage": _fig_json(_usage_figure(durations)),
        "ram": _fig_json(_gauge_figure("RAM", stats["ram_percent"])),
        "cpu": _fig_json(_gauge_figure("CPU", stats["cpu_percent"])),
    }