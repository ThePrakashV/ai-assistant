import json
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.security import crypto
from app.security.audit import audit_event

SAMPLE_RATE = 16000
MIN_EMBED_SECONDS = 0.5


class SpeakerModelError(RuntimeError):
    """Speaker model file illa / load aagala."""


def model_name() -> str:
    return Path(settings.speaker_model_path).name


# ===================== Small helpers =====================
def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-9 else vector


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """1.0 = ore voiceprint, 0.0 = sambandham illa."""
    return float(np.dot(_unit(a), _unit(b)))


def trim_silence(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Modhal / kadaisi silence ah vettidum (silence frames voiceprint ah kuraikkum)."""
    audio = np.asarray(audio, dtype=np.float32)
    frame = int(0.02 * sample_rate)                  # 20 ms frames
    count = len(audio) // frame
    if count < 5:
        return audio

    frames = audio[: count * frame].reshape(count, frame)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    reference = float(np.percentile(rms, 95))
    if reference < 1e-4:                             # mic dead / full silence
        return audio

    voiced = np.where(rms > max(reference * 0.12, 1e-4))[0]
    if len(voiced) == 0:
        return audio

    pad = 5                                          # 100 ms munnaadi / pinnaadi
    start = max(int(voiced[0]) - pad, 0)
    end = min(int(voiced[-1]) + pad + 1, count)
    return audio[start * frame : end * frame]


# ===================== Model =====================
class SpeakerModel:
    """Voice -> 256 numbers (voiceprint). WeSpeaker ONNX model + torchaudio fbank features."""

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise SpeakerModelError(
                f"Speaker model kidaikkala: {path}. Run: python scripts\\download_speaker_model.py"
            )

        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2             # RAM / CPU kammi
        try:
            self.session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise SpeakerModelError(f"Model load aagala: {exc}") from exc

        self.input_name = self.session.get_inputs()[0].name
        meta = dict(self.session.get_modelmeta().custom_metadata_map or {})
        self.meta = meta
        # Model oda metadata la irundhu preprocessing padikkurom (illana WeSpeaker default)
        self.normalize_samples = str(meta.get("normalize_samples", "0")).strip() == "1"
        self.window_type = str(meta.get("window_type", "hamming")).strip() or "hamming"
        self.global_mean = str(meta.get("feature_normalize_type", "global-mean")).strip() == "global-mean"

    def embed(self, audio: np.ndarray) -> np.ndarray:
        import torch
        import torchaudio.compliance.kaldi as kaldi

        audio = trim_silence(audio)
        if len(audio) < SAMPLE_RATE * MIN_EMBED_SECONDS:
            raise ValueError("Audio romba chinnadhu (speech 0.5 sec kooda illa).")

        wave = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)
        if not self.normalize_samples:
            wave = wave * 32768.0                    # model 16-bit scale ethirpaarkkum
        feats = kaldi.fbank(
            wave,
            num_mel_bins=80,
            frame_length=25.0,
            frame_shift=10.0,
            dither=0.0,
            sample_frequency=float(SAMPLE_RATE),
            window_type=self.window_type,
            use_energy=False,
        )
        if self.global_mean:
            feats = feats - feats.mean(dim=0, keepdim=True)

        output = self.session.run(None, {self.input_name: feats.unsqueeze(0).numpy()})[0]
        return _unit(np.asarray(output, dtype=np.float32).reshape(-1))


@lru_cache(maxsize=1)
def get_model() -> SpeakerModel:
    return SpeakerModel(Path(settings.speaker_model_path))


# ===================== Voiceprint storage (Phase 12 encryption use pannum) =====================
@dataclass
class Profile:
    model: str
    created: str
    embeddings: np.ndarray    # (samples, dim)
    centroid: np.ndarray      # (dim,)

    @property
    def samples(self) -> int:
        return int(len(self.embeddings))


def leave_one_out(embeddings: list[np.ndarray]) -> list[float]:
    """Ovvoru sample, matra samples oda average kooda evlo onnaa irukku. Kammi na adhu vera aal / noise."""
    array = np.stack(embeddings)
    total = array.sum(axis=0)
    return [cosine(row, total - row) for row in array]


def save_profile(embeddings: list[np.ndarray]) -> None:
    array = np.stack(embeddings)
    payload = {
        "version": 1,
        "model": model_name(),
        "created": datetime.now().isoformat(timespec="seconds"),
        "embeddings": array.tolist(),
        "centroid": _unit(array.mean(axis=0)).tolist(),
    }
    crypto.write_secure(Path(settings.speaker_profile), json.dumps(payload).encode("utf-8"))
    audit_event("speaker.enroll", samples=len(embeddings), model=model_name())


def load_profile() -> Profile | None:
    raw = crypto.read_secure(Path(settings.speaker_profile))
    if raw is None:
        return None
    data = json.loads(raw.decode("utf-8"))
    return Profile(
        model=data["model"],
        created=data["created"],
        embeddings=np.asarray(data["embeddings"], dtype=np.float32),
        centroid=np.asarray(data["centroid"], dtype=np.float32),
    )


def profile_info() -> dict | None:
    """Metadata mattum (embedding illa). Dashboard / export ku."""
    profile = load_profile()
    if profile is None:
        return None
    return {"samples": profile.samples, "created": profile.created, "model": profile.model}


def delete_profile() -> bool:
    path = Path(settings.speaker_profile)
    if not path.exists():
        return False
    path.unlink()
    audit_event("speaker.delete")
    return True


# ===================== The doorman =====================
@dataclass
class GateResult:
    allowed: bool
    reason: str              # off / no_profile / verified / trusted_short / rejected / too_short / ...
    score: float | None = None
    message: str = ""        # web UI ku (Tanglish)
    spoken: str = ""         # voice reply ku (English, Piper voice ku)


class SpeakerGate:
    """Utterance oda voiceprint, enrolled voiceprint kooda match aagudha nu paakkum."""

    def __init__(self) -> None:
        self._profile: Profile | None = None
        self._mtime: float | None = None
        self._trusted_until: dict[str, float] = {}
        self._warned = False

    def _current_profile(self) -> Profile | None:
        path = Path(settings.speaker_profile)
        mtime = path.stat().st_mtime if path.exists() else None
        if mtime != self._mtime:                     # CLI la puthusa enroll panna udane edukkum
            self._profile = load_profile() if mtime is not None else None
            self._mtime = mtime
        return self._profile

    def check(self, audio: np.ndarray, channel: str = "web") -> GateResult:
        if settings.speaker_mode != "enforce":
            return GateResult(True, "off")

        try:
            profile = self._current_profile()
        except Exception as exc:                     # key problem / corrupt file: fail closed
            audit_event("speaker.error", actor=channel, error=type(exc).__name__)
            return GateResult(
                False, "profile_error",
                message="Voiceprint padikka mudiyala (key / file problem). security_tool.py status paaru.",
                spoken="Sorry, I cannot check your voice right now.",
            )

        if profile is None:
            if not self._warned:
                print("[Speaker] SPEAKER_MODE=enforce, aana voiceprint illa. Enroll pannu: python scripts\\speaker_tool.py enroll")
                self._warned = True
            return GateResult(True, "no_profile")

        if profile.model != model_name():
            return GateResult(
                False, "profile_mismatch",
                message="Voiceprint vera model la eduthadhu. Thirumba enroll pannu.",
                spoken="Sorry, my voice profile is out of date.",
            )

        now = time.time()
        trimmed = trim_silence(np.asarray(audio, dtype=np.float32))
        seconds = len(trimmed) / SAMPLE_RATE

        if seconds < settings.speaker_min_seconds:
            if now < self._trusted_until.get(channel, 0.0):
                return GateResult(True, "trusted_short")
            audit_event("speaker.reject", actor=channel, reason="too_short", seconds=round(seconds, 1))
            return GateResult(
                False, "too_short",
                message="Audio romba chinnadhu. Konjam neelamaa (1+ sec) pesu.",
                spoken="Please speak a little longer.",
            )

        try:
            score = cosine(get_model().embed(trimmed), profile.centroid)
        except Exception as exc:
            audit_event("speaker.error", actor=channel, error=type(exc).__name__)
            return GateResult(
                False, "model_error",
                message=f"Voice verify panna mudiyala: {exc}",
                spoken="Sorry, I cannot check your voice right now.",
            )

        if score >= settings.speaker_threshold:
            self._trusted_until[channel] = now + settings.speaker_trust_seconds
            return GateResult(True, "verified", score)

        audit_event("speaker.reject", actor=channel, reason="mismatch", score=round(score, 3), seconds=round(seconds, 1))
        return GateResult(
            False, "rejected", score,
            message=f"Voice match aagala (score {score:.2f}). Naan en owner kural ku mattum respond pannuven.",
            spoken="Sorry, I only respond to my owner.",
        )


@lru_cache(maxsize=1)
def get_gate() -> SpeakerGate:
    return SpeakerGate()