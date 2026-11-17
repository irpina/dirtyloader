"""
Put mods on an M8 over USB: core 0.3 stores them on the SD card and loads them at the next boot.

    python -m dirtyloader.unit [--port COM11] info
    python -m dirtyloader.unit ls                       the .m8x files on the card, and which are on
    python -m dirtyloader.unit add mod.m8x [...]        upload, verify and switch on (restart to load)
    python -m dirtyloader.unit on NAME | off NAME       edit /dirtyloader/active.txt
    python -m dirtyloader.unit status                   what core loaded at the last boot (status.txt)
    python -m dirtyloader.unit good                     clear the crash guard
    python -m dirtyloader.unit restart

Close m8c first: the port is shared. The wire format (docs/LOADER.md, "Transfer"): a request is 0xD1, cmd,
seq, len (u16 LE), payload, sum8 of cmd..payload, sent inside the m8c serial stream; the reply is a SLIP frame
0xF1, cmd, seq, status, data.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import time
import zlib
from typing import List, Optional, Tuple

from dirtyloader.serialport import open_m8, SerialPort

MARK, REPLY = 0xD1, 0xF1
C_INFO, C_LIST, C_PUT, C_CHECK, C_GET, C_MKDIRS, C_RESTART, C_PEEK = range(1, 9)
STATUS = {0: "ok", 1: "bad request", 2: "checksum", 3: "bad path or no such file", 4: "SD error",
          5: "no SD card", 6: "timeout", 7: "unknown command"}
CHUNK = 1024
ACTIVE = "active.txt"


class UnitError(RuntimeError):
    pass


def request_bytes(cmd: int, seq: int, payload: bytes) -> bytes:
    head = bytes([cmd, seq & 0xFF]) + struct.pack("<H", len(payload))
    return bytes([MARK]) + head + payload + bytes([(sum(head) + sum(payload)) & 0xFF])


def slip_frames(buf: bytearray) -> List[bytes]:
    """Pop the complete SLIP frames off the front of `buf`."""
    out = []
    while True:
        end = buf.find(0xC0)
        if end < 0:
            return out
        raw, esc, frame = bytes(buf[:end]), False, bytearray()
        del buf[:end + 1]
        for b in raw:
            if esc:
                frame.append({0xDC: 0xC0, 0xDD: 0xDB}.get(b, b))
                esc = False
            elif b == 0xDB:
                esc = True
            else:
                frame.append(b)
        if frame:
            out.append(bytes(frame))


class Unit:
    def __init__(self, port: Optional[SerialPort] = None, name: Optional[str] = None):
        self.port = port or open_m8(name)
        self.seq = 0
        self.rx = bytearray()

    def close(self):
        self.port.close()

    def request(self, cmd: int, payload: bytes = b"", timeout: float = 3.0) -> bytes:
        self.seq = (self.seq + 1) & 0xFF
        self.port.write(request_bytes(cmd, self.seq, payload))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.rx += self.port.read(4096, 0.05)
            for f in slip_frames(self.rx):
                if len(f) >= 4 and f[0] == REPLY and f[1] == cmd and f[2] == self.seq:
                    if f[3]:
                        raise UnitError(f"command {cmd}: {STATUS.get(f[3], f[3])}")
                    return f[4:]
        raise UnitError(f"command {cmd}: no reply (is core 0.3 on the unit, and m8c closed?)")

    # -- primitives -------------------------------------------------------------
    def info(self) -> str:
        return self.request(C_INFO).decode("ascii", "replace")

    def mkdirs(self) -> None:
        self.request(C_MKDIRS)

    def list(self, sub: str = "mods") -> List[str]:
        return [n for n in self.request(C_LIST, sub.encode()).decode("ascii", "replace").split("\n") if n]

    def put(self, name: str, data: bytes) -> None:
        n = name.encode()
        for off in range(0, max(len(data), 1), CHUNK):
            chunk = data[off:off + CHUNK]
            wrote = struct.unpack("<I", self.request(C_PUT, struct.pack("<IB", off, len(n)) + n + chunk))[0]
            if wrote != len(chunk):
                raise UnitError(f"{name}: wrote {wrote} of {len(chunk)} bytes at {off}")

    def check(self, name: str) -> Tuple[int, int]:
        return struct.unpack("<II", self.request(C_CHECK, name.encode()))

    def get(self, name: str) -> bytes:
        out, n = b"", name.encode()
        while True:
            part = self.request(C_GET, struct.pack("<IHB", len(out), 512, len(n)) + n)
            out += part
            if len(part) < 512:
                return out

    def peek(self, addr: int, n: int) -> bytes:
        """Read the unit's memory (development: screen objects, tables, state)."""
        out = b""
        while len(out) < n:
            k = min(512, n - len(out))
            out += self.request(C_PEEK, struct.pack("<IH", addr + len(out), k))
        return out

    def restart(self) -> None:
        self.request(C_RESTART)

    # -- the mod set --------------------------------------------------------------
    def active(self) -> List[str]:
        try:
            text = self.get(ACTIVE).decode("ascii", "replace")
        except UnitError:
            return []
        return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]

    def set_active(self, names: List[str]) -> None:
        text = "# one .m8x per line, from /dirtyloader/mods/; core loads them at boot\n"
        self.put(ACTIVE, (text + "".join(n + "\n" for n in names)).encode("ascii"))
        self.put("guard", b"GOOD")                       # a new set gets a fresh try

    def add(self, path: str) -> str:
        data = open(path, "rb").read()
        from dirtyloader.cc import parse_m8x
        parse_m8x(data)                                  # refuse anything the core would refuse
        name = os.path.basename(path)
        self.mkdirs()
        self.put("mods/" + name, data)
        size, crc = self.check("mods/" + name)
        if (size, crc) != (len(data), zlib.crc32(data) & 0xFFFFFFFF):
            raise UnitError(f"{name}: verify failed (unit has {size} B, crc {crc:08x})")
        act = self.active()
        if name not in act:
            self.set_active(act + [name])
        return name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dirtyloader.unit", description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", help="serial port (default: the first M8 found)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("ls")
    a = sub.add_parser("add")
    a.add_argument("files", nargs="+")
    for c in ("on", "off"):
        sub.add_parser(c).add_argument("name")
    sub.add_parser("status")
    sub.add_parser("good")
    sub.add_parser("restart")
    args = ap.parse_args(argv)
    u = Unit(name=args.port)
    try:
        if args.cmd == "info":
            print(u.info(), end="")
        elif args.cmd == "ls":
            act = u.active()
            for n in u.list("mods"):
                print(("on   " if n in act else "off  ") + n)
        elif args.cmd == "add":
            for f in args.files:
                print("added", u.add(f))
            print("restart the unit to load (python -m dirtyloader.unit restart)")
        elif args.cmd in ("on", "off"):
            act = [n for n in u.active() if n != args.name]
            if args.cmd == "on":
                if args.name not in u.list("mods"):
                    raise UnitError(f"{args.name} is not on the card")
                act.append(args.name)
            u.set_active(act)
        elif args.cmd == "status":
            print(u.get("status.txt").decode("ascii", "replace"), end="")
        elif args.cmd == "good":
            u.put("guard", b"GOOD")
        elif args.cmd == "restart":
            u.restart()
    except UnitError as e:
        print("error:", e, file=sys.stderr)
        return 1
    finally:
        u.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
