"""
Intel HEX in and out, for the firmware Dirtywave ships as .hex (M8 Headless, and the TyUploader builds).

`read()` turns a HEX file into one flat image starting at its lowest address, gaps filled with 0xFF (erased
flash), and remembers which bytes the file covered. `write()` emits every covered byte plus any byte that is no
longer 0xFF, so a patch into a cave the stock file skipped still reaches the board, and an unpatched image
writes back the same records the stock file had. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class IHexError(Exception):
    pass


@dataclass
class HexImage:
    base: int
    data: bytearray
    covered: bytearray            # 1 where the file supplied the byte
    start: Optional[int] = None   # type-05 start linear address, if any


def read(path_or_text) -> HexImage:
    text = path_or_text
    if not isinstance(text, str) or "\n" not in text and not text.startswith(":"):
        with open(path_or_text, "r", encoding="ascii") as f:
            text = f.read()
    chunks = {}
    upper = 0
    start = None
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if line[0] != ":":
            raise IHexError(f"line {n}: no ':'")
        rec = bytes.fromhex(line[1:])
        if (sum(rec) & 0xFF) != 0:
            raise IHexError(f"line {n}: checksum")
        count, addr, typ = rec[0], (rec[1] << 8) | rec[2], rec[3]
        body = rec[4:4 + count]
        if len(body) != count:
            raise IHexError(f"line {n}: short record")
        if typ == 0x00:
            chunks[upper + addr] = body
        elif typ == 0x01:
            break
        elif typ == 0x02:
            upper = int.from_bytes(body, "big") << 4
        elif typ == 0x04:
            upper = int.from_bytes(body, "big") << 16
        elif typ == 0x05:
            start = int.from_bytes(body, "big")
        elif typ == 0x03:
            pass
        else:
            raise IHexError(f"line {n}: record type {typ:02X}")
    if not chunks:
        raise IHexError("no data records")
    lo = min(chunks)
    hi = max(a + len(b) for a, b in chunks.items())
    data = bytearray(b"\xFF" * (hi - lo))
    covered = bytearray(hi - lo)
    for a, b in chunks.items():
        data[a - lo:a - lo + len(b)] = b
        covered[a - lo:a - lo + len(b)] = b"\x01" * len(b)
    return HexImage(base=lo, data=data, covered=covered, start=start)


HEADLESS_MODEL = 0     # M8Firmware.model for an image read from .hex (M8 Headless)


def to_firmware(img: HexImage):
    """An M8Firmware view of a HEX image (the headless firmware has no M8FW container: model 0)."""
    from dirtyloader.m8fw import M8Firmware
    return M8Firmware(version=HEADLESS_MODEL << 16, load_addr=img.base, payload=bytearray(img.data))


def _rec(typ: int, addr: int, body: bytes) -> str:
    r = bytes([len(body), (addr >> 8) & 0xFF, addr & 0xFF, typ]) + body
    return ":" + (r + bytes([(-sum(r)) & 0xFF])).hex().upper()


def write(img: HexImage, data: Optional[bytes] = None, width: int = 16) -> str:
    """HEX text for `data` (default img.data) laid at img.base, keeping the stock file's coverage."""
    data = bytes(img.data if data is None else data)
    if len(data) != len(img.data):
        raise IHexError("image length changed; HEX images are fixed-size")
    out = []
    upper = None
    i = 0
    n = len(data)
    while i < n:
        if not (img.covered[i] or data[i] != 0xFF):
            i += 1
            continue
        addr = img.base + i
        # a record never crosses a 64 KB boundary or a gap, and starts aligned like the stock files
        end = min(n, i + width - (addr % width), (addr | 0xFFFF) + 1 - img.base)
        j = i
        while j < end and (img.covered[j] or data[j] != 0xFF):
            j += 1
        if (addr >> 16) != upper:
            upper = addr >> 16
            out.append(_rec(0x04, 0, upper.to_bytes(2, "big")))
        out.append(_rec(0x00, addr & 0xFFFF, data[i:j]))
        i = j
    if img.start is not None:
        out.append(_rec(0x05, 0, img.start.to_bytes(4, "big")))
    out.append(_rec(0x01, 0, b""))
    return "\n".join(out) + "\n"
