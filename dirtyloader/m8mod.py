"""
.m8mod -- the mod package format for dirtyloader.

A .m8mod is a small JSON document carrying ONLY the mod author's own bytes plus
the stock bytes each edit expects to overwrite. It never embeds Dirtywave's
firmware, so mods are freely shareable; the end user supplies their own stock
.bin and the loader applies the mod to it.

Design mirrors Elektron's .elemod: every patch is guarded by the stock bytes it
expects, so a mod physically cannot apply to firmware it wasn't built for.

JSON shape:
    {
      "m8mod_format": 1,
      "id": "demo-rename-scale",
      "name": "Rename Harmonic Major scale",
      "author": "you",
      "version": "1.0.0",
      "description": "...",
      "target":   { "model": 2, "stock_sha256": "fbc152..." },
      "requires": [],
      "conflicts": [],
      "patches": [
        { "note": "...", "addr": "0x601D0E62",
          "expect": "<stock hex>", "data": "<new hex>" }
      ]
    }

Each patch sets exactly one of `addr` (absolute flash address, resolved via the
firmware's load address) or `offset` (payload-relative). `expect` and `data`
must be equal length -- v1 is same-size byte replacement only (no relocation).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from dirtyloader.m8fw import M8Firmware, Patch, M8FWError

M8MOD_FORMAT = 1


def _hex_to_bytes(s: str, label: str) -> bytes:
    try:
        return bytes.fromhex(s.strip().replace(" ", ""))
    except (ValueError, AttributeError) as e:
        raise M8FWError(f"{label}: invalid hex {s!r}: {e}")


def _as_int(v) -> Optional[int]:
    if v is None:
        return None
    return int(v, 0) if isinstance(v, str) else int(v)


@dataclass
class ModPatch:
    data: bytes
    expect: Optional[bytes] = None
    offset: Optional[int] = None
    addr: Optional[int] = None
    note: str = ""

    def __post_init__(self):
        if (self.offset is None) == (self.addr is None):
            raise M8FWError(f"patch '{self.note}': set exactly one of offset/addr")
        if self.expect is not None and len(self.expect) != len(self.data):
            raise M8FWError(
                f"patch '{self.note}': expect ({len(self.expect)}) and data "
                f"({len(self.data)}) must be the same length"
            )

    def resolve(self, fw: M8Firmware) -> Patch:
        off = self.offset if self.offset is not None else fw.addr_to_offset(self.addr)
        return Patch(offset=off, new=self.data, expected=self.expect, note=self.note)

    @classmethod
    def from_dict(cls, d: dict) -> "ModPatch":
        return cls(
            data=_hex_to_bytes(d["data"], "data"),
            expect=_hex_to_bytes(d["expect"], "expect") if d.get("expect") else None,
            offset=_as_int(d.get("offset")),
            addr=_as_int(d.get("addr")),
            note=d.get("note", ""),
        )

    def to_dict(self) -> dict:
        out: dict = {"note": self.note}
        if self.addr is not None:
            out["addr"] = f"0x{self.addr:08X}"
        else:
            out["offset"] = f"0x{self.offset:X}"
        if self.expect is not None:
            out["expect"] = self.expect.hex()
        out["data"] = self.data.hex()
        return out


@dataclass
class Mod:
    id: str
    name: str
    patches: List[ModPatch]
    author: str = ""
    version: str = "0.0.0"
    description: str = ""
    target: dict = field(default_factory=dict)      # model / firmware_version / stock_sha256
    requires: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    # Core hook registrations: [{"event": int, "handler": int}]. The linker
    # allocates a free Core hook-table slot per entry (needs requires: ["core"]).
    hooks: List[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Mod":
        fmt = d.get("m8mod_format")
        if fmt != M8MOD_FORMAT:
            raise M8FWError(f"unsupported m8mod_format {fmt!r} (this build understands {M8MOD_FORMAT})")
        if not d.get("id") or not d.get("name"):
            raise M8FWError("mod is missing required 'id' or 'name'")
        return cls(
            id=d["id"],
            name=d["name"],
            patches=[ModPatch.from_dict(p) for p in d.get("patches", [])],
            author=d.get("author", ""),
            version=d.get("version", "0.0.0"),
            description=d.get("description", ""),
            target=dict(d.get("target") or {}),
            requires=list(d.get("requires", [])),
            conflicts=list(d.get("conflicts", [])),
            hooks=[{"event": _as_int(h["event"]), "handler": _as_int(h["handler"])}
                   for h in d.get("hooks", [])],
        )

    def to_dict(self) -> dict:
        return {
            "m8mod_format": M8MOD_FORMAT,
            "id": self.id,
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "description": self.description,
            "target": self.target,
            "requires": self.requires,
            "conflicts": self.conflicts,
            "hooks": [{"event": h["event"], "handler": f"0x{h['handler']:08X}"}
                      for h in self.hooks],
            "patches": [p.to_dict() for p in self.patches],
        }

    @classmethod
    def load(cls, path: str) -> "Mod":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")

    def resolve(self, fw: M8Firmware) -> List[Patch]:
        return [p.resolve(fw) for p in self.patches]
