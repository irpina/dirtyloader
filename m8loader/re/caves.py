"""
Code-cave survey: find contiguous runs of a fill byte in the firmware payload,
i.e. free flash the Core and code-injecting mods can use.

The M8 payload is densely packed (only ~2% 0xFF), so caves are scarce and mostly
live in the alignment gaps around the boot headers. This tool ranks them.

Usage:
    python -m m8loader.re.caves <stock.bin> [--fill 0xFF] [--min 64]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from m8loader.m8fw import M8Firmware
from m8loader.re.boot import LOAD


@dataclass
class Cave:
    offset: int          # payload offset
    length: int
    fill: int

    @property
    def addr(self) -> int:
        return LOAD + self.offset

    def __str__(self) -> str:
        return (f"0x{self.addr:08X}  (offset 0x{self.offset:06X})  "
                f"{self.length:>6} bytes  fill=0x{self.fill:02X}")


def find_caves(payload: bytes, fill: int, min_len: int = 64) -> List[Cave]:
    caves: List[Cave] = []
    n = len(payload)
    i = 0
    while i < n:
        if payload[i] != fill:
            i += 1
            continue
        j = i + 1
        while j < n and payload[j] == fill:
            j += 1
        if j - i >= min_len:
            caves.append(Cave(offset=i, length=j - i, fill=fill))
        i = j
    return caves


def survey(payload: bytes, min_len: int = 64) -> List[Cave]:
    caves = find_caves(payload, 0xFF, min_len) + find_caves(payload, 0x00, min_len)
    caves.sort(key=lambda c: c.length, reverse=True)
    return caves


def _main(argv=None) -> int:
    import sys
    args = argv or sys.argv[1:]
    path = args[0]
    fill = None
    min_len = 64
    for i, a in enumerate(args):
        if a == "--fill":
            fill = int(args[i + 1], 0)
        elif a == "--min":
            min_len = int(args[i + 1], 0)

    fw = M8Firmware.from_file(path, verify=True)
    payload = bytes(fw.payload)
    if fill is not None:
        caves = find_caves(payload, fill, min_len)
    else:
        caves = survey(payload, min_len)
    caves.sort(key=lambda c: c.length, reverse=True)

    total = sum(c.length for c in caves)
    print(f"caves >= {min_len} bytes: {len(caves)}, total {total} bytes free\n")
    for c in caves[:25]:
        print(" ", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
