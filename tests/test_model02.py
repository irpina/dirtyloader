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

    def test_mods_carry_the_model02_firmware_id(self):
        beat = open(os.path.join(self.info["sd"], "dirtyloader", "mods", "sd-heartbeat.m8x"), "rb").read()
        self.assertEqual(cc.parse_m8x(beat)["fw"], 0x02060602)

    def test_no_headless_ram_address_in_core(self):
        from dirtyloader.m8fw import M8Firmware
        out = M8Firmware.from_file(self.info["bin"])
        c = bytes(out.payload[0x1F0000:])
        words = {struct.unpack_from("<I", c, o)[0] for o in range(0, len(c) - 3, 4)}
        for hl in (0x2001C1A4, 0x20019160, 0x2000BE80, 0x20000B24, 0x200376EC, 0x2003382C, 0x20040264):
            self.assertNotIn(hl, words)


if __name__ == "__main__":
    unittest.main()
