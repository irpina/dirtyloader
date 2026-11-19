// A pretend M8 with dirtyloader core 0.7, for tests and for trying the page without hardware: it answers the same
// requests as core03.c's serve() from an in-memory card. fakePort() looks like a Web Serial port.
import { crc32 } from '../m8.js';

const enc = new TextEncoder(), dec = new TextDecoder('latin1');
const le32 = (v) => [v & 0xFF, (v >>> 8) & 0xFF, (v >>> 16) & 0xFF, (v >>> 24) & 0xFF];
const u32 = (b, o) => (b[o] | b[o + 1] << 8 | b[o + 2] << 16 | b[o + 3] << 24) >>> 0;

export class FakeCore {
  constructor({ fw = 0x02060602, loaded = [], files = {}, theme } = {}) {
    this.fw = fw; this.loaded = loaded;
    this.files = new Map(Object.entries(files).map(([k, v]) => [k, typeof v === 'string' ? enc.encode(v) : v]));
    this.theme = theme || Uint8Array.from([0, 0, 0, 0x20, 0x28, 0x30, 0x48, 0x50, 0x60, 0x90, 0xb0, 0xb8, 255, 255, 255, 255, 0x20, 0x40, 0, 255, 0x60, 0, 255, 255, 0, 255, 0x80, 0x90, 0xb8, 0xb8, 0, 255, 0xe0, 255, 255, 0x50, 255, 0, 0x80]);
    this.themeName = new Uint8Array(13);
    this.xflags = 0; this.xrgb = new Uint8Array(45); this.xsaved = 0;
    this.saved = 0; this.restarts = 0; this.dirs = new Set(); this.rx = []; this.out = null;
  }
  path(name, anywhere) {
    if (!name.length || name.length > 63 || (name[0] === '/' && !anywhere) || name.includes('..') || /[^A-Za-z0-9._\-/]/.test(name)) return null;
    return name[0] === '/' ? name : '/dirtyloader/' + name;
  }
  reply(cmd, seq, status, data = []) {
    const raw = [0xF1, cmd, seq, status, ...data], o = [];
    for (const b of raw) { if (b === 0xC0) o.push(0xDB, 0xDC); else if (b === 0xDB) o.push(0xDB, 0xDD); else o.push(b); }
    o.push(0xC0);
    this.out(Uint8Array.from(o));
  }
  feed(bytes) {
    this.rx.push(...bytes);
    for (;;) {
      const i = this.rx.indexOf(0xD1);
      if (i < 0) { this.rx = []; return; }
      if (i) this.rx.splice(0, i);
      if (this.rx.length < 6) return;
      const len = this.rx[3] | this.rx[4] << 8;
      if (this.rx.length < 6 + len) return;
      const pkt = this.rx.splice(0, 6 + len);
      let sum = 0; for (let k = 1; k < 5 + len; k++) sum += pkt[k];
      if ((sum & 0xFF) !== pkt[5 + len]) { this.reply(pkt[1], pkt[2], 2); continue; }
      this.serve(pkt[1], pkt[2], Uint8Array.from(pkt.slice(5, 5 + len)));
    }
  }
  serve(cmd, seq, p) {
    const ok = (d) => this.reply(cmd, seq, 0, d ? [...d] : []);
    const fail = (s) => this.reply(cmd, seq, s);
    switch (cmd) {
      case 1: return ok(enc.encode(`dirtyloader core 0.7\nfirmware 0x${this.fw.toString(16).padStart(8, '0')}\nsd mounted\nmods area 19808\nloaded ${this.loaded.join(' ')}\n`));
      case 7: this.restarts++; ok(); return;
      case 11: {
        if (!p.length) return ok([...this.theme, ...this.themeName]);
        if (p.length < 39 || p.length > 52) return fail(1);
        this.theme = p.slice(0, 39);
        if (p.length > 40) { this.themeName = new Uint8Array(13); this.themeName.set(p.slice(40, 52)); }
        if (p.length > 39 && p[39] & 1) this.saved++;
        return ok();
      }
      case 12: {
        if (!p.length) return ok([this.xflags, ...this.xrgb]);
        if (p.length !== 46 && p.length !== 47) return fail(1);
        this.xflags = p[0] & 7; this.xrgb = p.slice(1, 46);
        if (p.length === 47 && p[46] & 1) { this.xsaved++; this.files.set('/dirtyloader/theme.ext', Uint8Array.from([68, 76, 88, 84, this.xflags, 0, 0, 0, ...this.xrgb])); }
        return ok();
      }
      case 6: this.dirs.add('/dirtyloader/mods'); return ok();
      case 2: {
        const dir = this.path(dec.decode(p), true);
        if (!dir) return fail(3);
        const names = [...this.files.keys()].filter(k => k.startsWith(dir + '/') && !k.slice(dir.length + 1).includes('/')).map(k => k.slice(dir.length + 1));
        if (!names.length && !this.dirs.has(dir) && ![...this.files.keys()].some(k => k.startsWith(dir + '/'))) return fail(3);
        return ok(enc.encode(names.map(n => n + '\n').join('')));
      }
      case 3: {
        const n = p[4], path = this.path(dec.decode(p.subarray(5, 5 + n)), false);
        if (!path) return fail(3);
        const off = u32(p, 0), data = p.subarray(5 + n);
        const old = off ? (this.files.get(path) || new Uint8Array()) : new Uint8Array();
        const f = new Uint8Array(Math.max(old.length, off + data.length)); f.set(old); f.set(data, off);
        this.files.set(path, f);
        return ok(le32(data.length));
      }
      case 4: {
        const path = this.path(dec.decode(p), true), f = path && this.files.get(path);
        if (!f) return fail(3);
        return ok([...le32(f.length), ...le32(crc32(f))]);
      }
      case 5: {
        const n = p[6], path = this.path(dec.decode(p.subarray(7, 7 + n)), true), f = path && this.files.get(path);
        if (!f) return fail(3);
        const off = u32(p, 0), max = Math.min(512, p[4] | p[5] << 8);
        return ok(f.subarray(off, off + max));
      }
      case 9: {
        const path = this.path(dec.decode(p), false);
        if (!path || !this.files.delete(path)) return fail(3);
        return ok();
      }
      default: return fail(7);
    }
  }
}

/** Something shaped like a Web Serial SerialPort, wired to a FakeCore. */
export function fakePort(core = new FakeCore()) {
  let push;
  const readable = new ReadableStream({ start(c) { push = c; } });
  core.out = (b) => setTimeout(() => push.enqueue(b), 2);
  const writable = new WritableStream({ write(chunk) { core.feed(chunk); } });
  return { core, readable, writable, open: async () => {}, close: async () => {}, getInfo: () => ({ usbVendorId: 0x16C0, usbProductId: 0x048A }) };
}
