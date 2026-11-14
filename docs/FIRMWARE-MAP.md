# M8 firmware map (6.6.2A, Model:02)

A rough but complete picture of the whole 2 MB image: what is where, what runs when, and how the pieces
connect. Built statically (nothing here has run on hardware) with the `dirtyloader.re` tools listed at the end.
Detail docs: [hooks/MAPPING.md](hooks/MAPPING.md) (backlog), [hooks/SITES.md](hooks/SITES.md) (hook sites),
[hooks/static-m8-ui.md](hooks/static-m8-ui.md), [hooks/static-m8-loop.md](hooks/static-m8-loop.md),
[hooks/static-m8-fxcmd.md](hooks/static-m8-fxcmd.md), [hooks/static-m8-params.md](hooks/static-m8-params.md),
[hooks/static-m8-switches.md](hooks/static-m8-switches.md).

Addresses: **load** = where the bytes sit in the flash image (what a mod patches; file offset = load −
`0x60000000` + `0x200`); **run** = where the CPU sees them. They differ for ITCM code and `.data`.

## 1. The runtime memory map — read this first

The startup routine (`0x60001430`) copies two images out of flash, so not everything executes or is addressed
where it sits:

| image | load (flash) | run | size |
|---|---|---|---|
| **ITCM code** (`FASTRUN`) | `0x60001680..0x6002CF50` | **`0x00000000..0x0002B8D0`** | 174 KB |
| **`.data` + `.rodata`** | `0x601DE020..0x601EA2E0` | **`0x20000000..0x2000C2C0`** (DTCM) | 49 KB |

- FlexRAM (`GPR17 = 0xAAAAAFFF`): **ITCM 192 KB** (≈18 KB free above `0x2B8D0`), **DTCM 320 KB** (stack top
  `0x20050000`). OCRAM `0x20200000` (512 KB) holds `DMAMEM` buffers.
- RAM vector table at **`0x2000C000`** (176 entries, filled at boot with `unused_interrupt_vector`
  `0x600AE5FC`; real handlers attached at runtime).
- Consequences that cost weeks before they were understood:
  - **Teensy puts `.rodata` in `.data`.** Vtables, parameter labels and most strings live in DTCM and are
    referenced *only* by `0x2000xxxx` addresses — the old "indirection wall" around the parameter labels was
    this relocation (`0x601E4214` in flash = `0x200061F4` at run time).
  - **ITCM code cannot `bl` to a flash cave.** From `0x0002xxxx` the Core's cave at `0x60000200` is far beyond
    the ±16 MB `bl` range. Hooks inside ITCM code (the sequencer, the audio graph) need a long veneer
    (`ldr.w pc,[pc,#-0]` + literal, as the linker itself uses) or code placed in free ITCM.
  - Cross-segment calls go through **251 linker veneers**: 125 flash→ITCM at the end of `.text`
    (`0x600B4xxx`), 126 ITCM→flash at the end of the ITCM image (`0x6002CBxx`).

## 2. Layout of the image (load addresses)

| load range | size | contents |
|---|---|---|
| `0x60000000..0x60001000` | 4 KB | FlexSPI config block; **`0x60000200..0x60001000` is the 3.5 KB cave the Core uses** |
| `0x60001000..0x60001680` | 1.6 KB | IVT + boot data, a 980 B cave, `ResetHandler` `0x60001648`, startup `0x60001430` |
| `0x60001680..0x6002CF50` | 174 KB | **ITCM image** — audio DSP, sequencer, audio/SD/USB interrupt code (§4) |
| `0x6002CF50..0x600B5000` | ~520 KB | **flash-resident code** — UI, instruments, files, USB stack, libraries (§5) |
| `0x600B5000..0x600CE800` | ~100 KB | parameter descriptor tables, float32 tables, engine tables (chords, scales) |
| `0x600CE800..0x601C2000` | ~950 KB | **oscillator / wavetable banks**: ~370 KB smooth 8-bit tables, ~340 KB 8-bit and ~145 KB 16-bit audio-like data; not compressed; no direct code references (indexed by computed offset) |
| `0x601C2000..0x601DE000` | ~110 KB | string pools (UI text, help, FX command names `0x601D6FD8`), the WAVSYNTH parameter table `0x601C2FBC`, **font / bitmap data** `0x601D9ED8..0x601DD800` (read by the display driver) |
| `0x601DE020..0x601EA2E0` | 49 KB | **`.data` image** → DTCM: vtables (`0x601DF4B4..0x601E12xx`), parameter labels (`0x601E3C00..0x601E5E00`), the RAM vector table slot |
| `0x601EA2E0..0x601EB000` | 3 KB | zeros (the HAB `csf` points here; unused) — a 3 KB cave |

