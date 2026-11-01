import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.memory.rag import ingest_documents


def main():
    print(f"Documents folder: {settings.docs_dir}")
    files, chunks = ingest_documents()
    if files == 0:
        print("Edhuvum .txt / .md file kidaikkala. data\\docs la files podunga.")
        return
    print(f"\nDone. {files} file(s), {chunks} chunk(s) indexed.")


if __name__ == "__main__":
    main()