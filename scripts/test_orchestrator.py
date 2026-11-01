import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.agent.graph import NovaAgent
from app.core.config import settings
from app.orchestrator.orchestrator import TaskOrchestrator
from app.skills.context import SkillContext
from app.skills.scheduler import Scheduler

DEMO = [
    "What time is it and what is 48 divided by 6",
    "What's the weather in Chennai and convert 100 dollars to rupees and search for Albert Einstein",
    "Set a timer for 20 seconds and remind me to stretch in 1 minute",
    "Set a timer for 2 hours and 30 minutes",
    "What is the date today, then convert 10 miles to kilometers, then speak faster",
    "Hello Nova",
]

HELP = """
Commands:
  /demo      6 sample requests automatic ah run (multi-step kooda)
  /pending   active timers / reminders / alarms
  /clear     dashboard task list clear
  exit       quit
Dashboard: http://127.0.0.1:8000/dashboard  (vera CMD la uvicorn run pannanum)
"""


def show(task) -> None:
    total = (task.ended or time.time()) - task.created
    print(f"Nova : {task.reply}")
    print(f"  [task {task.id}] status={task.status} | {len(task.steps)} step(s) | {total:.1f}s | plan {task.plan_ms} ms")
    for step in task.steps:
        took = (step.ended - step.started) if step.started and step.ended else 0
        retry = f" (retry {step.retries})" if step.retries else ""
        print(f"    step {step.index}: {step.route} | {step.status}{retry} | {took:.1f}s | {step.text}")


async def main():
    # Text mode la TTS illa. Speed / volume skill work aaga oru fake object
    fake_tts = SimpleNamespace(speed=settings.tts_speed, volume=settings.tts_volume)

    scheduler = Scheduler()

    async def notify(message: str) -> None:
        print(f"\n  >>> [ALERT] {message}\nYou: ", end="", flush=True)

    scheduler.start(notify)

    agent = NovaAgent(session_id="orch-test", ctx=SkillContext(tts=fake_tts, scheduler=scheduler))
    orchestrator = TaskOrchestrator(agent)
    print(f"\nTask store backend: {orchestrator.store.backend}")
    print(HELP)

    while True:
        text = (await asyncio.to_thread(input, "\nYou: ")).strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        if text == "/pending":
            items = scheduler.pending()
            if not items:
                print("(Edhuvum pending illa)")
            for item in items:
                left = max(int(item.fire_at - time.time()), 0)
                print(f"  {item.kind:8} | {item.label or '-':20} | {left}s left")
            continue

        if text == "/clear":
            orchestrator.store.clear()
            print("Task list cleared.")
            continue

        if text == "/demo":
            for sentence in DEMO:
                print(f"\nYou: {sentence}")
                show(await orchestrator.handle(sentence))
            continue

        show(await orchestrator.handle(text))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")