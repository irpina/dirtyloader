"""core for M8 Model:02 6.6.4A: the build and its static checks. Needs the stock .bin (Dirtywave's, not in the repo): set
DIRTYLOADER_MODEL02_664_BIN, or it is looked for where Dirtywave's current zip unzips in the download folder; skipped
without it. docs/MODEL02-664-PORT.md says where each checked address comes from."""
import os
import struct
import tempfile
import unittest

from dirtyloader import cc

STOCK = os.environ.get("DIRTYLOADER_MODEL02_664_BIN", os.path.expanduser(
    r"~/Downloads/M8Firmware_V6_6_4/Firmware/Model02/M8_V6_6_4A_MODEL02.bin"))
IMAGE_END = 0x601F1400            # the stock image's end
CORE_AT = 0x601F8000              # bindings: loader.c_at


def bl_target(payload, load, at):
    o = at - load
    hi, lo = struct.unpack_from("<HH", payload, o)
    s = (hi >> 10) & 1
    j1, j2 = (lo >> 13) & 1, (lo >> 11) & 1
    off = (s << 24) | ((1 - (j1 ^ s)) << 23) | ((1 - (j2 ^ s)) << 22) | ((hi & 0x3FF) << 12) | ((lo & 0x7FF) << 1)
    if s:
        off -= 1 << 25
    return at + 4 + off


