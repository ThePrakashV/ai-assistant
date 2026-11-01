import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.agent.graph import NovaAgent
from app.core.config import settings
from app.skills.context import SkillContext
from app.skills.scheduler import Scheduler

DEMO = [
    "What time is it?",
    "What is today's date?",
    "What is 48 divided by 6",
    "What is the square root of 81",
    "What is 15 percent of 200",
    "Convert 10 miles to kilometers",
    "Convert 100 fahrenheit to celsius",
    "How much is 100 dollars in rupees",
    "What is the weather today?",
    "What is the weather in Chennai tomorrow?",
    "Search for Albert Einstein",
    "Speak faster",
    "Hello Nova",
    "What is the capital of France?",
    "What is my name?",
]

HELP = """
Commands:
  /demo      15 sample sentences automatic ah run
  /pending   active timers / reminders / alarms
  exit       quit
Edhavadhu type pannu: Nova skill use pannum, illana chat.
"""


def show(result) -> None:
    print(f"Nova : {result.reply}")
    total = sum(result.timings.values())
    print(
        f"  [{result.route}] intent={result.intent} ({result.confidence}) "
        f"| {total / 1000:.1f}s {result.timings}"
    )
    print(f"  [trace] {' -> '.join(result.trace)}")


async def main():
    # Text mode la TTS illa. Speed / volume skill work aaga oru fake object
    fake_tts = SimpleNamespace(speed=settings.tts_speed, volume=settings.tts_volume)

    scheduler = Scheduler()

    async def notify(message: str) -> None:
        print(f"\n  >>> [ALERT] {message}\nYou: ", end="", flush=True)

    scheduler.start(notify)

    agent = NovaAgent(session_id="agent-test", ctx=SkillContext(tts=fake_tts, scheduler=scheduler))
    print(f"\nShort-term memory backend: {agent.session.short.backend}")
    print(f"Pending items: {len(scheduler.pending())}")
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

        if text == "/demo":
            for sentence in DEMO:
                print(f"\nYou: {sentence}")
                show(await agent.handle(sentence))
            continue

        show(await agent.handle(text))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")