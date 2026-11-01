import argparse
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.security import speaker
from app.security.speaker import SAMPLE_RATE, cosine, trim_silence

ENROLL_PROMPTS = [
    "Hello Nova, what is the weather like today?",
    "Set a timer for ten minutes and remind me to take a break.",
    "Please play some relaxing music for me this evening.",
    "What is the capital of France, and who wrote Hamlet?",
    "Add milk, bread and eggs to my shopping list.",
    "Tell me the time, and then convert twenty miles to kilometers.",
    "I would like to know how the stock market works.",
    "Turn off the lights and lock the front door, please.",
]

IMPOSTOR_TEXTS = [
    "Hello, what is the weather like today?",
    "Set a timer for ten minutes please.",
    "Please open the door and turn on the lights.",
    "Tell me a story about a little dragon.",
    "I would like to order some food for dinner.",
    "What time does the next train leave the station?",
]

IMPOSTOR_DIR = Path("data/voice/impostors")


# ===================== helpers =====================
def listen(recorder, label: str):
    input(f"\n{label}\n  Enter press pannu, apparam pesu... ")
    audio = recorder.record(no_speech_timeout=10)
    if audio is None:
        print("  Edhuvum kekkala. Thirumba try pannu.")
        return None
    print(f"  Recorded: {len(trim_silence(audio)) / SAMPLE_RATE:.1f}s speech")
    return audio


