"""
.m8mod -- dirtyloader's mod format. The specification is docs/FORMAT.md.

Format 2 follows Elekloader's .elemod: a mod ships only its own bytes and a sha256 of the stock bytes each
site replaces, never the stock bytes. Where its bytes repeat the firmware it says ["stock", addr, n] and the
loader copies them from the user's own firmware. Format-1 files (which carried the stock bytes as "expect")
still load and are converted to format 2 in memory; save() always writes format 2.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional

from dirtyloader.m8fw import M8Firmware, Patch, M8FWError
from dirtyloader.core.abi import Event

FORMAT = 2
M8MOD_FORMAT = FORMAT          # kept for older imports
KINDS = ("code", "data")
DEVICES = {"m8-model02": 2, "m8-model01": 1, "m8-headless": 0}   # device -> M8Firmware.model
PRODUCTS = {2: "M8 Model:02", 1: "M8 Model:01", 0: "M8 Headless"}
DEFAULT_ORDER = 50


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _int(v) -> Optional[int]:
    if v is None:
        return None
    return int(v, 0) if isinstance(v, str) else int(v)


def _hex(s: str, label: str) -> bytes:
    try:
        return bytes.fromhex(s.strip().replace(" ", ""))
    except (ValueError, AttributeError) as e:
        raise M8FWError(f"{label}: invalid hex {s!r}: {e}")


def event_id(ev) -> int:
    """An event given by name ("TICK", or Elekloader-style "ev_tick") or number -> its numeric id."""
    if isinstance(ev, str) and not ev.strip().lstrip("-").isdigit() and not ev.lower().startswith("0x"):
        from dirtyloader.core.abi import by_name
        try:
            return int(by_name(ev))
        except KeyError:
            raise M8FWError(f"unknown event {ev!r}; known: {', '.join(e.name for e in Event)}")
    return int(_int(ev))


def event_name(ev) -> str:
    i = event_id(ev)
    try:
        return Event(i).name
    except ValueError:
        return f"0x{i:04X}"


# ---------------------------------------------------------------- sites
@dataclass
class Site:
    """A same-size change to the stock flash image, guarded by the stock bytes' hash."""
    addr: int
    len: int
    stock_sha256: str
    new: list                      # parts: ["hex", "..."] | ["stock", "0x...", n]
    kind: str = "data"
    note: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise M8FWError(f"site 0x{self.addr:08X}: kind {self.kind!r} is not one of {KINDS}")
        if len(self.stock_sha256 or "") != 64:
            raise M8FWError(f"site 0x{self.addr:08X}: stock_sha256 must be a sha256")
        declared = sum(len(bytes.fromhex(p[1])) if p[0] == "hex" else int(p[2]) for p in self.new)
        if declared != self.len:
            raise M8FWError(f"site 0x{self.addr:08X}: new parts add up to {declared} bytes, len is {self.len}")

    @classmethod
    def from_bytes(cls, addr: int, stock: bytes, new: bytes, kind: str = "data", note: str = "") -> "Site":
        if len(stock) != len(new):
            raise M8FWError(f"site 0x{addr:08X}: stock and new lengths differ")
        return cls(addr=addr, len=len(new), stock_sha256=sha256(stock), new=[["hex", new.hex()]],
                   kind=kind, note=note)

    def data(self, fw: M8Firmware) -> bytes:
        out = b""
        for p in self.new:
            if p[0] == "hex":
                out += bytes.fromhex(p[1])
            elif p[0] == "stock":
                o = fw.addr_to_offset(_int(p[1]))
                out += bytes(fw.payload[o:o + int(p[2])])
            else:
                raise M8FWError(f"site 0x{self.addr:08X}: unknown part {p[0]!r}")
        return out

    def resolve(self, fw: M8Firmware) -> Patch:
        return Patch(offset=fw.addr_to_offset(self.addr), new=self.data(fw),
                     expected_sha256=self.stock_sha256, note=self.note)

    @classmethod
    def from_dict(cls, d: dict) -> "Site":
        new = d["new"]
        if isinstance(new, str):
            new = [["hex", new]]
        for p in new:
            if p[0] == "hex":
                _hex(p[1], "new")
        return cls(addr=_int(d["addr"]), len=int(d["len"]), stock_sha256=str(d["stock_sha256"]).lower(),
                   new=[list(p) for p in new], kind=d.get("kind", "data"), note=d.get("note", ""))

    def to_dict(self) -> dict:
        new = self.new[0][1] if len(self.new) == 1 and self.new[0][0] == "hex" else self.new
        out = {"addr": f"0x{self.addr:08x}", "len": self.len, "kind": self.kind,
               "stock_sha256": self.stock_sha256, "new": new}
        if self.note:
            out["note"] = self.note
        return out


