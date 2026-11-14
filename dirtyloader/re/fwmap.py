"""
Offline whole-firmware map from a ghidra_map export (fwmap.json).

Every function is tagged from cheap, independent evidence:
  * peripherals it touches (iMXRT1062 MMIO bases, Cortex-M7 system registers)
  * FPU density (DSP code is VFP-heavy)
  * strings it references (translated through the runtime memory map)
  * C++ class membership (view classes vs. the large parameter classes)
  * call-graph position (callers / callees, library-like fan-in)
  * known anchors found by hand
Address windows are then labelled by their aggregated tags and merged into regions.

Usage:
    python -m dirtyloader.re.fwmap <stock.bin> <fwmap.json> [--window 8192] [--detail]
"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover
from dirtyloader.re.vtables import find_vtables

# ---------------------------------------------------------------- peripherals (iMXRT1062)
_P = [
    (0x40084000, 0x4000, "PIT"), (0x40094000, 0x4000, "ACMP"),
    (0x400A4000, 0x4000, "IOMUXC_SNVS_GPR"), (0x400A8000, 0x4000, "IOMUXC_SNVS"), (0x400AC000, 0x4000, "IOMUXC_GPR"),
    (0x400B0000, 0x4000, "FLEXRAM"), (0x400B4000, 0x4000, "EWM"), (0x400B8000, 0x4000, "WDOG1"),
    (0x400BC000, 0x4000, "RTWDOG"), (0x400C0000, 0x4000, "GPIO5"), (0x400C4000, 0x4000, "ADC1"),
    (0x400C8000, 0x4000, "ADC2"), (0x400CC000, 0x4000, "TRNG"), (0x400D0000, 0x4000, "WDOG2"),
    (0x400D4000, 0x4000, "SNVS"), (0x400D8000, 0x1000, "CCM_ANALOG"), (0x400D9000, 0x1000, "USBPHY1"),
    (0x400DA000, 0x1000, "USBPHY2"), (0x400DC000, 0x4000, "CSU"), (0x400E0000, 0x4000, "TSC"),
    (0x400E8000, 0x4000, "DMA"), (0x400EC000, 0x4000, "DMAMUX"), (0x400F4000, 0x4000, "GPC"),
    (0x400F8000, 0x4000, "SRC"), (0x400FC000, 0x4000, "CCM"),
    (0x40184000, 0x4000, "LPUART1"), (0x40188000, 0x4000, "LPUART2"), (0x4018C000, 0x4000, "LPUART3"),
    (0x40190000, 0x4000, "LPUART4"), (0x40194000, 0x4000, "LPUART5"), (0x40198000, 0x4000, "LPUART6"),
    (0x4019C000, 0x4000, "LPUART7"), (0x401A0000, 0x4000, "LPUART8"), (0x401AC000, 0x4000, "FLEXIO1"),
    (0x401B0000, 0x4000, "FLEXIO2"), (0x401B8000, 0x4000, "GPIO1"), (0x401BC000, 0x4000, "GPIO2"),
    (0x401C0000, 0x4000, "GPIO3"), (0x401C4000, 0x4000, "GPIO4"), (0x401D0000, 0x4000, "CAN1"),
    (0x401D4000, 0x4000, "CAN2"), (0x401D8000, 0x4000, "CAN3"), (0x401DC000, 0x4000, "TMR1"),
    (0x401E0000, 0x4000, "TMR2"), (0x401E4000, 0x4000, "TMR3"), (0x401E8000, 0x4000, "TMR4"),
    (0x401EC000, 0x4000, "GPT1"), (0x401F0000, 0x4000, "GPT2"), (0x401F4000, 0x4000, "OCOTP"),
    (0x401F8000, 0x4000, "IOMUXC"), (0x401FC000, 0x4000, "KPP"),
    (0x402A4000, 0x4000, "FLEXSPI2"), (0x402A8000, 0x4000, "FLEXSPI"), (0x402B4000, 0x4000, "PXP"),
    (0x402B8000, 0x4000, "LCDIF"), (0x402BC000, 0x4000, "CSI"), (0x402C0000, 0x4000, "USDHC1"),
    (0x402C4000, 0x4000, "USDHC2"), (0x402D4000, 0x4000, "ENET2"), (0x402D8000, 0x4000, "ENET"),
    (0x402E0000, 0x0200, "USB1"), (0x402E0200, 0x3E00, "USB2"), (0x402F0000, 0x4000, "SEMC"),
    (0x402FC000, 0x4000, "DCP"), (0x40380000, 0x4000, "SPDIF"), (0x40384000, 0x4000, "SAI1"),
    (0x40388000, 0x4000, "SAI2"), (0x4038C000, 0x4000, "SAI3"), (0x40394000, 0x4000, "LPSPI1"),
    (0x40398000, 0x4000, "LPSPI2"), (0x4039C000, 0x4000, "LPSPI3"), (0x403A0000, 0x4000, "LPSPI4"),
    (0x403B0000, 0x4000, "ADC_ETC"), (0x403BC000, 0x4000, "XBAR1"), (0x403C0000, 0x4000, "XBAR2"),
    (0x403C4000, 0x4000, "XBAR3"), (0x403C8000, 0x10000, "ENC"), (0x403DC000, 0x4000, "FLEXPWM1"),
    (0x403E0000, 0x4000, "FLEXPWM2"), (0x403E4000, 0x4000, "FLEXPWM3"), (0x403E8000, 0x4000, "FLEXPWM4"),
    (0x403F0000, 0x4000, "LPI2C1"), (0x403F4000, 0x4000, "LPI2C2"), (0x403F8000, 0x4000, "LPI2C3"),
    (0x403FC000, 0x4000, "LPI2C4"), (0x42000000, 0x4000, "GPIO6"), (0x42004000, 0x4000, "GPIO7"),
    (0x42008000, 0x4000, "GPIO8"), (0x4200C000, 0x4000, "GPIO9"), (0x42020000, 0x4000, "FLEXIO3"),
    (0xE0001000, 0x1000, "DWT"), (0xE000E010, 0x10, "SysTick"), (0xE000E100, 0x80, "NVIC_ISER"),
    (0xE000E180, 0x80, "NVIC_ICER"), (0xE000E200, 0x80, "NVIC_ISPR"), (0xE000E280, 0x80, "NVIC_ICPR"),
    (0xE000E400, 0x100, "NVIC_IPR"), (0xE000ED00, 0x90, "SCB"), (0xE000EF00, 0x4, "NVIC_STIR"),
    (0xE000EF30, 0x20, "FPU"), (0xE000EF50, 0x30, "CACHE"),
]

# what each peripheral most likely does on an M8 (Teensy 4.1); for labelling only
ROLE = {
    "SAI1": "audio I2S", "SAI2": "audio I2S", "SAI3": "audio I2S", "SPDIF": "audio",
    "LPI2C1": "I2C (codec/touch?)", "LPI2C2": "I2C", "LPI2C3": "I2C", "LPI2C4": "I2C",
    "LPSPI1": "SPI", "LPSPI2": "SPI", "LPSPI3": "SPI", "LPSPI4": "SPI (display?)",
    "USDHC1": "SD card", "USDHC2": "SD card", "USB1": "USB device", "USB2": "USB host", "USBPHY1": "USB",
    "USBPHY2": "USB host", "DMA": "DMA", "DMAMUX": "DMA",
    "LPUART1": "serial", "LPUART2": "serial", "LPUART3": "serial", "LPUART4": "serial",
    "LPUART5": "serial", "LPUART6": "serial (MIDI?)", "LPUART7": "serial", "LPUART8": "serial",
    "CCM": "clocks", "CCM_ANALOG": "clocks/PLL", "IOMUXC": "pin mux", "IOMUXC_GPR": "pin mux",
    "PIT": "timer", "GPT1": "timer", "GPT2": "timer", "TMR1": "timer", "TMR2": "timer", "TMR3": "timer",
    "TMR4": "timer", "FLEXPWM1": "PWM", "FLEXPWM2": "PWM", "FLEXPWM3": "PWM", "FLEXPWM4": "PWM",
    "ADC1": "ADC", "ADC2": "ADC", "FLEXSPI": "flash", "FLEXSPI2": "PSRAM", "TRNG": "random",
    "SysTick": "systick", "NVIC_STIR": "soft IRQ", "NVIC_ISPR": "soft IRQ",
}

# hand-found anchors (runtime addresses); see docs/hooks/*.md
ANCHORS = {
    0x60001430: "startup", 0x600AE04C: "main", 0x60082374: "setup", 0x60081BD4: "loop",
    0x6004B514: "display driver (RENDER)", 0x6004C6C8: "input router", 0x6004C13C: "set_view",
    0x600A5E60: "touch engine", 0x6002E2A8: "glyph renderer", 0x6002FDEC: "glyph renderer 2",
    0x60030ECC: "text draw", 0x600785C0: "value formatter", 0x6005ED6C: "FX value formatter",
    0x6008C4A4: "FX name lookup",
}


def periph(a: int) -> Optional[str]:
    for base, size, name in _P:
        if base <= a < base + size:
            return name
    return None


class Map:
    def __init__(self, fw: M8Firmware, export: dict):
        self.fw = fw
        self.p = bytes(fw.payload)
        self.base = fw.load_addr
        self.mm = recover(fw)
        self.funcs: Dict[int, dict] = {f["entry"]: f for f in export["functions"]}
        # ITCM anchors were found at load addresses; key them by runtime too
        self.anchors = dict(ANCHORS)
        for la in (0x600287A4, 0x60029270, 0x60029AA4, 0x60028700, 0x60025ED4, 0x60029BDC):
            names = {0x600287A4: "FX executor", 0x60029270: "FX dispatch", 0x60029AA4: "FX scan loop",
                     0x60028700: "ratchet tick", 0x60025ED4: "FX processor 2", 0x60029BDC: "pitch cmds"}
            self.anchors[self.mm.to_runtime(la)] = names[la]
        self.callers: Dict[int, set] = defaultdict(set)
        for e, f in self.funcs.items():
            for c in f["callees"]:
                tgt = self.funcs.get(c, {}).get("thunk") or c
                self.callers[tgt].add(e)
        self.vt_kind: Dict[int, str] = {}
        for vt in find_vtables(fw):
            kind = "view" if len(vt) in (8, 32) else "param-class" if len(vt) >= 46 else "class"
            for s in vt.slots:
                self.vt_kind.setdefault(s & ~1, kind)

    # -- strings
    def string_at(self, a: int, n: int = 40) -> Optional[str]:
        la = self.mm.to_load(a)
        if la is None or not (self.base <= la < self.base + len(self.p)):
            return None
        o = la - self.base
        e = self.p.find(b"\x00", o, o + n + 1)
        raw = self.p[o:(e if e != -1 else o + n)]
        if len(raw) < 3 or not all(32 <= b < 127 for b in raw):
            return None
        return raw.decode("ascii")

    def tags(self, f: dict) -> Counter:
        t: Counter = Counter()
        for a in f["mmio"]:
            pn = periph(a)
            if pn:
                t["periph:" + pn] += 1
        if f["insns"] >= 20 and f["fp"] >= 0.2 * f["insns"]:
            t["dsp"] += 1
        k = self.vt_kind.get(f["entry"])
        if k:
            t[k] += 1
        if f["entry"] in self.anchors:
            t["anchor:" + self.anchors[f["entry"]]] += 1
        if len(self.callers.get(f["entry"], ())) >= 40:
            t["library-like"] += 1
        return t

    def strings(self, f: dict, limit: int = 6) -> List[str]:
        out = []
        for a in f["drefs"]:
            s = self.string_at(a)
            if s and s not in out:
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def segment(self, e: int) -> str:
        if self.mm.itcm and self.mm.itcm.contains_runtime(e):
            return "ITCM"
        if 0x60000000 <= e < 0x70000000:
            return "flash"
        return "other"

    def windows(self, window: int = 8192):
        """Aggregate tags per load-address window."""
        acc = defaultdict(lambda: {"tags": Counter(), "funcs": [], "bytes": 0, "strings": Counter()})
        for e, f in self.funcs.items():
            la = f["load"] if f["load"] is not None else e
            if not (self.base <= la < self.base + len(self.p)):
                continue
            w = (la - self.base) // window * window + self.base
            a = acc[w]
            for k, v in self.tags(f).items():
                a["tags"][k] += v * max(1, f["size"] // 64)
            a["funcs"].append(f)
            a["bytes"] += f["size"]
            for s in self.strings(f, 3):
                a["strings"][s] += 1
        return dict(sorted(acc.items()))


def label(tags: Counter) -> str:
    if not tags:
        return "unlabelled"
    per = Counter()
    for k, v in tags.items():
        if k.startswith("periph:"):
            pn = k.split(":", 1)[1]
            if pn in ("CCM", "IOMUXC", "IOMUXC_GPR", "NVIC_ISER", "NVIC_ICER", "NVIC_IPR", "SCB", "CACHE", "DWT"):
                per["sys/" + pn] += v
            else:
                per[ROLE.get(pn, pn)] += v
        elif k.startswith("anchor:"):
            per[k.split(":", 1)[1]] += v * 4
        else:
            per[k] += v
    return ", ".join(k for k, _ in per.most_common(3))


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Whole-firmware map from a ghidra_map export.")
    ap.add_argument("firmware")
    ap.add_argument("export")
    ap.add_argument("--window", type=lambda s: int(s, 0), default=8192)
    ap.add_argument("--detail", action="store_true", help="list notable functions per window")
    a = ap.parse_args(argv)
    fw = M8Firmware.from_file(a.firmware, verify=True)
    m = Map(fw, json.load(open(a.export)))
    fs = list(m.funcs.values())
    seg = Counter(m.segment(f["entry"]) for f in fs)
    print("functions: %d (%s); bytes in functions: %d KB" % (
        len(fs), ", ".join("%s %d" % kv for kv in seg.items()), sum(f["size"] for f in fs) // 1024))
    pc = Counter()
    for f in fs:
        for x in {periph(q) for q in f["mmio"]} - {None}:
            pc[x] += 1
    print("peripherals by #functions: " + ", ".join("%s %d" % kv for kv in pc.most_common()))
    print()
    for w, info in m.windows(a.window).items():
        rt = m.mm.to_runtime(w)
        print("0x%08X%s  %3d fn %6d B  %-60s | %s" % (
            w, (" (run 0x%08X)" % rt) if rt != w else "", len(info["funcs"]), info["bytes"],
            label(info["tags"])[:60], "; ".join(s for s, _ in info["strings"].most_common(4))[:90]))
        if a.detail:
            for f in sorted(info["funcs"], key=lambda f: -f["size"])[:5]:
                print("      0x%08X %5d B fp %3d calls %2d callers %3d %s %s" % (
                    f["entry"], f["size"], f["fp"], len(f["callees"]), len(m.callers.get(f["entry"], ())),
                    " ".join(sorted(m.tags(f))), "| " + "; ".join(m.strings(f, 3))))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
