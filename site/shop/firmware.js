// Firmware in the browser: recognise Dirtywave's file (or the .zip it comes in) by its sha256, apply core's patch
// (site/shop/firmware/<target>.json, from make_firmware.py) and write the result as the M8's .bin and as a .hex.
// Nothing here leaves the page.
import { crc32, sha256hex } from './m8.js';

const dec = new TextDecoder('latin1');

// ---- the M8's .bin ("M8FW"): a 0x200-byte header, then the flash image (dirtyloader/m8fw.py) ----
const u32 = (b, o) => (b[o] | b[o + 1] << 8 | b[o + 2] << 16 | b[o + 3] << 24) >>> 0;
const put32 = (b, o, v) => { b[o] = v & 255; b[o + 1] = (v >>> 8) & 255; b[o + 2] = (v >>> 16) & 255; b[o + 3] = (v >>> 24) & 255; };

export function parseBin(bytes) {
  if (bytes.length < 0x200 || dec.decode(bytes.subarray(0, 4)) !== 'M8FW') throw new Error('not an M8 .bin (no M8FW header)');
  const version = u32(bytes, 4), len = u32(bytes, 8), crc = u32(bytes, 12), loadAddr = u32(bytes, 16), hcrc = u32(bytes, 20);
  const payload = bytes.subarray(0x200, 0x200 + len);
  if (payload.length !== len) throw new Error('the .bin is cut short');
  if (crc32(bytes.subarray(0, 20)) !== hcrc) throw new Error('the .bin header\'s checksum is wrong');
  if (crc32(payload) !== crc) throw new Error('the .bin\'s checksum is wrong: the file is damaged');
  return { version, loadAddr, payload };
}

export function buildBin(version, loadAddr, payload) {
  const out = new Uint8Array(0x200 + payload.length);
  out.set([0x4D, 0x38, 0x46, 0x57]);
  put32(out, 4, version); put32(out, 8, payload.length); put32(out, 12, crc32(payload)); put32(out, 16, loadAddr);
  put32(out, 20, crc32(out.subarray(0, 20)));
  out.set(payload, 0x200);
  return out;
}

// ---- Intel HEX ----
/** A .hex as one flat image from its lowest address, gaps 0xFF (dirtyloader/ihex.py read()). */
export function parseHex(text) {
  const chunks = [];
  let upper = 0, lo = Infinity, hi = 0;
  for (const [n, raw] of text.split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line) continue;
    if (line[0] !== ':' || line.length % 2 === 0) throw new Error(`.hex line ${n + 1}: not a record`);
    const r = new Uint8Array((line.length - 1) / 2);
    for (let i = 0; i < r.length; i++) r[i] = parseInt(line.substr(1 + 2 * i, 2), 16);
    if (r.reduce((a, b) => a + b, 0) & 255) throw new Error(`.hex line ${n + 1}: checksum`);
    const count = r[0], addr = r[1] << 8 | r[2], type = r[3], body = r.subarray(4, 4 + count);
    if (body.length !== count) throw new Error(`.hex line ${n + 1}: short record`);
    if (type === 0) { const a = upper + addr; chunks.push([a, body]); lo = Math.min(lo, a); hi = Math.max(hi, a + count); }
    else if (type === 1) break;
    else if (type === 2) upper = (body[0] << 8 | body[1]) << 4;
    else if (type === 4) upper = ((body[0] << 8 | body[1]) << 16) >>> 0;
    else if (type !== 3 && type !== 5) throw new Error(`.hex line ${n + 1}: record type ${type}`);
  }
  if (!chunks.length) throw new Error('the .hex has no data');
  const data = new Uint8Array(hi - lo).fill(0xFF);
  for (const [a, b] of chunks) data.set(b, a - lo);
  return { base: lo, data };
}

/** Every byte of `data` at `base`, 0xFF included: a bootloader that skips what a .hex leaves out can leave old bytes
 *  in flash (docs: the 0xFF lesson), so this .hex leaves nothing out. CRLF, as Dirtywave's files are. */
export function buildHex(base, data, width = 32) {
  const hx = (v) => v.toString(16).toUpperCase().padStart(2, '0');
  const rec = (type, addr, body) => {
    const r = [body.length, (addr >> 8) & 255, addr & 255, type, ...body];
    return ':' + r.map(hx).join('') + hx((-r.reduce((a, b) => a + b, 0)) & 255);
  };
  const out = [];
  let upper = -1;
  for (let i = 0; i < data.length;) {
    const addr = (base + i) >>> 0;
    if (addr >>> 16 !== upper) { upper = addr >>> 16; out.push(rec(4, 0, [upper >> 8, upper & 255])); }
    const n = Math.min(width, data.length - i, 0x10000 - (addr & 0xFFFF));
    out.push(rec(0, addr & 0xFFFF, data.subarray(i, i + n)));
    i += n;
  }
  out.push(rec(1, 0, []));
  return out.join('\r\n') + '\r\n';
}