# ---------------------------------------------------------------- mods
@dataclass
class Mod:
    id: str
    version: str = "0.0.0"
    title: str = ""
    description: str = ""
    category: str = ""
    author: str = ""
    license: str = ""
    target: dict = field(default_factory=dict)
    sites: List[Site] = field(default_factory=list)
    events: List[str] = field(default_factory=list)       # core only: events it installs
    subscribe: List[dict] = field(default_factory=list)   # [{"event", "handler", "order"}]
    core: Optional[str] = None                            # oldest core version this mod works with
    resources: dict = field(default_factory=dict)
    requires: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    signature: Optional[str] = None
    loaded_format: int = FORMAT

    @property
    def name(self) -> str:
        return self.title or self.id

    # -- loading ------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "Mod":
        if d.get("m8mod") == 2:
            return cls._from_v2(d)
        if d.get("m8mod_format") == 1:
            return cls._from_v1(d)
        raise M8FWError(f"not an .m8mod this build understands (m8mod={d.get('m8mod')!r}, "
                        f"m8mod_format={d.get('m8mod_format')!r})")

    @classmethod
    def _from_v2(cls, d: dict) -> "Mod":
        if not d.get("id"):
            raise M8FWError("mod is missing 'id'")
        subs = [{"event": event_name(s["event"]), "handler": _int(s["handler"]),
                 "order": int(s.get("order", DEFAULT_ORDER))} for s in d.get("subscribe", [])]
        return cls(
            id=d["id"], version=str(d.get("version", "0.0.0")), title=d.get("title", ""),
            description=d.get("description", ""), category=d.get("category", ""),
            author=d.get("author", ""), license=d.get("license", ""),
            target=dict(d.get("target") or {}),
            sites=[Site.from_dict(s) for s in d.get("sites", [])],
            events=[event_name(e) for e in d.get("events", [])],
            subscribe=subs, core=d.get("core"), resources=dict(d.get("resources") or {}),
            requires=list(d.get("requires", [])), conflicts=list(d.get("conflicts", [])),
            signature=d.get("signature"), loaded_format=2,
        )

    @classmethod
    def _from_v1(cls, d: dict) -> "Mod":
        """Format 1 carried stock bytes in each patch's "expect"; hash them into format-2 sites."""
        if not d.get("id"):
            raise M8FWError("mod is missing 'id'")
        sites = []
        for p in d.get("patches", []):
            if not p.get("expect"):
                raise M8FWError(f"format-1 patch '{p.get('note', '')}' has no expect; cannot be guarded")
            stock = _hex(p["expect"], "expect")
            new = _hex(p["data"], "data")
            addr = _int(p.get("addr"))
            off = _int(p.get("offset"))
            if addr is None:
                if off is None:
                    raise M8FWError("format-1 patch has neither addr nor offset")
                addr = 0x60000000 + off
            sites.append(Site.from_bytes(addr, stock, new, "data", p.get("note", "")))
        t = d.get("target") or {}
        target = {}
        if t.get("model") is not None:
            target["device"] = f"m8-model0{int(t['model'])}"
        if t.get("firmware_version"):
            target["firmware"] = t["firmware_version"]
        if t.get("stock_sha256"):
            target["bin_sha256"] = t["stock_sha256"].lower()
        subs = [{"event": event_name(h["event"]), "handler": _int(h["handler"]), "order": DEFAULT_ORDER}
                for h in d.get("hooks", [])]
        return cls(id=d["id"], version=str(d.get("version", "0.0.0")), title=d.get("name", ""),
                   description=d.get("description", ""), author=d.get("author", ""), target=target,
                   sites=sites, subscribe=subs, requires=list(d.get("requires", [])),
                   conflicts=list(d.get("conflicts", [])), loaded_format=1)

    @classmethod
    def load(cls, path: str) -> "Mod":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # -- saving -------------------------------------------------------
    def to_dict(self) -> dict:
        d = {"m8mod": FORMAT, "id": self.id, "version": self.version, "title": self.title,
             "description": self.description, "category": self.category, "author": self.author,
             "license": self.license, "target": self.target, "requires": self.requires,
             "conflicts": self.conflicts}
        if self.core:
            d["core"] = self.core
        if self.events:
            d["events"] = self.events
        d["sites"] = [s.to_dict() for s in self.sites]
        d["subscribe"] = [{"event": s["event"], "handler": f"0x{s['handler']:08x}", "order": s["order"]}
                          for s in self.subscribe]
        d["resources"] = self.resources or {"names": []}
        d["signature"] = self.signature
        return d

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1)
            f.write("\n")

    def resolve(self, fw: M8Firmware) -> List[Patch]:
        return [s.resolve(fw) for s in self.sites]


def make_target(fw: M8Firmware, bin_sha256: str, firmware: str = "") -> dict:
    """The `target` block for mods made against this stock firmware."""
    device = next((d for d, m in DEVICES.items() if m == fw.model), f"m8-model0{fw.model}")
    return {"device": device, "product": PRODUCTS.get(fw.model, f"M8 Model:0{fw.model}"), "firmware": firmware,
            "bin_sha256": bin_sha256, "payload_sha256": sha256(bytes(fw.payload)),
            "payload_len": len(fw.payload)}
