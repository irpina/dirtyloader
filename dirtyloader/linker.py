"""
The linker: combine selected mods onto a stock firmware (docs/FORMAT.md, "Building").

Before anything is applied it checks, for the whole selection:
  * every mod's target matches the supplied stock firmware (device, and the .bin / payload hashes)
  * requires / conflicts, and the `core` version a mod needs
  * named resources: no two mods claim the same one
  * sites: none overlap, and each one's stock bytes match its stock_sha256 (M8Firmware.apply_all)
  * subscriptions: each event is provided by some selected mod (the core)
Then it applies the sites, installs the subscriptions into the Core's hook table in (order, mod id) order,
and returns a new M8Firmware (both CRCs are recomputed on build()).

`diff_payloads` is the author-side helper behind `make-mod`: a hand-edited image -> hash-guarded sites.
"""
from __future__ import annotations

import hashlib
import struct
from typing import List

from dirtyloader.m8fw import M8Firmware, Patch, M8FWError
from dirtyloader.m8mod import Mod, Site, DEVICES, event_id
from dirtyloader.core import abi


class ConflictError(M8FWError):
    pass


def _ver(v: str):
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def _check_target(fw: M8Firmware, stock_sha256: str, mod: Mod) -> None:
    t = mod.target or {}
    dev = t.get("device")
    if dev is not None:
        if dev not in DEVICES:
            raise M8FWError(f"mod '{mod.id}' targets unknown device {dev!r}")
        if DEVICES[dev] != fw.model:
            raise M8FWError(f"mod '{mod.id}' targets {dev} but the stock firmware is Model:0{fw.model}")
    pin = (t.get("bin_sha256") or "").lower()
    if pin and pin != stock_sha256.lower():
        raise M8FWError(f"mod '{mod.id}' was made for stock {pin[:12]}..., "
                        f"but the stock file is {stock_sha256[:12]}...")
    psha = (t.get("payload_sha256") or "").lower()
    if psha and psha != hashlib.sha256(bytes(fw.payload)).hexdigest():
        raise M8FWError(f"mod '{mod.id}': the stock flash image does not match its payload_sha256")


def link(stock: M8Firmware, stock_sha256: str, mods: List[Mod]) -> M8Firmware:
    """Return a new patched M8Firmware. Raises M8FWError / ConflictError on any problem; `stock` is not
    mutated."""
    ids = [m.id for m in mods]
    if len(set(ids)) != len(ids):
        raise ConflictError("the same mod id appears more than once in the selection")
    by_id = {m.id: m for m in mods}

    for m in mods:
        _check_target(stock, stock_sha256, m)
        for req in m.requires:
            if req not in by_id:
                raise M8FWError(f"mod '{m.id}' requires '{req}', which is not in the selection")
        for con in m.conflicts:
            if con in by_id:
                raise ConflictError(f"mod '{m.id}' declares a conflict with selected mod '{con}'")
        if m.core:
            core = by_id.get("core")
            if core is None:
                raise M8FWError(f"mod '{m.id}' needs core {m.core} or newer, and no core is selected")
            if _ver(core.version) < _ver(m.core):
                raise M8FWError(f"mod '{m.id}' needs core {m.core} or newer; the selected core is {core.version}")

    claimed = {}
    for m in mods:
        for name in (m.resources or {}).get("names", []):
            if name in claimed:
                raise ConflictError(f"mods '{claimed[name]}' and '{m.id}' both claim resource {name!r}")
            claimed[name] = m.id

    provided = {e for m in mods for e in m.events}
    for m in mods:
        for s in m.subscribe:
            if s["event"] not in provided:
                raise M8FWError(f"mod '{m.id}' subscribes to {s['event']}, which no selected mod provides "
                                f"(add the 'core' mod)")

    fw = M8Firmware(version=stock.version, load_addr=stock.load_addr, payload=bytearray(stock.payload))
    patches: List[Patch] = []
    for m in mods:
        for p in m.resolve(fw):
            p.note = f"{m.id}: {p.note}" if p.note else m.id
            patches.append(p)
    fw.apply_all(patches)          # overlap + stock-hash checks happen here

    subs = sorted(((s["order"], m.id, s) for m in mods for s in m.subscribe), key=lambda t: (t[0], t[1]))
    if subs:
        _install_subscriptions(fw, [(mid, s) for _o, mid, s in subs])
    return fw


def _install_subscriptions(fw: M8Firmware, subs) -> None:
    """Give each subscription its own free slot in the Core's hook table, in the order given."""
    region_off = abi.CORE_REGION_ADDR - fw.load_addr
    if bytes(fw.payload[region_off:region_off + len(abi.CORE_MAGIC)]) != abi.CORE_MAGIC:
        raise M8FWError("subscriptions declared but the Core is not installed; add the 'core' mod")
    table_off = region_off + 0x10

    def free_slot() -> int:
        for i in range(abi.MAX_HOOKS):
            ev, _fl, hn = struct.unpack_from(abi.HOOK_ENTRY_FMT, fw.payload, table_off + i * abi.HOOK_ENTRY_SIZE)
            if ev == 0 and hn == 0:
                return i
        raise ConflictError("Core hook table is full")

    for _mid, s in subs:
        slot = free_slot()
        struct.pack_into(abi.HOOK_ENTRY_FMT, fw.payload, table_off + slot * abi.HOOK_ENTRY_SIZE,
                         event_id(s["event"]), abi.FLAG_ENABLED, int(s["handler"]))


def diff_payloads(stock: bytes, modified: bytes, gap: int = 8, load_addr: int = 0x60000000) -> List[Site]:
    """Hash-guarded same-size sites describing how `modified` differs from `stock`. Runs of differing bytes
    separated by fewer than `gap` identical bytes are coalesced into one site."""
    if len(stock) != len(modified):
        raise M8FWError(f"payload sizes differ ({len(stock)} vs {len(modified)}); make-mod needs same-size edits")
    n = len(stock)
    runs = []
    i = 0
    while i < n:
        if stock[i] == modified[i]:
            i += 1
            continue
        j = i + 1
        while j < n:
            if stock[j] != modified[j]:
                j += 1
                continue
            k = j
            while k < n and k < j + gap and stock[k] == modified[k]:
                k += 1
            if k < n and stock[k] != modified[k]:
                j = k
                continue
            break
        runs.append((i, j))
        i = j
    return [Site.from_bytes(load_addr + a, bytes(stock[a:b]), bytes(modified[a:b]), "data",
                            f"edit +{b - a}") for a, b in runs]
