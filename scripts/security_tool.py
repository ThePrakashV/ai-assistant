import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.security import crypto
from app.security.audit import get_audit


def data_files() -> list[Path]:
    memory = Path(settings.memory_dir)
    return [
        memory / "facts.faiss", memory / "facts.json",
        memory / "docs.faiss", memory / "docs.json",
        Path(settings.scheduler_file),
        Path(settings.speaker_profile),
    ]


def cmd_status(args) -> None:
    status = crypto.key_status()
    print("\n== Key ==")
    if status["available"]:
        print(f"  available: yes | source: {status['source']} | fingerprint: {status['fingerprint']}")
    else:
        print(f"  available: NO\n  {status['error']}")

    print("\n== Files ==")
    for path in data_files():
        print(f"  {crypto.file_state(path):10} {path}")

    print("\n== Settings ==")
    print(f"  ENCRYPT_AT_REST : {settings.encrypt_at_rest}")
    print(f"  OFFLINE_MODE    : {settings.offline_mode}")
    print(f"  DISABLED_SKILLS : {settings.disabled_skills or '(none)'}")
    print(f"  API_TOKEN       : {'set' if settings.api_token else 'NOT set'}")
    print(f"  AUDIT_LOG_TEXT  : {settings.audit_log_text}")
    print(f"  MLFLOW_LOG_TEXT : {settings.mlflow_log_text}")
    print(f"  SPEAKER_MODE    : {settings.speaker_mode}")

    result = get_audit().verify()
    print("\n== Audit log ==")
    print(f"  {settings.audit_file}: {result}")


def cmd_migrate(args) -> None:
    """Pazhaya plain files ah encrypt pannum (server nirutthittu run pannanum)."""
    if not settings.encrypt_at_rest:
        print("ENCRYPT_AT_REST=false. .env la true pannittu thirumba run pannu.")
        return

    targets = [path for path in data_files() if crypto.file_state(path) == "plaintext"]
    if not targets:
        print("Plain files illa. (Ellaam already encrypted, illa files illa.)")
        return

    if not args.no_backup:
        backup = Path(settings.security_dir).parent / f"backup-plaintext-{datetime.now():%Y%m%d-%H%M%S}"
        backup.mkdir(parents=True, exist_ok=True)
        for path in targets:
            shutil.copy2(path, backup / path.name)
        print(f"Plain backup: {backup}  (ellaam OK nu confirm aana aprom idha delete pannu)")

    for path in targets:
        raw = path.read_bytes()
        crypto.write_secure(path, raw)
        if crypto.read_secure(path) != raw:
            raise RuntimeError(f"Verify fail: {path}. Backup la irundhu restore pannu.")
        print(f"  encrypted: {path}")
    print("Done.")


def cmd_verify_audit(args) -> None:
    print(get_audit().verify())


def cmd_export_key(args) -> None:
    print("\nIDHU UN MASTER KEY. Password manager la save pannu. Yaarukkum kodukkaadha.")
    print("Key poiduchu na encrypted data (voiceprint kooda) thirumba padikka mudiyaadhu.\n")
    print(crypto.export_master_key())


def cmd_import_key(args) -> None:
    source = crypto.import_master_key(args.key)
    print(f"Key restore aachu ({source}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nova security tool")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    migrate = sub.add_parser("migrate", help="plain data files ah encrypt pannu")
    migrate.add_argument("--no-backup", action="store_true", help="plain backup eduthukkaadha")
    migrate.set_defaults(func=cmd_migrate)

    sub.add_parser("verify-audit").set_defaults(func=cmd_verify_audit)
    sub.add_parser("export-key").set_defaults(func=cmd_export_key)

    restore = sub.add_parser("import-key", help="backup key restore pannu")
    restore.add_argument("key", help="export-key la vandha base64 string")
    restore.set_defaults(func=cmd_import_key)

    args = parser.parse_args()
    try:
        args.func(args)
    except crypto.KeyUnavailableError as exc:
        print(f"KEY PROBLEM: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()