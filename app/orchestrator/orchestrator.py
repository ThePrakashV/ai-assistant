import asyncio
import re
import time
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.graph import NovaAgent
from app.core.config import settings
from app.orchestrator.models import StepRecord, TaskRecord
from app.orchestrator.planner import split_request
from app.orchestrator.store import TaskStore
from app.tracking.tracker import Tracker

# Skill indha maadhiri thodangina "seiya mudiyala" nu artham
FAIL_PREFIXES = ("i could not", "i cannot", "sorry")
# Idhula irundha network problem, so oru dhadavai retry
RETRYABLE = ("could not reach",)
# Idhula edhavadhu irundha steps ore order la, one-by-one run aaganum (cancel + set race thadukka)
ORDER_SENSITIVE_RE = re.compile(
    r"\b(cancel|stop|delete|remove|clear|forget|remember|faster|slower|louder|quieter)\b",
    re.IGNORECASE,
)


class OrchestratorState(TypedDict):
    task: TaskRecord


class TaskOrchestrator:
    """Head chef. handle(text) -> TaskRecord (steps + final reply). Ovvoru step um dashboard ku live ah update aagum."""

    def __init__(
        self,
        agent: NovaAgent,
        store: TaskStore | None = None,
        tracker: Tracker | None = None,
    ) -> None:
        self.agent = agent
        self.store = store or TaskStore()
        self.tracker = tracker or Tracker()  # MLflow (server illana auto off)
        self.graph = self._build_graph()

    # ---------- Flowchart ----------
    def _build_graph(self):
        builder = StateGraph(OrchestratorState)
        builder.add_node("plan", self._plan)
        builder.add_node("execute", self._execute)
        builder.add_node("summarize", self._summarize)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "execute")
        builder.add_edge("execute", "summarize")
        builder.add_edge("summarize", END)
        return builder.compile()

    # ---------- Node 1: plan ----------
    async def _plan(self, state: OrchestratorState) -> dict:
        task = state["task"]
        started = time.perf_counter()

        parts = split_request(task.text, settings.max_steps)
        task.steps = [StepRecord(index=i, text=part) for i, part in enumerate(parts, start=1)]
        task.plan_ms = round((time.perf_counter() - started) * 1000)
        task.status = "running"
        task.started = time.time()
        self.store.save(task)  # steps ellam "pending" ah dashboard la theriyum
        return {"task": task}

    # ---------- Node 2: execute ----------
    async def _execute(self, state: OrchestratorState) -> dict:
        task = state["task"]
        steps = task.steps

        order_matters = any(ORDER_SENSITIVE_RE.search(step.text) for step in steps)
        if len(steps) > 1 and not order_matters:
            gate = asyncio.Semaphore(settings.max_parallel_steps)

            async def guarded(step: StepRecord) -> None:
                async with gate:
                    await self._run_step(task, step)

            await asyncio.gather(*(guarded(step) for step in steps))
        else:
            for step in steps:
                await self._run_step(task, step)

        return {"task": task}

    async def _run_step(self, task: TaskRecord, step: StepRecord) -> None:
        step.status = "running"
        step.started = time.time()
        self.store.save(task)

        attempts = 0
        while True:
            try:
                result = await self.agent.handle(step.text)
            except Exception as exc:
                step.status = "failed"
                step.error = str(exc)
                step.reply = f"I could not finish this part: {step.text}."
                break

            step.reply = result.reply
            step.route = result.route
            step.intent = result.intent

            lowered = result.reply.strip().lower()
            failed = (not lowered) or lowered.startswith(FAIL_PREFIXES)

            # Network fail aana oru dhadavai thirumba try pannurom
            if failed and attempts < settings.step_retries and any(p in lowered for p in RETRYABLE):
                attempts += 1
                step.retries = attempts
                await asyncio.sleep(settings.step_retry_delay)
                continue

            step.status = "failed" if failed else "done"
            break

        step.ended = time.time()
        self.store.save(task)

    # ---------- Node 3: summarize ----------
    async def _summarize(self, state: OrchestratorState) -> dict:
        task = state["task"]
        failed = [step for step in task.steps if step.status == "failed"]
        done = [step for step in task.steps if step.status == "done"]

        if not failed:
            task.status = "done"
        elif done:
            task.status = "partial"
        else:
            task.status = "failed"

        replies = [(step.reply or "").strip() for step in task.steps]
        task.reply = " ".join(reply for reply in replies if reply)
        task.ended = time.time()
        self.store.save(task)
        return {"task": task}

    # ---------- Public API ----------
    async def handle(self, text: str, source: str = "text") -> TaskRecord:
        task = TaskRecord(id=uuid.uuid4().hex[:8], text=text, source=source, created=time.time())
        self.store.save(task)  # "planning" status udane dashboard la theriyum

        try:
            final = await self.graph.ainvoke({"task": task})
            task = final["task"]
        except Exception as exc:
            task.status = "failed"
            task.ended = time.time()
            task.reply = "Sorry, something went wrong with that request."
            print(f"[Orchestrator] error: {exc}")
            self.store.save(task)

        self.tracker.log_task(task)  # MLflow la oru run (background thread)
        return task