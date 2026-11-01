import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.llm import ChatSession
from app.memory.long_term import get_long_term

HELP = """
Commands:
  /facts       long-term facts list
  /history     short-term history (evlo messages)
  /reset       short-term history clear (facts / docs apdiye irukkum)
  /clearfacts  long-term facts ellam delete
  exit         quit
"""


async def main():
    session = ChatSession(session_id="demo")
    memory = get_long_term()
    name = settings.assistant_name

    print(f"\nShort-term memory backend : {session.short.backend}")
    print(f"Short-term messages       : {len(session.short.get())}")
    print(f"Long-term facts           : {memory.facts.count}")
    print(f"Document chunks           : {memory.docs.count}")
    print(HELP)

    while True:
        text = (await asyncio.to_thread(input, "\nYou: ")).strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        if text == "/reset":
            session.reset()
            print("Short-term history cleared.")
            continue
        if text == "/history":
            print(f"{len(session.short.get())} messages in short-term ({session.short.backend})")
            continue
        if text == "/facts":
            if not memory.facts.records:
                print("(Facts edhuvum illa)")
            for i, record in enumerate(memory.facts.records, start=1):
                print(f"{i}. {record['text']}   [{record.get('source')}]")
            continue
        if text == "/clearfacts":
            memory.facts.clear()
            print("Long-term facts cleared.")
            continue

        start = time.time()
        print(f"{name}: ", end="", flush=True)
        async for token in session.stream_reply(text):
            print(token, end="", flush=True)
        print(f"\n[{time.time() - start:.1f}s]")

        # Memory enna panniduchu nu kaattrom (debug)
        if session.last_captured:
            print(f"  [Saved fact] {session.last_captured}")
        for fact, score in session.last_facts:
            print(f"  [Fact {score:.2f}] {fact}")
        for source, chunk, score in session.last_docs:
            preview = chunk.replace("\n", " ")[:70]
            print(f"  [Doc {score:.2f} | {source}] {preview}...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")