"""
A synthetic M8FW firmware image for the firmware-free test suite.

The real test scripts (dirtyloader/test_*.py) run against the stock Dirtywave
`.bin`, which is never committed, so they cannot run in CI. These helpers build a
small, obviously-fake container -- *not* Dirtywave's bytes -- that is shaped like
the real one (valid M8FW header, a Core region, a code cave) so the container,
format and linker logic can be exercised without any firmware on disk.
"""
from __future__ import annotations

import hashlib

from dirtyloader.m8fw import M8Firmware
from dirtyloader.m8mod import Mod, Site, make_target
from dirtyloader.core import abi

LOAD = 0x60000000
PAYLOAD_LEN = 0x4000            # 16 KiB, enough for the Core region + a cave
CAVE = 0x60000800              # a free spot for handler code, well past the table


def synth_stock(seed: bytes = b"dirtyloader-synthetic") -> M8Firmware:
    """A deterministic, fake stock image. Its Core region is zeroed so a synthetic
    core mod has predictable stock bytes to guard against."""
    payload = bytearray(
        hashlib.sha256(seed + i.to_bytes(4, "little")).digest()[0]
        for i in range(PAYLOAD_LEN)
    )
    region_off = abi.CORE_REGION_ADDR - LOAD
    for i in range(region_off, region_off + abi.CORE_REGION_SIZE):
        payload[i] = 0
    return M8Firmware(version=0x00020001, load_addr=LOAD, payload=payload)


def stock_sha(fw: M8Firmware) -> str:
    return hashlib.sha256(fw.build()).hexdigest()


def synth_core(fw: M8Firmware, sha: str) -> Mod:
    """A stand-in Core mod: it only writes the DLCORE magic + an empty table into
    the Core region, enough for the linker to accept subscriptions."""
    region_off = abi.CORE_REGION_ADDR - LOAD
    stock = bytes(fw.payload[region_off:region_off + 16])
    new = abi.CORE_MAGIC + b"\x00" * (16 - len(abi.CORE_MAGIC))
    site = Site.from_bytes(abi.CORE_REGION_ADDR, stock, new, "data", "core header")
    return Mod(
        id="core", version="0.1.0", title="synthetic core", events=["TICK"],
        target=make_target(fw, sha, "synthetic"),
        sites=[site], resources={"names": ["core:hook-table"]},
    )


def synth_handler(fw: M8Firmware, sha: str, cave: int = CAVE, mod_id: str = "demo") -> Mod:
    """A stand-in handler mod: a 2-byte `bx lr` in the cave, subscribed to TICK."""
    off = cave - LOAD
    stock = bytes(fw.payload[off:off + 2])
    site = Site.from_bytes(cave, stock, b"\x70\x47", "code", "handler")
    return Mod(
        id=mod_id, version="1.0.0", title="synthetic handler",
        requires=["core"], core="0.1", target=make_target(fw, sha, "synthetic"),
        sites=[site], subscribe=[{"event": "TICK", "handler": cave | 1, "order": 60}],
    )
