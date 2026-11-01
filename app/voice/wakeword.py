import queue

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from app.core.config import settings

SAMPLE_RATE = 16000
FRAME_SIZE = 1280  # 80 ms. openWakeWord ku ideal frame size


class WakeWordDetector:
    """Mic ah continuous ah kekkum. Wake word kettaa mattum return aagum."""

    def __init__(self) -> None:
        print(f"Loading wake word model '{settings.wake_word_model}' ...")
        self.model = Model(
            wakeword_models=[settings.wake_word_model],
            inference_framework="onnx",  # Windows la ONNX thaan
        )
        self.threshold = settings.wake_threshold
        print("Wake word model loaded.")

    def _score(self, frame: np.ndarray) -> tuple[str, float]:
        prediction = self.model.predict(frame)
        # Oru model mattum load pannirukkom, so max score eduthukkalam
        name, score = max(prediction.items(), key=lambda item: item[1])
        return name, float(score)

    def wait_for_wake_word(self, on_score=None) -> tuple[str, float]:
        """Wake word ketkara varaikkum block aagum. (model_name, score) return pannum.

        on_score: optional function(name, score), ovvoru frame ku call aagum (debug / tuning ku).
        """
        audio_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            audio_queue.put(indata[:, 0].copy())

        # Munnaadi detection oda leftover audio features clear pannurom
        if hasattr(self.model, "reset"):
            self.model.reset()

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",  # openWakeWord int16 audio ethirpaarkkum
            blocksize=FRAME_SIZE,
            callback=callback,
        ):
            while True:
                frame = audio_queue.get()
                name, score = self._score(frame)
                if on_score:
                    on_score(name, score)
                if score >= self.threshold:
                    return name, score