// The shop's firmware builder (site/shop/firmware.js) and USB flasher (site/shop/halfkay.js).
//   node tests/test_firmware.mjs
// With Dirtywave's stock files on this computer (as make_firmware.py finds them, or DIRTYLOADER_MODEL02_BIN /
// DIRTYLOADER_MODEL02_664_BIN / DIRTYLOADER_HEADLESS_HEX / DIRTYLOADER_MODEL02_ZIP / DIRTYLOADER_MODEL02_664_ZIP), it also
// builds every firmware from them; CI has none.
import { readFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { deflateRawSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { parseBin, buildBin, parseHex, buildHex, zipEntries, identify, applyPatch, buildFirmware } from '../site/shop/firmware.js';
import { flashImage, BLOCK } from '../site/shop/halfkay.js';

const SHOP = new URL('../site/shop/', import.meta.url);
const DL = join(homedir(), 'Downloads');
const STOCK = {
  'm8-model02': process.env.DIRTYLOADER_MODEL02_BIN || join(DL, 'M8Firmware_V6_6_2', 'Firmware', 'Model02', 'M8_V6_6_2A_MODEL02.bin'),
  'm8-model02-664': process.env.DIRTYLOADER_MODEL02_664_BIN || join(DL, 'M8Firmware_V6_6_4', 'Firmware', 'Model02', 'M8_V6_6_4A_MODEL02.bin'),
  'm8-headless': process.env.DIRTYLOADER_HEADLESS_HEX || join(DL, 'M8Headless_6_6_4A', 'M8_V6_6_4A_HEADLESS.hex'),
};
const ZIP = process.env.DIRTYLOADER_MODEL02_ZIP || join(DL, 'M8Firmware_V6_6_2.zip');
const ZIP664 = process.env.DIRTYLOADER_MODEL02_664_ZIP || join(DL, 'M8Firmware_V6_6_4', 'M8Firmware.zip');
const sha = (b) => createHash('sha256').update(b).digest('hex');
let n = 0, skipped = 0;
const test = async (name, fn) => { await fn(); n++; console.log('ok', name); };
const skip = (name) => { skipped++; console.log('skip', name, '(no stock file here)'); };

// a zip as Dirtywave's: deflated entries, a folder, a __MACOSX copy
function makeZip(files) {
  const parts = [], dir = [];
  let off = 0;
  for (const [name, data] of files) {
    const nm = Buffer.from(name), body = data ? deflateRawSync(data) : Buffer.alloc(0);
    const h = Buffer.alloc(30); h.writeUInt32LE(0x04034b50, 0); h.writeUInt16LE(data ? 8 : 0, 8);
    h.writeUInt32LE(body.length, 18); h.writeUInt32LE(data ? data.length : 0, 22); h.writeUInt16LE(nm.length, 26);
    const c = Buffer.alloc(46); c.writeUInt32LE(0x02014b50, 0); c.writeUInt16LE(data ? 8 : 0, 10);
    c.writeUInt32LE(body.length, 20); c.writeUInt32LE(data ? data.length : 0, 24); c.writeUInt16LE(nm.length, 28); c.writeUInt32LE(off, 42);
    parts.push(h, nm, body); dir.push(c, nm); off += 30 + nm.length + body.length;
  }
  const cd = Buffer.concat(dir), e = Buffer.alloc(22);
  e.writeUInt32LE(0x06054b50, 0); e.writeUInt16LE(files.length, 8); e.writeUInt16LE(files.length, 10);
  e.writeUInt32LE(cd.length, 12); e.writeUInt32LE(off, 16);
  return new Uint8Array(Buffer.concat([...parts, cd, e]));
}

await test('.bin round trip, CRCs checked', () => {
  const p = Uint8Array.from({ length: 5000 }, (_, i) => (i * 7) & 255);
  const b = buildBin(0x00020001, 0x60000000, p);
  const r = parseBin(b);
  assert.equal(r.version, 0x00020001); assert.equal(r.loadAddr, 0x60000000); assert.deepEqual(r.payload, p);
  b[0x300] ^= 1;
  assert.throws(() => parseBin(b), /checksum/);
});
await test('.hex round trip leaves no byte out, 0xFF included', () => {
  const d = new Uint8Array(70000).fill(0xFF); d[3] = 1; d[69999] = 2;
  const text = buildHex(0x6000FFF0, d);
  const h = parseHex(text);
  assert.equal(h.base, 0x6000FFF0); assert.deepEqual(h.data, d);
  const bytesInRecords = text.split('\r\n').filter(l => l.slice(7, 9) === '00').reduce((a, l) => a + parseInt(l.slice(1, 3), 16), 0);
  assert.equal(bytesInRecords, d.length);
});
await test('a .zip\'s files, deflated', async () => {
  const z = makeZip([['Firmware/', null], ['Firmware/a.bin', Buffer.from('hello hello hello')]]);
  const e = zipEntries(z);
  assert.equal(e.length, 1); assert.equal(e[0].name, 'Firmware/a.bin');
  assert.equal(new TextDecoder().decode(await e[0].read()), 'hello hello hello');
});
await test('a patch on a pretend stock image: puts, copies, and the sha256 check', async () => {
  const stock = Uint8Array.from({ length: 4096 }, (_, i) => (i * 13) & 255);
  const want = new Uint8Array(5000).fill(0xFF); want.set(stock); want.set([1, 2, 3], 10); want.set(stock.subarray(100, 120), 4500);
  const patch = { stock: { payload: 4096 }, out: { payload: 5000, sha256: sha(want) },
    ops: [[10, Buffer.from([1, 2, 3]).toString('base64')], [4500, 100, 20]] };
  assert.deepEqual(await applyPatch(patch, stock), want);
  patch.ops[1][2] = 19;
  await assert.rejects(applyPatch(patch, stock), /not the one/);
});

const index = JSON.parse(readFileSync(new URL('firmware/index.json', SHOP)));
await test('every firmware patch is listed and ships none of the stock file\'s size', () => {
  for (const e of index) {
    const p = JSON.parse(readFileSync(new URL(e.file, SHOP)));
    assert.equal(p.stock.sha256, e.stock_sha256); assert.equal(p.core, e.core);
    const shipped = p.ops.filter(o => o.length === 2).reduce((a, o) => a + Buffer.from(o[1], 'base64').length, 0);
    assert.ok(shipped < p.stock.payload / 20, `${e.target}: ${shipped} bytes`);
  }
});
for (const e of index) {
  const path = STOCK[e.target];
  if (!existsSync(path)) { skip(`build ${e.target} from the stock file`); continue; }
  await test(`build ${e.target} from the stock file: recognised, patched, the files check out`, async () => {
    const patch = JSON.parse(readFileSync(new URL(e.file, SHOP)));
    const raw = new Uint8Array(readFileSync(path));
    const id = await identify(raw, path.split(/[\\/]/).pop(), index);
    assert.equal(id.entry.target, e.target);
    const { image, files } = await buildFirmware(patch, raw);
    assert.equal(sha(image), patch.out.sha256);
    const hex = files.find(f => f.kind === 'hex');
    const h = parseHex(new TextDecoder().decode(hex.data));
    assert.equal(h.base, patch.out.load_addr); assert.equal(sha(h.data), patch.out.sha256);
    if (patch.stock.kind === 'bin') assert.equal(files.find(f => f.kind === 'bin').sha256, patch.out.bin_sha256);
  });
}
if (existsSync(ZIP)) {
  await test('Dirtywave\'s .zip, as downloaded, is recognised', async () => {
    const id = await identify(new Uint8Array(readFileSync(ZIP)), 'M8Firmware_V6_6_2.zip', index);
    assert.equal(id.entry.target, 'm8-model02'); assert.equal(id.name, 'M8_V6_6_2A_MODEL02.bin');
  });
} else skip('the .zip');
if (existsSync(ZIP664)) {
  await test("Dirtywave's current .zip (6.6.4A), as downloaded, is recognised as the Model:02's", async () => {
    const id = await identify(new Uint8Array(readFileSync(ZIP664)), 'M8Firmware.zip', index);
    assert.equal(id.entry.target, 'm8-model02-664'); assert.equal(id.name, 'M8_V6_6_4A_MODEL02.bin');
  });
} else skip('the 6.6.4A .zip');
await test('a file that isn\'t one says what was looked at', async () => {
  const r = await identify(new TextEncoder().encode('nope'), 'x.hex', index);
  assert.equal(r.candidates.length, 1);
});

// ---- HalfKay, the Teensy's bootloader, with a pretend one ----
class FakeHalfKay {
  constructor({ busyFirst = 0 } = {}) { this.flash = new Map(); this.busy = busyFirst; this.booted = false; this.calls = 0; }
  async sendReport(id, data) {
    this.calls++;
    assert.equal(id, 0); assert.equal(data.length, BLOCK + 64);
    if (this.busy > 0) { this.busy--; throw new Error('NotAllowedError: busy erasing'); }
    const a = data[0] | data[1] << 8 | data[2] << 16;
    if (a === 0xFFFFFF) { this.booted = true; return; }
    assert.ok(data.subarray(3, 64).every(b => b === 0));
    this.flash.set(a, data.slice(64));
  }
}
await test('HalfKay: every block written, 0xFF ones too, in order, then boot', async () => {
  const img = new Uint8Array(BLOCK * 3 + 100).fill(0xFF); img[5] = 7; img[BLOCK * 3 + 99] = 9;
  const hk = new FakeHalfKay({ busyFirst: 2 });
  const seen = [];
  await flashImage(hk, img, { onProgress: (p) => seen.push(p), retryMs: 1 });
  assert.deepEqual([...hk.flash.keys()], [0, BLOCK, BLOCK * 2, BLOCK * 3]);
  assert.equal(hk.flash.get(0)[5], 7); assert.equal(hk.flash.get(BLOCK * 3)[99], 9);
  assert.ok(hk.flash.get(BLOCK * 3).subarray(100).every(b => b === 0xFF));
  assert.equal(hk.booted, true); assert.equal(seen.at(-1), 1);
});
await test('HalfKay: refuses an image bigger than a Teensy 4.1\'s flash', async () => {
  await assert.rejects(flashImage(new FakeHalfKay(), new Uint8Array(9 * 1024 * 1024)), /too big/);
});

console.log(`${n} passed${skipped ? `, ${skipped} skipped` : ''}`);
