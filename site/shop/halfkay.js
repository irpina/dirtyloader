// Flashing an M8 from the page: the Teensy 4.1's bootloader (HalfKay) over WebHID, as the Teensy Loader and
// TyUploader do it. The bootloader is in the Teensy's own chip and nothing here writes it, so a failed or wrong
// flash is always undone by flashing again (Dirtywave's stock file included).
//
// Protocol (Teensy 4.x): one HID output report per 1 KB block, 64 bytes of header (the block's offset in flash,
// 24 bits, little-endian; the rest 0) then the 1024 data bytes. The first block also erases, so it can be refused
// for a while: keep sending it. On the spare Teensy 4.1 the bootloader took blocks 0 and 1 at once, then refused
// writes for over 5 s while it erased; later blocks are sometimes refused for ~20 ms. A header of FF FF FF reboots
// into the new firmware.

export const BLOCK = 1024;
export const HALFKAY = { vendorId: 0x16C0, productId: 0x0478 };
export const MAX_IMAGE = 8126464;                 // a Teensy 4.1's program flash (8 MB less the EEPROM and recovery)
const ERASE_BLOCKS = 8;                           // blocks that may wait for the erase (up to a minute each)

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function send(dev, report, ms, retryMs) {
  const until = Date.now() + ms;
  for (;;) {
    try { await dev.sendReport(0, report); return; } catch (e) {
      if (Date.now() > until) throw new Error(`the bootloader stopped answering (${e.message || e})`);
      await sleep(retryMs);
    }
  }
}

/**
 * Write `image` (the flash image from 0x60000000) block by block, every block, 0xFF ones too, then reboot.
 * `dev` has sendReport(reportId, data) (a WebHID HIDDevice, opened).
 */
export async function flashImage(dev, image, { onProgress = () => {}, retryMs = 10, signal } = {}) {
  if (image.length > MAX_IMAGE) throw new Error('the image is too big for a Teensy 4.1');
  const blocks = Math.ceil(image.length / BLOCK);
  const report = new Uint8Array(BLOCK + 64);
  for (let k = 0; k < blocks; k++) {
    if (signal?.aborted) throw new Error('stopped');
    const at = k * BLOCK;
    report.fill(0);
    report[0] = at & 255; report[1] = (at >> 8) & 255; report[2] = (at >> 16) & 255;
    report.fill(0xFF, 64);
    report.set(image.subarray(at, Math.min(at + BLOCK, image.length)), 64);
    // the bootloader takes the first two blocks, then erases (on the spare Teensy: more than 5 s, measured)
    await send(dev, report, k < ERASE_BLOCKS ? 60000 : 5000, retryMs);
    onProgress((k + 1) / (blocks + 1), k + 1 < ERASE_BLOCKS ? 'erasing' : 'writing');
  }
  report.fill(0); report[0] = report[1] = report[2] = 0xFF;
  try { await dev.sendReport(0, report); } catch { /* it's rebooting */ }
  onProgress(1);
}

// ---- getting to the bootloader, in a browser ----
export const hidSupported = () => typeof navigator !== 'undefined' && 'hid' in navigator;

/** A bootloader this page may already use (allowed before), or null. */
export async function knownBootloader() {
  if (!hidSupported()) return null;
  const list = await navigator.hid.getDevices();
  return list.find(d => d.vendorId === HALFKAY.vendorId && d.productId === HALFKAY.productId) || null;
}

/** Ask the user to pick the bootloader in the browser's chooser (needs a click). */
export async function chooseBootloader() {
  const [d] = await navigator.hid.requestDevice({ filters: [HALFKAY] });
  return d || null;
}

/** Wait until a bootloader the page may use appears (after a reboot into it). */
export async function waitForBootloader(ms = 8000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const d = await knownBootloader();
    if (d) return d;
    await sleep(150);
  }
  return null;
}

/** Open a HIDDevice for flashImage. */
export async function openBootloader(d) {
  if (!d.opened) await d.open();
  return d;
}

/**
 * Restart a running M8 into its bootloader: Teensyduino reboots into HalfKay when its USB serial is set to
 * 134 baud (what TyUploader does). `port` is a Web Serial port, closed.
 */
export async function rebootToBootloader(port) {
  try {
    await port.open({ baudRate: 134 });
    await sleep(250);
  } finally {
    try { await port.close(); } catch { /* gone already: it's rebooting */ }
  }
}
