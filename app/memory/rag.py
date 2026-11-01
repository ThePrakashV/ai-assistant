import re
from pathlib import Path

from app.core.config import settings
from app.memory.long_term import get_long_term

SUPPORTED_EXTENSIONS = {".txt", ".md"}


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Periya document ah chinna chunks ah pirikkum (paragraph boundary paathu).

    Analogy: Textbook ah pages ah pirikkura maadhiri. Oru page = oru chunk.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > size:
            # Oru paragraph ae romba periyadhu na character count padi vettrom (overlap oda)
            if current:
                chunks.append(current)
                current = ""
            step = max(size - overlap, 1)
            for start in range(0, len(paragraph), step):
                chunks.append(paragraph[start : start + size])
                if start + size >= len(paragraph):
                    break
            continue

        if current and len(current) + len(paragraph) + 2 > size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph

    if current:
        chunks.append(current)
    return chunks


def ingest_documents() -> tuple[int, int]:
    """data/docs la irukkura ellaa .txt/.md files ah index pannum. (files, chunks) return."""
    memory = get_long_term()
    memory.docs.clear()  # ovvoru dhadavayum fresh ah rebuild (duplicate varaadhu)

    folder = Path(settings.docs_dir)
    files = sorted(
        p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    total_chunks = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        metas = [{"source": path.name, "chunk": i} for i in range(len(chunks))]
        memory.docs.add(chunks, metas)
        total_chunks += len(chunks)
        print(f"  {path.name}: {len(chunks)} chunks")

    return len(files), total_chunks