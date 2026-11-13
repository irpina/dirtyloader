"""
Trace the M8 firmware entry down to its main loop with capstone (no Ghidra).

The firmware is stripped, but the reset path is deterministic Teensy-style code:

    IVT.entry -> ResetHandler -> startup() -> ... -> main()
    main(): setup(); while (1) { loop(); yield(); }

This tool follows that chain structurally and returns the key addresses plus the
per-frame functions main's loop calls -- the Core's hook sites. Only capstone is
needed, so it runs in a second and is easy to re-point at a new firmware build.

Usage:
    python -m dirtyloader.re.trace <stock.bin>
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.boot import LOAD, parse_boot

try:
    import capstone
    from capstone import arm as cs_arm
except ImportError:  # pragma: no cover
    capstone = None

_RETURN_POPS = ("pop", "ldm", "ldmia", "ldmfd")


def _md():
    if capstone is None:
        raise RuntimeError("capstone is not installed (pip install capstone)")
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB + capstone.CS_MODE_MCLASS)
    md.detail = True
    return md


def _run(payload: bytes, start: int, limit: int = 0x800):
    """Linearly disassemble from `start` (Thumb) until a return or an
    unconditional branch. Returns (bl_targets[(addr,tgt)], back_branch(addr,tgt)|None,
    end_addr)."""
    md = _md()
    base = start & ~1
    off = base - LOAD
    bls: List[Tuple[int, int]] = []
    back = None
    end = base
    for ins in md.disasm(payload[off:off + limit], base):
        end = ins.address
        m = ins.mnemonic
        if m in ("bl", "blx") and ins.operands and ins.operands[0].type == cs_arm.ARM_OP_IMM:
            bls.append((ins.address, ins.operands[0].imm))
        if m in ("b", "b.w") and ins.operands and ins.operands[0].type == cs_arm.ARM_OP_IMM:
            tgt = ins.operands[0].imm
            if base <= tgt <= ins.address:
                back = (ins.address, tgt)
            break  # unconditional branch ends the linear run
        if m == "bx" and ins.op_str.strip() == "lr":
            break
        if m in _RETURN_POPS and "pc" in ins.op_str:
            break
    return bls, back, end


@dataclass
class HookMap:
    entry: int
    startup: int
    main: int
    setup: Optional[int]
    frame_calls: List[int]            # calls inside while(1): typically [loop, yield]
    loop: Optional[int]
    yield_: Optional[int]
    loop_subsystems: List[int] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"entry   : 0x{self.entry:08X}",
            f"startup : 0x{self.startup:08X}",
            f"main    : 0x{self.main:08X}",
            f"setup   : 0x{self.setup:08X}  (one-time init -> BOOT hook)" if self.setup else "setup   : ?",
            f"loop    : 0x{self.loop:08X}  (per-frame app -> TICK/RENDER/INPUT hook)" if self.loop else "loop    : ?",
            f"yield   : 0x{self.yield_:08X}  (Teensy USB/event service)" if self.yield_ else "yield   : ?",
        ]
        if self.loop_subsystems:
            lines.append("loop() subsystems (finer hook targets):")
            lines += [f"  0x{a:08X}" for a in self.loop_subsystems]
        return "\n".join(lines)


def trace(payload: bytes) -> HookMap:
    boot = parse_boot(payload)
    entry = boot.entry
    # entry -> startup (first call)
    e_bls, _, _ = _run(payload, entry)
    startup = e_bls[0][1]
    # startup's calls; main is the callee whose own run contains a while(1)
    s_bls, _, _ = _run(payload, startup, 0x2000)
    main = None
    for _, tgt in s_bls:
        _, back, _ = _run(payload, tgt, 0x4000)
        if back is not None:
            main = tgt  # keep last looping callee == main()
    if main is None and s_bls:
        main = s_bls[-1][1]
    # dissect main: setup (pre-loop call) + frame calls (inside the loop)
    m_bls, m_back, _ = _run(payload, main, 0x400)
    loop_start = m_back[1] if m_back else main
    branch_at = m_back[0] if m_back else None
    setup = next((t for a, t in m_bls if a < loop_start), None)
    frame = [t for a, t in m_bls if loop_start <= a and (branch_at is None or a < branch_at)]
    loop_fn = frame[0] if frame else None
    yield_fn = frame[1] if len(frame) > 1 else None
    subsystems = []
    if loop_fn:
        l_bls, _, _ = _run(payload, loop_fn, 0x800)
        seen = []
        for _, t in l_bls:
            if t not in seen:
                seen.append(t)
        subsystems = seen
    return HookMap(entry=entry, startup=startup, main=main, setup=setup,
                   frame_calls=frame, loop=loop_fn, yield_=yield_fn,
                   loop_subsystems=subsystems)


def _main(argv=None) -> int:
    import sys
    path = (argv or sys.argv[1:])[0]
    fw = M8Firmware.from_file(path, verify=True)
    print(trace(bytes(fw.payload)).summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
