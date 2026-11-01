import queue
import time

import numpy as np
import sounddevice as sd
import torch
from silero_vad import VADIterator, load_silero_vad

SAMPLE_RATE = 16000
CHUNK_SIZE = 512  # Silero VAD 16kHz ku exact 512 samples (32 ms) thevai


class VADRecorder:
    """Mic la irundhu kekkum. Nee pesa aarambichu, niruthi pause pannina
    appuram audio ah return pannum."""

    def __init__(
        self,
        silence_ms: int = 800,
        max_seconds: int = 30,
        threshold: float = 0.5,
    ) -> None:
        print("Loading Silero VAD model ...")
        self.model = load_silero_vad()
        self.silence_ms = silence_ms      # evlo neram silence na "pesi mudinjuchu"
        self.max_seconds = max_seconds    # maximum wait time
        self.threshold = threshold        # 0-1, adhigam na strict

    def record(self, no_speech_timeout: float | None = None) -> np.ndarray | None:
        """Pesi mudikkara varaikkum record pannum.

        no_speech_timeout: itha seconds kulla pesa aarambikkala na None return pannum.
        None (default) na max_seconds varaikkum wait pannum.
        """
        iterator = VADIterator(
            self.model,
            threshold=self.threshold,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=self.silence_ms,
            speech_pad_ms=100,
        )

        audio_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            # Mic thread la irundhu chunks ah queue ku anuppurom
            audio_queue.put(indata[:, 0].copy())

        collected: list[np.ndarray] = []
        pre_roll: list[np.ndarray] = []  # pesa aarambikkum munnaadi 10 chunks (~320ms)
        speaking = False
        start_time = time.time()

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SIZE,
            callback=callback,
        ):
            while time.time() - start_time < self.max_seconds:
                # Pesa aarambikkala na, timeout aanadhum nirutthidrom
                if (
                    not speaking
                    and no_speech_timeout is not None
                    and time.time() - start_time > no_speech_timeout
                ):
                    break

                try:
                    chunk = audio_queue.get(timeout=1)
                except queue.Empty:
                    continue

                event = iterator(torch.from_numpy(chunk))

                if event and "start" in event and not speaking:
                    speaking = True
                    collected = list(pre_roll)  # first word kattai aagaama irukka

                if speaking:
                    collected.append(chunk)
                else:
                    pre_roll.append(chunk)
                    if len(pre_roll) > 10:
                        pre_roll.pop(0)

                if event and "end" in event and speaking:
                    break

        if not collected:
            return None
        return np.concatenate(collected)