By content: ~800 KB code, ~1 MB data/tables, ~117 KB text, 2916 functions found (442 in ITCM).

## 3. What runs when

```
reset → ResetHandler 0x60001648 → startup 0x60001430 (copy ITCM + .data, clear .bss, vectors, clocks)
      → main 0x600AE04C:  setup() 0x60082374;  while (1) { loop() 0x60081BD4;  yield() }

loop()  — the UI thread, a cooperative scheduler behind timing gates
  ├─ ~5 ms   0x60081A90  key scan / service group (GPIO7/8 reads 0x6007C9E4, ...)
  ├─ always  0x600A5E60  touch / gesture engine → per-view touch handlers
  ├─ always  0x60062944, watchdog kick 0x60081958
  └─ ~10 ms  UI-frame gate 0x6008196C →  input router 0x6004C6C8 → current view vtable +0x08
                                       →  frame refresh 0x6004B514 (~15 ms) → display SPI (LPSPI4) 0x6008D920

IRQ 70 (software, priority 0xD0) — the audio thread, once per audio block
  software_isr 0x2929C (AudioStream::update_all): for each node in the list → node->vtable[0]() = update()
  ├─ sequencer clock node   0x22720  double-precision phase accumulator → ticks (sample-accurate tempo)
  │     → row fire / note trigger 0x24DE0 → FX columns 0..2 via 0x24854 (72-case, cmds 0x00..0x47)
  │     → per-tick slot scan 0x28424 → dispatch 0x27BF0 → executor 0x27124 (78-case) ; ratchet 0x27080
  ├─ instrument voice nodes (one class per engine, below)
  ├─ ~15 mix / send / master-chain nodes built by 0x6009A9F4
  └─ I2S output node update 0x1F8F0 → SAI1 DMA (ISR 0x1EA9C)
```

The **sequencer runs inside the audio interrupt**, as an audio-graph node, which is why it was never reachable
from `loop()`. UI code that touches audio state brackets it with `AudioNoInterrupts()`/`AudioInterrupts()`
(writes to NVIC `ICER[2]`/`ISER[2]` bit `0x40` — seen in ~105 functions).

## 4. The ITCM image (run `0x00000000..0x0002B8D0`)

| run | what | evidence |
|---|---|---|
| `0x0000..~0x1A000` | **audio DSP**: the `update()` of ~30 `AudioStream` nodes — voices, effects, mixing | FPU-dense; vtable slot 0 of the node classes |
| `0x18D14` | clock configuration (CCM, 2.9 KB) | CCM refs |
| `0x1BE04` | `AudioStream::update_setup` — registers IRQ 70, prio `0xD0` | RAM-vector write to slot 86 |
| `0x1EA9C..0x226D4` | Teensy Audio **I2S out/in** + **DMA ISRs** (SAI1, eDMA, DMAMUX) | peripheral refs |
| `0x22720..0x28C00` | **sequencer**: clock node, row fire, FX applier/executor, track/phrase players (38-slot classes `0x601DFB1C`, `0x601E03C0`, `0x601E058C`) | decompiles, call graph |
| `0x2929C` | `software_isr` (audio `update_all`) ; `0x29300` PendSV ; `usb_isr` just after | decompile, startup literals |
| `0x29D34..` | FLEXSPI flash writes (EEPROM emulation) | FLEXSPI refs |
| `0x2A088..0x2B310` | **SD card** (USDHC1, SdFat SDIO) — a 26-slot card class `0x601E1220`; IRQ 110 | USDHC1 refs |

