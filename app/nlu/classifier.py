import time

from app.core.config import settings
from app.memory.embedder import embed, get_embedder
from app.nlu.intents import FALLBACK_INTENT, INTENT_EXAMPLES


class IntentClassifier:
    """Sentence ah vector (coordinates) ah maathi, nerukkamana example ah kandupidikkum."""

    def __init__(self) -> None:
        start = time.time()
        get_embedder()  # Phase 7 oda same embedding model share (thirumba load aagaadhu)

        self.labels: list[str] = []
        texts: list[str] = []
        for intent, examples in INTENT_EXAMPLES.items():
            for example in examples:
                self.labels.append(intent)
                texts.append(example)

        # Ellaa examples um oru dhadavai mattum vector ah maathi vechikkurom
        self.example_vecs = embed(texts)
        print(
            f"Intent classifier ready in {time.time() - start:.1f}s "
            f"({len(texts)} examples, {len(INTENT_EXAMPLES)} intents)"
        )

    def classify(self, text: str) -> tuple[str, float, list[tuple[str, float]]]:
        """(intent, confidence, top3) return pannum."""
        vec = embed([text])[0]
        similarities = self.example_vecs @ vec  # ovvoru example oda similarity

        # Ovvoru intent ku adhula irukkura best example oda score
        best: dict[str, float] = {}
        for label, score in zip(self.labels, similarities):
            if score > best.get(label, -1.0):
                best[label] = float(score)

        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
        intent, confidence = ranked[0]

        if confidence < settings.intent_threshold:
            intent = FALLBACK_INTENT  # puriyala na normal LLM chat

        return intent, round(confidence, 3), [(k, round(v, 3)) for k, v in ranked[:3]]