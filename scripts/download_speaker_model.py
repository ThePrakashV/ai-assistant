import os
import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings

MIN_BYTES = 15_000_000  # model ~26 MB. Idhukku kammi na download poorna aagala

SOURCES = [
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/{name}",
    "https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/{name}",
]


def download(url: str, destination: Path) -> bool:
    temp = destination.with_name(destination.name + ".part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
            if response.status_code != 200:
                print(f"  HTTP {response.status_code}")
                return False
            total = int(response.headers.get("content-length", 0))
            done, shown = 0, 0
            with open(temp, "wb") as handle:
                for chunk in response.iter_bytes(1024 * 256):
                    handle.write(chunk)
                    done += len(chunk)
                    if done - shown >= 2_000_000:
                        shown = done
                        percent = f" ({done * 100 // total}%)" if total else ""
                        print(f"  {done / 1e6:.1f} MB{percent}", end="\r")
        print()
    except httpx.HTTPError as exc:
        print(f"  Network error: {type(exc).__name__}: {exc}")
        return False

    if temp.stat().st_size < MIN_BYTES:
        print(f"  File chinnadhu ({temp.stat().st_size} bytes), download sariyaa aagala.")
        temp.unlink(missing_ok=True)
        return False

    os.replace(temp, destination)
    return True


def main() -> None:
    destination = Path(settings.speaker_model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.stat().st_size >= MIN_BYTES:
        print(f"Already irukku: {destination} ({destination.stat().st_size / 1e6:.1f} MB)")
    else:
        for template in SOURCES:
            url = template.format(name=destination.name)
            print(f"Downloading: {url}")
            if download(url, destination):
                break
        else:
            print(
                "\nEdhuvum work aagala. Browser la manually download panni "
                f"{destination} la vechuko:\n  " + SOURCES[0].format(name=destination.name)
            )
            sys.exit(1)

    # Model load aagudha nu check
    import onnxruntime as ort

    session = ort.InferenceSession(str(destination), providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()[0]
    outputs = session.get_outputs()[0]
    print(f"\nModel OK: {destination}")
    print(f"  input : {inputs.name} {inputs.shape}")
    print(f"  output: {outputs.name} {outputs.shape}")
    meta = dict(session.get_modelmeta().custom_metadata_map or {})
    print(f"  metadata: {meta if meta else '(illa, WeSpeaker defaults use pannum)'}")


if __name__ == "__main__":
    main()