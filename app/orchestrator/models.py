from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "running", "done", "failed"]
TaskStatus = Literal["planning", "running", "done", "partial", "failed"]


class StepRecord(BaseModel):
    """Oru chinna ticket. Edha seiyanum, ippo enna status, evlo neram aachu."""

    index: int
    text: str
    status: StepStatus = "pending"
    route: str | None = None      # "skill:weather" illa "chat"
    intent: str | None = None
    started: float | None = None  # unix time
    ended: float | None = None
    reply: str | None = None
    error: str | None = None
    retries: int = 0


class TaskRecord(BaseModel):
    """Oru periya order. Steps + final reply."""

    id: str
    text: str
    source: str = "text"          # "text" / "voice" / "api"
    status: TaskStatus = "planning"
    created: float
    started: float | None = None
    ended: float | None = None
    plan_ms: int = 0
    steps: list[StepRecord] = Field(default_factory=list)
    reply: str = ""