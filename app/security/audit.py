import hashlib
import hmac
import json
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.security.crypto import audit_key

GENESIS = "0" * 64


class AuditLog:
    """CCTV logbook. Ovvoru entry kum HMAC seal, munnaadi entry oda seal kooda serthu (chain)."""

    def __init__(self) -> None:
        self.path = Path(settings.audit_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._last = GENESIS
        self._ready = False
        self._warned = False

    # ---------- internals ----------
    def _read_tail(self) -> None:
        if self._ready:
            return
        if self.path.exists():
            for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
                try:
                    row = json.loads(line)
                    self._seq, self._last = row["seq"], row["mac"]
                    break
                except (ValueError, KeyError):
                    continue
        self._ready = True

    @staticmethod
    def _mac(entry: dict) -> str:
        body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(audit_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()

    # ---------- API ----------
    def log(self, event: str, actor: str = "system", detail: dict | None = None) -> None:
        """Audit failure assistant ah thadukkaadhu (oru dhadavai warning mattum)."""
        try:
            with self._lock:
                self._read_tail()
                entry = {
                    "seq": self._seq + 1,
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "event": event,
                    "actor": actor,
                    "detail": detail or {},
                    "prev": self._last,
                }
                mac = self._mac(entry)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({**entry, "mac": mac}, ensure_ascii=False) + "\n")
                self._seq, self._last = entry["seq"], mac
        except Exception as exc:
            if not self._warned:
                print(f"[Audit] log panna mudiyala: {type(exc).__name__}: {exc}")
                self._warned = True

    def _rows(self) -> list[str]:
        if not self.path.exists():
            return []
        return [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def count(self) -> int:
        return len(self._rows())

    def recent(self, limit: int = 30) -> list[dict]:
        rows = []
        for line in self._rows()[-limit:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                rows.append({"seq": None, "event": "UNREADABLE LINE", "actor": "?", "detail": {}, "ts": ""})
        return rows

    def verify(self) -> dict:
        """Chain + seal check. Maathina / remove panna entry ah kandupidikkum."""
        previous, count = GENESIS, 0
        for line_no, line in enumerate(self._rows(), start=1):
            try:
                row = json.loads(line)
                mac = row.pop("mac")
            except (ValueError, KeyError):
                return {"ok": False, "entries": count, "bad_line": line_no, "reason": "unreadable line"}
            if row.get("prev") != previous:
                return {"ok": False, "entries": count, "bad_line": line_no, "reason": "chain broken (entry remove / reorder)"}
            if not hmac.compare_digest(self._mac(row), mac):
                return {"ok": False, "entries": count, "bad_line": line_no, "reason": "entry modified (seal match aagala)"}
            previous, count = mac, count + 1
        return {"ok": True, "entries": count}


@lru_cache(maxsize=1)
def get_audit() -> AuditLog:
    return AuditLog()


def audit_event(event: str, actor: str = "system", **detail) -> None:
    """Short helper. audit_event('request', actor='web:127.0.0.1', status='done')"""
    clean = {key: (value[:200] if isinstance(value, str) else value) for key, value in detail.items()}
    get_audit().log(event, actor, clean)