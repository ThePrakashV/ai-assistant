import re

# Oru puthu step aarambikkara words. "and" / "then" ku apparam idhula onnu vandha mattum split.
# ("2 hours and 30 minutes" la "and" ku apparam "30" varum, adhu starter illa, so split aagaadhu.)
_STARTER_WORDS = [
    r"what(?:'s|s)?", "how", "when", "where", "who", "why",
    "set", "start", "cancel", "stop", "remind", "play", "pause", "skip",
    "turn", "switch", "lock", "search", "google", "convert", "calculate",
    "speak", "talk", "check", "remember", "forget",
    r"tell me", r"give me",
]
_STARTER = r"(?:please\s+)?(?:" + "|".join(_STARTER_WORDS) + r")\b"

_SPLIT_RE = re.compile(
    r"\s*(?:;|,|\b(?:and then|and also|and|then|also|after that)\b,?)\s+(?=" + _STARTER + ")",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.?!])\s+")
_LEADING_RE = re.compile(r"^(?:first|next|finally|then|and|also)\b[,\s]*", re.IGNORECASE)


def split_request(text: str, max_steps: int = 5) -> list[str]:
    """Oru request ah steps ah pirikkum. Pirikka mudiyala na [text] (1 step)."""
    text = " ".join(text.split())
    if not text:
        return []

    parts: list[str] = []
    for sentence in _SENTENCE_RE.split(text):
        for fragment in _SPLIT_RE.split(sentence):
            fragment = _LEADING_RE.sub("", fragment.strip(" ,;.")).strip(" ,;.")
            if len(fragment) >= 2:
                parts.append(fragment)

    if not parts:
        return [text]
    return parts[:max_steps]