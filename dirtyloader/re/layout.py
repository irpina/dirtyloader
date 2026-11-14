"""
Whole-image layout: classify every chunk of the flash image and merge the
result into regions -- a coarse map of where code, text, pointer tables and
other data live, independent of any disassembler's function analysis.

Chunk classes:
  fill   all 0x00 or all 0xFF
  text   mostly printable ASCII + NULs (string pools)
  ptrs   at least half the words point into the image, ITCM or DTCM (vtables,
         descriptor tables, function-pointer arrays)
  code   decodes as Thumb with a high share of ordinary instructions
  data   anything else (numeric tables, wavetables, fonts, compressed blobs)

Usage:
    python -m dirtyloader.re.layout <stock.bin> [--chunk 256] [--min-region 1024]
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from typing import List

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover

_COMMON = set("""push pop bl blx bx b cbz cbnz ldr ldrb ldrh ldrsb ldrsh ldrd str strb strh strd ldm ldmia stm
stmia stmdb mov movs movw movt mvn mvns add adds addw sub subs subw adc adcs sbc sbcs rsb rsbs mul muls mla mls
and ands orr orrs orn eor eors bic bics lsl lsls lsr lsrs asr asrs ror rors cmp cmn tst teq it ite itt ite itte
ittt itee iteee ittee uxtb uxth sxtb sxth ubfx sbfx bfi bfc udiv sdiv umull smull clz tbb tbh nop vldr vstr
vmov vadd vsub vmul vdiv vcvt vcmp vcmpe vmrs vpush vpop vmla vmls vneg vabs vsqrt vfma vfms vldmia vstmia
uxtab uxtah sxtab adr""".split())
_CONDS = ("eq", "ne", "cs", "hs", "cc", "lo", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le", "al")


def _base(m: str) -> str:
    m = m.split(".")[0]
    if m in _COMMON:
        return m
    for c in _CONDS:
        if m.endswith(c) and m[:-2] in _COMMON:
            return m[:-2]
    return m


@dataclass
class Region:
    start: int
    end: int
    kind: str

    @property
    def size(self) -> int:
        return self.end - self.start


def classify(fw: M8Firmware, chunk: int = 256) -> List[str]:
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    p = bytes(fw.payload)
    base, end = fw.load_addr, fw.load_addr + len(p)
    mm = recover(fw)
    itcm = mm.itcm
    data = mm.data
    kinds = []
    for off in range(0, len(p), chunk):
        c = p[off:off + chunk]
        if c.count(0) == len(c) or c.count(0xFF) == len(c):
            kinds.append("fill")
            continue
        if c.count(b"\x5f\xf8\x00\xf0") >= 4:        # linker long-branch veneers (ldr.w pc,[pc,#-0])
            kinds.append("code")
            continue
        printable = sum(1 for b in c if 32 <= b < 127 or b in (0, 9, 10, 13))
        if printable >= 0.9 * len(c) and sum(1 for b in c if 32 <= b < 127) >= 16:
            kinds.append("text")
            continue
        words = [struct.unpack_from("<I", c, k)[0] for k in range(0, len(c) - 3, 4)]
        ptr = 0
        for v in words:
            if (base <= v < end or (itcm and itcm.dest <= (v & ~1) < itcm.end and v > 0x100)
                    or (data and data.dest <= v < 0x20050000)):
                ptr += 1
        if words and ptr >= 0.5 * len(words):
            kinds.append("ptrs")
            continue
        n = good = covered = 0
        for i in md.disasm(c, base + off):
            n += 1
            covered += i.size
            if _base(i.mnemonic) in _COMMON:
                good += 1
        if covered >= 0.9 * len(c) and n and good >= 0.85 * n:
            kinds.append("code")
        else:
            kinds.append("data")
    return kinds


def regions(fw: M8Firmware, chunk: int = 256, smooth: int = 1) -> List[Region]:
    kinds = classify(fw, chunk)
    # smooth isolated chunks sandwiched between two of the same kind
    for _ in range(smooth):
        for k in range(1, len(kinds) - 1):
            if kinds[k - 1] == kinds[k + 1] != kinds[k]:
                kinds[k] = kinds[k - 1]
    out: List[Region] = []
    base = fw.load_addr
    for k, kind in enumerate(kinds):
        a = base + k * chunk
        if out and out[-1].kind == kind:
            out[-1].end = a + chunk
        else:
            out.append(Region(a, a + chunk, kind))
    out[-1].end = min(out[-1].end, base + len(fw.payload))
    return out


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Classify the flash image into code/text/ptrs/data/fill regions.")
    ap.add_argument("firmware")
    ap.add_argument("--chunk", type=int, default=256)
    ap.add_argument("--min-region", type=int, default=1024, help="hide regions smaller than this")
    a = ap.parse_args(argv)
    fw = M8Firmware.from_file(a.firmware, verify=True)
    mm = recover(fw)
    rs = regions(fw, a.chunk)
    totals: dict = {}
    for r in rs:
        totals[r.kind] = totals.get(r.kind, 0) + r.size

    def seg(addr):
        for c, name in ((mm.itcm, "ITCM image"), (mm.data, ".data image")):
            if c and c.contains_load(addr):
                return name
        return "XIP flash"

    print("totals: " + ", ".join("%s %d KB" % (k, v // 1024) for k, v in sorted(totals.items(), key=lambda t: -t[1])))
    for r in rs:
        if r.size >= a.min_region:
            print("0x%08X..0x%08X  %-5s %7d B  [%s]" % (r.start, r.end, r.kind, r.size, seg(r.start)))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
