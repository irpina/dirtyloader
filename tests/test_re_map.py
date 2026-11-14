"""
The whole-firmware mapping tools on synthetic data (no firmware needed):

  * memmap: load <-> run-time translation for the ITCM and .data copies
  * params: 28-byte descriptor records whose strings are .data (DTCM) pointers
  * layout: fill / text classification (needs capstone)
"""
import struct
import unittest

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import MemMap, Copy
from dirtyloader.re import params

LOAD = 0x60000000

try:
    import capstone  # noqa: F401
    HAVE_CAPSTONE = True
except Exception:
    HAVE_CAPSTONE = False


def _mm():
    return MemMap(entry=0, startup=None, copies=[
        Copy(dest=0x00000000, src=0x60001000, end=0x00000800),      # ITCM: 2 KB
        Copy(dest=0x20000000, src=0x60003000, end=0x20000400),      # .data: 1 KB
    ])


class TestMemMap(unittest.TestCase):
    def test_translation(self):
        mm = _mm()
        self.assertEqual(mm.itcm.size, 0x800)
        self.assertEqual(mm.to_runtime(0x60001234), 0x00000234)        # ITCM load -> run
        self.assertEqual(mm.to_runtime(0x60003010), 0x20000010)        # .data load -> run
        self.assertEqual(mm.to_runtime(0x60005000), 0x60005000)        # XIP code runs in place
        self.assertEqual(mm.to_load(0x00000234), 0x60001234)
        self.assertEqual(mm.to_load(0x20000010), 0x60003010)
        self.assertIsNone(mm.to_load(0x20100000))                      # bss: no load image

    def test_flexram(self):
        mm = MemMap(entry=0, startup=None, flexram_config=0xAAAAAFFF)
        self.assertEqual(mm.flexram_banks(), {"ITCM": 6, "DTCM": 10})


class TestParams(unittest.TestCase):
    def setUp(self):
        self.fw = M8Firmware(version=0x00020001, load_addr=LOAD, payload=bytearray(0x4000))
        p = self.fw.payload
        strings = [b"DELAY VOL", b"DEL ", b"SDL", b"SEND DELAY"]
        ptrs, off = [], 0x3000
        for s in strings:                                               # strings in the .data image
            p[off:off + len(s) + 1] = s + b"\x00"
            ptrs.append(0x20000000 + (off - 0x3000))
            off += 16
        for k in range(6):                                              # six records at 0x2000:
            rec = 0x2000 + 28 * k                                       # 4 strings, flags, range, index
            struct.pack_into("<4IIII", p, rec, *ptrs, 0xC0000001, 0x000C_FF00, 0x0F + k)

    def test_scan(self):
        tables = params.scan(self.fw, mm=_mm())
        self.assertEqual(len(tables), 1)
        t = tables[0]
        self.assertEqual((t.addr, len(t.params)), (LOAD + 0x2000, 6))
        x = t.params[0]
        self.assertEqual((x.index, x.name, x.label, x.code, x.help), (0x0F, "DELAY VOL", "DEL ", "SDL", "SEND DELAY"))
        self.assertEqual((x.min, x.max, x.b2, x.b3, x.flags), (0, 255, 0x0C, 0, 0xC0000001))
        self.assertEqual(t.params[5].index, 0x14)


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class TestObjects(unittest.TestCase):
    def test_inline_vptr_store(self):
        from dirtyloader.re import objects
        fw = M8Firmware(version=0x00020001, load_addr=LOAD, payload=bytearray(0x4000))
        p = fw.payload
        code = bytes.fromhex(
            "024b"      # 0x2000 ldr r3, [pc, #8]   -> object 0x20001000
            "034a"      # 0x2002 ldr r2, [pc, #12]  -> vtable
            "1a60"      # 0x2004 str r2, [r3]
            "7047"      # 0x2006 bx lr
            "00bf00bf"  # 0x2008 padding
        )
        p[0x2000:0x2000 + len(code)] = code
        vt = LOAD + 0x3008
        struct.pack_into("<II", p, 0x200C, 0x20001000, vt)            # literal pool
        struct.pack_into("<IIII", p, 0x3000, 0, 0, LOAD + 0x2001, LOAD + 0x2001)   # {0,0} + 2 slots
        export = {"functions": [{"entry": LOAD + 0x2000, "load": LOAD + 0x2000, "size": 8,
                                 "callees": [], "thunk": None}]}
        objs, _ctors, vts = objects.scan(fw, export)
        self.assertIn(0x20001000, objs)
        self.assertEqual(objs[0x20001000][0], vt)
        self.assertEqual(len(vts[vt]), 2)


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class TestLayout(unittest.TestCase):
    def test_fill_and_text(self):
        from dirtyloader.re.layout import classify
        fw = M8Firmware(version=0x00020001, load_addr=LOAD, payload=bytearray(b"\xff" * 0x800))
        fw.payload[0x400:0x500] = (b"HELLO M8 WORLD\x00" * 20)[:0x100]
        kinds = classify(fw, 256)
        self.assertEqual(kinds[0], "fill")
        self.assertEqual(kinds[4], "text")


if __name__ == "__main__":
    unittest.main()
