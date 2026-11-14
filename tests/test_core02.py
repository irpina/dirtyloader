"""Core 0.2 on a synthetic image: the three site kinds, prologue relocation, and handler order in the table.

The image is made here from a few hand-written instructions (no Dirtywave bytes): a main() that calls setup()
and loop(), and a function whose prologue loads a pc-relative literal, the shape of the headless set_tempo.
"""
import hashlib
import struct
import unittest

try:
    import keystone  # noqa: F401
    import capstone
    HAVE_TOOLS = True
except ImportError:  # pragma: no cover
    HAVE_TOOLS = False

from dirtyloader.m8fw import M8Firmware
from dirtyloader.core import abi

LOAD = 0x60000000
MAIN, SETUP, LOOP, FN = 0x60002000, 0x60002100, 0x60002110, 0x60002200
CAVE = 0x60001100
LITERAL = 0x2000ABCD


def _image():
    from dirtyloader.core.builder import _asm
    p = bytearray(b"\xFF" * 0x4000)

    def put(addr, asm):
        b = _asm(asm, addr)
        p[addr - LOAD:addr - LOAD + len(b)] = b

    put(MAIN, f"push {{r3, lr}}\n bl #{SETUP}\n loop_: bl #{LOOP}\n b loop_")
    put(SETUP, "bx lr")
    put(LOOP, "bx lr")
    put(FN, "ldr r3, [pc, #8]\n ldr r3, [r3]\n push {r4, lr}\n pop {r4, pc}")
    struct.pack_into("<I", p, FN + 4 + 8 - LOAD, LITERAL)            # (FN + 4) & ~3 == FN + 4
    return M8Firmware(version=0x00020001, load_addr=LOAD, payload=p)


BINDINGS = {"firmware": "synthetic", "core": {
    "BOOT": {"kind": "call_post", "patch_at": hex(MAIN + 2), "target": hex(SETUP)},
    "TICK": {"kind": "call_pre", "patch_at": hex(MAIN + 6), "target": hex(LOOP)},
    "TEMPO": {"kind": "entry", "patch_at": hex(FN)},
}}


def _dis(data: bytes, addr: int):
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    return [(i.address, i.mnemonic, i.op_str) for i in md.disasm(data, addr)]


@unittest.skipUnless(HAVE_TOOLS, "keystone/capstone not installed")
class TestCore02(unittest.TestCase):
    def setUp(self):
        from dirtyloader.core import builder
        self.builder = builder
        self.fw = _image()
        self.sha = hashlib.sha256(self.fw.build()).hexdigest()

    def test_sites_and_stubs(self):
        img = self.builder.build_core02(self.fw, BINDINGS)
        self.assertEqual(img.blob[:8], abi.CORE_MAGIC)
        self.assertEqual(struct.unpack_from("<HHI", img.blob, 8), (2, abi.MAX_HOOKS, img.dispatch | 1))
        self.assertEqual(img.blob[0x10:0x210], bytes(0x200))              # table starts empty
        sites = {a: n for a, n, _ in img.sites}
        self.assertEqual(_dis(sites[MAIN + 2], MAIN + 2)[0][1:], ("bl", f"#0x{img.stubs['BOOT']:x}"))
        self.assertEqual(_dis(sites[MAIN + 6], MAIN + 6)[0][1:], ("bl", f"#0x{img.stubs['TICK']:x}"))
        self.assertEqual(_dis(sites[FN], FN)[0][1:], ("b.w", f"#0x{img.stubs['TEMPO']:x}"))

        code = img.blob[0x210:]
        stub = _dis(code[img.stubs["TEMPO"] - self.builder.CODE:][:64], img.stubs["TEMPO"])
        text = [f"{m} {o}" for _, m, o in stub]
        self.assertIn(f"movw r3, #0x{LITERAL & 0xFFFF:x}", text)            # the pc-relative literal, relocated
        self.assertIn(f"movt r3, #0x{LITERAL >> 16:x}", text)
        self.assertIn("ldr r3, [r3]", text)
        self.assertIn(f"b.w #0x{FN + 4:x}", text)                         # back into the function
        self.assertIn("movt ip, #1", text)                                # TEMPO is takeable

        boot = [f"{m} {o}" for _, m, o in _dis(code[img.stubs["BOOT"] - self.builder.CODE:][:16],
                                                img.stubs["BOOT"])]
        self.assertEqual(boot[1], f"bl #0x{SETUP:x}")                    # setup() first, then the event
        self.assertEqual(boot[3], f"bl #0x{img.dispatch:x}")

    def test_relocation_refuses_branches(self):
        p = self.fw.payload
        b = self.builder._asm(f"b #{FN + 0x40}", FN)
        p[FN - LOAD:FN - LOAD + len(b)] = b
        with self.assertRaises(RuntimeError):
            self.builder.relocate_prologue(self.fw, FN)

    def test_link_orders_handlers(self):
        from dirtyloader.linker import link
        core = self.builder.build_core02_mod(self.fw, self.sha, BINDINGS)
        self.assertEqual(core.events, ["BOOT", "TICK", "TEMPO"])
        late = self.builder.build_asm_mod(self.fw, self.sha, "late", "late", CAVE,
                                          [("ev_tick", "bx lr", 80)])
        early = self.builder.build_asm_mod(self.fw, self.sha, "early", "early", CAVE + 0x40,
                                           [("ev_tick", "bx lr", 20), ("ev_tempo", "movs r0, #1\n bx lr", 50)])
        out = link(self.fw, self.sha, [core, late, early])
        table = abi.CORE_REGION_ADDR + 0x10 - LOAD
        rows = [struct.unpack_from(abi.HOOK_ENTRY_FMT, out.payload, table + 8 * i) for i in range(4)]
        self.assertEqual(rows[0], (int(abi.Event.TICK), abi.FLAG_ENABLED, (CAVE + 0x40) | 1))   # order 20
        self.assertEqual(rows[1][0], int(abi.Event.TEMPO))                                      # order 50
        self.assertEqual(rows[2], (int(abi.Event.TICK), abi.FLAG_ENABLED, CAVE | 1))            # order 80
        self.assertEqual(rows[3], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
