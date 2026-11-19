"""core 0.5 for M8 Model:02 6.6.2A: the build and its static checks. Needs the stock .bin (Dirtywave's, not in the
repo): set DIRTYLOADER_MODEL02_BIN, or it is looked for in the usual download folder; skipped without it."""
import os
import struct
import tempfile
import unittest

from dirtyloader import cc

STOCK = os.environ.get("DIRTYLOADER_MODEL02_BIN", os.path.expanduser(
    r"~/Downloads/M8Firmware_V6_6_2/Firmware/Model02/M8_V6_6_2A_MODEL02.bin"))


@unittest.skipUnless(os.path.exists(STOCK) and cc.available(), "the Model:02 6.6.2A .bin or the ARM compiler is missing")
class TestModel02(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dirtyloader.core import build_model02
        cls.out = tempfile.mkdtemp()
        cls.info = build_model02.build(STOCK, cls.out)

    def test_bin_parses_and_grows_for_the_loader(self):
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])          # both CRCs verified
        self.assertGreater(len(out.payload), 0x1EB000)       # the loader past the stock image (ends 0x601EB000)
        self.assertEqual(bytes(out.payload[0x200:0x206]), b"DLCORE")

    def test_every_headless_event_is_there(self):
        import json
        hl = json.load(open(os.path.join(os.path.dirname(__file__), "..", "dirtyloader", "core", "bindings",
                                         "m8_6.6.4A_headless.json")))
        names = {n.split("@")[0] for n in hl["core"]} | {c["event"] for c in hl["loader"]["calls"].values()}
        self.assertEqual(names - set(self.info["core_events"]), set())

    def test_extended_destination_sites(self):
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        for at in (0x600585C2, 0x60058C0C, 0x60058110, 0x60054EC4, 0x60058334, 0x60058876):
            o = at - out.load_addr
            self.assertEqual(out.payload[o + 1] & 0xF8, 0xF0, hex(at))        # now a b.w to core's stub
            self.assertEqual(out.payload[o + 3] & 0xD0, 0x90, hex(at))

    def test_lfo_sends_builds_for_model02(self):
        from dirtyloader.core.build_model02 import _alias_dir
        blob, info = cc.build_m8x(["examples/lfo-sends/lfo_sends.c"], defines={"M8_MODEL02": "1"},
                                  includes=[_alias_dir()])
        self.assertEqual(cc.parse_m8x(blob)["fw"], 0x02060602)

    def test_core_uses_the_model02_vector_table(self):
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        self.assertEqual(struct.unpack_from("<I", out.payload, 0x1600)[0], 0x2000C000)   # what the startup puts in VTOR
        c = bytes(out.payload[0x1F0000:])
        self.assertIn(struct.pack("<I", 0x2000C000), c)

    def test_the_visualizer_has_its_draw_event(self):
        from dirtyloader.m8fw import M8Firmware
        self.assertIn("VIS_DRAW", self.info["core_events"])
        out = M8Firmware.from_file(self.info["bin"])
        o = 0x6004B620 - out.load_addr
        self.assertEqual(out.payload[o + 3] & 0xF8, 0xB8)        # the strh.w is now a b.w to core's stub
        self.assertEqual(out.payload[o + 1] & 0xF8, 0xF0)

    def test_full_screen_pages_hold_off_the_side_column(self):
        # core's MOD LOADER / OPTIONS: the right-hand column's routines are called through core (core_side*), so
        # each bl now lands in core's C past the stock image; the view-draw dispatcher's own bl stays stock
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])

        def bl_target(at):
            o = at - out.load_addr
            hi, lo = struct.unpack_from("<HH", out.payload, o)
            s = (hi >> 10) & 1
            j1, j2 = (lo >> 13) & 1, (lo >> 11) & 1
            off = (s << 24) | ((1 - (j1 ^ s)) << 23) | ((1 - (j2 ^ s)) << 22) | ((hi & 0x3FF) << 12) | ((lo & 0x7FF) << 1)
            if s: off -= 1 << 25
            return at + 4 + off
        for at in (0x6004B642, 0x6004B680, 0x6004B696, 0x6004B6EC, 0x6004CB94, 0x6004CBA0, 0x6004CBAC, 0x6004CBB6):
            self.assertGreaterEqual(bl_target(at), 0x601EB000, hex(at))
        self.assertEqual(bl_target(0x6004B68A), 0x6004CB7C)

    def test_the_theme_routines_are_where_fw_h_says(self):
        # core's THEME command (the shop's theme picker) calls these: check the stock code at each address
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        at = lambda a, n: bytes(out.payload[a - out.load_addr:a - out.load_addr + n])
        self.assertEqual(at(0x600A7318, 8), bytes.fromhex("70b50546 0024c822"))     # settings save: 0xC8 bytes summed
        self.assertEqual(at(0x600A5654, 4), bytes.fromhex("0c290bd8"))              # set_pal: cmp r1, #12; bhi
        self.assertEqual(at(0x6004AF18, 4), bytes.fromhex("2de9f047"))              # the redraw: push.w {r4-r10, lr}

    def test_the_extended_theme_finds_its_palette_pointer(self):
        # core repoints the attribute draw loop's palette (ITCM run 0x18C1C, loaded from 0x60001680 + it) only when it
        # holds the firmware's palette: check the stock image says so, and the loop decodes 'D'.. as 13..
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        word = lambda a: struct.unpack_from("<I", out.payload, a - out.load_addr)[0]
        self.assertEqual(word(0x60001680 + 0x18C1C), 0x2000BC20)                    # FW_ATTR_PAL_LIT -> FW_PALETTE
        self.assertEqual(word(0x600A5674), 0x2000BC20)                              # set_pal writes that palette
        loop = bytes(out.payload[0x60001680 + 0x18BAA - out.load_addr:][:2])
        self.assertEqual(loop, bytes.fromhex("a1f1"))                                # sub.w r4, r1, #0x2e

    def test_mods_carry_the_model02_firmware_id(self):
        beat = open(os.path.join(self.info["sd"], "dirtyloader", "mods", "sd-heartbeat.m8x"), "rb").read()
        self.assertEqual(cc.parse_m8x(beat)["fw"], 0x02060602)
        # pin 13 (pad GPIO_B0_03) is in use on a Model:02: turning it into a GPIO hangs the unit. The headless
        # build reaches the pad through a literal of the IOMUXC base (str [base, #0x148]); this one must not.
        self.assertNotIn(struct.pack("<I", 0x401F8000), beat)

    def test_no_headless_ram_address_in_core(self):
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        c = bytes(out.payload[0x1F0000:])
        words = {struct.unpack_from("<I", c, o)[0] for o in range(0, len(c) - 3, 4)}
        for hl in (0x2001C1A4, 0x20019160, 0x2000BE80, 0x20000B24, 0x200376EC, 0x2003382C, 0x20040264,
                   0x2000B800):                                  # headless's vector table: was hard-coded in core
            self.assertNotIn(hl, words)


if __name__ == "__main__":
    unittest.main()
