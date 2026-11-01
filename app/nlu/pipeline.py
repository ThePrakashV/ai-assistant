import time

from app.nlu.classifier import IntentClassifier
from app.nlu.entities import extract_entities
from app.nlu.intents import INTENT_SLOTS
from app.nlu.schemas import NLUResult


class NLU:
    """Sentence -> (intent + entities). Phase 8 skills idha thaan use pannum."""

    def __init__(self) -> None:
        self.classifier = IntentClassifier()

    async def understand(self, text: str) -> NLUResult:
        # Step 1: Edha kekkura (vegam, LLM illa)
        start = time.perf_counter()
        intent, confidence, top = self.classifier.classify(text)
        classify_ms = (time.perf_counter() - start) * 1000

        # Step 2: Details eduthal (slots irukkura intents ku mattum LLM call)
        entities: dict = {}
        extract_ms = 0.0
        if intent in INTENT_SLOTS:
            start = time.perf_counter()
            entities = await extract_entities(intent, text)
            extract_ms = (time.perf_counter() - start) * 1000

        return NLUResult(
            text=text,
            intent=intent,
            confidence=confidence,
            top_matches=top,
            entities=entities,
            classify_ms=round(classify_ms, 1),
            extract_ms=round(extract_ms, 1),
        )