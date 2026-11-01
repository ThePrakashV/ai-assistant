from typing import Any

from pydantic import BaseModel, Field


class NLUResult(BaseModel):
    """NLU oda final output. Phase 8 la skills ku indha object thaan pogum."""

    text: str
    intent: str
    confidence: float
    top_matches: list[tuple[str, float]] = Field(default_factory=list)
    # Slot name -> value. Sollaadha slot ku None (later "edhu venum?" nu thirumba kekkalam)
    entities: dict[str, Any] = Field(default_factory=dict)
    classify_ms: float = 0.0
    extract_ms: float = 0.0