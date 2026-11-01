import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.voice.stt import SpeechToText
from app.voice.vad_recorder import SAMPLE_RATE, VADRecorder


def main():
    stt = SpeechToText()
    recorder = VADRecorder()

    print("\nReady! Pesu, niruthunadhum automatic ah text varum. Exit panna Ctrl+C.")

    try:
        while True:
            print("\n[Listening...]")
            audio = recorder.record()

            if audio is None:
                print("Edhuvum kekkala.")
                continue

            print(f"[Recorded {len(audio) / SAMPLE_RATE:.1f}s, transcribing...]")
            start = time.time()
            result = stt.transcribe(audio)

            if not result["text"]:
                print("(Text edhuvum varala)")
                continue

            print(f"You said : {result['text']}")
            print(f"Language : {result['language']} ({result['probability']})")
            print(f"Time     : {time.time() - start:.2f}s")

    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()