import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.nlu.pipeline import NLU

SAMPLES = [
    "What's the weather like in Madurai tomorrow?",
    "Set a timer for two hours and thirty minutes",
    "Remind me to submit the report at 5 pm",
    "What is 48 divided by 6",
    "Convert 10 miles to kilometers",
    "How much is 250 euros in rupees",
    "Search for the best laptops under 50000",
    "Play Kannana Kanne on YouTube",
    "Turn off the fan in the kitchen",
    "What time is it right now",
    "Speak a little slower please",
    "Tell me something interesting about space",
]


def show(result) -> None:
    print(f"\nText      : {result.text}")
    print(f"Intent    : {result.intent}  (confidence {result.confidence})")
    top = " | ".join(f"{name} {score}" for name, score in result.top_matches)
    print(f"Top 3     : {top}")
    print(f"Entities  : {result.entities}")
    print(
        f"Time      : classify {result.classify_ms} ms | extract {result.extract_ms} ms"
    )


async def main():
    nlu = NLU()

    print("\n===== PART 1: Sample sentences =====")
    for text in SAMPLES:
        show(await nlu.understand(text))

    print("\n===== PART 2: Nee type pannu (exit na 'exit') =====")
    while True:
        text = await asyncio.to_thread(input, "\nYou: ")
        text = text.strip()
        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue
        show(await nlu.understand(text))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")