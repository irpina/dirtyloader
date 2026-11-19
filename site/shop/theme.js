// M8 themes: the 13 colours of SYSTEM SETTINGS > THEME, the .m8t file, the page's colours made from them, and a small
// M8 screen drawn in them (core's 5 x 7 font).
import { FONT } from './font.js';

export const SLOTS = [
  { key: 'background', label: 'BACKGROUND', hint: 'Behind everything' },
  { key: 'empty', label: 'TEXT:EMPTY', hint: 'Empty steps (--) and blank fields' },
  { key: 'info', label: 'TEXT:INFO', hint: 'Row numbers, labels, the page map' },
  { key: 'default', label: 'TEXT:DEFAULT', hint: 'Plain text: the tempo, track list' },
  { key: 'value', label: 'TEXT:VALUE', hint: 'Values you can change' },
  { key: 'titles', label: 'TEXT:TITLES', hint: 'The page title' },
  { key: 'play', label: 'PLAY MARKERS', hint: 'Where the song is playing' },
  { key: 'cursor', label: 'CURSOR', hint: 'The cursor and the current column' },
  { key: 'selection', label: 'SELECTION', hint: 'A selected block' },
  { key: 'scope', label: 'SCOPE/SLIDER', hint: 'The scope and sliders' },
  { key: 'low', label: 'METER LOW', hint: 'Level meters, quiet' },
  { key: 'mid', label: 'METER MID', hint: 'Level meters, loud' },
  { key: 'peak', label: 'METER PEAK', hint: 'Level meters, clipping' },
];

// core's extended theme (dirtyloader core 0.7, THEMEX): 15 more colours the firmware's screens never had
export const EXT_SLOTS = [
  ...[1, 2, 3, 4, 5, 6, 7, 8].map(t => ({ label: `TRACK ${t}`, hint: t === 1 ? "SONG's column and the track list" : '' })),
  { label: 'TITLE:SONG', hint: 'The SONG title' }, { label: 'TITLE:CHAIN', hint: '' }, { label: 'TITLE:PHRASE', hint: '' },
  { label: 'TITLE:INSTR', hint: 'INSTRUMENT, MODS, POOL' }, { label: 'TITLE:TABLE', hint: '' },
  { label: 'TITLE:MIXER', hint: 'MIXER, EFFECTS, EQ, LIMITER' }, { label: 'TITLE:OTHER', hint: 'PROJECT, settings...' },
];
export const EXT_FLAGS = { tracks: 1, titles: 2, follow: 4 };
export const EXT_PRESETS = {
  RAINBOW: 'ff4060ff9030ffe04060e06030d0e04080ffa060ffff60d0ff4060ffe04030d0e060e060a060ffff9030ffffff',
  PASTEL: 'ffa0b4ffc8a0fff0a0b4f0b4a0e8f0a0c0ffcab4ffffb4e6ffa0b4fff0a0a0e8f0b4f0b4cab4ffffc8a0f0f0f0',
  NEON: 'ff2a6dff7b00f5ff0000ff9f00e5ff2d6bffb300ffff00d4ff2a6df5ff0000e5ff00ff9fb300ffff7b00ffffff',
};
const hexToBytes = (h) => Uint8Array.from(h.match(/../g).map(x => parseInt(x, 16)));
export const toHex = (c, i) => '#' + [c[i * 3], c[i * 3 + 1], c[i * 3 + 2]].map(v => v.toString(16).padStart(2, '0')).join('');
export const setHex = (c, i, hex) => { const b = hexToBytes(hex.replace('#', '')); c.set(b, i * 3); };

// The M8's own default (what a reset gives), and themes made for this shop. The M8's nine stock themes are read from
// your card's /Themes folder when it is connected: they are Dirtywave's, so the page doesn't carry them.
export const PRESETS = [
  { name: 'DEFAULT', colors: hexToBytes('00000020283048506090b0b8ffffffff204000ff6000ffff00ff8090b8b800ffe0ffff50ff0080'), from: 'm8' },
  { name: 'DIRTYLOADER', colors: hexToBytes('0b0912262035756a8ac9bcd8fff2d8b84dff30e0a0ffd25c3c2a6abb7cff3cdc8cffd25cff4078'), from: 'shop' },
  { name: 'NIGHTSHIFT', colors: hexToBytes('101418252c3554606c9aa6b2eef2f5ffb02e6dd68e5fb3ff2a4a6e7cc4e05fd68effd25cff5f56'), from: 'shop' },
  { name: 'PAPERTAPE', colors: hexToBytes('ece6d8cfc6b28d8574524b3f1c1814c2391b2e7d32005fb8d9730d1f6aa52e7d32c99a06c2391b'), from: 'shop' },
  { name: 'PHOSPHOR', colors: hexToBytes('050a06102a14246b33409a52a8ffb46bff8fd4ff5a62ff8a1f5c2c62ff8a62ff8ae6ff5aff7a3c'), from: 'shop' },
  { name: 'SAKURA', colors: hexToBytes('1c1219352230805c6eccaab8fff0f4ff8fb8a8e6cfffd36e5a2f4aff9ec8a8e6cfffd36eff5f7e'), from: 'shop' },
];

