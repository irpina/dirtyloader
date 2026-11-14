"""
Provisional Core ABI -- the contract shared by the Core builder and by mods.

EVERYTHING HERE IS PROVISIONAL until the Ghidra function map is in and the layout
has been validated on hardware. Addresses come from the 6.6.2A Model02 code-cave
survey (see docs/CORE.md); other builds will differ and the Core mod must pin
itself to a stock sha256 like any other mod.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    """The hook bus's events (docs/CORE-EVENTS.md). The numeric ids are stable ABI; the
    *addresses* each event hooks are bound per firmware and recorded in the Core mod's
    bindings, not here. In mod.json / .m8mod a mod may name an event as `TICK` or, as on
    Elekloader, `ev_tick`."""
    BOOT = 0x0001        # once, after setup(), before the first loop()
    TICK = 0x0010        # each loop() iteration (UI thread)
    DRAW = 0x0020        # each UI frame, before it is pushed to the display
    RENDER_IN = 0x0030   # audio block entry (audio thread, IRQ 70)
    RENDER_OUT = 0x0031  # audio block exit
    KEY = 0x0040         # an input action, before the current view handles it
    VIEW = 0x0041        # a screen change (set_view)
    TOUCH = 0x0042       # a touch frame, before the stock touch engine
    MIDI = 0x0043        # a MIDI message in (site pending)
    SETTINGS = 0x0044    # the settings screen is built (design only)
    NOTE = 0x0050        # a row fires on a track (audio thread)
    FX_COMMAND = 0x0051  # an FX command runs (per-tick executor, audio thread)
    FX_ROW = 0x0052      # a row's FX column is applied at row fire (audio thread)
    MOD_APPLY = 0x0053   # a modulator targets a destination past the stock list (audio thread)
    TEMPO = 0x0060       # the tempo is set
    TRANSPORT = 0x0061   # play / pause / stop
    # earlier names, same ids (core 0.1 files may use them)
    RENDER = 0x0020
    AUDIO_BLOCK = 0x0030
    INPUT = 0x0040


@dataclass(frozen=True)
class EventInfo:
    name: str          # Elekloader-style name
    thread: str        # "ui" | "audio"
    takeable: bool     # int-returning: a nonzero return stops the event and the stock code
    prototype: str     # the handler's C prototype
    status: str        # "implemented" | "site pinned" | "site pending" | "design only"


EVENTS = {
    Event.BOOT: EventInfo("ev_boot", "ui", False, "void f(void)", "site pinned"),
    Event.TICK: EventInfo("ev_tick", "ui", False, "void f(void)", "implemented"),
    Event.DRAW: EventInfo("ev_draw", "ui", False, "void f(void *ui)", "site pinned"),
    Event.RENDER_IN: EventInfo("ev_render_in", "audio", False, "void f(void)", "site pinned"),
    Event.RENDER_OUT: EventInfo("ev_render_out", "audio", False, "void f(void)", "site pinned"),
    Event.KEY: EventInfo("ev_key", "ui", True, "int f(void *ui, int action)", "site pinned"),
    Event.VIEW: EventInfo("ev_view", "ui", True, "int f(void *ui, int view)", "site pinned"),
    Event.TOUCH: EventInfo("ev_touch", "ui", True, "int f(struct m8_touch *t)", "site pinned"),
    Event.MIDI: EventInfo("ev_midi", "ui", True, "int f(const unsigned char *msg, int port)", "site pending"),
    Event.SETTINGS: EventInfo("ev_settings", "ui", False, "void f(void *menu)", "design only"),
    Event.NOTE: EventInfo("ev_note", "audio", True, "int f(int track, const unsigned char *step)", "site pinned"),
    Event.FX_COMMAND: EventInfo("ev_fx_command", "audio", True, "int f(int track, int cmd, int value)",
                                "site pinned"),
    Event.FX_ROW: EventInfo("ev_fx_row", "audio", True, "int f(int track, int column, int cmd, int value)",
                            "site pinned"),
    Event.MOD_APPLY: EventInfo("ev_mod_apply", "audio", False,
                               "void f(int engine, void *voice, void *mod, int dest)", "site pinned"),
    Event.TEMPO: EventInfo("ev_tempo", "ui", True, "int f(float bpm)", "site pinned"),
    Event.TRANSPORT: EventInfo("ev_transport", "ui", True, "int f(int state)", "site pinned"),
}


def by_name(name: str) -> Event:
    """`TICK`, `tick` or `ev_tick` -> Event.TICK. Raises KeyError."""
    n = name.strip()
    if n.lower().startswith("ev_"):
        n = n[3:]
    return Event[n.upper()]


# Handler flags
FLAG_ENABLED = 0x0001
FLAG_ONESHOT = 0x0002
