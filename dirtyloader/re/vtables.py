"""
C++ vtable finder.

The M8 firmware is C++ built without RTTI, so every vtable in flash is a
`{0, 0}` header (offset-to-top, null typeinfo) followed by a run of Thumb code
pointers. Finding those runs recovers the firmware's class hierarchy with no
symbols: the base `View` interface is 8 slots, list-style views 32, and the
parameter-bearing classes (the 7 instrument engines, FX objects) 46..109.

Locating a known function inside the vtables gives its virtual slot -- e.g.
every per-view input handler sits at slot +0x08.

Usage:
    python -m dirtyloader.re.vtables <stock.bin>                  # list + size histogram
    python -m dirtyloader.re.vtables <stock.bin> --find 0x6004F7DE 0x600539F6
"""
from __future__ import annotations

import argparse
import struct
from collections import Counter
from dataclasses import dataclass
from typing import List, Tuple

from dirtyloader.m8fw import M8Firmware


@dataclass
class VTable:
    addr: int            # address point (first slot)
    slots: List[int]     # Thumb code pointers (bit 0 set)

    def __len__(self) -> int:
        return len(self.slots)

    def slot(self, off: int) -> int:
        return self.slots[off // 4]


def find_vtables(fw: M8Firmware, min_slots: int = 1) -> List[VTable]:
    p = bytes(fw.payload)
    base, end = fw.load_addr, fw.load_addr + len(fw.payload)

    def word(i):
        return struct.unpack_from("<I", p, i * 4)[0]

    def code(v):
        return bool(v & 1) and base + 0x1000 <= (v & ~1) < end

    out, n, i = [], len(p) // 4, 2
    while i < n:
        if code(word(i)) and word(i - 1) == 0 and word(i - 2) == 0:
            j = i
            while j < n and code(word(j)):
                j += 1
            if j - i >= min_slots:
                out.append(VTable(addr=base + i * 4, slots=[word(k) for k in range(i, j)]))
            i = j
        else:
            i += 1
    return out


def locate(vts: List[VTable], fn: int, slack: int = 8) -> List[Tuple[VTable, int, int]]:
    """Every (vtable, slot offset, true entry) whose slot points at `fn` or up to `slack` bytes before it
    (a heuristic function start such as the first `push` often sits a few bytes past the real entry)."""
    hits = []
    for vt in vts:
        for k, v in enumerate(vt.slots):
            entry = v & ~1
            if 0 <= (fn & ~1) - entry <= slack:
                hits.append((vt, 4 * k, entry))
    return hits


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find C++ vtables in an M8 firmware image.")
    ap.add_argument("firmware")
    ap.add_argument("--find", nargs="*", default=[], help="function addresses to locate in vtables")
    a = ap.parse_args(argv)
    vts = find_vtables(M8Firmware.from_file(a.firmware, verify=True))
    if a.find:
        for f in a.find:
            fn = int(f, 16)
            hits = locate(vts, fn)
            if not hits:
                print("0x%08X: not in any vtable" % fn)
            for vt, off, entry in hits:
                print("0x%08X: vtable 0x%08X (%d slots) slot +0x%X  true entry 0x%08X" % (
                    fn, vt.addr, len(vt), off, entry))
        return 0
    print("%d vtables; size histogram (slots: count): %s" % (
        len(vts), ", ".join("%d:%d" % kv for kv in sorted(Counter(len(v) for v in vts).items()))))
    for vt in vts:
        print("0x%08X  %3d slots  +00:%08X +08:%08X" % (vt.addr, len(vt), vt.slots[0],
                                                      vt.slots[2] if len(vt) > 2 else 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
