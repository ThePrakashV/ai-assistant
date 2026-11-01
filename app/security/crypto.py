import base64
import hashlib
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

MAGIC = b"NOVAENC1:"                 # encrypted file oda aarambam (plain file ah kandupidikka)
KEYRING_SERVICE = "nova-assistant"
KEYRING_USER = "master-key"

_source = "unknown"


class KeyUnavailableError(RuntimeError):
    """Master key kidaikkala / thappu. Encrypted data ah padikka mudiyaadhu."""


def _security_dir() -> Path:
    path = Path(settings.security_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fingerprint(key: bytes) -> str:
    return hashlib.sha256(b"nova-fingerprint" + key).hexdigest()[:12]


# ===================== Key storage =====================
def _keyring_get() -> bytes | None:
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        return base64.b64decode(value) if value else None
    except Exception:
        return None


def _keyring_set(key: bytes) -> bool:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, base64.b64encode(key).decode())
        return _keyring_get() == key
    except Exception:
        return False


def _file_get() -> bytes | None:
    path = _security_dir() / "master.key"
    try:
        return base64.b64decode(path.read_text(encoding="ascii").strip()) if path.exists() else None
    except Exception:
        return None


def _store_key(key: bytes) -> str:
    """Key ah save pannum. 'keyring' (Windows Credential Manager), illana 'file'."""
    if _keyring_set(key):
        return "keyring"
    (_security_dir() / "master.key").write_text(base64.b64encode(key).decode(), encoding="ascii")
    print(
        "[Security] OS keyring kidaikkala. Key data/security/master.key la save aachu. "
        "Idha data folder oda sync / backup pannaadhinga (key + data ore idathula irundha payan illa)."
    )
    return "file"


@lru_cache(maxsize=1)
def _master_key() -> bytes:
    global _source
    marker = _security_dir() / "key.id"

    key = _keyring_get()
    _source = "keyring"
    if key is None:
        key = _file_get()
        _source = "file"

    if key is None:
        if marker.exists():
            # Key irundhuchu aana ippo illa. Puthu key create panna encrypted data permanent ah poidum
            raise KeyUnavailableError(
                "Master key kidaikkala (Credential Manager / master.key illa), aana munnaadi irundhuchu. "
                "Backup la irundhu restore pannu: python scripts\\security_tool.py import-key <key>"
            )
        key = secrets.token_bytes(32)
        _source = _store_key(key)
        marker.write_text(_fingerprint(key), encoding="ascii")
        print(f"[Security] Puthu master key create aachu ({_source}). 'security_tool.py export-key' la backup eduthuko.")
        return key

    fingerprint = _fingerprint(key)
    if marker.exists():
        if marker.read_text(encoding="ascii").strip() != fingerprint:
            raise KeyUnavailableError("Master key maariduchu (data/security/key.id match aagala). Sariyaana key restore pannu.")
    else:
        marker.write_text(fingerprint, encoding="ascii")
    return key


def _derive(info: bytes) -> bytes:
    """Ore master key la irundhu vera vera purpose ku thani keys (encryption, audit)."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(_master_key())


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive(b"nova-encryption-v1")))


def audit_key() -> bytes:
    return _derive(b"nova-audit-v1")


# ===================== Encrypt / decrypt =====================
def is_encrypted(blob: bytes) -> bool:
    return blob.startswith(MAGIC)


def encrypt_bytes(data: bytes) -> bytes:
    return MAGIC + _fernet().encrypt(data)


def decrypt_bytes(blob: bytes) -> bytes:
    """Encrypted na decrypt. Plain (pazhaya) file na apdiye return (migration ku)."""
    if not is_encrypted(blob):
        return blob
    try:
        return _fernet().decrypt(blob[len(MAGIC):])
    except InvalidToken as exc:
        raise KeyUnavailableError("Decrypt aagala: key thappu illa file sedhamadaindhirukku.") from exc


def read_secure(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return decrypt_bytes(path.read_bytes())


def write_secure(path: Path, data: bytes) -> None:
    """Atomic write (tmp file -> replace), so beech la crash aanaalum file sedhaadhu."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_bytes(data) if settings.encrypt_at_rest else data
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def file_state(path: Path) -> str:
    """'missing' / 'encrypted' / 'plaintext'"""
    if not path.exists():
        return "missing"
    with open(path, "rb") as handle:
        return "encrypted" if handle.read(len(MAGIC)) == MAGIC else "plaintext"


# ===================== Status / backup =====================
def key_status() -> dict:
    try:
        key = _master_key()
        return {"available": True, "source": _source, "fingerprint": _fingerprint(key)}
    except KeyUnavailableError as exc:
        return {"available": False, "error": str(exc)}


def export_master_key() -> str:
    return base64.b64encode(_master_key()).decode()


def import_master_key(encoded: str) -> str:
    key = base64.b64decode(encoded.strip())
    if len(key) != 32:
        raise ValueError("Key 32 bytes irukkanum (base64 string thappu).")
    source = _store_key(key)
    (_security_dir() / "key.id").write_text(_fingerprint(key), encoding="ascii")
    _master_key.cache_clear()
    _fernet.cache_clear()
    return source