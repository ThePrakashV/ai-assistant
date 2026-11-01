import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "icons"

BG = (15, 20, 25)
CIRCLE = (52, 152, 219)
WHITE = (255, 255, 255)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def mix(a, b, t: float):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def distance_to_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = clamp(((px - ax) * dx + (py - ay) * dy) / length_sq) if length_sq else 0.0
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def make_png(size: int) -> bytes:
    """Dark background + blue circle + white 'N'. 'N' center la (maskable safe zone kulla)."""
    cx = cy = size / 2
    radius = size * 0.36
    stroke = size * 0.075
    left, right, top, bottom = size * 0.35, size * 0.65, size * 0.32, size * 0.68
    segments = [
        (left, bottom, left, top),
        (left, top, right, bottom),
        (right, bottom, right, top),
    ]

    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter type 0
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            color = mix(BG, CIRCLE, clamp(radius - math.hypot(px - cx, py - cy) + 0.5))
            nearest = min(distance_to_segment(px, py, *seg) for seg in segments)
            color = mix(color, WHITE, clamp(stroke / 2 - nearest + 0.5))
            row.extend(color)
        rows.append(bytes(row))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        path = OUT / f"icon-{size}.png"
        path.write_bytes(make_png(size))
        print(f"Created {path}")


if __name__ == "__main__":
    main()