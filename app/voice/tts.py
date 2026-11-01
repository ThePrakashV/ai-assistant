import io
import re
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

from app.core.config import settings


def _clean_text(text: str) -> str:
    """LLM reply la irukkura markdown symbols (*, #, `) TTS la padikka koodaadhu."""
    text = re.sub(r"[*#`_]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    """Piper voice ah oru dhadavai load panni, text ah kural la pesum."""

    def __init__(self) -> None:
        model_path = Path(settings.tts_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Voice model kedaikkala: {model_path}. "
                "Project root la irundhu run pannunga, illa Step 2 (download) check pannunga."
            )

        print(f"Loading Piper voice '{model_path.name}' ...")
        start = time.time()
        self.voice = PiperVoice.load(str(model_path))
        self.sample_rate = self.voice.config.sample_rate
        self.speed = settings.tts_speed
        self.volume = settings.tts_volume
        self._synth_lock = threading.Lock()  # web server la rendu per ore neram synth panna
        print(f"Voice loaded in {time.time() - start:.1f}s")

    def _make_config(self, speed: float, volume: float) -> SynthesisConfig:
        speed = min(max(speed, 0.5), 2.0)      # 0.5x to 2x ku limit
        volume = min(max(volume, 0.0), 1.0)    # 0 to 1 ku limit
        # Piper la length_scale > 1 = slow. So speed ah reverse pannurom.
        return SynthesisConfig(length_scale=1.0 / speed, volume=volume)

    def speak(
        self,
        text: str,
        speed: float | None = None,
        volume: float | None = None,
    ) -> float | None:
        """Text ah pesum. First audio varra varaikkum aana neram (seconds) return pannum."""
        text = _clean_text(text)
        if not text:
            return None

        config = self._make_config(
            speed if speed is not None else self.speed,
            volume if volume is not None else self.volume,
        )

        start = time.time()
        first_audio_at = None

        with sd.OutputStream(
            samplerate=self.sample_rate, channels=1, dtype="int16"
        ) as stream:
            # synthesize() oru oru chunk ah yield pannum, so udane play pannalam
            for chunk in self.voice.synthesize(text, syn_config=config):
                if first_audio_at is None:
                    first_audio_at = time.time() - start
                audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                stream.write(audio.reshape(-1, 1))

        return first_audio_at

    def synthesize_wav(
        self,
        text: str,
        speed: float | None = None,
        volume: float | None = None,
    ) -> bytes | None:
        """Text -> WAV bytes (speaker la play pannaadhu). Web / mobile clients ku."""
        text = _clean_text(text)
        if not text:
            return None

        config = self._make_config(
            speed if speed is not None else self.speed,
            volume if volume is not None else self.volume,
        )

        buffer = io.BytesIO()
        frames = 0
        with self._synth_lock:
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(self.sample_rate)
                for chunk in self.voice.synthesize(text, syn_config=config):
                    wav.writeframes(chunk.audio_int16_bytes)
                    frames += len(chunk.audio_int16_bytes) // 2

        return buffer.getvalue() if frames else None