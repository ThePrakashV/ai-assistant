import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.voice.wakeword import WakeWordDetector

state = {"frames": 0, "max": 0.0}


def show_score(name: str, score: float) -> None:
    state["frames"] += 1
    state["max"] = max(state["max"], score)
    bar = "#" * int(score * 40)
    print(
        f"\r{score:5.2f} |{bar:<40}| max={state['max']:.2f} frames={state['frames']}",
        end="",
        flush=True,
    )


def main():
    detector = WakeWordDetector()
    print(f"\nSay '{settings.wake_word_display}'. Threshold = {settings.wake_threshold}")
    print("Score bar la spike varanum. Exit panna Ctrl+C.\n")

    count = 0
    try:
        while True:
            name, score = detector.wait_for_wake_word(on_score=show_score)
            count += 1
            print(f"\n>>> WAKE WORD DETECTED #{count}  ({name}, score {score:.2f})\n")
            time.sleep(1.0)  # udane thirumba trigger aagaama irukka
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()