"""
Known stock-firmware registry.

Maps the SHA-256 of an *unmodified* M8 ".bin" (the whole M8FW container, exactly
as Dirtywave ships it) to a human-readable identity. This lets the loader tell
the user which firmware they supplied and lets a mod pin itself to an exact build.

Only hashes are stored here -- never the firmware itself.
"""
from __future__ import annotations

import hashlib
from typing import Optional

# sha256(stock .bin) -> identity
KNOWN_FIRMWARES = {
    "fbc15296886a278bd72a0040ce07b13d17c7928c1850721299ba5dd4eaf30326": {
        "name": "M8 firmware 6.6.2A (Model02)",
        "model": 2,
        "version": "6.6.2A",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def identify(sha256: str) -> Optional[dict]:
    return KNOWN_FIRMWARES.get(sha256.lower())
