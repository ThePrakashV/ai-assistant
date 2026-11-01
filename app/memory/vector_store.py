import json
import os
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import faiss
import numpy as np

from app.core.config import settings
from app.memory.embedder import embed, embed_dim
from app.security.crypto import read_secure, write_secure


class VectorStore:
    """Librarian. Texts ah vector ah maathi FAISS la vechikkum, artham vechi thedum.
    Disk la save aagum (ENCRYPT_AT_REST=true na encrypted), so script restart panninaalum irukkum."""

    def __init__(self, name: str) -> None:
        folder = Path(settings.memory_dir)
        folder.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.index_path = folder / f"{name}.faiss"
        self.meta_path = folder / f"{name}.json"

        self.records: list[dict] = []
        # IndexFlatIP = Inner Product. Normalized vectors na idhu cosine similarity
        self.index = faiss.IndexFlatIP(embed_dim())
        self._load()

    def _load(self) -> None:
        index_bytes = read_secure(self.index_path)   # plain / encrypted rendum padikkum
        meta_bytes = read_secure(self.meta_path)
        if index_bytes is None or meta_bytes is None:
            return

        index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype="uint8"))
        records = json.loads(meta_bytes.decode("utf-8"))
        if index.ntotal == len(records):
            self.index, self.records = index, records
        else:
            print(f"[Memory] '{self.name}' files mismatch, empty ah start pannurom.")

    def save(self) -> None:
        write_secure(self.index_path, faiss.serialize_index(self.index).tobytes())
        write_secure(
            self.meta_path, json.dumps(self.records, ensure_ascii=False, indent=2).encode("utf-8")
        )

    @property
    def count(self) -> int:
        return len(self.records)

    def add(self, texts: list[str], metas: list[dict] | None = None) -> None:
        if not texts:
            return
        metas = metas or [{} for _ in texts]
        self.index.add(embed(texts))
        for text, meta in zip(texts, metas):
            self.records.append({"text": text, **meta})
        self.save()

    def search(
        self, query: str, k: int = 3, min_score: float = 0.0
    ) -> list[tuple[dict, float]]:
        """(record, score) list return pannum. score 1.0 = ore artham."""
        if self.index.ntotal == 0:
            return []
        k = min(k, self.index.ntotal)
        scores, ids = self.index.search(embed([query]), k)
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx >= 0 and score >= min_score:
                results.append((self.records[idx], float(score)))
        return results

    def clear(self) -> None:
        self.index = faiss.IndexFlatIP(embed_dim())
        self.records = []
        self.save()