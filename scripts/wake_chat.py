import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.agent.graph import NovaAgent
from app.core.config import settings
from app.memory.long_term import get_long_term
from app.orchestrator.orchestrator import TaskOrchestrator
from app.security.speaker import get_gate
from app.skills.context import SkillContext
from app.skills.scheduler import Scheduler
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech
from app.voice.vad_recorder import VADRecorder
from app.voice.wakeword import WakeWordDetector

SLEEP_PHRASES = ("go to sleep", "goodbye", "stop listening")
MAX_REJECTS = 2   # indha alavukku thappa kural vandha thoongidum


async def main():
    stt = SpeechToText()
    recorder = VADRecorder()
    tts = TextToSpeech()
    detector = WakeWordDetector()

    # Embedding model + FAISS files ah startup la load pannidrom (modhal reply slow aagaama irukka)
    memory = get_long_term()
    print(f"[Memory] facts: {memory.facts.count} | document chunks: {memory.docs.count}")

    scheduler = Scheduler()
    agent = NovaAgent(session_id="voice", ctx=SkillContext(tts=tts, scheduler=scheduler))
    orchestrator = TaskOrchestrator(agent)
    gate = get_gate()
    print(f"[Memory] short-term backend: {agent.session.short.backend}")
    print(f"[Tasks] store backend: {orchestrator.store.backend}  (dashboard: http://127.0.0.1:8001/dashboard)")
    print(f"[Speaker] mode: {settings.speaker_mode} (threshold {settings.speaker_threshold})")
    name = settings.assistant_name

    # Rendu per ore neram la pesa koodaadhu (reply + timer alert). Lock = oru neram oruthar mattum
    speak_lock = asyncio.Lock()

    async def say(text: str) -> None:
        async with speak_lock:
            await asyncio.to_thread(tts.speak, text)

    async def notify(message: str) -> None:
        print(f"\n[ALERT] {message}")
        await say(message)

    scheduler.start(notify)
    print(f"[Scheduler] pending items: {len(scheduler.pending())}")

    while True:
        # ---------- STATE 1: SLEEPING ----------
        print(f"\n[Sleeping... say '{settings.wake_word_display}']")
        model_name, score = await asyncio.to_thread(detector.wait_for_wake_word)
        print(f"[Wake word detected: {model_name} ({score:.2f})]")

        # ---------- STATE 2: ACK ----------
        await say(settings.wake_ack_text)

        # ---------- STATE 3: CONVERSATION ----------
        first_turn = True
        rejects = 0
        while True:
            timeout = settings.listen_timeout if first_turn else settings.followup_timeout
            print("[Listening...]")
            audio = await asyncio.to_thread(recorder.record, timeout)

            if audio is None:
                print("[Yaarum pesala, thoongaren...]")
                break

            # Voice biometrics: Whisper ku munnaadi. Un kural illa na ignore
            verdict = await asyncio.to_thread(gate.check, audio, "voice")
            if not verdict.allowed:
                rejects += 1
                score_text = f"{verdict.score:.2f}" if verdict.score is not None else "-"
                print(f"[Speaker: {verdict.reason}, score {score_text}]")
                await say(verdict.spoken or "Sorry, I only respond to my owner.")
                if rejects >= MAX_REJECTS:
                    print("[Thappa kural, thoongaren...]")
                    break
                continue
            rejects = 0

            result = await asyncio.to_thread(stt.transcribe, audio)
            user_text = result["text"]
            if not user_text:
                print("[Text edhuvum varala, thoongaren...]")
                break
            print(f"You  : {user_text}")
            first_turn = False

            # Sleep command check
            lowered = user_text.lower()
            if any(phrase in lowered for phrase in SLEEP_PHRASES):
                await say("Okay, going to sleep.")
                break

            # Orchestrator: steps ah pirichu (parallel) run pannum
            task = await orchestrator.handle(user_text, source="voice")
            print(f"{name}: {task.reply}")
            for step in task.steps:
                took = (step.ended - step.started) if step.started and step.ended else 0
                print(f"  [step {step.index}] {step.route} | {step.status} | {took:.1f}s | {step.text}")
            if agent.session.last_captured:
                print(f"  [Saved fact] {agent.session.last_captured}")

            await say(task.reply or "Sorry, I have nothing to say.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")