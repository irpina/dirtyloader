"""
Find the addresses of one build of the M8 firmware again in a later build of the same model.

Two builds of the same model differ by the code Dirtywave changed between them; nearly everything else moved
as a block. This maps each address an old build's bindings and device header use:

  * **code and flash data** (0x60000000.., and ITCM run addresses through their flash copy): the bytes around
    the address are compared with every place in the new image after both are normalised (the offsets of
    PC-relative branches, literal loads and adr zeroed, and literal words that hold an address zeroed). Each
    window of WINDOW bytes within REACH of the address that occurs exactly once in the new image votes for a
    delta; the address moves by the delta most windows give.
  * **RAM** (DTCM / OCRAM): through the literals that name it. Every aligned word in the old image's code and
    flash data that holds the address (or the nearest base up to NEAR bytes below it) is found again by the
    mapping above, and the word read there in the new image, plus the same offset, is a vote.

Each result carries its evidence: how many windows (or literals) agreed out of how many voted, and how many
normalised bytes from the address on are the same. An address with no majority is reported as unmapped.

    python -m dirtyloader.re.portmap <old .bin> <new .bin> 0x6004C13C 0x20015458 0x0002464C ...
"""
from __future__ import annotations

import struct
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover

WINDOW = 24          # bytes per window
REACH = 96           # windows start within this many bytes of the address
NEAR = 0x400         # a literal up to this far below a RAM address votes for it


def is_ram(a: int) -> bool:
    return 0x20000000 <= a < 0x20080000 or 0x20200000 <= a < 0x20280000


def normalise(p: bytes) -> bytes:
    """The image with what moves between builds zeroed: PC-relative offsets and address literals."""
    out = bytearray(p)
    n = len(p) & ~1
    for o in range(0, n - 3, 4):                      # literal words that hold an address
        v = struct.unpack_from("<I", p, o)[0]
        if 0x60000000 <= v < 0x60400000 or is_ram(v) or (0x100 < v < 0x40000 and v & 1):
            out[o:o + 4] = b"\0\0\0\0"
    i = 0
    while i < n - 2:
        h = p[i] | p[i + 1] << 8
        if h & 0xF800 in (0xE800, 0xF000, 0xF800):    # 32-bit
            lo = p[i + 2] | p[i + 3] << 8
            if h & 0xF800 == 0xF000 and lo & 0x8000:                  # b.w / bl / blx / b<c>.w
                struct.pack_into("<HH", out, i, h & 0xF800 if lo & 0x1000 else h & 0xFBC0, lo & 0xD000)
            elif h & 0xFF7F == 0xF85F or h & 0xFE7F == 0xF81F or h & 0xFE7F == 0xF91F:   # ldr(b/h/sb/sh).w [pc]
                struct.pack_into("<HH", out, i, h, lo & 0xF000)
            elif h & 0xFF3F == 0xED1F:                                # vldr [pc]
                struct.pack_into("<HH", out, i, h, lo & 0xFF00)
            elif h & 0xFBFF in (0xF20F, 0xF2AF):                      # adr.w
                struct.pack_into("<HH", out, i, h & 0xFBFF, lo & 0x0F00)
            elif h & 0xFF7F in (0xE95F, 0xE9DF):                      # ldrd [pc]
                struct.pack_into("<HH", out, i, h, lo & 0xFF00)
            i += 4
            continue
        if h & 0xF800 == 0x4800 or h & 0xF800 == 0xA000:              # ldr [pc] / adr
            struct.pack_into("<H", out, i, h & 0xFF00)
        elif h & 0xF000 == 0xD000 and h & 0x0F00 < 0x0E00:            # b<c>
            struct.pack_into("<H", out, i, h & 0xFF00)
        elif h & 0xF800 == 0xE000:                                    # b
            struct.pack_into("<H", out, i, 0xE000)
        elif h & 0xF500 == 0xB100:                                    # cbz / cbnz
            struct.pack_into("<H", out, i, h & 0xFD07)
        i += 2
    return bytes(out)


@dataclass
class Image:
    fw: M8Firmware
    norm: bytes = b""
    index: Dict[bytes, int] = field(default_factory=dict)       # window -> offset, or -1 when it repeats
    itcm_load: int = 0                                          # file offsets of the startup's two copies
    itcm_size: int = 0
    data_load: int = 0
    data_size: int = 0

    @classmethod
    def load(cls, path: str, with_index: bool = False) -> "Image":
        if path.lower().endswith(".hex"):                 # headless: Dirtywave ships an Intel HEX
            from dirtyloader import ihex
            fw = ihex.to_firmware(ihex.read(open(path, encoding="ascii").read()))
        else:
            fw = M8Firmware.from_file(path)
        mm = recover(fw)
        im = cls(fw=fw, norm=normalise(bytes(fw.payload)))
        im.itcm_load, im.itcm_size = mm.itcm.src - fw.load_addr, mm.itcm.size
        d = next(c for c in mm.copies if c.dest == 0x20000000)
        im.data_load, im.data_size = d.src - fw.load_addr, d.size
        if with_index:
            idx: Dict[bytes, int] = {}
            nb = im.norm
            for o in range(0, len(nb) - WINDOW, 2):
                w = nb[o:o + WINDOW]
                if w.count(0) > WINDOW // 2 or w.count(0xFF) > WINDOW // 2:
                    continue
                idx[w] = -1 if w in idx else o
            im.index = idx
        return im

    def word(self, off: int) -> int:
        return struct.unpack_from("<I", self.fw.payload, off)[0]


