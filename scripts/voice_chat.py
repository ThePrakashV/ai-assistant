import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.llm import ChatSession
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech
from app.voice.vad_recorder import VADRecorder


async def main():
    stt = SpeechToText()
    recorder = VADRecorder()
    tts = TextToSpeech()
    session = ChatSession()
    name = settings.assistant_name

    print(f"\n{name} ready! Pesu. Exit panna Ctrl+C.")

    while True:
        print("\n[Listening...]")
        # Blocking functions ah thread la run pannurom (async loop block aagaama irukka)
        audio = await asyncio.to_thread(recorder.record)
        if audio is None:
            continue

        result = await asyncio.to_thread(stt.transcribe, audio)
        user_text = result["text"]
        if not user_text:
            print("(Text edhuvum varala)")
            continue
        print(f"You  : {user_text}")

        start = time.time()
        print(f"{name}: ", end="", flush=True)
        reply = ""
        async for token in session.stream_reply(user_text):
            print(token, end="", flush=True)
            reply += token
        print(f"\n[LLM {time.time() - start:.1f}s]")

        # Nova pesum bodhu mic kekka koodaadhu (echo), so pesi mudikkara varaikkum wait
        await asyncio.to_thread(tts.speak, reply)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")