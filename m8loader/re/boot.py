"""
Parse the IMXRT1062 boot structures at the head of an M8 firmware payload.

The payload (everything after the 0x200-byte M8FW header) is a flat flash image
mapped at 0x60000000:

    0x60000000  FlexSPI Configuration Block (FCFB), tag "FCFB"
    0x60001000  Image Vector Table (IVT), tag byte 0xD1
    0x60001020  Boot Data (image start / length / plugin)
    ...         ResetHandler + ARM vector table + application code & data

Usage:
    python -m m8loader.re.boot <stock.bin>
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

from m8loader.m8fw import M8Firmware

LOAD = 0x60000000
IVT_OFF = 0x1000

try:
    import capstone  # optional; only needed for disassembly helpers
except ImportError:  # pragma: no cover
    capstone = None


@dataclass
class BootInfo:
    fcfb_ok: bool
    ivt_tag_ok: bool
    entry: int
    dcd: int
    boot_data: int
    ivt_self: int
    csf: int
    image_start: int
    image_length: int
    plugin: int

    @property
    def hab_signed_pointer(self) -> bool:
        """csf != 0 means a HAB Command Sequence File is referenced. HAB is only
        *enforced* on fuse-closed parts; stock Teensy 4.1 ships open, so this is
        informational unless the device has been secured."""
        return self.csf != 0

    def summary(self) -> str:
        return (
            f"FCFB: {'ok' if self.fcfb_ok else 'MISSING'}  "
            f"IVT: {'ok' if self.ivt_tag_ok else 'BAD'}\n"
            f"entry      : 0x{self.entry:08X}\n"
            f"dcd        : 0x{self.dcd:08X}\n"
            f"boot_data  : 0x{self.boot_data:08X}\n"
            f"ivt_self   : 0x{self.ivt_self:08X}\n"
            f"csf        : 0x{self.csf:08X}  "
            f"({'HAB pointer present - not enforced on open Teensy' if self.hab_signed_pointer else 'none'})\n"
            f"image_start: 0x{self.image_start:08X}\n"
            f"image_len  : 0x{self.image_length:08X} ({self.image_length} bytes)\n"
            f"plugin     : 0x{self.plugin:08X}"
        )


def parse_boot(payload: bytes) -> BootInfo:
    def u32(off: int) -> int:
        return struct.unpack_from("<I", payload, off)[0]

    ivt_hdr = u32(IVT_OFF)
    boot_data = u32(IVT_OFF + 0x10)
    bd = boot_data - LOAD
    return BootInfo(
        fcfb_ok=payload[0:4] == b"FCFB",
        ivt_tag_ok=(ivt_hdr & 0xFF) == 0xD1,
        entry=u32(IVT_OFF + 0x04),
        dcd=u32(IVT_OFF + 0x0C),
        boot_data=boot_data,
        ivt_self=u32(IVT_OFF + 0x14),
        csf=u32(IVT_OFF + 0x18),
        image_start=u32(bd),
        image_length=u32(bd + 4),
        plugin=u32(bd + 8),
    )


def disassemble(payload: bytes, addr: int, count: int = 24) -> List[Tuple[int, str, str]]:
    """Disassemble `count` Thumb instructions at absolute flash `addr`. The low
    bit (Thumb indicator) is masked off before indexing. Returns (addr, mnemonic,
    operands) tuples. Requires capstone."""
    if capstone is None:
        raise RuntimeError("capstone is not installed (pip install capstone)")
    base = (addr & ~1)
    off = base - LOAD
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB + capstone.CS_MODE_MCLASS)
    out = []
    for ins in md.disasm(payload[off:off + count * 4], base):
        out.append((ins.address, ins.mnemonic, ins.op_str))
        if len(out) >= count:
            break
    return out


def _main(argv=None) -> int:
    import sys
    path = (argv or sys.argv[1:])[0]
    fw = M8Firmware.from_file(path, verify=True)
    payload = bytes(fw.payload)
    info = parse_boot(payload)
    print(info.summary())
    if capstone is not None:
        print(f"\nResetHandler / entry disassembly @0x{info.entry & ~1:08X}:")
        for a, m, o in disassemble(payload, info.entry, 16):
            print(f"  0x{a:08X}: {m:<8} {o}")
    else:
        print("\n(install capstone for entry disassembly)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