### Audio-graph nodes (`update()` in ITCM)

| node | `update()` | size / FPU insns | owner (constructor) | conf |
|---|---|---|---|---|
| sequencer clock | `0x22720` | 402 B / 44 | graph builder `0x6009A9F4` | S1 |
| HYPERSYNTH voice | `0x0F3FC` | **9.1 KB / 2038** | `0x60040114` (HYPERSYNTH source span) | S3 |
| SAMPLER voice | `0x15144` | 5.9 KB / 756 | `0x60046240` | S3 |
| FMSYNTH voice | `0x0D990` | 2.9 KB / 514 | `0x6003F6B8` | S3 |
| WAVSYNTH voice | `0x18574` | 1.5 KB / 193 | `0x60047018` | S3 |
| MACROSYNTH voice | `0x122CC` | 0.8 KB / 106 | `0x6004530C` | S3 |
| EXTERNAL input? | `0x09328` | 3.3 KB / 561 | `0x6009CD94` | S3 |
| effect-like nodes | `0x02B80`, `0x08CD8` (1.4 KB/226), `0x0AEB0` | | files sorting before "external" (`0x6003BA48..0x6003D960`) | S3 |
| mix / send / master chain | `0x061F4` (3.1 KB/594), `0x070D8`, `0x0AF20`, `0x05E20`, `0x053AC`, `0x05AC0`, `0x05740`, `0x20B08`, `0x228C8`, `0x1FB44`, `0x1E9C8`, `0x22510`, `0x037D4`, `0x03760` | | graph builder `0x6009A9F4` | S3 |
| USB audio in/out? | `0x1FE64`, `0x203B8`, `0x041A8` (4.6 KB/872), `0x05C50` | | `0x6009990C..0x60099B4C` (USB region) | S3 |
| I2S output | `0x1F8F0` | 308 B / 0 | `0x60021130` (next to the SAI code) | S2 |

Engine ownership comes from the linker placing each engine's source in name order (EXTERNAL `0x6003E270` <
FMSYNTH `0x6003F270` < HYPERSYNTH `0x6003FBD8` < MACROSYNTH `0x60044DC0` < MIDI OUT `0x6004552C` < SAMPLER
`0x60046B38` < WAVSYNTH `0x6004713C`) and each voice constructor falling in one span; MIDI OUT, correctly, owns
no audio node.

## 5. Flash code (load `0x6002CF50..0x600B5000`)

| load range | subsystem | landmarks |
|---|---|---|
| `0x6002CF50..0x60034000` | **text rendering** | glyph renderers `0x6002E2A8`, `0x6002FDEC` (ASCII switch), text draw `0x60030ECC`, number formatting |
| `0x60034000..0x6003BA00` | system odds and ends | USB reset, `/System/HPPDisable.txt`, DSP helpers |
| `0x6003BA00..0x60048000` | **instrument engines** (UI / parameter side, one source file per engine, alphabetical) | voice constructors; parameter value text (`:%i (RELATIVE)`, `CHORD VOICE:%i`) |
| `0x60048000..0x60078000` | **views** (31 screen classes) | display refresh `0x6004B514`, `set_view` `0x6004C13C`, input router `0x6004C6C8`; mixer (`MIX LIM DJF SPEAKER VOL`), project/file browser (`.m8s`, `/Backup/`), sample editor (`TEMP1.wav`, `NOTHING TO SLICE`), `.m8n`/`.m8t` screens |
| `0x60078000..0x60080000` | **system / hardware UI** | buttons & LEDs (GPIO6–9 `0x6007B170..0x6007CCE4`, button IRQ 157), power hold, `M8VERSION`, note names, backlight PWM `0x600787A4`, value formatter `0x600785C0` |
| `0x60080000..0x60084000` | **main loop & setup** | `loop` `0x60081BD4`, `setup` `0x60082374`, watchdog `0x60081958`, WAV file I/O (`RIFF`/`WAVE`) |
| `0x60084000..0x6008C000` | **song model & editing** | `OUT OF EMPTY CHAINS!`, `OUT OF EMPTY PHRASES!`, transpose, MIDI map |
| `0x6008C000..0x60090000` | FX command names, **display SPI driver** | FX name lookup `0x6008C4A4`, LPSPI4 `0x6008D920`, metronome |
| `0x60090000..0x60098000` | clocks, cache, RTC (SNVS) | `setup`-time configuration |
| `0x60098000..0x600A8000` | **USB device, audio graph, instrument base, touch** | USB setup requests `0x600992B8`, graph builder `0x6009A9F4`, instrument base methods `0x6009B9xx` (parameter interface `+0x88/+0x90/+0x94`), instrument factory (type names), touch engine `0x600A5E60`, Launchpad Pro support, NONE instrument |
| `0x600A8000..0x600B0000` | audio I/O setup, **SD filesystem (exFAT)**, USB serial/MIDI, `main` `0x600AE04C` | SAI1 `0x600A8114`, ADC `0x600AD7E0`, PIT `0x600AD41C` |
| `0x600B0000..0x600B5000` | **Teensy core + newlib** | SysTick `0x600B01E0`, `attachInterrupt` `0x600B03E0`, malloc/`dtoa` (`Balloc`), `assert`; flash→ITCM veneers |

