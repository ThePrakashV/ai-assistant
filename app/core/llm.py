import asyncio
import uuid

import ollama

from app.core.config import settings
from app.memory.long_term import get_long_term
from app.memory.short_term import ShortTermMemory

# Evlo recent messages vara LLM ku anuppanum (RAM + speed ku)
MAX_HISTORY = 20

# Async client = oru user ku wait pannitu irukkum bodhu, vera user ah serve panna mudiyum
_client = ollama.AsyncClient(host=settings.ollama_base_url)


def build_system_prompt(
    facts: list[tuple[str, float]] | None = None,
    docs: list[tuple[str, str, float]] | None = None,
) -> dict:
    content = (
        f"You are {settings.assistant_name}, a helpful personal AI assistant. "
        "Keep answers short and clear. "
        "Always reply in simple English using the Roman alphabet only. "
        "Never use Tamil script. "
        "The user may write in Tanglish (Tamil written in English letters); "
        "understand it and answer in English. "
        "Never invent personal facts about the user."
    )

    if facts:
        lines = "\n".join(f"- {text}" for text, _ in facts)
        content += f"\n\nFacts the user told you earlier:\n{lines}"

    if docs:
        lines = "\n".join(
            f"[{i}] ({source}) {text}" for i, (source, text, _) in enumerate(docs, start=1)
        )
        content += (
            f"\n\nExcerpts from the user's documents:\n{lines}\n"
            "Answer using the excerpts when they are relevant. "
            "If the excerpts do not contain the answer, say you do not know."
        )

    return {"role": "system", "content": content}


class ChatSession:
    """Oru conversation. Short-term (Redis) + long-term (FAISS) memory use pannum.

    session_id same ah irundha, script restart panninaalum history thodarum (Redis irundha).
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.short = ShortTermMemory(self.session_id)

        # Debug ku: last turn la enna memory use aachu
        self.last_facts: list[tuple[str, float]] = []
        self.last_docs: list[tuple[str, str, float]] = []
        self.last_captured: str | None = None

    def reset(self) -> None:
        """Short-term history mattum clear. Long-term facts / documents apdiye irukkum."""
        self.short.clear()

    def _prepare(self, user_text: str):
        """Blocking work (embedding + FAISS). Thread la run aagum."""
        self.last_facts, self.last_docs, self.last_captured = [], [], None
        try:
            memory = get_long_term()

            canned = memory.handle_command(user_text)
            if canned is not None:
                return canned

            # Modhalil retrieve, appuram capture (same sentence thirumba retrieve aagaama irukka)
            self.last_facts, self.last_docs = memory.retrieve(user_text)
            self.last_captured = memory.auto_capture(user_text)
        except Exception as exc:
            print(f"[Memory disabled for this turn] {exc}")
        return None

    async def stream_reply(self, user_text: str):
        """LLM reply ah token token ah yield pannum."""
        canned = await asyncio.to_thread(self._prepare, user_text)

        if canned is not None:
            yield canned
            self.short.append("user", user_text)
            self.short.append("assistant", canned)
            return

        messages = (
            [build_system_prompt(self.last_facts, self.last_docs)]
            + self.short.get(MAX_HISTORY)
            + [{"role": "user", "content": user_text}]
        )

        full_reply = ""
        async for chunk in await _client.chat(
            model=settings.ollama_model, messages=messages, stream=True
        ):
            token = chunk["message"]["content"]
            full_reply += token
            yield token

        # Error illaama mudinja mattum history la save (error na user message save aagaadhu)
        self.short.append("user", user_text)
        self.short.append("assistant", full_reply)