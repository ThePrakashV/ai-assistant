import time

import numpy as np
from faster_whisper import WhisperModel

from app.core.config import settings


class SpeechToText:
    """Whisper model ah oru dhadavai load panni, audio ah text ah maathum."""

    def __init__(self) -> None:
        print(f"Loading Whisper model '{settings.whisper_model}' ...")
        start = time.time()
        # Modhal dhadavai run panna model internet la irundhu download aagum
        self.model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type=settings.whisper_compute_type,
        )
        print(f"Model loaded in {time.time() - start:.1f}s")

    def transcribe(self, audio: np.ndarray) -> dict:
        """audio = float32 numpy array, 16000 Hz, mono."""
        language = settings.whisper_language or None  # "" na auto detect

        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=5,                       # konjam careful ah decode pannum
            repetition_penalty=1.1,            # same words thirumba varaama thadukkum
            vad_filter=True,                   # silence parts ah skip pannum
            condition_on_previous_text=False,  # hallucination loop ah thadukkum
        )

        texts = []
        for seg in segments:
            # Whisper thaane "idhu pesu illa, noise" nu sonna andha segment ah skip
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            # Same words adhigam repeat aana segment (loop) ah skip
            if seg.compression_ratio > 2.4:
                continue
            texts.append(seg.text.strip())

        text = " ".join(texts).strip()

        return {
            "text": text,
            "language": info.language,
            "probability": round(info.language_probability, 2),
        }