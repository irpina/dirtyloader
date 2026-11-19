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
    CARD_READY = 0x0002  # the SD card is up, before the firmware uses it (core 0.4: right after loading mods)
    USB = 0x0003         # USB configured or lost (core 0.4, from ev_tick)
    CRASH = 0x0004       # a fault, before Teensyduino's handler records it and resets
    TICK = 0x0010        # each loop() iteration (UI thread)
    DRAW = 0x0020        # each UI frame, before it is pushed to the display
    VIS_DRAW = 0x0021    # each visualizer frame (Model:02), before it is pushed: ev_draw doesn't run there
    VIS_SCOPE = 0x0022   # the visualizer is about to draw one track's scope (Model:02); take it to skip it
    RENDER_IN = 0x0030   # audio block entry (audio thread, IRQ 70)
    RENDER_OUT = 0x0031  # audio block exit
    AUDIO_OUT = 0x0032   # the master output block, before USB / I2S (insert or exclusive audio)
    TRACK_AUDIO = 0x0033 # a track's rendered block, before its mixer strip and sends
    FX_AUDIO = 0x0034    # a send effect's input block, before it runs (MFX, delay, reverb)
    RENDER_PARAMS = 0x0035  # once per audio block, before the sequencer and the tracks
    KEY = 0x0040         # an input action, before the current view handles it
    VIEW = 0x0041        # a screen change (set_view)
    TOUCH = 0x0042       # a touch frame, before the stock touch engine
    MIDI = 0x0043        # a MIDI message in (headless: each USB MIDI packet)
    SETTINGS = 0x0044    # the settings screen is built (design only)
    SYSEX = 0x0047       # a USB MIDI SysEx chunk arrives (headless)
    SERIAL = 0x0045      # the m8c serial parser is about to read the USB serial input (headless)
    MIDI_OUT = 0x0046    # a USB MIDI packet is about to be sent (headless)
    NOTE = 0x0050        # a row fires on a track (audio thread)
    FX_COMMAND = 0x0051  # an FX command runs (per-tick executor, audio thread)
    FX_ROW = 0x0052      # a row's FX column is applied at row fire (audio thread)
    MOD_APPLY = 0x0053   # a modulator is applied to its destination (audio thread)
    NOTE_OFF = 0x0054    # a track's note is released or killed (audio thread)
    ROW = 0x0055         # the sequencer fires a new row on a track (audio thread)
    LIVE_NOTE = 0x0056   # a note played from the keys / preview, not the sequencer
    TEMPO = 0x0060       # the tempo is set
    TRANSPORT = 0x0061   # play / pause / stop
    PLAY = 0x0062        # the sequencer starts
    STOP = 0x0063        # the sequencer stops
    SEQ_TICK = 0x0064    # each sequencer tick (192 a beat; audio thread)
    MUTE = 0x0065        # a track's mute / solo state is applied
    SONG_LOAD = 0x0070   # a song file is about to be loaded
    SONG_SAVE = 0x0071   # a song file is about to be saved
    INST_LOAD = 0x0072   # an instrument file is about to be loaded into a slot
    INST_SAVE = 0x0073   # an instrument slot is about to be saved to a file
    INST_CLEAR = 0x0074  # an instrument slot is about to be cleared
    INST_COPY = 0x0075   # an instrument is cloned into another slot
    INST_PASTE = 0x0076  # the copied instrument is pasted into a slot
    PARAM_SET = 0x0080   # an instrument parameter was edited
    STEP_EDIT = 0x0081   # phrase cells were edited
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
    Event.BOOT: EventInfo("ev_boot", "ui", False, "void f(void)", "implemented (headless)"),
    Event.CARD_READY: EventInfo("ev_card_ready", "ui", False, "void f(int mounted)", "implemented (headless)"),
    Event.USB: EventInfo("ev_usb", "ui", False, "void f(int configured)", "implemented (headless)"),
    Event.CRASH: EventInfo("ev_crash", "fault", False, "void f(const uint32_t *frame)", "implemented (headless)"),
    Event.TICK: EventInfo("ev_tick", "ui", False, "void f(void)", "implemented (Model:02, headless)"),
    Event.DRAW: EventInfo("ev_draw", "ui", False, "void f(void *ui)", "implemented (headless)"),
    Event.RENDER_IN: EventInfo("ev_render_in", "audio", False, "void f(void)", "implemented (headless)"),
    Event.RENDER_OUT: EventInfo("ev_render_out", "audio", False, "void f(void)", "implemented (headless)"),
    Event.AUDIO_OUT: EventInfo("ev_audio_out", "audio", True, "int f(float *left, float *right, int frames)", "implemented (headless)"),
    Event.TRACK_AUDIO: EventInfo("ev_track_audio", "audio", False, "void f(float *left, float *right, int track)", "implemented (headless)"),
    Event.FX_AUDIO: EventInfo("ev_fx_audio", "audio", True, "int f(int stage, float *left, float *right)", "implemented (headless)"),
    Event.RENDER_PARAMS: EventInfo("ev_render_params", "audio", False, "void f(void *engine)", "implemented (headless)"),
    Event.KEY: EventInfo("ev_key", "ui", True, "int f(void *ui, int action)", "implemented (headless)"),
    Event.VIEW: EventInfo("ev_view", "ui", True, "int f(void *ui, int view)", "implemented (headless)"),
    Event.VIS_DRAW: EventInfo("ev_vis_draw", "ui", False, "void f(void *grid)", "implemented (Model:02)"),
    Event.VIS_SCOPE: EventInfo("ev_vis_scope", "ui", True, "int f(void *scope)", "implemented (Model:02)"),
    Event.TOUCH: EventInfo("ev_touch", "ui", True, "int f(void *touch)", "implemented (Model:02)"),
    Event.MIDI: EventInfo("ev_midi", "ui", True, "int f(uint32_t packet)", "implemented (headless: USB MIDI)"),
    Event.MIDI_OUT: EventInfo("ev_midi_out", "ui", True, "int f(uint32_t packet)", "implemented (headless: USB MIDI)"),
    Event.SETTINGS: EventInfo("ev_settings", "ui", False, "void f(void *menu)", "design only"),
    Event.SERIAL: EventInfo("ev_serial", "ui", True, "int f(void *m8c)", "implemented (headless)"),
    Event.NOTE: EventInfo("ev_note", "audio", True, "int f(void *player, int instrument)", "implemented (headless)"),
    Event.FX_COMMAND: EventInfo("ev_fx_command", "audio", True, "int f(void *runner, int column, int cmd, int value)",
                                "implemented (headless: table FX)"),
    Event.FX_ROW: EventInfo("ev_fx_row", "audio", True, "int f(void *player, int column, int cmd, int value)",
                            "implemented (headless: phrase FX)"),
    Event.MOD_APPLY: EventInfo("ev_mod_apply", "audio", True, "int f(int dest, void *modulator, void *target, int engine)",
                               "implemented (headless: 6 engines)"),
    Event.NOTE_OFF: EventInfo("ev_note_off", "audio", True, "int f(void *player, int kill)", "implemented (headless)"),
    Event.LIVE_NOTE: EventInfo("ev_live_note", "audio", True, "int f(void *player, int instrument, int note, int velocity)", "implemented (headless)"),
    Event.ROW: EventInfo("ev_row", "audio", False, "void f(void *player)", "implemented (headless)"),
    Event.SEQ_TICK: EventInfo("ev_seq_tick", "audio", True, "int f(void *engine)", "implemented (headless)"),
    Event.MUTE: EventInfo("ev_mute", "ui", True, "int f(void *mixer, int track)", "implemented (headless)"),
    Event.INST_LOAD: EventInfo("ev_inst_load", "ui", True, "int f(void *songs, const char *path, int slot)", "implemented (headless)"),
    Event.INST_SAVE: EventInfo("ev_inst_save", "ui", True, "int f(void *songs, const char *path, int slot)", "implemented (headless)"),
    Event.INST_CLEAR: EventInfo("ev_inst_clear", "ui", True, "int f(void *song, int slot, int full)", "implemented (headless)"),
    Event.INST_COPY: EventInfo("ev_inst_copy", "ui", True, "int f(void *instview, int src, int dst)", "implemented (headless)"),
    Event.INST_PASTE: EventInfo("ev_inst_paste", "ui", True, "int f(void *instview, int action)", "implemented (headless)"),
    Event.PARAM_SET: EventInfo("ev_param_set", "ui", False, "void f(void *instview, int field, int old)", "implemented (headless)"),
    Event.STEP_EDIT: EventInfo("ev_step_edit", "ui", False, "void f(void *phraseview, uint8_t *cell, int n, int column)", "implemented (headless)"),
    Event.SYSEX: EventInfo("ev_sysex", "ui", True, "int f(const uint8_t *data, int len, int last)", "implemented (headless)"),
    Event.TEMPO: EventInfo("ev_tempo", "ui", True, "int f(float bpm)", "implemented (headless)"),
    Event.TRANSPORT: EventInfo("ev_transport", "ui", True, "int f(int state)", "site pinned"),
    Event.PLAY: EventInfo("ev_play", "ui", True, "int f(void *seq, int mode)", "implemented (headless)"),
    Event.STOP: EventInfo("ev_stop", "ui", True, "int f(void)", "implemented (headless)"),
    Event.SONG_LOAD: EventInfo("ev_song_load", "ui", False, "void f(void *songs, const char *path)", "implemented (headless)"),
    Event.SONG_SAVE: EventInfo("ev_song_save", "ui", False, "void f(void *songs, const char *path)", "implemented (headless)"),
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
