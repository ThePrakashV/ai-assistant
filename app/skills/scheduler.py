import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable

from app.core.config import settings
from app.security.crypto import read_secure, write_secure


@dataclass
class ScheduledItem:
    id: str
    kind: str        # "timer" | "reminder" | "alarm"
    label: str
    fire_at: float   # unix time (seconds)


def _message(item: ScheduledItem, missed: bool = False) -> str:
    """Time aanadhum Nova enna solla vendiyadhu."""
    if item.kind == "timer":
        return f"Your {item.label} timer is done." if item.label else "Your timer is done."
    if item.kind == "alarm":
        return "You missed your alarm." if missed else "Your alarm is ringing."
    text = item.label.strip(" .")
    text = text[:1].upper() + text[1:]
    return f"You missed a reminder. {text}." if missed else f"Reminder. {text}."


class Scheduler:
    """Alarm clock + diary. Items JSON file la save aagum (encrypted), so restart panninaalum irukkum."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or settings.scheduler_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.items: list[ScheduledItem] = []
        self._notify: Callable[[str], Awaitable[None]] | None = None
        self._task: asyncio.Task | None = None
        self._load()

    # ---------- Storage ----------
    def _load(self) -> None:
        try:
            raw = read_secure(self.path)   # KeyUnavailableError varalam, adhai mazhaikka koodaadhu
            if raw is None:
                return
            rows = json.loads(raw.decode("utf-8"))
            self.items = [ScheduledItem(**row) for row in rows]
        except (json.JSONDecodeError, TypeError, OSError):
            self.items = []

    def _save(self) -> None:
        rows = [asdict(item) for item in self.items]
        write_secure(self.path, json.dumps(rows, indent=2).encode("utf-8"))

    # ---------- API ----------
    def add(self, kind: str, label: str, fire_at: float) -> ScheduledItem:
        item = ScheduledItem(id=uuid.uuid4().hex[:8], kind=kind, label=label, fire_at=fire_at)
        self.items.append(item)
        self._save()
        return item

    def cancel_all(self, kind: str) -> int:
        remaining = [item for item in self.items if item.kind != kind]
        removed = len(self.items) - len(remaining)
        self.items = remaining
        self._save()
        return removed

    def pending(self, kind: str | None = None) -> list[ScheduledItem]:
        items = [i for i in self.items if kind is None or i.kind == kind]
        return sorted(items, key=lambda item: item.fire_at)

    # ---------- Background loop ----------
    def start(self, notify: Callable[[str], Awaitable[None]]) -> None:
        """Running event loop kulla irundhu call pannanum."""
        self._notify = notify
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        # Assistant off la irundha neram time aanadhu: timer na drop, reminder / alarm na "missed" nu solrom
        now = time.time()
        overdue = [item for item in self.items if item.fire_at <= now]
        for item in overdue:
            self.items.remove(item)
        self._save()
        for item in overdue:
            if item.kind != "timer":
                await self._fire(item, missed=True)

        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            due = [item for item in self.items if item.fire_at <= now]
            for item in due:
                self.items.remove(item)
                self._save()
                await self._fire(item)

    async def _fire(self, item: ScheduledItem, missed: bool = False) -> None:
        try:
            if self._notify:
                await self._notify(_message(item, missed))
        except Exception as exc:
            print(f"[Scheduler] notify error: {exc}")