/** A .m8t: "M8VERSION\0", 4 version bytes (the M8 reads and ignores them), the 13 colours. */
export function parseM8t(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const head = new TextDecoder('latin1').decode(b.subarray(0, 9));
  if (head !== 'M8VERSION' || b.length < 53) throw new Error('not an M8 theme (.m8t) file');
  return b.slice(14, 53);
}
export function encodeM8t(colors) {
  const out = new Uint8Array(53);
  out.set(new TextEncoder().encode('M8VERSION'), 0);
  out.set([2, 1, 0, 0x20], 10);
  out.set(colors.subarray(0, 39), 14);
  return out;
}

// ---- the page in the theme's colours ------------------------------------------------------------------------------
const rgb = (c, i) => [c[i * 3], c[i * 3 + 1], c[i * 3 + 2]];
const mix = (a, b, t) => a.map((v, k) => Math.round(v + (b[k] - v) * t));
const css = (v) => `rgb(${v[0]} ${v[1]} ${v[2]})`;
const lum = (v) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(v[0]) + 0.7152 * f(v[1]) + 0.0722 * f(v[2]); };
export const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

/** CSS custom properties for the page, from the theme: BACKGROUND is the page, TEXT:EMPTY its panels and lines,
 *  TEXT:DEFAULT the text, VALUE the strong text, TITLES the headings, CURSOR the buttons, SELECTION what's picked,
 *  PLAY "on", SCOPE the progress bars, the meters ok / warning / error. */
export function tokens(c) {
  const bg = rgb(c, 0), empty = rgb(c, 1), info = rgb(c, 2), text = rgb(c, 3), value = rgb(c, 4), title = rgb(c, 5);
  const play = rgb(c, 6), cursor = rgb(c, 7), sel = rgb(c, 8), scope = rgb(c, 9), low = rgb(c, 10), mid = rgb(c, 11), peak = rgb(c, 12);
  const light = lum(bg) > 0.4;
  // the panels: BACKGROUND moved a little towards TEXT:EMPTY (or towards grey when the two are the same)
  const toward = contrast(bg, empty) > 1.15 ? empty : (light ? [0, 0, 0] : [255, 255, 255]);
  const ink = (on) => (contrast(on, bg) >= contrast(on, value) ? bg : value);
  const readable = (v, min) => { let o = v; for (let t = 0.15; contrast(o, bg) < min && t <= 1; t += 0.15) o = mix(v, light ? [0, 0, 0] : [255, 255, 255], t); return o; };
  return {
    '--bg': css(bg), '--panel': css(mix(bg, toward, 0.22)), '--panel-2': css(mix(bg, toward, 0.36)),
    '--line': css(mix(bg, toward, 0.55)), '--empty': css(readable(empty, 1.6)), '--info': css(readable(info, 3)),
    '--text': css(readable(text, 4.5)), '--value': css(readable(value, 4.5)), '--title': css(readable(title, 3)),
    '--play': css(readable(play, 3)), '--cursor': css(cursor), '--on-cursor': css(ink(cursor)),
    '--sel': css(sel), '--sel-soft': css(mix(bg, sel, 0.22)), '--on-sel': css(ink(sel)),
    '--scope': css(scope), '--low': css(low), '--mid': css(mid), '--peak': css(peak),
    '--cursor-soft': css(mix(bg, cursor, 0.18)), '--title-soft': css(mix(bg, title, 0.18)),
    '--peak-soft': css(mix(bg, peak, 0.2)), '--play-soft': css(mix(bg, play, 0.18)),
    '--scheme': light ? 'light' : 'dark',
  };
}
export function applyTokens(c, el = document.documentElement) {
  const t = tokens(c);
  for (const [k, v] of Object.entries(t)) if (k !== '--scheme') el.style.setProperty(k, v);
  el.style.colorScheme = t['--scheme'];
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = toHex(c, 0);
}

