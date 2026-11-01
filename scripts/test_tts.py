import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.voice.tts import TextToSpeech


def main():
    tts = TextToSpeech()
    name = settings.assistant_name

    tests = [
        ("Normal speed", 1.0, 1.0, f"Hello, I am {name}, your personal AI assistant."),
        ("Slow speed (0.7x)", 0.7, 1.0, "This sentence is spoken slowly."),
        ("Fast speed (1.5x)", 1.5, 1.0, "This sentence is spoken quickly."),
        ("Low volume (0.2)", 1.0, 0.2, "This sentence is spoken quietly."),
        ("Full volume (1.0)", 1.0, 1.0, "This sentence is spoken at full volume."),
    ]

    for label, speed, volume, text in tests:
        print(f"\n[{label}] speed={speed}, volume={volume}")
        print(f"Text: {text}")
        latency = tts.speak(text, speed=speed, volume=volume)
        print(f"First audio after: {latency:.2f}s")


if __name__ == "__main__":
    main()