@dataclass
class Result:
    old: int
    new: Optional[int]
    how: str
    votes: int = 0
    of: int = 0
    same: int = 0            # normalised bytes from the address on that are the same (code); exact literals (RAM)
    note: str = ""

    @property
    def strength(self) -> str:
        if self.new is None:
            return "none"
        if self.how == "fixed":
            return "S1"
        if self.votes == self.of and self.votes >= 3:
            return "S1"
        return "S2" if self.votes * 2 > self.of else "weak"

    def evidence(self) -> str:
        if self.how == "fixed":
            return self.note
        if self.how in ("ram", "data"):
            return f"{self.votes}/{self.of} literals agree ({self.same} name it exactly; {self.note})"
        return f"{self.votes}/{self.of} unique windows agree; {self.same} normalised bytes on are the same"


def map_offset(old: Image, new: Image, off: int, reach: int = REACH) -> Tuple[Optional[int], int, int, int]:
    """(new offset, agreeing windows, voting windows, equal normalised bytes from the offset on)."""
    deltas: Counter = Counter()
    for k in range(-reach, reach + 1, 2):
        o = off + k
        if o < 0 or o + WINDOW > len(old.norm):
            continue
        h = new.index.get(old.norm[o:o + WINDOW])
        if h is not None and h >= 0:
            deltas[h - o] += 1
    if not deltas:
        return None, 0, 0, 0
    d, v = deltas.most_common(1)[0]
    total = sum(deltas.values())
    if v * 2 <= total:
        return None, v, total, 0
    nb = off + d
    same = 0
    while off + same < len(old.norm) and nb + same < len(new.norm) and same < 64 and \
            old.norm[off + same] == new.norm[nb + same]:
        same += 1
    return nb, v, total, same


def map_code(old: Image, new: Image, addr: int) -> Result:
    """Code or flash data by its bytes; when no window near it is unique, further out (REACH x 4, x 16)."""
    thumb, a = addr & 1, addr & ~1
    itcm = a < 0x40000                                # an ITCM run address: through its flash copy
    off = a + old.itcm_load if itcm else a - old.fw.load_addr
    for reach in (REACH, REACH * 4, REACH * 16):
        nb, v, t, s = map_offset(old, new, off, reach)
        if nb is not None and (reach == REACH or v >= 3):
            break
        nb = None
    if nb is not None:
        nb = (nb - new.itcm_load) if itcm else nb + new.fw.load_addr
    r = Result(addr, None if nb is None else nb | thumb, "itcm" if itcm else "flash", v, t, s)
    if reach != REACH:
        r.note = f"windows within {reach} bytes"
    return r


def literal_sites(im: Image, lo: int, hi: int) -> List[Tuple[int, int]]:
    """(offset, value) of every aligned word before the .data image (code and flash data) with lo <= value < hi."""
    p = im.fw.payload
    return [(o, v) for o in range(0, im.data_load, 4) for v in (struct.unpack_from("<I", p, o)[0],) if lo <= v < hi]


def map_ram(old: Image, new: Image, addr: int, sites=None, how: str = "ram") -> Result:
    """A RAM address (or flash data) through the literals that name it, or the nearest base below it."""
    lits = [(o, v) for o, v in (sites if sites is not None else literal_sites(old, addr - NEAR, addr + 1))
            if addr - NEAR <= v <= addr]
    if not lits:
        return Result(addr, None, how, note="no literal names it")
    best = max(v for _, v in lits)                     # the nearest base below it (the address, when one names it)
    votes: Counter = Counter()
    for o, v in lits:
        if v != best:
            continue
        nb, _, _, _ = map_offset(old, new, o)
        if nb is None or nb % 4:
            continue
        nv = new.word(nb)
        if is_ram(nv) or (how != "ram" and 0x60000000 <= nv < 0x60000000 + len(new.fw.payload)):
            votes[nv + (addr - v)] += 1
    if not votes:
        return Result(addr, None, how, note=f"{len(lits)} literals, none found again")
    na, v = votes.most_common(1)[0]
    t = sum(votes.values())
    exact = sum(1 for _, x in lits if x == addr)
    note = "exact" if best == addr else f"base 0x{best:08X} + 0x{addr - best:X}"
    if v * 2 <= t:
        return Result(addr, None, how, v, t, exact, note=f"no majority: {dict(votes)}")
    return Result(addr, na, how, v, t, exact, note=note)


def map_any(old: Image, new: Image, addr: int, ram_sites=None) -> Result:
    if is_ram(addr):
        return map_ram(old, new, addr, ram_sites)
    if 0x60000000 <= addr < 0x60000000 + len(old.fw.payload) or addr < 0x40000:
        r = map_code(old, new, addr)
        if r.new is None and addr >= 0x60000000:      # flash data no window finds: through its literals
            d = map_ram(old, new, addr, how="data")
            if d.new is not None:
                return d
        return r
    return Result(addr, addr, "fixed", note="outside the image and RAM: kept")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 3:
        raise SystemExit(__doc__)
    old, new = Image.load(argv[0]), Image.load(argv[1], with_index=True)
    for s in argv[2:]:
        r = map_any(old, new, int(s, 16))
        n = f"0x{r.new:08X}" if r.new is not None else "-"
        print(f"0x{r.old:08X} -> {n:10} {r.strength:4} {r.how:5} {r.evidence()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
