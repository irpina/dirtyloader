"""dirtyloader.unit against a fake unit that answers the way core 0.3's core_serial does (core03.c, serve())."""
import struct
import unittest
import zlib

from dirtyloader import unit as U


def slip(frame: bytes) -> bytes:
    out = bytearray()
    for b in frame:
        out += {0xC0: b"\xdb\xdc", 0xDB: b"\xdb\xdd"}.get(b, bytes([b]))
    return bytes(out) + b"\xc0"


class FakeUnit:
    """A serial port with core_serial behind it and a dict for the SD card under /dirtyloader."""

    def __init__(self):
        self.files, self.out, self.restarted = {}, bytearray(), False
        self.dirs = False
        self.noise = slip(b"\xfe" + bytes(11))           # a display frame the host must skip

    def write(self, data):
        assert data[0] == U.MARK
        cmd, seq, n = data[1], data[2], struct.unpack_from("<H", data, 3)[0]
        p = bytes(data[5:5 + n])
        assert len(data) == 6 + n and (sum(data[1:5 + n]) & 0xFF) == data[5 + n]
        status, reply = 0, b""
        if cmd == U.C_INFO:
            reply = b"dirtyloader core 0.5\n"
        elif cmd == U.C_MKDIRS:
            self.dirs = True
        elif cmd == U.C_LIST:
            reply = "".join(k[len("mods/"):] + "\n" for k in self.files if k.startswith("mods/")).encode()
        elif cmd == U.C_PUT:
            off, k = struct.unpack_from("<IB", p)
            name, data_ = p[5:5 + k].decode(), p[5 + k:]
            if name.startswith("mods/") and not self.dirs:
                status = 4
            else:
                cur = self.files.get(name, b"") if off else b""
                self.files[name] = cur[:off] + data_
                reply = struct.pack("<I", len(data_))
        elif cmd == U.C_CHECK:
            d = self.files.get(p.decode())
            if d is None:
                status = 3
            else:
                reply = struct.pack("<II", len(d), zlib.crc32(d) & 0xFFFFFFFF)
        elif cmd == U.C_GET:
            off, mx, k = struct.unpack_from("<IHB", p)
            d = self.files.get(p[7:7 + k].decode())
            if d is None:
                status = 3
            else:
                reply = d[off:off + min(mx, 512)]
        elif cmd == U.C_RESTART:
            self.restarted = True
        elif cmd == U.C_DELETE:
            if self.files.pop(p.decode(), None) is None:
                status = 3
        else:
            status = 7
        self.out += self.noise + slip(bytes([U.REPLY, cmd, seq, status]) + reply)

    def read(self, n=4096, timeout=0.1):
        chunk, self.out = bytes(self.out[:n]), self.out[n:]
        return chunk

    def close(self):
        pass


def _m8x(image_extra=b""):
    """A minimal valid .m8x: a dl_mod header with no subscriptions, no relocations."""
    from dirtyloader.cc import M8X_HEADER, M8X_MAGIC, DL_MOD_MAGIC
    strings = b"t\0" + b"0.1\0" + b"T\0"
    base = 32
    img = struct.pack("<IHHIIIII", DL_MOD_MAGIC, 1, 0, base, base + 2, base + 6, 0, 0) + strings + image_extra
    return M8X_HEADER.pack(M8X_MAGIC, len(img), 0, 0, zlib.crc32(img) & 0xFFFFFFFF) + img


class TestWire(unittest.TestCase):
    def test_request_format(self):
        r = U.request_bytes(U.C_PUT, 7, b"\x01\x02")
        self.assertEqual(r[:5], bytes([0xD1, U.C_PUT, 7, 2, 0]))
        self.assertEqual(r[-1], (U.C_PUT + 7 + 2 + 1 + 2) & 0xFF)

    def test_slip_frames_unescape_and_keep_partial(self):
        buf = bytearray(slip(b"\xf1\xc0\xdb") + b"\xf1\x01")
        self.assertEqual(U.slip_frames(buf), [b"\xf1\xc0\xdb"])
        self.assertEqual(bytes(buf), b"\xf1\x01")


class TestUnit(unittest.TestCase):
    def setUp(self):
        self.fake = FakeUnit()
        self.u = U.Unit(port=self.fake)

    def test_add_uploads_verifies_and_switches_on(self, ):
        import tempfile, os
        data = _m8x(bytes(3000))                          # several chunks
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "big.m8x")
            open(path, "wb").write(data)
            self.assertEqual(self.u.add(path), "big.m8x")
        self.assertEqual(self.fake.files["mods/big.m8x"], data)
        self.assertEqual(self.u.active(), ["big.m8x"])
        self.assertEqual(self.fake.files["guard"], b"GOOD")
        self.assertEqual(self.u.list(), ["big.m8x"])

    def test_off_and_on(self):
        self.fake.dirs = True
        self.fake.files["mods/a.m8x"] = b"x"
        self.u.set_active(["a.m8x"])
        U.Unit.set_active(self.u, [n for n in self.u.active() if n != "a.m8x"])
        self.assertEqual(self.u.active(), [])

    def test_add_off_then_remove(self):
        import tempfile, os
        data = _m8x(bytes(16))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "quiet.m8x")
            open(path, "wb").write(data)
            self.u.add(path, on=False)
        self.assertIn("mods/quiet.m8x", self.fake.files)
        self.assertEqual(self.u.active(), [])
        self.u.set_active(["quiet.m8x"])
        self.u.remove("quiet.m8x")
        self.assertNotIn("mods/quiet.m8x", self.fake.files)
        self.assertEqual(self.u.active(), [])
        with self.assertRaises(U.UnitError):
            self.u.delete("mods/quiet.m8x")

    def test_errors_surface(self):
        with self.assertRaises(U.UnitError):
            self.u.check("mods/missing.m8x")

    def test_corrupt_mod_is_refused_before_upload(self):
        import tempfile, os
        bad = bytearray(_m8x())
        bad[-1] ^= 0xFF
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.m8x")
            open(path, "wb").write(bad)
            with self.assertRaises(Exception):
                self.u.add(path)
        self.assertNotIn("mods/bad.m8x", self.fake.files)


if __name__ == "__main__":
    unittest.main()
