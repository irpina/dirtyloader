"""
A minimal serial port for talking to an M8 over USB, with no dependencies: win32 through ctypes, termios
elsewhere. Only what dirtyloader.unit needs: open with DTR set, write, read with a timeout, close, and finding
the port of an M8 (Teensy USB id 16C0:048A).
"""
from __future__ import annotations

import glob
import os
import sys
import time
from typing import List, Optional

M8_USB = ("16C0", "048A")


class SerialError(OSError):
    pass


def find_m8_ports() -> List[str]:
    """Serial ports that belong to an M8 (Model:02 or headless), best guess first."""
    if sys.platform == "win32":
        import winreg
        ports = []
        key = r"SYSTEM\CurrentControlSet\Enum\USB\VID_%s&PID_%s&MI_00" % M8_USB
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                i = 0
                while True:
                    try:
                        inst = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(k, inst + r"\Device Parameters") as p:
                            ports.append(winreg.QueryValueEx(p, "PortName")[0])
                    except OSError:
                        pass
        except OSError:
            pass
        live = set()
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as k:
                i = 0
                while True:
                    try:
                        live.add(winreg.EnumValue(k, i)[1])
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return [p for p in ports if p in live]
    found = sorted(glob.glob("/dev/serial/by-id/*M8*")) + sorted(glob.glob("/dev/cu.usbmodem*"))
    return found or sorted(glob.glob("/dev/ttyACM*"))


class SerialPort:
    def __init__(self, name: str):
        self.name = name
        if sys.platform == "win32":
            self._open_win(name)
        else:
            self._open_posix(name)

    # -- windows ----------------------------------------------------------------
    def _open_win(self, name):
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        path = name if name.startswith("\\\\.\\") else "\\\\.\\" + name
        h = k32.CreateFileW(path, 0xC0000000, 0, None, 3, 0, None)          # GENERIC_READ|WRITE, OPEN_EXISTING
        if h in (None, wintypes.HANDLE(-1).value):
            raise SerialError(ctypes.get_last_error(), f"cannot open {name}")

        class TIMEOUTS(ctypes.Structure):
            _fields_ = [(f, wintypes.DWORD) for f in ("ri", "rm", "rc", "wm", "wc")]
        self._k32, self._h, self._ct, self._TIMEOUTS = k32, h, ctypes, TIMEOUTS
        k32.EscapeCommFunction(h, 5)                                      # SETDTR
        k32.PurgeComm(h, 0x0008)                                          # PURGE_RXCLEAR

    def _read_win(self, n, timeout):
        ct = self._ct
        t = self._TIMEOUTS(0xFFFFFFFF, 0xFFFFFFFF, max(1, int(timeout * 1000)), 0, 2000)
        self._k32.SetCommTimeouts(self._h, ct.byref(t))
        buf = ct.create_string_buffer(n)
        got = ct.c_ulong(0)
        if not self._k32.ReadFile(self._h, buf, n, ct.byref(got), None):
            raise SerialError(ct.get_last_error(), f"read from {self.name} failed")
        return buf.raw[:got.value]

    def _write_win(self, data):
        ct = self._ct
        done = ct.c_ulong(0)
        if not self._k32.WriteFile(self._h, data, len(data), ct.byref(done), None) or done.value != len(data):
            raise SerialError(ct.get_last_error(), f"write to {self.name} failed")

    # -- posix ------------------------------------------------------------------
    def _open_posix(self, name):
        import termios
        fd = os.open(name, os.O_RDWR | os.O_NOCTTY)
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
        self._fd = fd

    def _read_posix(self, n, timeout):
        import select
        r, _, _ = select.select([self._fd], [], [], timeout)
        return os.read(self._fd, n) if r else b""

    # -- common -----------------------------------------------------------------
    def write(self, data: bytes) -> None:
        if sys.platform == "win32":
            self._write_win(bytes(data))
        else:
            os.write(self._fd, bytes(data))

    def read(self, n: int = 4096, timeout: float = 0.1) -> bytes:
        return self._read_win(n, timeout) if sys.platform == "win32" else self._read_posix(n, timeout)

    def close(self) -> None:
        if sys.platform == "win32":
            if getattr(self, "_h", None):
                self._k32.CloseHandle(self._h)
                self._h = None
        elif getattr(self, "_fd", None) is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_m8(port: Optional[str] = None, wait: float = 0.0) -> SerialPort:
    """Open `port`, or the first M8 found (waiting up to `wait` seconds for one to appear)."""
    deadline = time.monotonic() + wait
    while True:
        names = [port] if port else find_m8_ports()
        for name in names:
            try:
                return SerialPort(name)
            except OSError:
                pass
        if time.monotonic() >= deadline:
            raise SerialError(2, f"no M8 serial port {'at ' + port if port else 'found'}")
        time.sleep(0.25)
