from pathlib import Path

from app.core.config import settings
from app.memory.long_term import get_long_term
from app.memory.short_term import ShortTermMemory
from app.security import crypto, speaker
from app.security.access import disabled_skills
from app.security.audit import audit_event, get_audit

SCOPES = ("facts", "documents", "history", "tasks", "scheduler", "voiceprint")
HISTORY_LIMIT = 40
SESSIONS = ("web", "voice")   # chat history Redis la irukkura sessions


def _files_state(*names: str) -> str:
    states = [crypto.file_state(Path(settings.memory_dir) / name) for name in names]
    existing = [state for state in states if state != "missing"]
    if not existing:
        return "empty"
    return "plaintext" if "plaintext" in existing else "encrypted"


def _voiceprint_row() -> dict:
    path = Path(settings.speaker_profile)
    state = crypto.file_state(path)
    try:
        info = speaker.profile_info()
    except Exception:
        info = None
        state = "unreadable (key?)"
    return {
        "id": "voiceprint",
        "label": "Voiceprint (un kural biometric)",
        "count": info["samples"] if info else 0,
        "where": settings.speaker_profile,
        "protection": "empty" if state == "missing" else state,
    }


def inventory(runtime) -> dict:
    memory = get_long_term()
    history = sum(len(ShortTermMemory(session).get(HISTORY_LIMIT)) for session in SESSIONS)
    scheduler_items = runtime.scheduler.pending() if runtime.scheduler else []
    tasks = runtime.orchestrator.store.recent(settings.tasks_keep)
    scheduler_state = crypto.file_state(Path(settings.scheduler_file))

    return {
        "stored": [
            {"id": "facts", "label": "Long-term facts", "count": memory.facts.count,
             "where": "data/memory/facts.*", "protection": _files_state("facts.faiss", "facts.json")},
            {"id": "documents", "label": "Document chunks (RAG)", "count": memory.docs.count,
             "where": "data/memory/docs.*", "protection": _files_state("docs.faiss", "docs.json")},
            {"id": "history", "label": "Chat history", "count": history,
             "where": f"Redis ({settings.redis_ttl_seconds // 3600}h)", "protection": "plain (Redis)"},
            {"id": "tasks", "label": "Task records (dashboard)", "count": len(tasks),
             "where": f"Redis ({settings.task_ttl_seconds // 86400}d)", "protection": "plain (Redis)"},
            {"id": "scheduler", "label": "Timers / reminders / alarms", "count": len(scheduler_items),
             "where": settings.scheduler_file, "protection": "empty" if scheduler_state == "missing" else scheduler_state},
            _voiceprint_row(),
        ],
        "audit": {"entries": get_audit().count(), "file": settings.audit_file, "logs_text": settings.audit_log_text},
        "security": {
            "encrypt_at_rest": settings.encrypt_at_rest,
            "key": crypto.key_status(),
            "token_required": bool(settings.api_token),
            "offline_mode": settings.offline_mode,
            "disabled_skills": sorted(disabled_skills()),
            "mlflow_logs_text": settings.mlflow_enabled and settings.mlflow_log_text,
            "speaker_mode": settings.speaker_mode,
        },
    }


def export_data(runtime) -> dict:
    """Nova un pathi vechirukkura ellaa data (audit log + raw voiceprint thavira) JSON ah."""
    memory = get_long_term()
    sources: dict[str, int] = {}
    for record in memory.docs.records:
        name = record.get("source", "?")
        sources[name] = sources.get(name, 0) + 1

    try:
        voiceprint = speaker.profile_info()
    except Exception:
        voiceprint = None

    return {
        "facts": [
            {"text": r["text"], "source": r.get("source"), "created": r.get("created")}
            for r in memory.facts.records
        ],
        "documents": [{"file": name, "chunks": count} for name, count in sources.items()],
        "chat_history": {
            session: ShortTermMemory(session).get(HISTORY_LIMIT) for session in SESSIONS
        },
        "scheduler": [
            {"kind": i.kind, "label": i.label, "fire_at": i.fire_at}
            for i in (runtime.scheduler.pending() if runtime.scheduler else [])
        ],
        "tasks": [
            {"id": t.id, "text": t.text, "reply": t.reply, "status": t.status, "created": t.created}
            for t in runtime.orchestrator.store.recent(settings.tasks_keep)
        ],
        # Raw embedding export pannala (biometric). Metadata mattum
        "voiceprint": {"enrolled": voiceprint is not None, **(voiceprint or {})},
    }


def delete_data(runtime, scopes: list[str], actor: str) -> dict[str, int]:
    wanted = set(SCOPES) if "all" in scopes else {scope for scope in scopes if scope in SCOPES}
    counts: dict[str, int] = {}
    memory = get_long_term()

    if "facts" in wanted:
        counts["facts"] = memory.facts.count
        memory.facts.clear()
    if "documents" in wanted:
        counts["documents"] = memory.docs.count
        memory.docs.clear()
    if "history" in wanted:
        counts["history"] = sum(len(ShortTermMemory(s).get(HISTORY_LIMIT)) for s in SESSIONS)
        runtime.agent.session.reset()
        for session in SESSIONS:
            ShortTermMemory(session).clear()
    if "tasks" in wanted:
        counts["tasks"] = len(runtime.orchestrator.store.recent(settings.tasks_keep))
        runtime.orchestrator.store.clear()
    if "scheduler" in wanted and runtime.scheduler:
        counts["scheduler"] = len(runtime.scheduler.pending())
        for kind in ("timer", "reminder", "alarm"):
            runtime.scheduler.cancel_all(kind)
    if "voiceprint" in wanted:
        counts["voiceprint"] = 1 if speaker.delete_profile() else 0

    audit_event("data.delete", actor=actor, scopes=",".join(sorted(wanted)), counts=str(counts))
    return counts