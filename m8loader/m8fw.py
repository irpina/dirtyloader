"""
m8fw -- parser / builder for the Dirtywave M8 ".bin" firmware container ("M8FW").

This is the foundation layer for an Elekloader-style mod patcher: it unpacks the
stock firmware, lets you patch the payload, and repacks it with both integrity
CRCs recomputed so the M8's on-device firmware updater accepts the result.

Container layout (reverse-engineered from M8 6.6.2 Model02):

    offset  size  field          notes
    0x00    4     magic          b"M8FW"
    0x04    4     version        u32 LE. high byte of low word = model (0x0002 => Model02)
    0x08    4     payload_len    u32 LE, == len(payload)
    0x0C    4     payload_crc32  u32 LE, == zlib.crc32(payload)
    0x10    4     load_addr      u32 LE, 0x60000000 (Teensy 4.1 FlexSPI flash base)
    0x14    4     header_crc32   u32 LE, == zlib.crc32(header[0x00:0x14])
    0x18..  ..    zero padding up to 0x200
    0x200   N     payload        flat IMXRT1062 flash image mapped at load_addr

Both CRCs are standard zlib CRC-32 (poly 0xEDB88320). No cryptographic signature
is present, which is what makes recompile-free binary modding possible.

Pure stdlib. No third-party deps.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from typing import List, Optional

MAGIC = b"M8FW"
HEADER_SIZE = 0x200
HEADER_FIELDS_END = 0x14  # header_crc32 covers header[0:0x14]
DEFAULT_LOAD_ADDR = 0x60000000


class M8FWError(Exception):
    """Raised on malformed containers or failed integrity checks."""


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


@dataclass
class Patch:
    """A single byte-level edit, expressed in payload-relative offset space.

    `expected` guards against applying a mod to the wrong firmware: the bytes
    currently at `offset` must equal `expected` or the patch is rejected.
    """
    offset: int
    new: bytes
    expected: Optional[bytes] = None
    note: str = ""

    def __post_init__(self):
        if self.expected is not None and len(self.expected) != len(self.new):
            raise M8FWError(
                f"patch @0x{self.offset:X}: expected/new length mismatch "
                f"({len(self.expected)} vs {len(self.new)})"
            )


@dataclass
class M8Firmware:
    version: int
    load_addr: int
    payload: bytearray
    # values as read from the stock header (for verification / reporting)
    stored_payload_len: Optional[int] = None
    stored_payload_crc: Optional[int] = None
    stored_header_crc: Optional[int] = None

    # ---- parsing -----------------------------------------------------------
    @classmethod
    def parse(cls, data: bytes, verify: bool = True) -> "M8Firmware":
        if len(data) < HEADER_SIZE:
            raise M8FWError(f"file too small ({len(data)} < {HEADER_SIZE} header bytes)")
        if data[:4] != MAGIC:
            raise M8FWError(f"bad magic {data[:4]!r}, expected {MAGIC!r}")
        version, payload_len, payload_crc, load_addr, header_crc = struct.unpack_from(
            "<IIIII", data, 4
        )
        payload = bytearray(data[HEADER_SIZE:HEADER_SIZE + payload_len])
        fw = cls(
            version=version,
            load_addr=load_addr,
            payload=payload,
            stored_payload_len=payload_len,
            stored_payload_crc=payload_crc,
            stored_header_crc=header_crc,
        )
        if verify:
            problems = fw.check_stock(data)
            if problems:
                raise M8FWError("; ".join(problems))
        return fw

    @classmethod
    def from_file(cls, path: str, verify: bool = True) -> "M8Firmware":
        with open(path, "rb") as f:
            return cls.parse(f.read(), verify=verify)

    def check_stock(self, original: bytes) -> List[str]:
        """Validate a freshly-parsed container against its own header. Returns
        a list of human-readable problems (empty == valid stock firmware)."""
        problems: List[str] = []
        if self.stored_payload_len != len(self.payload):
            problems.append(
                f"payload length {len(self.payload)} != header 0x{self.stored_payload_len:X} "
                f"(truncated or trailing data)"
            )
        if self.stored_payload_crc != crc32(self.payload):
            problems.append(
                f"payload CRC mismatch: header 0x{self.stored_payload_crc:08X} "
                f"!= computed 0x{crc32(self.payload):08X}"
            )
        header_crc_calc = crc32(original[0:HEADER_FIELDS_END])
        if self.stored_header_crc != header_crc_calc:
            problems.append(
                f"header CRC mismatch: header 0x{self.stored_header_crc:08X} "
                f"!= computed 0x{header_crc_calc:08X}"
            )
        return problems

    # ---- derived info ------------------------------------------------------
    @property
    def model(self) -> int:
        # version 0x00020001 -> model 2 (Model02)
        return (self.version >> 16) & 0xFFFF

    @property
    def format_rev(self) -> int:
        return self.version & 0xFFFF

    def payload_crc32(self) -> int:
        return crc32(self.payload)

    def addr_to_offset(self, addr: int) -> int:
        """Convert an absolute flash address (as seen in a disassembler) to a
        payload offset."""
        off = addr - self.load_addr
        if not (0 <= off < len(self.payload)):
            raise M8FWError(f"address 0x{addr:08X} outside payload range")
        return off

    # ---- patching ----------------------------------------------------------
    def apply(self, patch: Patch) -> None:
        end = patch.offset + len(patch.new)
        if patch.offset < 0 or end > len(self.payload):
            raise M8FWError(
                f"patch @0x{patch.offset:X} (+{len(patch.new)}) outside payload "
                f"(size 0x{len(self.payload):X})"
            )
        if patch.expected is not None:
            actual = bytes(self.payload[patch.offset:end])
            if actual != patch.expected:
                raise M8FWError(
                    f"patch @0x{patch.offset:X} expected {patch.expected.hex()} "
                    f"but found {actual.hex()}"
                    + (f" ({patch.note})" if patch.note else "")
                )
        self.payload[patch.offset:end] = patch.new

    def apply_all(self, patches: List[Patch]) -> None:
        # overlap detection -- two mods editing the same bytes is a conflict
        spans = sorted((p.offset, p.offset + len(p.new), p.note) for p in patches)
        for (s1, e1, n1), (s2, e2, n2) in zip(spans, spans[1:]):
            if s2 < e1:
                raise M8FWError(
                    f"conflicting patches overlap at 0x{s2:X} "
                    f"({n1 or 'patch A'} vs {n2 or 'patch B'})"
                )
        for p in patches:
            self.apply(p)

    # ---- building ----------------------------------------------------------
    def build(self) -> bytes:
        """Serialize to a flashable .bin with both CRCs recomputed."""
        payload = bytes(self.payload)
        header = bytearray(HEADER_SIZE)
        header[0:4] = MAGIC
        struct.pack_into(
            "<IIII", header, 4,
            self.version, len(payload), crc32(payload), self.load_addr,
        )
        struct.pack_into("<I", header, 0x14, crc32(bytes(header[0:HEADER_FIELDS_END])))
        return bytes(header) + payload

    def to_file(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.build())

    def sha256(self) -> str:
        return hashlib.sha256(self.build()).hexdigest()

    def summary(self) -> str:
        return (
            f"M8FW  model={self.model:02d}  format_rev={self.format_rev}  "
            f"payload=0x{len(self.payload):X} ({len(self.payload)} B)  "
            f"load=0x{self.load_addr:08X}  payload_crc=0x{self.payload_crc32():08X}"
        )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python m8fw.py <firmware.bin>")
        raise SystemExit(2)
    fw = M8Firmware.from_file(sys.argv[1])
    print(fw.summary())
    print("sha256:", fw.sha256())
