"""
The linker: combine selected mods onto a stock firmware.

Responsibilities:
  * verify each mod targets the supplied stock (model + optional sha256 pin)
  * resolve requires / conflicts across the selected set
  * resolve every mod's patches to concrete payload offsets
  * detect cross-mod byte overlaps and stale `expect` bytes (via M8Firmware.apply_all)
  * return a patched M8Firmware with both CRCs recomputed on build()

Plus `diff_payloads`, the author-side helper behind `make-mod`: it turns a
hand-modified .bin into a set of guarded patches.
"""
from __future__ import annotations

import struct
from typing import List

from dirtyloader.m8fw import M8Firmware, Patch, M8FWError
from dirtyloader.m8mod import Mod, ModPatch
from dirtyloader.core import abi


class ConflictError(M8FWError):
    pass


def _check_target(fw: M8Firmware, stock_sha256: str, mod: Mod) -> None:
    t = mod.target or {}
    model = t.get("model")
    if model is not None and int(model) != fw.model:
        raise M8FWError(
            f"mod '{mod.id}' targets model {model} but supplied firmware is model {fw.model}"
        )
    pin = (t.get("stock_sha256") or "").lower()
    if pin and pin != stock_sha256.lower():
        raise M8FWError(
            f"mod '{mod.id}' targets stock sha256 {pin[:12]}... "
            f"but supplied stock is {stock_sha256[:12]}..."
        )


def link(stock: M8Firmware, stock_sha256: str, mods: List[Mod]) -> M8Firmware:
    """Return a new patched M8Firmware. Raises M8FWError/ConflictError on any
    unmet requirement, conflict, overlap, or stale expected-bytes mismatch.
    `stock` is not mutated."""
    ids = [m.id for m in mods]
    if len(set(ids)) != len(ids):
        raise ConflictError("the same mod id appears more than once in the selection")
    idset = set(ids)

    for m in mods:
        for req in m.requires:
            if req not in idset:
                raise M8FWError(f"mod '{m.id}' requires '{req}', which is not in the selection")
        for con in m.conflicts:
            if con in idset:
                raise ConflictError(f"mod '{m.id}' declares a conflict with selected mod '{con}'")
        _check_target(stock, stock_sha256, m)

    fw = M8Firmware(
        version=stock.version,
        load_addr=stock.load_addr,
        payload=bytearray(stock.payload),
    )

    patches: List[Patch] = []
    for m in mods:
        for p in m.resolve(fw):
            p.note = f"{m.id}: {p.note}" if p.note else m.id
            patches.append(p)

    fw.apply_all(patches)  # overlap + expected-byte checks happen here

    hooks = [(m.id, h) for m in mods for h in m.hooks]
    if hooks:
        _install_hooks(fw, hooks)
    return fw


def _install_hooks(fw: M8Firmware, hooks) -> None:
    """Register each declared hook into a free Core hook-table slot. Requires the
    Core to be installed (its magic present at CORE_REGION_ADDR). This is what
    lets several mods hook one event -- each gets its own slot, so they coexist
    instead of overwriting one call site."""
    region_off = abi.CORE_REGION_ADDR - fw.load_addr
    if bytes(fw.payload[region_off:region_off + len(abi.CORE_MAGIC)]) != abi.CORE_MAGIC:
        raise M8FWError("hooks declared but the Core is not installed; add the 'core' mod")
    table_off = region_off + 0x10

    def free_slot() -> int:
        for i in range(abi.MAX_HOOKS):
            ev, _fl, hn = struct.unpack_from(abi.HOOK_ENTRY_FMT, fw.payload, table_off + i * abi.HOOK_ENTRY_SIZE)
            if ev == 0 and hn == 0:
                return i
        raise ConflictError("Core hook table is full")

    for mid, h in hooks:
        slot = free_slot()
        struct.pack_into(abi.HOOK_ENTRY_FMT, fw.payload, table_off + slot * abi.HOOK_ENTRY_SIZE,
                         int(h["event"]), abi.FLAG_ENABLED, int(h["handler"]))


def diff_payloads(stock: bytes, modified: bytes, gap: int = 8) -> List[ModPatch]:
    """Produce guarded same-size patches describing how `modified` differs from
    `stock`. Runs of differing bytes separated by fewer than `gap` identical
    bytes are coalesced into a single patch to keep the mod tidy."""
    if len(stock) != len(modified):
        raise M8FWError(
            f"payload sizes differ ({len(stock)} vs {len(modified)}); "
            f"v1 make-mod only supports same-size edits"
        )
    n = len(stock)
    runs: List[tuple] = []
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
            # peek: if another difference falls within `gap`, swallow the gap
            k = j
            while k < n and k < j + gap and stock[k] == modified[k]:
                k += 1
            if k < n and stock[k] != modified[k]:
                j = k
                continue
            break
        runs.append((i, j))
        i = j

    return [
        ModPatch(
            offset=a,
            expect=bytes(stock[a:b]),
            data=bytes(modified[a:b]),
            note=f"edit @0x{a:X} (+{b - a})",
        )
        for (a, b) in runs
    ]