// ---- .zip, as Dirtywave's firmware comes ----
/** [{name, size, read()}] for the files in a .zip (stored or deflated). */
export function zipEntries(bytes) {
  let e = bytes.length - 22;
  while (e >= 0 && u32(bytes, e) !== 0x06054b50) e--;
  if (e < 0) throw new Error('not a .zip');
  const count = bytes[e + 10] | bytes[e + 11] << 8;
  let p = u32(bytes, e + 16);
  const list = [];
  for (let k = 0; k < count; k++) {
    if (u32(bytes, p) !== 0x02014b50) throw new Error('the .zip\'s directory is damaged');
    const method = bytes[p + 10] | bytes[p + 11] << 8, csize = u32(bytes, p + 20), size = u32(bytes, p + 24);
    const nlen = bytes[p + 28] | bytes[p + 29] << 8, xlen = bytes[p + 30] | bytes[p + 31] << 8, clen = bytes[p + 32] | bytes[p + 33] << 8;
    const local = u32(bytes, p + 42), name = new TextDecoder().decode(bytes.subarray(p + 46, p + 46 + nlen));
    p += 46 + nlen + xlen + clen;
    if (name.endsWith('/')) continue;
    list.push({
      name, size,
      read: async () => {
        const lo = local + 30 + (bytes[local + 26] | bytes[local + 27] << 8) + (bytes[local + 28] | bytes[local + 29] << 8);
        const raw = bytes.subarray(lo, lo + csize);
        if (method === 0) return raw.slice();
        if (method !== 8) throw new Error(`${name}: compressed in a way this page can't read`);
        const out = await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer();
        return new Uint8Array(out);
      },
    });
  }
  return list;
}

// ---- recognising the stock file, and building ----
/**
 * Find the firmware this page can build in a dropped file: the file itself, or a .bin/.hex inside a .zip.
 * `known` is site/shop/firmware/index.json. Returns { entry, bytes, name } for a match, or { candidates } listing
 * what was looked at (name and sha256) when nothing matched.
 */
export async function identify(bytes, fileName, known) {
  const bySha = new Map(known.map(k => [k.stock_sha256, k]));
  const looked = [];
  const tryOne = async (data, name) => {
    const sha = await sha256hex(data);
    looked.push({ name, sha256: sha, size: data.length });
    return bySha.has(sha) ? { entry: bySha.get(sha), bytes: data, name: name.split('/').pop() } : null;
  };
  if (bytes.length > 4 && u32(bytes, 0) === 0x04034b50) {
    for (const z of zipEntries(bytes)) {
      if (z.name.includes('__MACOSX') || !/\.(bin|hex)$/i.test(z.name)) continue;
      const hit = await tryOne(await z.read(), z.name);
      if (hit) return hit;
    }
    return { candidates: looked };
  }
  return (await tryOne(bytes, fileName)) || { candidates: looked };
}

/** What a stock file is, from its own bytes, for telling the user why it isn't one this page builds. */
export function describeStock(bytes, name) {
  try {
    const b = parseBin(bytes);
    const model = (b.version >>> 16) & 0xFFFF;
    return `${name}: an M8 Model:0${model} .bin (format ${b.version & 0xFFFF})`;
  } catch { /* not a .bin */ }
  if (bytes[0] === 0x3A) return `${name}: a .hex`;
  return name;
}

/** The stock file's flash image, as the patch expects it. */
export function stockPayload(patch, bytes) {
  if (patch.stock.kind === 'bin') return parseBin(bytes).payload;
  const h = parseHex(dec.decode(bytes));
  if (h.base !== patch.out.load_addr) throw new Error(`the .hex starts at 0x${h.base.toString(16)}, not the M8's flash`);
  return h.data;
}

/** Apply core's patch to the stock image; checks the result against the sha256 the patch was made with. */
export async function applyPatch(patch, stock) {
  if (stock.length !== patch.stock.payload) throw new Error('the stock image is not the size the patch was made for');
  const img = new Uint8Array(patch.out.payload).fill(0xFF);
  img.set(stock.subarray(0, Math.min(stock.length, img.length)));
  for (const op of patch.ops) {
    if (op.length === 2) img.set(Uint8Array.from(atob(op[1]), c => c.charCodeAt(0)), op[0]);
    else img.set(stock.subarray(op[1], op[1] + op[2]), op[0]);
  }
  const sha = await sha256hex(img);
  if (sha !== patch.out.sha256) throw new Error('the built image is not the one this patch makes: nothing was written');
  return img;
}

/**
 * Build: stock file bytes -> { image, files: [{name, kind, data, sha256}] }. A Model:02 gets the .bin (SD card
 * FIRMWARE UPDATE) and a .hex (TyUploader); a Headless gets the .hex. `image` is the flash image the page flashes.
 */
export async function buildFirmware(patch, stockBytes) {
  const image = await applyPatch(patch, stockPayload(patch, stockBytes));
  const files = [];
  if (patch.stock.kind === 'bin') {
    const bin = buildBin(patch.out.version, patch.out.load_addr, image);
    const sha = await sha256hex(bin);
    if (patch.out.bin_sha256 && sha !== patch.out.bin_sha256) throw new Error('the .bin is not the one this patch makes');
    files.push({ name: patch.out.name + '.bin', kind: 'bin', data: bin, sha256: sha });
  }
  const hex = new TextEncoder().encode(buildHex(patch.out.load_addr, image));
  files.push({ name: patch.out.name + '.hex', kind: 'hex', data: hex, sha256: await sha256hex(hex) });
  return { image, files };
}