## 6. Interrupts (attached at run time)

| IRQ | handler / attached by | role |
|---|---|---|
| 70 (software) | `0x2929C` ← `0x1BE04` | **audio update** (`update_all`) — runs the sequencer and the DSP graph |
| eDMA channels | `0x1EA9C` ← I2S `begin()` (`0x1ECE0` out, `0x226D4` in) | audio I/O buffer swaps |
| 110 (USDHC1) | ← `0x2A25C` | SD card |
| 113 (USB1) | `usb_isr` (ITCM, after PendSV) | USB device |
| 157 (GPIO6–9) | ← `0x6007B58C` | **buttons** |
| 92 (WDOG1) | ← `0x600818D4` | watchdog |
| PendSV / SysTick | `0x29300` / `0x600B01E0` | EventResponder / millis |

## 7. Peripherals → drivers

| peripheral | role | functions (load) |
|---|---|---|
| SAI1 + eDMA + DMAMUX | audio codec I2S in/out | `0x6002011C..0x60023D54` (ITCM), `0x600A8114` |
| USDHC1 | SD card | `0x6002B708..0x6002BCD4` (ITCM) |
| USB1 / USBPHY | USB device (serial, MIDI, audio) | `0x6002A984` (ITCM), `0x60096DCC`, `0x600992B8`, `0x600AE84C..` |
| LPSPI4 | **display** | `0x6008D920` |
| GPIO6–9 | buttons, LEDs, power | `0x6007B170..0x6007CCE4`, `0x600895F8` |
| FLEXSPI | flash writes | `0x6002B3B4..0x6002B558` (ITCM) |
| FlexPWM / QuadTimer | backlight / LED PWM | `0x600787A4`, `0x600AE3B0` |
| ADC1/2, PIT, SNVS, WDOG1 | analog reads, interval timer, RTC, watchdog | `0x600AD7E0`, `0x600AD41C`, `0x60094C08`, `0x60081958` |
| CCM / CCM_ANALOG | clocks, PLLs (incl. the audio PLL) | `0x6001A394` (ITCM), `0x60090320`, `0x60090A20` |

