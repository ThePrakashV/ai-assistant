import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.memory.long_term import get_long_term
from app.memory.short_term import ShortTermMemory
from app.memory.vector_store import VectorStore
from app.security.crypto import MAGIC, decrypt_text, encrypt_text, is_encrypted
from app.skills.scheduler import Scheduler

SECRET = "CRYPTO-TEST-SECRET-98765"
results: list[bool] = []


def check(label: str, ok: bool) -> None:
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")


def test_text() -> None:
    print("\n--- 1. Text encrypt / decrypt ---")
    token = encrypt_text(SECRET)
    check("Encrypted text la secret theriyaadhu", SECRET not in token)
    check("Decrypt panna original thirumba varum", decrypt_text(token) == SECRET)
    check("Pazhaya plain text appadiye varum", decrypt_text("plain text") == "plain text")


def test_vector_store() -> None:
    print("\n--- 2. VectorStore (FAISS) file encryption ---")
    store = VectorStore("cryptotest")
    store.add([SECRET])

    raw_index = store.index_path.read_bytes()
    raw_meta = store.meta_path.read_bytes()
    check("Disk file la secret theriyaadhu", SECRET.encode() not in raw_index + raw_meta)
    check("Rendu file um encrypted (sticker irukku)", raw_index.startswith(MAGIC) and raw_meta.startswith(MAGIC))

    reloaded = VectorStore("cryptotest")
    hits = reloaded.search(SECRET, k=1)
    check("Restart apparam decrypt aagi search work aagudhu", bool(hits) and hits[0][0]["text"] == SECRET)

    store.index_path.unlink(missing_ok=True)
    store.meta_path.unlink(missing_ok=True)


def test_redis() -> None:
    print("\n--- 3. Redis chat history encryption ---")
    stm = ShortTermMemory("cryptotest")
    if not stm._redis:
        print("[SKIP] Redis connect aagala (docker compose ps check pannunga)")
        return

    stm.append("user", SECRET)
    raw_items = stm._redis.lrange(stm.key, 0, -1)
    check("Redis la secret theriyaadhu", all(SECRET not in item for item in raw_items))
    history = stm.get()
    check("Decrypt aagi history thirumba varudhu", bool(history) and history[-1]["content"] == SECRET)
    stm.clear()


def test_real_files() -> None:
    print("\n--- 4. Un real data files ---")
    get_long_term()   # facts + docs load aagumbodhu pazhaya files auto encrypt aagum
    Scheduler()       # scheduler.json um
    folder = Path(settings.memory_dir)
    paths = [
        folder / "facts.faiss",
        folder / "facts.json",
        folder / "docs.faiss",
        folder / "docs.json",
        Path(settings.scheduler_file),
    ]
    for path in paths:
        if not path.exists():
            print(f"[----] {path} (file illa, adhu ok)")
        else:
            check(f"{path} encrypted", is_encrypted(path))


def main() -> None:
    print(f"ENCRYPT_AT_REST = {settings.encrypt_at_rest}")
    print(f"Key file        = {settings.data_key_file}")
    test_text()
    test_vector_store()
    test_redis()
    test_real_files()
    print(f"\nResult: {sum(results)} / {len(results)} PASS")


if __name__ == "__main__":
    main()