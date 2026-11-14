"""
Parameter descriptor tables.

Every instrument engine, the modulators and the project settings describe their
parameters with 28-byte records in plain flash:

    +0x00 char* long name      ("DELAY VOL")      -- pointers into .data (DTCM)
    +0x04 char* UI label       ("DEL ")
    +0x08 char* 3-char code    ("SDL")
    +0x0C char* help text      ("SEND DELAY")
    +0x10 u32   flags          (0x80000000 relative/signed, 0x00010000, 0x100 ...)
    +0x14 u8    min, u8 max, u8 b2, u8 b3
    +0x18 u32   parameter index

The instrument's virtual getParamDescriptor(idx) (vtable +0xBC) returns
`table + idx * 28` for engine parameters and defers indices 0x30..0x47 (the four
modulator slots) to +0xC4 -- the table base is formed arithmetically, so no
pointer to it is stored anywhere. The string pointers are DTCM run-time
addresses. Records are found by shape: four pointers into the .data run-time
range followed by flags, range and an index below 0x400.

Usage:
    python -m dirtyloader.re.params <stock.bin> [--names]
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from typing import List, Optional

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover

REC = 28


@dataclass
class Param:
    addr: int
    index: int
    name: str
    label: str
    code: str
    help: str
    flags: int
    min: int
    max: int
    b2: int                     # meaning unconfirmed (0xFF for most continuous params)
    b3: int


@dataclass
class Table:
    addr: int
    params: List[Param]


def scan(fw: M8Firmware, min_len: int = 5, mm=None) -> List[Table]:
    p = bytes(fw.payload)
    base = fw.load_addr
    mm = mm or recover(fw)
    d = mm.data
    if d is None:
        return []

    def w(a):
        return struct.unpack_from("<I", p, a - base)[0]

    def is_str(v):
        return d.dest <= v < d.end

    def s(v, n=48):
        la = d.src + (v - d.dest)
        o = la - base
        e = p.find(b"\x00", o, o + n)
        return p[o:(e if e != -1 else o + n)].decode("latin1")

    def is_rec(a):
        return a + REC <= base + len(p) and all(is_str(w(a + k)) for k in (0, 4, 8, 12)) and w(a + 24) < 0x400

    out: List[Table] = []
    a, end = base, base + len(p) - REC
    while a < end:
        if not is_rec(a):
            a += 4
            continue
        start, recs = a, []
        while is_rec(a):
            pk = w(a + 20)
            recs.append(Param(addr=a, index=w(a + 24), name=s(w(a)), label=s(w(a + 4)), code=s(w(a + 8)),
                              help=s(w(a + 12)), flags=w(a + 16), min=pk & 0xFF, max=(pk >> 8) & 0xFF,
                              b2=(pk >> 16) & 0xFF, b3=(pk >> 24) & 0xFF))
            a += REC
        if len(recs) >= min_len:
            out.append(Table(addr=start, params=recs))
    return out


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List the parameter descriptor tables.")
    ap.add_argument("firmware")
    ap.add_argument("--names", action="store_true", help="list every parameter")
    a = ap.parse_args(argv)
    tables = scan(M8Firmware.from_file(a.firmware, verify=True))
    print("%d tables, %d parameters" % (len(tables), sum(len(t.params) for t in tables)))
    for t in tables:
        print("0x%08X  %3d params: %s" % (t.addr, len(t.params), ", ".join(x.name for x in t.params[:6]) + " ..."))
        if a.names:
            for x in t.params:
                print("    0x%08X idx 0x%02X %-16s %-9s %-4s flags %08X  %3d..%3d  b2 %02X b3 %02X | %s" % (
                    x.addr, x.index, x.name, x.label, x.code, x.flags, x.min, x.max, x.b2, x.b3, x.help))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