No LPUART (DIN/TRS MIDI) or LPI2C (codec control) driver was matched by constant addresses yet; they are
probably reached through peripheral pointers held in objects (Teensy's `HardwareSerial`/`Wire` style).

## 8. Classes (92 vtables)

| class family | vtables | interface |
|---|---|---|
| **View** (screens) | 26 × 8 slots, 5 × 32 slots | `+0x00` enter, `+0x08` input action, `+0x0C/+0x10` view-specific, `+0x14` leave, `+0x18/+0x1C` queries |
| **Instrument** (7 engines + NONE) | WAVSYNTH `0x601DFE18`, MACROSYNTH `0x601E0220`, SAMPLER `0x601E07EC`, MIDI OUT `0x601DFBBC`, FMSYNTH `0x601DF97C`, HYPERSYNTH `0x601E0058`, EXTERNAL `0x601E0A14` (102–109 slots); NONE `0x601E0E34` | shared parameter interface `+0x88/+0x90/+0x94`; FX-command name `+0xA4`, count `+0xD4`, value text `+0xC8` |
| other parameter objects | 4 × 46 slots | same base — likely FX / mixer objects |
| **AudioStream nodes** | ~30 × 1–4 slots | slot 0 = `update()` in ITCM (§4) |
| track / phrase players | 3 × 38 slots | methods in the ITCM sequencer region |
| SD card | 1 × 26 slots (`0x601E1220`) | all ITCM |

## 9. Data model

- **Parameters**: 8 descriptor tables, 254 parameters, 28-byte records (id, name, label, 3-char code, help,
  flags, min, max, field offset) — one per engine, plus the modulators and the sampler/project settings.
  See [hooks/static-m8-params.md](hooks/static-m8-params.md). Every engine ends with the same block (FILTER,
  AMP, LIMIT, PAN, DRY, **MODFX/DELAY/REVERB send**), so the sends are ordinary parameters with known offsets.
- **Modulators**: 6 types (AHD, ADSR, DRUM env, LFO, TRIG env, TRACKING), each slot with TYPE, **DEST (byte
  `+0x02`)**, AMOUNT (`+0x04`) and type-specific fields.
- **FX commands**: 78 global (`0x00..0x4D`) + instrument commands (`0x80|n`, via the instrument vtable).
- **Views**: 30 ids (`0x00..0x1D`, 7 unused), current at `ui+0x15`.

## 10. Libraries recognised

Teensy 4 core (startup, `yield`/EventResponder, SysTick, USB device, `attachInterrupt`), **Teensy Audio**
(`AudioStream` graph, I2S, `AudioNoInterrupts`), **SdFat** (SDIO driver, exFAT), **newlib** (`printf`/`dtoa`,
`malloc`, `assert`; built by a Jenkins GNU toolchain). The synth engines are Dirtywave's own classes; the
MACROSYNTH and wavetable data are consistent with Braids-style oscillator tables but that is not confirmed.

## 11. What is still rough

- Which mix/master node is which (reverb, delay, MODFX, EQ, limiter, OTT, DJ filter, scope) — the KAOSS mod's
  targets. One decompile pass over the ~15 graph-builder nodes would settle it.
- The engine↔voice mapping (S3, by source order) and the "USB audio" reading of the `0x60099xxx` nodes.
- The 950 KB oscillator data: which bank belongs to which engine (reached by computed offsets).
- LPUART/LPI2C users (MIDI DIN/TRS, codec control) — not matched by constant address.
- Exactly which view vtable slot draws (`+0x0C` vs `+0x10`).

## How this map was made (and how to redo it for a new firmware)

```
python -m dirtyloader.re.memmap   <stock.bin>          # runtime memory map from the startup copies
python -m dirtyloader.re.layout   <stock.bin>          # code / text / tables / fill regions
python -m dirtyloader.re.switches <stock.bin>          # every tbb/tbh switch, bound + bias
python -m dirtyloader.re.vtables  <stock.bin>          # C++ class hierarchy (flash + ITCM methods)
python -m dirtyloader.re.params   <stock.bin>          # parameter descriptor tables
python -m dirtyloader.re.ghidra_map <stock.bin> <work> # ONE Ghidra pass, runtime memory map, seeded, saved
python -m dirtyloader.re.fwmap    <stock.bin> <work>/fwmap.json   # tag + label the whole image offline
python -m dirtyloader.re.ghidra_map decompile <work> <addr...>    # cheap follow-ups on the saved project
```

The byte-level tools take seconds; the single Ghidra pass about a minute; decompiles from the saved project a
second each. The method that made it fast: get the **memory map** right first (ITCM, `.data`), seed functions
from **vtables, veneers and code pointers**, analyse **once**, and answer questions offline from the export.
