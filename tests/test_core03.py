"""Core 0.3 on a synthetic headless image, and loadable mods (.m8x).

Needs arm-none-eabi-gcc (WSL on Windows) as well as keystone/capstone; skipped without them. The image is the
hand-written one from test_core02, as model 0 (headless), so nothing from Dirtywave is used.
"""
import hashlib
import struct
import unittest

from dirtyloader import cc, ihex
from dirtyloader.core import abi
from dirtyloader.m8fw import M8Firmware

try:
    import keystone  # noqa: F401
    import capstone  # noqa: F401
    HAVE_ASM = True
except ImportError:  # pragma: no cover
    HAVE_ASM = False
HAVE_CC = HAVE_ASM and cc.available()

from tests.test_core02 import BINDINGS as B02, MAIN, SETUP, LOAD, _dis, _image  # noqa: E402

C_AT, RAM, RAM_END = 0x60010000, 0x00029B40, 0x00030000
BINDINGS = dict(B02, loader={"c_at": hex(C_AT), "ram": hex(RAM), "ram_end": hex(RAM_END),
                             "fw_header": "m8-headless/fw.h", "load_at": hex(SETUP + 2)})
INNER = SETUP + 0x40               # setup() calls it; core 0.3's loader runs just before that call
HEARTBEAT = "examples/sd-heartbeat/heartbeat.c"


def _headless():
    from dirtyloader.core.builder import _asm
    fw = _image()
    for addr, asm in ((SETUP, f"push {{r3, lr}}; bl #{INNER}; pop {{r3, pc}}"), (INNER, "bx lr")):
        b = _asm(asm, addr)
        fw.payload[addr - LOAD:addr - LOAD + len(b)] = b
    return M8Firmware(version=ihex.HEADLESS_MODEL << 16, load_addr=fw.load_addr, payload=fw.payload)


@unittest.skipUnless(HAVE_CC, "arm-none-eabi-gcc, keystone or capstone not available")
class TestCore03(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dirtyloader.core import builder
        cls.builder = builder
        cls.fw = _headless()
        cls.sha = hashlib.sha256(bytes(cls.fw.payload)).hexdigest()
        cls.core = builder.build_core03_mod(cls.fw, cls.sha, BINDINGS)

    def test_core_links_past_the_image(self):
        from dirtyloader.linker import link
        self.assertEqual(self.core.version, "0.3.0")
        self.assertEqual(self.core.target["payload_len"], len(self.fw.payload))   # targets the stock image
        out = link(self.fw, self.sha, [self.core])
        loader = [s for s in self.core.sites if s.addr == C_AT][0]
        self.assertEqual(len(out.payload), C_AT - LOAD + loader.len)              # padded to fit the loader
        self.assertEqual(struct.unpack_from("<HH", out.payload, 0x208), (3, abi.MAX_HOOKS))  # layout 3
        self.assertEqual(bytes(out.payload[0x210:0x410]), bytes(0x200))         # no flash-linked hooks

    def test_boot_stub_runs_the_loader_around_setup(self):
        out_img = self.builder.build_core02(self.fw, BINDINGS, ram=RAM, early=C_AT + 0x100, boot=C_AT + 0x200,
                                            layout=3)
        code = out_img.blob[0x210:]
        stub = [f"{m} {o}" for _, m, o in _dis(code[out_img.stubs["BOOT"] - self.builder.CODE:][:24],
                                                out_img.stubs["BOOT"])]
        self.assertEqual(stub[1:4], [f"bl #0x{C_AT + 0x100:x}", f"bl #0x{SETUP:x}", f"bl #0x{C_AT + 0x200:x}"])
        disp = [f"{m} {o}" for _, m, o in _dis(code[:0x40], self.builder.CODE)]
        self.assertIn(f"movw sb, #0x{RAM & 0xFFFF:x}", disp)                    # reads the ITCM table's magic
        self.assertIn(f"movt r0, #0x{self.builder.RAM_MAGIC >> 16:x}", disp)

    def test_loader_runs_before_the_call_inside_setup(self):
        site = [s for s in self.core.sites if s.addr == SETUP + 2][0]
        stub = int(_dis(bytes.fromhex(site.new[0][1]), SETUP + 2)[0][2].lstrip("#"), 16)
        o = stub - LOAD
        text = [f"{m} {o_}" for _, m, o_ in _dis(bytes(self.core.sites[0].data(self.fw))[stub - abi.CORE_REGION_ADDR:][:16], stub)]
        self.assertTrue(text[1].startswith("bl #0x6001"))                       # core_load, in the C loader
        self.assertEqual(text[3], f"b.w #0x{INNER:x}")                          # then the original call

    def test_hex_carries_bytes_past_the_stock_end(self):
        from dirtyloader.linker import link
        out = link(self.fw, self.sha, [self.core])
        img = ihex.HexImage(base=LOAD, data=bytearray(self.fw.payload), covered=bytearray(b"\x01" * 0x4000),
                            start=None)
        back = ihex.read(ihex.write(img, bytes(out.payload)))
        self.assertEqual(bytes(back.data[C_AT - LOAD:]), bytes(out.payload[C_AT - LOAD:]).rstrip(b"\xff"))


@unittest.skipUnless(HAVE_CC, "arm-none-eabi-gcc not available")
class TestM8x(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.info = cc.build_m8x([HEARTBEAT])

    def test_header_and_subscriptions(self):
        m = cc.parse_m8x(self.blob)
        self.assertEqual((m["id"], m["version"], m["abi"]), ("sd-heartbeat", "0.1.0", 1))
        self.assertEqual(m["fw"], 0x00060604)
        self.assertEqual([(s["event"], s["order"]) for s in m["subscribe"]],
                         [(int(abi.Event.BOOT), 50), (int(abi.Event.TICK), 50), (int(abi.Event.TEMPO), 50)])
        self.assertTrue(all(s["handler"] & 1 and s["handler"] < m["image"] for s in m["subscribe"]))
        self.assertEqual(m["bss"], 4)

    def test_relocations_cover_every_internal_pointer(self):
        m = cc.parse_m8x(self.blob)
        img = self.blob[cc.M8X_HEADER.size:cc.M8X_HEADER.size + m["image"]]
        # dl_mod's id, version, title and subs pointers and each handler pointer must be relocated
        self.assertTrue({8, 12, 16, 20} <= set(m["relocations"]))
        subs = struct.unpack_from("<I", img, 20)[0]
        self.assertTrue({subs + 4 + 8 * i for i in range(3)} <= set(m["relocations"]))

    def test_corruption_is_refused(self):
        bad = bytearray(self.blob)
        bad[cc.M8X_HEADER.size + 40] ^= 1
        with self.assertRaises(cc.CCError):
            cc.parse_m8x(bytes(bad))


if __name__ == "__main__":
    unittest.main()