@unittest.skipUnless(os.path.exists(STOCK) and cc.available(), "the Model:02 6.6.4A .bin or the ARM compiler is missing")
class TestModel02v664(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dirtyloader.core import build_model02
        from dirtyloader.m8fw import M8Firmware
        cls.out = tempfile.mkdtemp()
        cls.info = build_model02.build(STOCK, cls.out)
        cls.fw = M8Firmware.from_file(cls.info["bin"])          # both CRCs verified
        cls.stock = M8Firmware.from_file(STOCK)

    def at(self, a, n, img=None):
        img = img or self.stock
        return bytes(img.payload[a - img.load_addr:a - img.load_addr + n])

    def word(self, a, img=None):
        return struct.unpack_from("<I", self.at(a, 4, img))[0]

    def data(self, ram):
        """a .data word as the startup copies it (load 0x601E42E0 -> 0x20000000)"""
        return self.word(0x601E42E0 + ram - 0x20000000)

    def test_picked_by_sha256(self):
        self.assertEqual(self.info["firmware"], "6.6.4A")
        self.assertTrue(self.info["bin"].endswith("M8_V6_6_4A_MODEL02_core.bin"))

    def test_bin_parses_and_grows_for_the_loader(self):
        self.assertEqual(len(self.stock.payload), IMAGE_END - 0x60000000)
        self.assertGreater(len(self.fw.payload), CORE_AT - 0x60000000)
        self.assertEqual(bytes(self.fw.payload[0x200:0x206]), b"DLCORE")

    def test_every_headless_event_is_there(self):
        import json
        hl = json.load(open(os.path.join(os.path.dirname(__file__), "..", "dirtyloader", "core", "bindings",
                                         "m8_6.6.4A_headless.json")))
        names = {n.split("@")[0] for n in hl["core"]} | {c["event"] for c in hl["loader"]["calls"].values()}
        self.assertEqual(names - set(self.info["core_events"]), set())
        for ev in ("TOUCH", "VIS_SCOPE", "VIS_DRAW"):               # and the Model:02's own
            self.assertIn(ev, self.info["core_events"])

    def test_the_main_loop_sites(self):
        # main: bl setup, bl loop (a veneer to 0x6008646C), bl yield; the loop body's bl frame_refresh and router
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600B42F2), 0x6008595C)
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600B42F6), 0x60085368)
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600B42FA), 0x600BAF30)
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600862EE), 0x6004E218)   # DRAW
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600863F2), 0x6004F620)   # KEY
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x60086030), 0x6007F180)   # TOUCH
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x60085A4E), 0x600A07AC)   # core_load before it
        for at in (0x600B42F2, 0x600B42F6, 0x600862EE, 0x600863F2, 0x60086030):
            self.assertNotEqual(self.at(at, 4, self.fw), self.at(at, 4), hex(at))             # now core's

    def test_extended_destination_sites(self):
        for at in (0x6005B63A, 0x6005BC84, 0x6005B188, 0x60057E94, 0x6005B3AC, 0x6005B8EE):
            o = at - self.fw.load_addr
            self.assertEqual(self.fw.payload[o + 1] & 0xF8, 0xF0, hex(at))        # now a b.w to core's stub
            self.assertEqual(self.fw.payload[o + 3] & 0xD0, 0x90, hex(at))

    def test_core_uses_the_model02_vector_table(self):
        self.assertEqual(self.word(0x60001600), 0x2000C000)          # what the startup puts in VTOR
        self.assertIn(struct.pack("<I", 0x2000C000), bytes(self.fw.payload[CORE_AT - 0x60000000:]))

    def test_the_visualizer_has_its_draw_event(self):
        self.assertEqual(self.at(0x6004E32C, 4), bytes.fromhex("a4f8ea82"))        # stock: strh.w r8, [r4, #0x2ea]
        o = 0x6004E32C - self.fw.load_addr
        self.assertEqual(self.fw.payload[o + 3] & 0xF8, 0xB8)        # now a b.w to core's stub
        self.assertEqual(self.fw.payload[o + 1] & 0xF8, 0xF0)
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x6004E312), 0x6004D31A)   # the scope call

    def test_full_screen_pages_hold_off_the_side_column(self):
        stock = {0x6004E376: 0x6004A1BC, 0x6004E3B0: 0x6004ADB0, 0x6004E3C6: 0x6004C3C0, 0x6004E408: 0x6004DFF8,
                 0x6004F4BC: 0x6004E600, 0x6004F4C8: 0x6004D214, 0x6004F4D4: 0x6004C330, 0x6004F4DE: 0x6004BD84}
        for at, target in stock.items():
            self.assertEqual(bl_target(self.stock.payload, 0x60000000, at), target, hex(at))
            self.assertGreaterEqual(bl_target(self.fw.payload, 0x60000000, at), CORE_AT, hex(at))
        self.assertEqual(bl_target(self.fw.payload, 0x60000000, 0x6004E3BA), 0x6004F4A4)   # the dispatcher stays

    def test_set_view_reads_the_view_table(self):
        self.assertEqual(self.word(0x6004F030), 0x20000BD8)          # set_view's literal: fw_views
        self.assertEqual(self.data(0x20000BD8 + 4 * 7), 0)           # slot 7 is free for core's MODS page
        self.assertEqual(self.data(0x20000BD8 + 4 * 0x1C), 0x2001C87C)   # SYSTEM SETTINGS: fw_settings

    def test_the_audio_graph_slots(self):
        # each class slot holds the update() found from headless's (ITCM)
        for slot, update in ((0x20002514, 0x2499), (0x20002D50, 0x8F55), (0x20002F48, 0x7359), (0x200029F0, 0x95AD),
                             (0x20002060, 0x22B19)):
            self.assertEqual(self.data(slot), update, hex(slot))
        self.assertEqual(self.word(0x600A046C), 0x2000C780)          # the engine's static, built by 0x6009D9D4
        self.assertEqual(bl_target(self.stock.payload, 0x60000000, 0x600A042A), 0x6009D9D4)

    def test_the_sequencer_block_offsets(self):
        """0x28 further into the engine than on headless: play tests and sets the playing byte (ldrb/strb.w r?, [r3,
        #0x3E0]) and set_tempo stores the tempo (vstr s0, [r3, #0x3E8]); fw.h must say the same."""
        import re
        play = self.at(0x600A1010, 0x40)
        self.assertIn(bytes.fromhex("93f8e003"), play)               # ldrb.w r0, [r3, #0x3E0]
        self.assertIn(bytes.fromhex("83f8e003"), play)               # strb.w r0, [r3, #0x3E0]
        self.assertIn(bytes.fromhex("83ed fa0a".replace(" ", "")), self.at(0x600A1370, 0x40))  # vstr s0, [r3, #0x3E8]
        h = open(os.path.join(os.path.dirname(cc.__file__), "sdk", "include", "m8-model02-6.6.4A", "fw.h"),
                 encoding="utf-8").read()
        for name, off in (("FW_SEQ_PLAYING", 0x3E0), ("fw_bpm", 0x3E8), ("fw_mixer", 0x408), ("FW_CLOCK_OBJ", 0x3B8)):
            m = re.search(r"#define %s\s+.*?(0x[0-9A-Fa-f]+)u" % name, h)
            self.assertEqual(int(m.group(1), 16), off, name)

    def test_the_frame_gate(self):
        self.assertEqual(self.at(0x6004E240, 2), bytes.fromhex("0f2e"))             # cmp r6, #15
        self.assertEqual(self.word(0x6004E420), 0x2004054C)                       # fw_millis
        self.assertEqual(self.word(0x6004E424), 0x200206F0)                       # fw_frame_last

    def test_spare_ram_is_past_bss(self):
        self.assertEqual(self.word(0x6000142C), 0x200418E0)          # the reset handler's .bss end
        self.assertGreater(0x20041A00, 0x200418E0)

    def test_the_theme_routines_are_where_fw_h_says(self):
        self.assertEqual(self.at(0x600AD5BE, 8), bytes.fromhex("70b50546 0024c822"))   # settings save: 0xC8 bytes summed
        self.assertEqual(self.at(0x600AB980, 4), bytes.fromhex("0c290bd8"))            # set_pal: cmp r1, #12; bhi
        self.assertEqual(self.word(0x600AB9A0), 0x2000BD08)                            # set_pal writes FW_PALETTE
        self.assertEqual(self.at(0x6004DBF0, 4), bytes.fromhex("2de9f047"))            # the redraw: push.w

    def test_the_extended_theme_finds_its_palette_pointer(self):
        self.assertEqual(self.word(0x60001680 + 0x18FEC), 0x2000BD08)              # FW_ATTR_PAL_LIT -> FW_PALETTE
        self.assertEqual(self.at(0x6001A612, 4), bytes.fromhex("a0f12e04"))         # the loop: sub.w r4, r0, #0x2e

    def test_the_settings_row(self):
        tpl = 0x601D871C
        self.assertEqual(self.at(tpl + 21 * 40, 23), b" FIRMWARE      {UPDATE}")
        self.assertEqual(self.at(tpl + 22 * 40, 40), b" " * 40)
        for lit, v in ((0x60078150, tpl), (0x60078158, tpl + 0x3C4), (0x60078934, tpl + 0x3C4)):
            self.assertEqual(self.word(lit), v, hex(lit))
            self.assertGreaterEqual(self.word(lit, self.fw), CORE_AT)                 # now core's copy

    def test_mods_carry_the_model02_664_firmware_id(self):
        beat = open(os.path.join(self.info["sd"], "dirtyloader", "mods", "sd-heartbeat.m8x"), "rb").read()
        self.assertEqual(cc.parse_m8x(beat)["fw"], 0x02060604)
        # pin 13 (pad GPIO_B0_03) is in use on a Model:02: turning it into a GPIO hangs the unit. The headless
        # build reaches the pad through a literal of the IOMUXC base (str [base, #0x148]); this one must not.
        self.assertNotIn(struct.pack("<I", 0x401F8000), beat)

    def test_the_examples_build_for_it(self):
        from dirtyloader.core.build_model02 import _alias_dir
        for src in ("examples/lfo-sends/lfo_sends.c", "examples/chaos-control/chaos.c", "examples/perf-mon/perf.c"):
            blob, _ = cc.build_m8x([src], defines={"M8_MODEL02": "1"}, includes=[_alias_dir("6.6.4A")])
            self.assertEqual(cc.parse_m8x(blob)["fw"], 0x02060604, src)

    def test_no_other_firmwares_ram_address_in_core(self):
        c = bytes(self.fw.payload[CORE_AT - 0x60000000:])
        words = {struct.unpack_from("<I", c, o)[0] for o in range(0, len(c) - 3, 4)}
        for other in (0x20015458, 0x20012464, 0x2001DA34, 0x2000D218, 0x20040358,      # 6.6.2A Model:02
                      0x2001C1A4, 0x20019160, 0x2000BE80, 0x20040264, 0x20000B24,      # Headless 6.6.4A
                      0x2000B800):
            self.assertNotIn(other, words, hex(other))


if __name__ == "__main__":
    unittest.main()
