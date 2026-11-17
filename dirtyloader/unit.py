"""
Put mods on an M8 over USB: core 0.3 stores them on the SD card and loads them at the next boot.

    python -m dirtyloader.unit [--port COM11] info
    python -m dirtyloader.unit ls                       the .m8x files on the card, and which are on
    python -m dirtyloader.unit add [--off] mod.m8x ...  upload, verify and switch on (restart to load)
    python -m dirtyloader.unit on NAME | off NAME       edit /dirtyloader/active.txt
    python -m dirtyloader.unit remove NAME [...]        delete from the card (and switch off)
    python -m dirtyloader.unit clear                    delete every mod on the card
    python -m dirtyloader.unit status                   what core loaded at the last boot (status.txt)
    python -m dirtyloader.unit good                     clear the crash guard
    python -m dirtyloader.unit safe                     boot once without mods (run it, then plug in / reset)
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
SAFE_MAGIC = bytes([0xF5, 0xDA, 0xA5, 0xFE, 0xC4, 0xB7])   # core_load's safe-boot request (no m8c command)
C_INFO, C_LIST, C_PUT, C_CHECK, C_GET, C_MKDIRS, C_RESTART, C_PEEK, C_DELETE, C_POKE = range(1, 11)
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

    def poke(self, addr: int, data: bytes) -> None:
        """Write the unit's RAM (development and tests: 0x20000000..0x20280000 only)."""
        for off in range(0, len(data), 512):
            self.request(C_POKE, struct.pack("<I", addr + off) + data[off:off + 512])

    def restart(self) -> None:
        self.request(C_RESTART)

    def delete(self, name: str) -> None:
        """Delete a file under /dirtyloader (core 0.4)."""
        self.request(C_DELETE, name.encode())

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

    def remove(self, name: str) -> None:
        act = self.active()
        if name in act:
            self.set_active([n for n in act if n != name])
        self.delete("mods/" + name)

    def add(self, path: str, on: bool = True) -> str:
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
        if on and name not in act:
            self.set_active(act + [name])
        elif not on and name in act:
            self.set_active([n for n in act if n != name])
        return name


def safe_boot(port_name: Optional[str], wait: float) -> int:
    """The skip key at power-on (core 0.4): send SAFE_MAGIC over and over while the unit boots; core_load looks for it
    and loads no mods. Run it, then plug the unit in (or reset it)."""
    from dirtyloader.serialport import find_m8_ports
    deadline = time.monotonic() + wait
    if find_m8_ports():                                  # up already: its status is the last boot's
        print("the M8 is up: reset it or unplug it and plug it back in")
        while find_m8_ports():
            if time.monotonic() > deadline:
                print("the M8 did not restart", file=sys.stderr)
                return 1
            time.sleep(0.02)
    else:
        print("waiting for the M8: plug it in now")
    while time.monotonic() < deadline:
        ports = [port_name] if port_name else find_m8_ports()
        for p in ports:
            try:
                u = Unit(port=open_m8(p))
            except Exception:
                continue
            try:
                t = time.monotonic()
                while time.monotonic() - t < 20:          # a reset drops the port: the outer loop reopens it
                    u.port.write(SAFE_MAGIC * 8)
                    time.sleep(0.02)
                    try:
                        status = u.get("status.txt").decode("ascii", "replace")
                    except UnitError:
                        continue
                    if "safe boot" in status:
                        print("booted without mods (the MODS page's RESTART, or `good`, loads them again)")
                        return 0
                    if "dirtyloader core" in status:
                        print("the unit booted with its mods: it was already up, or does not have core 0.4")
                        return 1
            except OSError:
                pass
            finally:
                try:
                    u.close()
                except OSError:
                    pass
        time.sleep(0.05)
    print("no M8 appeared", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dirtyloader.unit", description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", help="serial port (default: the first M8 found)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("ls")
    a = sub.add_parser("add")
    a.add_argument("--off", action="store_true", help="upload switched off")
    a.add_argument("files", nargs="+")
    sub.add_parser("remove").add_argument("names", nargs="+")
    sub.add_parser("clear")
    for c in ("on", "off"):
        sub.add_parser(c).add_argument("name")
    sub.add_parser("status")
    sub.add_parser("good")
    s = sub.add_parser("safe")
    s.add_argument("--wait", type=float, default=60.0, help="seconds to wait for the unit")
    sub.add_parser("restart")
    args = ap.parse_args(argv)
    if args.cmd == "safe":
        return safe_boot(args.port, args.wait)
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
                print("added", u.add(f, on=not args.off))
            print("restart the unit to load (python -m dirtyloader.unit restart)")
        elif args.cmd in ("on", "off"):
            act = [n for n in u.active() if n != args.name]
            if args.cmd == "on":
                if args.name not in u.list("mods"):
                    raise UnitError(f"{args.name} is not on the card")
                act.append(args.name)
            u.set_active(act)
        elif args.cmd == "remove":
            for n in args.names:
                u.remove(n)
                print("removed", n)
        elif args.cmd == "clear":
            for n in u.list("mods"):
                u.remove(n)
                print("removed", n)
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
