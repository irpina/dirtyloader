"""
Whole-image switch census.

Every PC-relative table branch in the firmware -- `tbb [pc, Rm]` (E8DF F00m) and
`tbh [pc, Rm, lsl #1]` (E8DF F01m) -- is found by its fixed encoding, so this does
not depend on Ghidra's auto-analysis (which misses much of the M8's computed-call
code). For each one the bound is recovered from the preceding `cmp Rm, #N` /
`bhi` pair and the jump table is decoded into its case targets.

Switches are the M8's dispatch skeleton: command executors, view and key
handlers, glyph renderers, protocol parsers. Matching a switch's case count (and
any `sub Rm, #base` bias) to a known enum is often enough to identify it -- the
FX-command executor is the 78-case switch at 0x60028802 (commands 0x00..0x4D).

Usage:
    python -m dirtyloader.re.switches <stock.bin> [-o switches.txt] [--min N]
Needs capstone (requirements-re.txt).
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass, field
from typing import List, Optional

from dirtyloader.m8fw import M8Firmware


@dataclass
class Switch:
    addr: int                 # the tbb/tbh instruction
    kind: str                 # "tbb" | "tbh"
    reg: int                  # index register number
    cases: Optional[int]      # number of table entries (None if the bound wasn't recovered)
    bias: Optional[int]       # value subtracted before the switch (sub Rm, Rx, #bias), if any
    targets: List[int] = field(default_factory=list)
    function: Optional[int] = None    # nearest preceding push {..,lr} (a rough function start)
    context: str = ""

    @property
    def distinct(self) -> int:
        return len(set(self.targets))


def _md():
    import capstone
    return capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)


def _window(md, p: bytes, base: int, addr: int):
    """Decode a few instructions ending exactly at `addr` (Thumb is not self-synchronising,
    so try several start points and keep one that lands on the switch)."""
    for back in range(24, 2, -2):
        s = addr - back
        if s < base:
            continue
        insns = list(md.disasm(p[s - base:addr - base + 4], s))
        if any(i.address == addr for i in insns):
            return [i for i in insns if i.address <= addr]
    return []


def _push_before(p: bytes, base: int, addr: int, limit: int = 0x400) -> Optional[int]:
    a = addr
    while a > max(base, addr - limit):
        a -= 2
        hw = struct.unpack_from("<H", p, a - base)[0]
        if (hw & 0xFF00) == 0xB500:                                   # push {..., lr}
            return a
        if hw == 0xE92D and struct.unpack_from("<H", p, a + 2 - base)[0] & 0x4000:   # push.w {..., lr}
            return a
    return None


def census(fw: M8Firmware, max_cases: int = 512) -> List[Switch]:
    md = _md()
    p = bytes(fw.payload)
    base = fw.load_addr
    out: List[Switch] = []
    for off in range(0, len(p) - 4, 2):
        if p[off] != 0xDF or p[off + 1] != 0xE8 or p[off + 3] != 0xF0 or p[off + 2] & 0xE0:
            continue
        is_h = bool(p[off + 2] & 0x10)
        rm = p[off + 2] & 0x0F
        addr = base + off
        ins = _window(md, p, base, addr)
        # capstone prints r9..r14 by their ABI aliases
        names = {"r%d" % rm, {9: "sb", 10: "sl", 11: "fp", 12: "ip", 13: "sp", 14: "lr"}.get(rm, "r%d" % rm)}
        bound, cond, bias = None, "", None
        for i in reversed(ins[:-1]):
            ops = [o.strip() for o in i.op_str.split(",")]
            if i.mnemonic.startswith("cmp") and ops and ops[0] in names and "#" in i.op_str:
                try:
                    bound = int(i.op_str.split("#")[-1], 0)
                except ValueError:
                    pass
                break
        for i in ins[-4:-1]:
            if i.mnemonic.startswith(("bhi", "bhs", "bcs", "bls", "blo")):
                cond = i.mnemonic
        for i in ins[:-1]:
            ops = [o.strip() for o in i.op_str.split(",")]
            if i.mnemonic.startswith("sub") and ops and ops[0] in names and "#" in i.op_str:
                try:
                    bias = int(i.op_str.split("#")[-1], 0)
                except ValueError:
                    pass
        cases = None
        if bound is not None:
            cases = bound if cond.startswith(("bhs", "bcs")) else bound + 1
        targets: List[int] = []
        table = addr + 4
        if cases and cases <= max_cases:
            for k in range(cases):
                v = (struct.unpack_from("<H", p, table - base + 2 * k)[0] if is_h
                     else p[table - base + k])
                targets.append(table + 2 * v)
        out.append(Switch(addr=addr, kind="tbh" if is_h else "tbb", reg=rm, cases=cases, bias=bias,
                          targets=targets, function=_push_before(p, base, addr),
                          context=" | ".join("%s %s" % (i.mnemonic, i.op_str) for i in ins[-5:])))
    return out


def format_table(rows: List[Switch], min_cases: int = 0) -> str:
    lines = ["addr        kind reg cases distinct bias   fn~         context"]
    for s in rows:
        if s.cases is not None and s.cases < min_cases:
            continue
        lines.append("0x%08X  %s  r%-2d %5s %8s %6s  %s  %s" % (
            s.addr, s.kind, s.reg, s.cases if s.cases is not None else "?",
            s.distinct if s.cases else "-", ("0x%X" % s.bias) if s.bias is not None else "-",
            ("0x%08X" % s.function) if s.function else "?         ", s.context))
    return "\n".join(lines) + "\n"


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Census every tbb/tbh switch in an M8 firmware image.")
    ap.add_argument("firmware")
    ap.add_argument("-o", "--output", help="write the table here (default: stdout)")
    ap.add_argument("--min", type=int, default=0, help="only list switches with at least N cases")
    a = ap.parse_args(argv)
    rows = census(M8Firmware.from_file(a.firmware, verify=True))
    text = format_table(rows, a.min)
    if a.output:
        open(a.output, "w").write(text)
        print("%d switches -> %s" % (len(rows), a.output))
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