def decode_wav(source) -> np.ndarray:
    """16-bit PCM WAV -> float32 mono 16 kHz."""
    with wave.open(source, "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("16-bit PCM WAV mattum support aagum")

    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        import torch
        import torchaudio.functional as F

        data = F.resample(torch.from_numpy(data).unsqueeze(0), rate, SAMPLE_RATE).squeeze(0).numpy()
    return data


# ===================== commands =====================
def cmd_probe(args) -> None:
    model = speaker.get_model()
    print(f"\nModel   : {speaker.model_name()}")
    print(f"Input   : {model.input_name}")
    print(f"Metadata: {model.meta if model.meta else '(illa, defaults)'}")
    print(
        f"Preproc : normalize_samples={model.normalize_samples}, "
        f"window={model.window_type}, global_mean={model.global_mean}"
    )

    noise = (np.random.default_rng(0).standard_normal(SAMPLE_RATE * 3) * 0.05).astype(np.float32)
    started = time.perf_counter()
    embedding = model.embed(noise)
    print(f"\nTest embedding: shape={embedding.shape}, norm={np.linalg.norm(embedding):.3f}, "
          f"time={(time.perf_counter() - started) * 1000:.0f} ms")
    print("Probe OK (256 numbers varanum).")


def cmd_enroll(args) -> None:
    from app.voice.vad_recorder import VADRecorder

    model = speaker.get_model()
    recorder = VADRecorder()
    wanted = max(args.samples, 4)

    print(f"\n{wanted} sentences pesanum. Amaidhiyaana idam, un normal mic distance, normal kural.")
    print("(Kaathu / jalubu illama, Bluetooth headset illama, idhe mic la thaan Nova use pannum.)")

    embeddings: list[np.ndarray] = []
    index = 0
    while len(embeddings) < wanted:
        prompt = ENROLL_PROMPTS[index % len(ENROLL_PROMPTS)]
        index += 1
        audio = listen(recorder, f"[{len(embeddings) + 1}/{wanted}] Padi (illa edhavadhu normal ah pesu): \"{prompt}\"")
        if audio is None:
            continue
        if len(trim_silence(audio)) / SAMPLE_RATE < 2.0:
            print("  Romba chinnadhu (2+ sec venum). Konjam neelamaa pesu.")
            continue
        embeddings.append(model.embed(audio))
        print("  OK")

    consistency = speaker.leave_one_out(embeddings)
    print("\nConsistency (ovvoru sample, matravanga kooda evlo onnaa):")
    for number, value in enumerate(consistency, start=1):
        flag = "" if value >= args.min_consistency else "   <-- kuraivu (vera kural / noise?)"
        print(f"  sample {number}: {value:.2f}{flag}")

    keep = [e for e, value in zip(embeddings, consistency) if value >= args.min_consistency]
    if len(keep) < 4:
        print("\nSamples consistent illa (4 kooda sariyaa illa). Amaidhiyaana idam, ore mic distance la thirumba enroll pannu.")
        return

    speaker.save_profile(keep)
    print(f"\nEnroll aachu: {len(keep)} samples. Voiceprint {settings.speaker_profile} la save aachu (encrypted: {settings.encrypt_at_rest}).")
    print("Adutha step: python scripts\\speaker_tool.py test   (apparam calibrate)")


def cmd_test(args) -> None:
    from app.voice.vad_recorder import VADRecorder

    profile = speaker.load_profile()
    if profile is None:
        print("Voiceprint illa. Modhalil: python scripts\\speaker_tool.py enroll")
        return

    model = speaker.get_model()
    recorder = VADRecorder()
    print(f"\nThreshold: {settings.speaker_threshold} (SPEAKER_THRESHOLD). Ctrl+C la exit.")
    try:
        while True:
            audio = listen(recorder, "Edhavadhu pesu (nee, appuram vera oruthar, appuram YouTube / TV audio)")
            if audio is None:
                continue
            try:
                score = cosine(model.embed(audio), profile.centroid)
            except ValueError as exc:
                print(f"  {exc}")
                continue
            verdict = "ACCEPT" if score >= settings.speaker_threshold else "REJECT"
            print(f"  score = {score:.3f}  ->  {verdict}")
    except KeyboardInterrupt:
        print("\nBye!")


def cmd_calibrate(args) -> None:
    profile = speaker.load_profile()
    if profile is None:
        print("Voiceprint illa. Modhalil: python scripts\\speaker_tool.py enroll")
        return

    from app.tracking.tracker import Tracker
    from app.voice.vad_recorder import VADRecorder

    model = speaker.get_model()
    recorder = VADRecorder()
    tracker = Tracker(settings.mlflow_speaker_experiment)
    genuine: list[float] = []
    impostor: list[tuple[str, float]] = []

    # ---- Part 1: nee ----
    print(f"\n=== Part 1: NEE ({args.genuine} sentences, ovvoru dhadavayum different) ===")
    for number in range(1, args.genuine + 1):
        while True:
            audio = listen(recorder, f"[{number}/{args.genuine}] Edhavadhu normal ah pesu")
            if audio is None:
                continue
            try:
                genuine.append(cosine(model.embed(audio), profile.centroid))
                break
            except ValueError as exc:
                print(f"  {exc}")

    # ---- Part 2: vera kuralgal ----
    print("\n=== Part 2: VERA KURALGAL ===")
    if not args.no_tts:
        from app.voice.tts import TextToSpeech

        tts = TextToSpeech()
        for text in IMPOSTOR_TEXTS:
            wav = tts.synthesize_wav(text)
            if wav:
                score = cosine(model.embed(decode_wav(io.BytesIO(wav))), profile.centroid)
                impostor.append(("piper-tts", score))
        print(f"  Piper TTS voice: {len(IMPOSTOR_TEXTS)} sentences")

    if IMPOSTOR_DIR.exists():
        for path in sorted(IMPOSTOR_DIR.glob("*.wav")):
            try:
                impostor.append((path.name, cosine(model.embed(decode_wav(str(path))), profile.centroid)))
                print(f"  {path.name}")
            except Exception as exc:
                print(f"  {path.name} skip: {exc}")

    for number in range(1, args.impostor_live + 1):
        print(f"\nIdhu VERA ORUTHAR (nee illa) pesa vendiya neram. Mic ah avanga kitta kudu.")
        while True:
            audio = listen(recorder, f"[{number}/{args.impostor_live}] Vera aal: edhavadhu pesu")
            if audio is None:
                continue
            try:
                impostor.append(("live-other", cosine(model.embed(audio), profile.centroid)))
                break
            except ValueError as exc:
                print(f"  {exc}")

    # ---- Results ----
    g = np.array(genuine)
    i = np.array([score for _, score in impostor])
    print("\n=== Scores ===")
    print(f"NEE     : min {g.min():.2f} | mean {g.mean():.2f} | max {g.max():.2f}   (n={len(g)})")
    if len(i):
        print(f"VERA    : min {i.min():.2f} | mean {i.mean():.2f} | max {i.max():.2f}   (n={len(i)})")
        for source, score in impostor:
            print(f"   {source:20} {score:.2f}")

    thresholds = [round(float(t), 2) for t in np.arange(0.20, 0.901, 0.05)]
    rows = []
    print("\nthreshold |  FRR (nee reject)  |  FAR (vera aal accept)")
    print("----------+--------------------+-----------------------")
    for t in thresholds:
        frr = float(np.mean(g < t))
        far = float(np.mean(i >= t)) if len(i) else float("nan")
        rows.append((t, frr, far))
        far_text = f"{far:.2f}" if len(i) else "  -"
        print(f"   {t:.2f}   |       {frr:.2f}         |        {far_text}")

        tracker.log_run(
            run_name=f"speaker-threshold-{t:.2f}",
            params={"threshold": t, "model": speaker.model_name(), "genuine_n": len(g), "impostor_n": len(i)},
            metrics={"frr": frr, **({"far": far} if len(i) else {})},
            tags={"type": "speaker-eval"},
        )

    if len(i):
        best = min(rows, key=lambda row: (row[1] + row[2], -row[0]))   # FRR+FAR kammi, tie na adhigam threshold (secure)
        suggestion = best[0]
        if g.min() <= i.max():
            print("\nWARNING: Nee-oda kammi score <= vera aal oda adhigam score. Rendu groups um overlap aagudhu.")
            print("  Enroll thirumba pannu (quiet room, ore mic), illana vera mic use pannu.")
    else:
        suggestion = max(0.30, round(float(np.percentile(g, 10)) - 0.05, 2))
        print("\n(Vera kural data illa, so suggestion rough. TTS / wav / --impostor-live add pannu.)")

    print(f"\nSuggested: SPEAKER_THRESHOLD={suggestion:.2f}")
    print("Idha .env la podu, SPEAKER_MODE=enforce pannu, server / wake_chat restart pannu.")
    print("NOTE: Idhu recorded / TTS voice ku protection illa (replay attack). Security layer illa, convenience layer.")


def cmd_status(args) -> None:
    from app.security import crypto

    path = Path(settings.speaker_profile)
    print(f"\nMode      : {settings.speaker_mode}")
    print(f"Threshold : {settings.speaker_threshold}")
    print(f"Model     : {settings.speaker_model_path}  ({'irukku' if Path(settings.speaker_model_path).exists() else 'ILLA'})")
    print(f"Profile   : {path}  [{crypto.file_state(path)}]")
    try:
        info = speaker.profile_info()
    except crypto.KeyUnavailableError as exc:
        print(f"  KEY PROBLEM: {exc}")
        return
    if info:
        print(f"  samples: {info['samples']} | created: {info['created']} | model: {info['model']}")
    else:
        print("  (enroll aagala)")


def cmd_delete(args) -> None:
    if input("Voiceprint delete aagum. 'DELETE' nu type pannu: ").strip() != "DELETE":
        print("Cancel.")
        return
    print("Deleted." if speaker.delete_profile() else "Voiceprint illa.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nova voice biometrics tool")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="model load aagudha, preprocessing enna nu paakkum").set_defaults(func=cmd_probe)

    enroll = sub.add_parser("enroll", help="un kural ah register pannum")
    enroll.add_argument("--samples", type=int, default=settings.speaker_enroll_samples)
    enroll.add_argument("--min-consistency", type=float, default=0.35)
    enroll.set_defaults(func=cmd_enroll)

    sub.add_parser("test", help="live: pesi score paaru").set_defaults(func=cmd_test)

    calibrate = sub.add_parser("calibrate", help="best threshold kandupidikkum")
    calibrate.add_argument("--genuine", type=int, default=8, help="nee evlo sentences pesanum")
    calibrate.add_argument("--impostor-live", type=int, default=0, help="vera oruthar evlo sentences pesanum")
    calibrate.add_argument("--no-tts", action="store_true", help="Piper TTS voice impostor ah use pannaadha")
    calibrate.set_defaults(func=cmd_calibrate)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("delete").set_defaults(func=cmd_delete)

    args = parser.parse_args()
    try:
        args.func(args)
    except speaker.SpeakerModelError as exc:
        print(f"MODEL PROBLEM: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()