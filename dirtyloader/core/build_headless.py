"""
Build core 0.2 and the hardware smoke-test mod for M8 Headless, and link them into a flashable .hex.

    python -m dirtyloader.core.build_headless <stock M8_V6_6_4A_HEADLESS.hex> <out dir>

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
    patched = link(fw, sha, [core, led])
    os.makedirs(out, exist_ok=True)
    core.save(os.path.join(out, "core.m8mod"))
    led.save(os.path.join(out, "led-heartbeat.m8mod"))
    hex_path = os.path.join(out, "M8_HEADLESS_core02_led.hex")
    with open(hex_path, "w", newline="\r\n") as f:          # CRLF, as Dirtywave ships it
        f.write(ihex.write(img, bytes(patched.payload)))
    changed = sum(1 for x, y in zip(fw.payload, patched.payload) if x != y)
    return {"hex": hex_path, "changed_bytes": changed, "core_events": core.events,
            "subscriptions": [(s["event"], hex(s["handler"])) for s in led.subscribe]}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(json.dumps(build(sys.argv[1], sys.argv[2]), indent=1))
