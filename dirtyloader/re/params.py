"""
Parameter descriptor tables.

Every instrument engine, the modulators and the project settings describe their
parameters with 28-byte records in plain flash:

    +0x00 u32   id
    +0x04 char* long name      ("DELAY VOL")      -- pointers into .data (DTCM)
    +0x08 char* 4-char label   ("DEL ")
    +0x0C char* 3-char code    ("SDL")
    +0x10 char* help text      ("SEND DELAY")
    +0x14 u32   flags          (0x80000000 relative/signed, 0x40000000 ..., 0x100 ...)
    +0x18 u8    min, u8 max, u8 field offset (0xFF = not stored, e.g. a command), u8 ?

The string pointers are DTCM runtime addresses, which is why these tables looked
unreachable from a flash-only view. Records are found by shape: an id below
0x400 followed by four pointers into the .data runtime range.

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
    id: int
    name: str
    label: str
    code: str
    help: str
    flags: int
    min: int
    max: int
    offset: Optional[int]       # None when 0xFF (not a stored field)


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
        return a + REC <= base + len(p) and w(a) < 0x400 and all(is_str(w(a + k)) for k in (4, 8, 12, 16))

    out: List[Table] = []
    a, end = base, base + len(p) - REC
    while a < end:
        if not is_rec(a):
            a += 4
            continue
        start, recs = a, []
        while is_rec(a):
            pk = w(a + 24)
            off = (pk >> 16) & 0xFF
            recs.append(Param(addr=a, id=w(a), name=s(w(a + 4)), label=s(w(a + 8)), code=s(w(a + 12)),
                              help=s(w(a + 16)), flags=w(a + 20), min=pk & 0xFF, max=(pk >> 8) & 0xFF,
                              offset=None if off == 0xFF else off))
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
                print("    0x%08X id 0x%02X %-16s %-5s %-4s flags %08X  %3d..%3d  off %s  | %s" % (
                    x.addr, x.id, x.name, x.label, x.code, x.flags, x.min, x.max,
                    "--" if x.offset is None else "0x%02X" % x.offset, x.help))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
