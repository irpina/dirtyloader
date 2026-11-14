"""
The firmware's runtime memory map, recovered from its startup code.

A Teensy 4 image is not all executed in place. At reset the startup routine
copies two images out of flash:

  * the ITCM code image  (FASTRUN functions)  -> 0x00000000 ...
  * the .data image      (initialised data, and on Teensy also .rodata:
                          vtables, const tables, most strings) -> DTCM 0x20000000 ...

Code refers to those bytes by their *runtime* addresses, so a flash-only view of
the image sees no references to them -- the M8's parameter labels looked
"unreachable" until translated (0x601E4214 in flash is 0x200061F4 at runtime).

This module finds the copy calls by tracking the literal loads into r0/r1/r2
before each `bl` in the startup function, and offers load <-> runtime
translation.

Usage:
    python -m dirtyloader.re.memmap <stock.bin>
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional

from dirtyloader.m8fw import M8Firmware


@dataclass
class Copy:
    dest: int      # runtime start
    src: int       # flash load address
    end: int       # runtime end (exclusive)

    @property
    def size(self) -> int:
        return self.end - self.dest

    def contains_load(self, a: int) -> bool:
        return self.src <= a < self.src + self.size

    def contains_runtime(self, a: int) -> bool:
        return self.dest <= a < self.end


@dataclass
class MemMap:
    entry: int
    startup: Optional[int]
    copies: List[Copy] = field(default_factory=list)
    flexram_config: Optional[int] = None    # IOMUXC_GPR_GPR17
    stack_top: Optional[int] = None
    vectors_ram: Optional[int] = None

    @property
    def itcm(self) -> Optional[Copy]:
        return next((c for c in self.copies if c.dest < 0x00100000), None)

    @property
    def data(self) -> Optional[Copy]:
        return next((c for c in self.copies if 0x20000000 <= c.dest < 0x20100000), None)

    def to_runtime(self, load: int) -> int:
        for c in self.copies:
            if c.contains_load(load):
                return c.dest + (load - c.src)
        return load

    def to_load(self, runtime: int) -> Optional[int]:
        for c in self.copies:
            if c.contains_runtime(runtime):
                return c.src + (runtime - c.dest)
        return runtime if 0x60000000 <= runtime < 0x70000000 else None

    def flexram_banks(self) -> dict:
        """Bank counts per type from GPR17 (2 bits/bank: 01 OCRAM, 10 DTCM, 11 ITCM; 32 KB each)."""
        if self.flexram_config is None:
            return {}
        kinds = {1: "OCRAM", 2: "DTCM", 3: "ITCM"}
        out: dict = {}
        for b in range(16):
            k = kinds.get((self.flexram_config >> (2 * b)) & 3)
            if k:
                out[k] = out.get(k, 0) + 1
        return out

    def summary(self) -> str:
        lines = ["entry      : 0x%08X" % self.entry]
        if self.startup:
            lines.append("startup    : 0x%08X" % self.startup)
        for c in self.copies:
            kind = "ITCM code" if c.dest < 0x00100000 else ".data (DTCM)" if c.dest < 0x20100000 else "copy"
            lines.append("%-11s: load 0x%08X..0x%08X -> run 0x%08X..0x%08X (%d bytes)" % (
                kind, c.src, c.src + c.size, c.dest, c.end, c.size))
        if self.flexram_config is not None:
            banks = self.flexram_banks()
            lines.append("FlexRAM    : GPR17=0x%08X  %s" % (self.flexram_config, ", ".join(
                "%s %d KB" % (k, 32 * v) for k, v in sorted(banks.items()))))
        if self.stack_top:
            lines.append("stack top  : 0x%08X" % self.stack_top)
        if self.vectors_ram:
            lines.append("vectors RAM: 0x%08X" % self.vectors_ram)
        return "\n".join(lines)


def _md():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    return md


def _walk(md, p: bytes, base: int, start: int, max_insns: int = 160):
    """Yield (insn, literal-or-None) along a straight-line walk."""
    n = 0
    for i in md.disasm(p[start - base:start - base + max_insns * 4], start):
        lit = None
        if i.mnemonic.startswith("ldr") and "[pc" in i.op_str and "#" in i.op_str:
            try:
                imm = int(i.op_str.split("#")[-1].rstrip("]"), 0)
                la = ((i.address + 4) & ~3) + imm
                lit = struct.unpack_from("<I", p, la - base)[0]
            except (ValueError, struct.error):
                lit = None
        yield i, lit
        n += 1
        if n >= max_insns:
            return


def recover(fw: M8Firmware) -> MemMap:
    from dirtyloader.re.boot import parse_boot
    p = bytes(fw.payload)
    base = fw.load_addr
    end = base + len(p)
    try:
        entry = parse_boot(p).entry & ~1
    except Exception:                       # no IVT (not a bootable image): no copies to recover
        return MemMap(entry=0, startup=None)
    mm = MemMap(entry=entry, startup=None)
    if not (base <= entry < end):
        return mm
    md = _md()

    regs: dict = {}
    # ResetHandler: FlexRAM config (str to IOMUXC_GPR +0x44), stack, then bl startup
    for i, lit in _walk(md, p, base, entry, 40):
        dst = i.op_str.split(",")[0].strip()
        if lit is not None:
            regs[dst] = lit
        if i.mnemonic == "str" and "#0x44]" in i.op_str and regs.get(i.op_str.split("[")[1].split(",")[0]) == 0x400AC000:
            mm.flexram_config = regs.get(dst)
        if lit is not None and 0x20000000 <= lit < 0x20100000 and mm.stack_top is None and (lit & 0xFFF) == 0:
            mm.stack_top = lit
        if i.mnemonic == "bl":
            mm.startup = int(i.op_str.lstrip("#"), 0)
            break

    if mm.startup is None:
        return mm
    regs = {}
    calls: dict = {}
    for i, lit in _walk(md, p, base, mm.startup, 200):
        dst = i.op_str.split(",")[0].strip()
        if lit is not None:
            regs[dst] = lit
        if i.mnemonic == "bl":
            tgt = int(i.op_str.lstrip("#"), 0)
            r0, r1, r2 = regs.get("r0"), regs.get("r1"), regs.get("r2")
            if (r0 is not None and r1 is not None and r2 is not None and base <= r1 < end
                    and (r0 < 0x00100000 or 0x20000000 <= r0 < 0x20300000) and r2 > r0
                    and r1 + (r2 - r0) <= end):
                calls.setdefault(tgt, []).append(Copy(dest=r0, src=r1, end=r2))
            regs = {}
        # the RAM vector table: a DTCM literal later written to SCB_VTOR (0xE000ED08)
        if lit is not None and mm.vectors_ram is None and 0x20000000 <= lit < 0x20100000 and (lit & 0x7F) == 0 \
                and lit not in (0x20000000,):
            mm.vectors_ram = lit
    # memory_copy is the function called with copy-shaped arguments
    if calls:
        tgt = max(calls, key=lambda t: len(calls[t]))
        mm.copies = calls[tgt]
    return mm


def _main(argv=None) -> int:
    import sys
    path = (argv or sys.argv[1:])[0]
    print(recover(M8Firmware.from_file(path, verify=True)).summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
