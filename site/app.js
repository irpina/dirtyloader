/* dirtyloader in-browser builder.
 *
 * Loads the pure-Python dirtyloader package into Pyodide and drives it. The stock
 * firmware the visitor picks is written into Pyodide's in-memory filesystem and
 * read back by Python -- it never leaves the browser. Mods are fetched as .m8mod
 * JSON from this same site and passed in as text.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { py: null, stock: null, stockInfo: null, catalog: null };

function log(msg) {
  const el = $("log");
  el.hidden = false;
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}

async function boot() {
  try {
    state.py = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/" });
  } catch (e) {
    $("offline").hidden = false;
    $("engineVer").textContent = "engine unavailable";
    return;
  }
  const cat = await (await fetch("catalog.json", { cache: "no-store" })).json();
  state.catalog = cat;
  const zip = await (await fetch(cat.engine, { cache: "no-store" })).arrayBuffer();
  state.py.unpackArchive(zip, "zip");
  await state.py.runPythonAsync("import dirtyloader, dirtyloader.web as web");
  $("engineVer").textContent = cat.generator;
  window.dl = state;            // debug handle: inspect the engine from devtools
  renderMods(cat.mods);
  $("stock").addEventListener("change", onStock);
  $("build").addEventListener("click", onBuild);
}

function renderMods(mods) {
  const box = $("mods");
  box.innerHTML = "";
  for (const m of mods) {
    const row = document.createElement("label");
    row.className = "mod" + (m.is_core ? " locked" : "");
    const needs = m.requires.length ? ` · needs ${m.requires.join(", ")}` : "";
    const gives = m.provides.length ? ` · provides ${m.provides.join(", ")}` : "";
    row.innerHTML = `
      <input type="checkbox" data-id="${m.id}" ${m.is_core ? "disabled" : ""}>
      <div>
        <div class="title">${esc(m.title)}
          <span class="pill">${esc(m.id)} ${esc(m.version)}</span>
          <span class="pill">${esc(m.firmware || m.device)}</span>
        </div>
        <div class="desc">${esc(m.description)}${esc(needs)}${esc(gives)}</div>
      </div>`;
    box.appendChild(row);
  }
  box.addEventListener("change", refreshCoreLock);
}

/* Auto-select + lock the Core whenever any checked mod requires it. */
function refreshCoreLock() {
  const checked = selectedIds();
  const needCore = state.catalog.mods.some(
    (m) => checked.includes(m.id) && m.requires.includes("core"));
  const coreBox = document.querySelector('input[data-id="core"]');
  if (coreBox) { coreBox.checked = needCore; coreBox.disabled = true; }
}

function selectedIds() {
  return [...document.querySelectorAll(".mod input:checked")].map((c) => c.dataset.id);
}

async function onStock(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const buf = new Uint8Array(await file.arrayBuffer());
  state.stock = buf;
  state.py.FS.writeFile("/tmp/stock.bin", buf);
  let info;
  try {
    info = state.py.runPython(
      "import json; json.dumps(web.inspect_stock(open('/tmp/stock.bin','rb').read()))");
    info = JSON.parse(info);
  } catch (e) {
    showStock(`<span class="bad">Not an M8 firmware file: ${esc(String(e)).slice(0, 200)}</span>`);
    state.stock = null; $("build").disabled = true; return;
  }
  state.stockInfo = info;
  const id = info.known ? `<span class="ok">${esc(info.identity)}</span>`
                        : `<span class="warnt">unknown build</span>`;
  const valid = info.valid ? `<span class="ok">valid CRCs</span>`
                           : `<span class="bad">${esc((info.problems || []).join("; "))}</span>`;
  showStock(
    `<div class="row"><span>${file.name}</span><span class="mono">${(buf.length/1024/1024).toFixed(2)} MB</span></div>
     <div class="row"><span>identity</span><span>${id}</span></div>
     <div class="row"><span>integrity</span><span>${valid}</span></div>
     <div class="row"><span>sha256</span><span class="mono">${info.sha256.slice(0,24)}…</span></div>`);
  $("build").disabled = false;
}

function showStock(html) { const el = $("stockInfo"); el.hidden = false; el.innerHTML = html; }

async function onBuild() {
  if (!state.stock) return;
  $("build").disabled = true;
  $("log").hidden = false; $("log").textContent = "";
  $("result").hidden = true;
  const ids = selectedIds();
  if (!ids.length) { log("Pick at least one mod."); $("build").disabled = false; return; }
  try {
    log("Fetching mods: " + ids.join(", "));
    const jsons = [];
    for (const m of state.catalog.mods.filter((x) => ids.includes(x.id) || (x.is_core && coreNeeded(ids)))) {
      jsons.push(await (await fetch(m.file, { cache: "no-store" })).text());
    }
    state.py.globals.set("_mods_json", JSON.stringify(jsons));
    log("Linking " + jsons.length + " mod(s) onto stock…");
    const metaStr = await state.py.runPythonAsync(`
import json
_meta = web.build_patched(open('/tmp/stock.bin','rb').read(), json.loads(_mods_json))
_data = _meta.pop('bytes')
open('/tmp/out.bin','wb').write(_data)
json.dumps(_meta)
`);
    const meta = JSON.parse(metaStr);
    const out = state.py.FS.readFile("/tmp/out.bin");
    const url = URL.createObjectURL(new Blob([out], { type: "application/octet-stream" }));
    log("Built " + meta.name + "  (" + meta.size + " bytes, payload CRC " + meta.payload_crc + ")");
    log("Done. Flash via PROJECT > SYSTEM SETTINGS > FIRMWARE UPDATE, or TyTools.");
    $("result").hidden = false;
    $("result").innerHTML =
      `<div class="row"><span>mods</span><span>${esc(meta.mods.join(", "))}</span></div>
       <div class="row"><span>sha256</span><span class="mono">${meta.sha256.slice(0,24)}…</span></div>
       <a class="download" download="${esc(meta.name)}" href="${url}">⬇ Download ${esc(meta.name)}</a>`;
  } catch (e) {
    log("Build failed: " + String(e).split("\n").filter(Boolean).pop());
  }
  $("build").disabled = false;
}

function coreNeeded(ids) {
  return state.catalog.mods.some((m) => ids.includes(m.id) && m.requires.includes("core"));
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

boot();
