import re
from datetime import datetime
from functools import lru_cache

from app.core.config import settings
from app.memory.vector_store import VectorStore

# "remember that my passport is in the blue drawer"
REMEMBER_RE = re.compile(
    r"^(?:please\s+)?(?:remember|make a note|note)(?:\s+that)?\s+(.+)$", re.IGNORECASE
)
FORGET_RE = re.compile(
    r"^(?:please\s+)?(?:forget everything|forget all|(?:clear|delete) (?:my |your )?memory)\b",
    re.IGNORECASE,
)
RECALL_RE = re.compile(r"^what do you (?:remember|know) about me\b", re.IGNORECASE)

# Automatic ah save panna vendiya personal statements
PERSONAL_RE = re.compile(
    r"\b(my name is|call me|i live in|i am from|i'm from|i work|i study|i like|i love|"
    r"i hate|i prefer|i was born|my favou?rite|my birthday|"
    r"my (?:wife|husband|mother|father|mom|dad|brother|sister|son|daughter|friend|dog|cat)\b)",
    re.IGNORECASE,
)
QUESTION_START_RE = re.compile(
    r"^(what|where|when|who|why|how|do|does|did|can|could|is|are|will)\b", re.IGNORECASE
)

DUPLICATE_SCORE = 0.92  # idhukku mela similar na already irukku, thirumba save pannaadhu


class LongTermMemory:
    """Diary (facts) + textbook (documents). Rendum FAISS la."""

    def __init__(self) -> None:
        self.facts = VectorStore("facts")
        self.docs = VectorStore("docs")

    # ---------- Commands ----------
    def handle_command(self, text: str) -> str | None:
        """Memory commands na direct reply return pannum (LLM thevai illa). Illana None."""
        clean = text.strip()

        match = REMEMBER_RE.match(clean)
        if match:
            fact = match.group(1).strip(" .!")
            if len(fact) >= 3:
                self._store_fact(fact, source="explicit")
                return "Okay, I will remember that."

        if FORGET_RE.match(clean):
            self.facts.clear()
            return "Done. I have forgotten everything I knew about you."

        if RECALL_RE.match(clean):
            if not self.facts.records:
                return "I don't remember anything about you yet."
            items = [record["text"] for record in self.facts.records[-10:]]
            return "Here is what I remember. " + ". ".join(items) + "."

        return None

    # ---------- Automatic capture ----------
    def auto_capture(self, text: str) -> str | None:
        """'My name is Prakash' maadhiri statement ah automatic ah save pannum."""
        clean = text.strip()
        if not (8 <= len(clean) <= 200):
            return None
        if clean.endswith("?") or QUESTION_START_RE.match(clean):
            return None
        if not PERSONAL_RE.search(clean):
            return None

        fact = clean.strip(" .!")
        return fact if self._store_fact(fact, source="auto") else None

    def _store_fact(self, fact: str, source: str) -> bool:
        similar = self.facts.search(fact, k=1)
        if similar and similar[0][1] >= DUPLICATE_SCORE:
            return False  # already irukku
        self.facts.add(
            [fact], [{"source": source, "created": datetime.now().isoformat(timespec="seconds")}]
        )
        return True

    # ---------- Retrieval ----------
    def retrieve(
        self, query: str
    ) -> tuple[list[tuple[str, float]], list[tuple[str, str, float]]]:
        """(facts, doc_chunks) return pannum. Threshold ku mela irukkuradhu mattum."""
        fact_hits = [
            (record["text"], score)
            for record, score in self.facts.search(
                query, k=settings.memory_top_k, min_score=settings.fact_threshold
            )
        ]
        doc_hits = [
            (record.get("source", "doc"), record["text"], score)
            for record, score in self.docs.search(
                query, k=settings.rag_top_k, min_score=settings.rag_threshold
            )
        ]
        return fact_hits, doc_hits


@lru_cache(maxsize=1)
def get_long_term() -> LongTermMemory:
    """Oru dhadavai mattum load aagum (embedding model + FAISS files)."""
    return LongTermMemory()