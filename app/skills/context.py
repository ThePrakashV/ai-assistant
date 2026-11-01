from dataclasses import dataclass
from typing import Any

from app.skills.scheduler import Scheduler


@dataclass
class SkillContext:
    """Skills ku thevai padra shared things (TTS, scheduler). Idhu vazhiya thaan skill Nova oda kural / timers ah control pannum."""

    tts: Any | None = None
    scheduler: Scheduler | None = None