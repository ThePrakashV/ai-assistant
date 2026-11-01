import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import sounddevice as sd

from app.voice.stt import SpeechToText

SAMPLE_RATE = 16000
SECONDS = 5


def main():
    stt = SpeechToText()

    input(f"\nEnter press pannu, appuram {SECONDS} seconds pesu...")
    print("Recording... pesu!")
    recording = sd.rec(
        int(SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    print("Recording mudinjuchu. Transcribing...")

    audio = recording[:, 0]
    print(f"Audio max volume: {abs(audio).max():.3f}  (0.000 na mic work aagala)")

    start = time.time()
    result = stt.transcribe(audio)
    print(f"\nText     : {result['text']}")
    print(f"Language : {result['language']} ({result['probability']})")
    print(f"Time     : {time.time() - start:.2f}s")


if __name__ == "__main__":
    main()