// ---- an M8 screen, drawn the way the firmware lays out SONG --------------------------------------------------------
// 40 x 24 cells of 8 x 10 px (320 x 240, the Model:01's screen; the Model:02 doubles the font). `glow` picks a slot
// to blink, so you can see what a colour paints.
export function drawScreen(canvas, c, { glow = -1, phase = 0, scale = 1, ext = null } = {}) {
  const W = 320, H = 240;
  if (canvas.width !== W * scale) { canvas.width = W * scale; canvas.height = H * scale; }
  const g = canvas.getContext('2d');
  g.setTransform(scale, 0, 0, scale, 0, 0);
  g.imageSmoothingEnabled = false;
  // 13.. are core's extended slots (ext.rgb), shown where the M8 shows them when their switch is on
  const hexAt = (i) => (i < 13 ? toHex(c, i) : toHex(ext.rgb, i - 13));
  const col = (i) => (i === glow && phase ? toHex(c, i === 0 ? 4 : 0) : hexAt(i));
  const xf = ext ? ext.flags : 0, trk = (t, plain) => (xf & 1 ? 13 + t : plain);
  g.fillStyle = glow === 0 && phase ? toHex(c, 1) : toHex(c, 0);
  g.fillRect(0, 0, W, H);
  const text = (cx, cy, s, slot, dx = 0) => {
    g.fillStyle = col(slot);
    for (let k = 0; k < s.length; k++) {
      const rows = FONT[s[k].toUpperCase()];
      if (!rows) continue;
      const x0 = cx * 8 + dx + k * 8 + 1, y0 = cy * 10 + 1;
      for (let r = 0; r < 7; r++) for (let b = 0; b < 5; b++) if (rows[r] & (0x10 >> b)) g.fillRect(x0 + b, y0 + r, 1, 1);
    }
  };
  // the scope along the top
  g.fillStyle = col(9);
  for (let x = 0; x < W; x++) {
    const y = 9 + Math.round(Math.sin(x * 0.11) * 4 * Math.sin(x * 0.013 + 1) + Math.sin(x * 0.37) * 1.5);
    g.fillRect(x, y, 1, 1);
  }
  text(1, 2, 'SONG', xf & 2 ? 21 : 5);
  for (let t = 0; t < 8; t++) text(4 + t * 3, 4, String(t + 1), t === 0 ? 7 : trk(t, 2));
  // a selection (rows 01..03, tracks 3..4): the M8 outlines it and draws its values in SELECTION
  g.fillStyle = col(8);
  { const x = (4 + 2 * 3) * 8 - 2, y = 6 * 10 - 1, w = 6 * 8 - 3, h = 3 * 10 + 1;
    g.fillRect(x, y, w, 1); g.fillRect(x, y + h - 1, w, 1); g.fillRect(x, y, 1, h); g.fillRect(x + w - 1, y, 1, h); }
  const chains = { '0,0': '00', '0,1': '00', '1,0': '01', '1,1': '02', '2,0': '03', '1,2': '08', '1,3': '09', '2,2': '08', '3,3': '0A', '6,2': '04', '6,3': '05', '7,2': '04', '7,3': '05', '8,2': '06', '8,3': '07', '3,0': '01' };
  for (let r = 0; r < 16; r++) {
    const row = r.toString(16).toUpperCase().padStart(2, '0');
    text(1, 5 + r, row, r === 0 ? 7 : 2);
    for (let t = 0; t < 8; t++) {
      const v = chains[`${r},${t}`];
      const inSel = r >= 1 && r <= 3 && (t === 2 || t === 3);
      if (v) text(4 + t * 3, 5 + r, v, inSel ? 8 : trk(t, 4));
      else text(4 + t * 3, 5 + r, '--', 1);
    }
  }
  // the play marker, and the cursor's brackets
  text(3, 7, '>', 6, -2);
  g.fillStyle = col(7);
  const bx = 4 * 8 - 3, by = 5 * 10 - 2, bw = 2 * 8 + 5, bh = 12;
  for (const [x, y, w, h] of [[bx, by, 4, 1], [bx, by, 1, 4], [bx + bw - 4, by, 4, 1], [bx + bw - 1, by, 1, 4],
    [bx, by + bh - 1, 4, 1], [bx, by + bh - 4, 1, 4], [bx + bw - 4, by + bh - 1, 4, 1], [bx + bw - 1, by + bh - 4, 1, 4]]) g.fillRect(x, y, w, h);
  // the right-hand column: tempo, tracks, meters, the page map
  text(32, 4, 'T>120', 3);
  for (let t = 0; t < 8; t++) { text(32, 6 + t, String(t + 1), t === 0 ? 7 : trk(t, 3)); text(34, 6 + t, '---', 1); }
  const meter = (x, lv) => {
    for (let k = 0; k < 20; k++) {
      if (k > lv) break;
      g.fillStyle = col(k >= 17 ? 12 : k >= 12 ? 11 : 10);
      g.fillRect(x, 160 - k * 4, 6, 3);
    }
  };
  meter(296, 18); meter(305, 13);
  text(32, 18, 'P', 2); text(31, 19, 'SCPIT', 2); text(31, 19, 'S', 4); text(32, 20, 'V', 2);
}
