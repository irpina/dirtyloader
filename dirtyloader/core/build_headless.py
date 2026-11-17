"""
Build core and its hardware smoke test for M8 Headless, and link them into a flashable .hex.

    python -m dirtyloader.core.build_headless <stock M8_V6_6_4A_HEADLESS.hex> <out dir> [--core 0.2]

core 0.3 (the default) writes <out>/M8_HEADLESS_core03.hex, <out>/core.m8mod and <out>/sd/, a folder to copy
to the root of the SD card: sd/dirtyloader/mods/sd-heartbeat.m8x (examples/sd-heartbeat), active.txt naming
it, and guard = GOOD. The heartbeat then comes from a mod the core loaded off the card (docs/LOADER.md).

core 0.2 (--core 0.2) builds the flash-linked smoke test below instead:

Writes <out>/core.m8mod, <out>/led-heartbeat.m8mod and <out>/M8_HEADLESS_core02_led.hex. Flash the .hex with
TyTools (`tycmd upload`) or the Teensy Loader; the stock .hex restores the board.

The smoke test: `ev_boot` makes Teensy pin 13 (the onboard LED, GPIO7 bit 3, unused by this firmware) an
output and lights it; `ev_tick` then shows a heartbeat from the firmware's millisecond counter -- two 128 ms
flashes every 1.024 s. Solid on means BOOT ran but TICK did not; dark means the core never ran.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from dirtyloader import ihex
from dirtyloader.core import builder
from dirtyloader.linker import link

BINDINGS = os.path.join(os.path.dirname(__file__), "bindings", "m8_6.6.4A_headless.json")
LED_CAVE = 0x6000102C          # 980 B of 0xFF between the boot data and the startup code

# Teensy 4.1 pin 13 = GPIO_B0_03, on the fast GPIO7 bank (bit 3)
BOOT_LED = """
    movw r0, #0x8148    @ IOMUXC_SW_MUX_CTL_PAD_GPIO_B0_03
    movt r0, #0x401F
    movs r1, #5    @ ALT5 = GPIO
    str  r1, [r0]
    movw r0, #0x8338    @ IOMUXC_SW_PAD_CTL_PAD_GPIO_B0_03
    movt r0, #0x401F
    movs r1, #0x38    @ DSE(7)
    str  r1, [r0]
    movw r0, #0xC06C    @ IOMUXC_GPR_GPR27: route the pin to GPIO7
    movt r0, #0x400A
    ldr  r1, [r0]
    orr  r1, r1, #8
    str  r1, [r0]
    movw r0, #0x4000    @ GPIO7
    movt r0, #0x4200
    ldr  r1, [r0, #4]    @ GDIR
    orr  r1, r1, #8
    str  r1, [r0, #4]
    movs r1, #8
    str  r1, [r0, #0x84]    @ DR_SET: LED on
    bx   lr
"""


def tick_led(millis: int) -> str:
    return f"""
    movw r3, #{millis & 0xFFFF}
    movt r3, #{millis >> 16}
    ldr  r3, [r3]
    ubfx r3, r3, #7, #3    @ 128 ms phase, 0..7
    movw r2, #0x4000
    movt r2, #0x4200
    movs r1, #8
    cmp  r3, #0
    beq  led_on
    cmp  r3, #2
    beq  led_on
    str  r1, [r2, #0x88]    @ DR_CLEAR
    bx   lr
led_on:
    str  r1, [r2, #0x84]    @ DR_SET
    bx   lr
"""


def _cover(mods):
    """Every site the mods place, for ihex.write to emit byte for byte (0xFF included)."""
    return [(s.addr, s.len) for m in mods for s in m.sites]


def build(stock_hex: str, out: str) -> dict:
    with open(stock_hex, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    with open(BINDINGS) as f:
        b = json.load(f)
    if sha != b["stock_sha256"]:
        raise SystemExit(f"{stock_hex} is not {b['firmware']} (sha256 {sha[:12]}...)")
    img = ihex.read(raw.decode("ascii"))
    fw = ihex.to_firmware(img)
    core = builder.build_core02_mod(fw, sha, b)
    led = builder.build_asm_mod(
        fw, sha, "led-heartbeat", "LED heartbeat (core smoke test)", LED_CAVE,
        [("ev_boot", BOOT_LED, 50), ("ev_tick", tick_led(int(b["exports"]["millis"], 16)), 50)],
        description="Lights the Teensy's LED at ev_boot, then double-blinks it from ev_tick.",
        firmware=b["firmware"])
    mods = [core, led]
    patched = link(fw, sha, mods)
    os.makedirs(out, exist_ok=True)
    core.save(os.path.join(out, "core.m8mod"))
    led.save(os.path.join(out, "led-heartbeat.m8mod"))
    hex_path = os.path.join(out, "M8_HEADLESS_core02_led.hex")
    with open(hex_path, "w", newline="\r\n") as f:          # CRLF, as Dirtywave ships it
        f.write(ihex.write(img, bytes(patched.payload), cover=_cover(mods)))
    changed = sum(1 for x, y in zip(fw.payload, patched.payload) if x != y)
    return {"hex": hex_path, "changed_bytes": changed, "core_events": core.events,
            "subscriptions": [(s["event"], hex(s["handler"])) for s in led.subscribe]}


HEARTBEAT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "examples", "sd-heartbeat", "heartbeat.c")


def write_sd(out: str, mods: dict) -> str:
    """<out>/sd/dirtyloader/: the mods ({file name: .m8x bytes}), active.txt listing them, guard = GOOD."""
    root = os.path.join(out, "sd", "dirtyloader")
    os.makedirs(os.path.join(root, "mods"), exist_ok=True)
    for name, blob in mods.items():
        with open(os.path.join(root, "mods", name), "wb") as f:
            f.write(blob)
    lines = ["# one .m8x per line, from /dirtyloader/mods/; core 0.3 loads them at boot"] + list(mods)
    with open(os.path.join(root, "active.txt"), "wb") as f:
        f.write(("".join(line + chr(10) for line in lines)).encode("ascii"))
    with open(os.path.join(root, "guard"), "wb") as f:
        f.write(b"GOOD")
    return os.path.join(out, "sd")


def build03(stock_hex: str, out: str) -> dict:
    from dirtyloader import cc
    with open(stock_hex, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    with open(BINDINGS) as f:
        b = json.load(f)
    if sha != b["stock_sha256"]:
        raise SystemExit(f"{stock_hex} is not {b['firmware']} (sha256 {sha[:12]}...)")
    img = ihex.read(raw.decode("ascii"))
    fw = ihex.to_firmware(img)
    core = builder.build_core03_mod(fw, sha, b)
    mods = [core]
    patched = link(fw, sha, mods)
    beat, info = cc.build_m8x([HEARTBEAT])
    os.makedirs(out, exist_ok=True)
    core.save(os.path.join(out, "core.m8mod"))
    sd = write_sd(out, {"sd-heartbeat.m8x": beat})
    hex_path = os.path.join(out, "M8_HEADLESS_core03.hex")
    with open(hex_path, "w", newline="\r\n") as f:          # CRLF, as Dirtywave ships it
        f.write(ihex.write(img, bytes(patched.payload), cover=_cover(mods)))
    n = len(fw.payload)
    changed = sum(1 for x, y in zip(fw.payload, patched.payload[:n]) if x != y) + len(patched.payload) - n
    return {"hex": hex_path, "sd": sd, "changed_bytes": changed, "core_events": core.events,
            "heartbeat": {k: v for k, v in info.items() if k != "symbols"}}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    old = "--core" in sys.argv and sys.argv[sys.argv.index("--core") + 1] == "0.2"
    if old:
        args = [a for a in args if a != "0.2"]
    print(json.dumps((build if old else build03)(args[0], args[1]), indent=1))
