"""
Provisional Core ABI -- the contract shared by the Core builder and by mods.

EVERYTHING HERE IS PROVISIONAL until the Ghidra function map is in and the layout
has been validated on hardware. Addresses come from the 6.6.2A Model02 code-cave
survey (see docs/CORE.md); other builds will differ and the Core mod must pin
itself to a stock sha256 like any other mod.
"""
from __future__ import annotations

from enum import IntEnum

# --- where the Core lives -------------------------------------------------
# Largest fixed, predictable free region: the 0xFF padding after the FlexSPI
# config block (0x60000200 .. 0x60001000), 3584 bytes. The Core dispatcher +
# handler table live here.
CORE_REGION_ADDR = 0x60000200
CORE_REGION_SIZE = 0x0E00  # 3584 bytes

# A magic placed at the region start so a mod (or the loader) can confirm the
# Core is installed and read its version/table pointer.
CORE_MAGIC = b"DLCORE\x00\x01"  # 8 bytes: "DLCORE" + version (0x0001)

# Secondary caves the Core may spill into (boot gap, csf/reserved tail).
SPARE_CAVES = (
    (0x6000102C, 0x03D4),  # 980 B, boot-data -> vectors gap (0xFF)
    (0x601EA400, 0x0C00),  # 3072 B, csf/reserved tail (0x00)
)

# --- handler table ---------------------------------------------------------
MAX_HOOKS = 64
# table entry: event_id:u16, flags:u16, handler_addr:u32  (8 bytes, little-endian)
HOOK_ENTRY_FMT = "<HHI"
HOOK_ENTRY_SIZE = 8


class Event(IntEnum):
    """Named firmware integration points. The numeric ids are stable ABI; the
    *addresses* each event hooks into are bound per-firmware after Ghidra
    analysis and recorded in the Core mod's manifest, not here."""
    BOOT = 0x0001        # once, late in startup, before the main loop
    TICK = 0x0010        # each main-loop iteration
    RENDER = 0x0020      # UI / display frame
    AUDIO_BLOCK = 0x0030 # audio buffer fill
    INPUT = 0x0040       # key / encoder input event


# Handler flags
FLAG_ENABLED = 0x0001
FLAG_ONESHOT = 0x0002
