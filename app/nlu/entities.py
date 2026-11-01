import json
import re

import ollama

from app.core.config import settings
from app.nlu.intents import INTENT_SLOTS

_client = ollama.AsyncClient(host=settings.ollama_base_url)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60,
}
_UNIT_SECONDS = {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}

# Idhu free-text slots: value user sentence la nijamave irukkanum.
# (expression, currency code, action, change, setting maadhiri LLM derive panra slots idhula illa)
GROUNDED_SLOTS = {
    "location", "date", "label", "task", "time",
    "query", "song_or_artist", "platform", "room", "duration",
}


def _replace_number_words(text: str) -> str:
    for word, number in sorted(_WORD_NUMBERS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{word}\b", str(number), text)
    return text


def parse_duration_seconds(text: str) -> int | None:
    """'5 minutes', 'two hours', 'an hour and 30 minutes' -> seconds. Puriyala na None."""
    text = _replace_number_words(text.lower())
    text = re.sub(r"\b(an|a)\s+hour", "1 hour", text)
    text = text.replace("half an hour", "30 minutes")

    total = 0.0
    found = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(hour|hr|minute|min|second|sec)", text):
        total += float(value) * _UNIT_SECONDS[unit]
        found = True
    return int(total) if found else None


def _normalize(text: str) -> list[str]:
    text = _replace_number_words(text.lower())
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return text.split()


def _token_in(token: str, text_tokens: list[str]) -> bool:
    if token in text_tokens:
        return True
    # laptop / laptops maadhiri singular-plural difference ku
    return len(token) > 3 and any(
        len(t) > 3 and (t.startswith(token) or token.startswith(t)) for t in text_tokens
    )


def is_grounded(value: str, text: str) -> bool:
    """LLM kudutha value oda ellaa words um user sentence la irukka nu check."""
    value_tokens = _normalize(value)
    text_tokens = _normalize(text)
    return bool(value_tokens) and all(_token_in(tok, text_tokens) for tok in value_tokens)


def _build_messages(intent: str, text: str) -> list[dict]:
    spec = INTENT_SLOTS[intent]
    slot_lines = "\n".join(f"- {name}: {desc}" for name, desc in spec["slots"].items())
    example_text, example_json = spec["example"]

    system = (
        "You extract details from a user's request to a voice assistant.\n"
        f"The request intent is: {intent}\n"
        "Fill these slots (use null if the user did not mention it):\n"
        f"{slot_lines}\n"
        "Rules:\n"
        "- Reply with ONLY a JSON object that has exactly these keys.\n"
        "- Copy values from the user's words. Never invent values.\n"
        "- If the user did not say a value, use null. Do NOT reuse values from the example.\n"
        "- Values must be strings or null."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": example_text},
        {"role": "assistant", "content": json.dumps(example_json)},
        {"role": "user", "content": text},
    ]


async def extract_entities(intent: str, text: str) -> dict:
    """Intent ku sonna slots ah LLM la irundhu eduthu, clean + verify panni return pannum."""
    spec = INTENT_SLOTS.get(intent)
    if not spec:
        return {}

    try:
        response = await _client.chat(
            model=settings.ollama_model,
            messages=_build_messages(intent, text),
            format="json",                  # LLM ah JSON mattum kudukka sollum
            options={"temperature": 0},     # random illaama, ore answer
        )
        data = json.loads(response["message"]["content"])
    except (json.JSONDecodeError, KeyError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    # Namma slots mattum vechikkurom. LLM extra keys kuduthaa ignore.
    entities: dict = {}
    for slot in spec["slots"]:
        value = data.get(slot)
        if value is None or str(value).strip().lower() in {"", "null", "none"}:
            entities[slot] = None
            continue

        value = str(value).strip()

        # Grounding check: user sollaadha value (example la irundhu copy) na None
        if slot in GROUNDED_SLOTS and not is_grounded(value, text):
            entities[slot] = None
        else:
            entities[slot] = value

    # Timer ku: "5 minutes" -> 300 seconds (code la accurate ah)
    if intent == "set_timer":
        source = entities.get("duration") or text
        entities["duration_seconds"] = parse_duration_seconds(source)

    return entities