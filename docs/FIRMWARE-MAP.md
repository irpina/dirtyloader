# M8 firmware map (6.6.2A, Model:02)

A rough but complete picture of the whole 2 MB image: what is where, what runs when, and how the pieces
connect. Built statically (nothing here has run on hardware) with the `dirtyloader.re` tools listed at the end.
Detail docs: [hooks/MAPPING.md](hooks/MAPPING.md) (backlog), [hooks/SITES.md](hooks/SITES.md) (hook sites),
[hooks/static-m8-ui.md](hooks/static-m8-ui.md), [hooks/static-m8-loop.md](hooks/static-m8-loop.md),
[hooks/static-m8-fxcmd.md](hooks/static-m8-fxcmd.md), [hooks/static-m8-params.md](hooks/static-m8-params.md),
[hooks/static-m8-song.md](hooks/static-m8-song.md), and the hook bus built on all of it:
[CORE-EVENTS.md](CORE-EVENTS.md),
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
| `0x600CE800..0x601C2000` | ~950 KB | **oscillator / wavetable banks**: ~370 KB smooth 8-bit tables, ~340 KB 8-bit and ~145 KB 16-bit audio-like data; not compressed; no direct code references (indexed by computed offset). The region starts right after **WAVSYNTH's shape-name list** (`0x600CE388..0x600CE79F`: 9 basic shapes, then 60 wavetables `OSC:` ×17, `BNK:` ×7, `HRM:` ×13, `EFX:` ×21, `VOX:` ×2). Only WAVSYNTH code (`0x6004712C`) references that list, so the first, smooth block is WAVSYNTH's 60 wavetables (S3). The rest is unassigned. |
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
  └─ outputs: USB audio node 0x1F8F0, I2S output node 0x1E9C8 → SAI1 DMA (ISR 0x1EA9C)
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

### The audio graph (`update()` in ITCM)

Every global object was mapped to its class (`python -m dirtyloader.re.objects`), so node **instance counts**
are known, and they expose the per-track design:

| instances | `update()` | size / FPU insns | reading | conf |
|---|---|---|---|---|
| **32** | `0x037D4` | 266 B / 0 | 4-input integer mixers (`AudioMixer4`-style, 4 inputs from the base ctor) — **8 tracks × 4 buses** (dry, MODFX, delay, reverb sends) | S2 |
| **24** | `0x1FE64` | 1.3 KB / 167 | **8 tracks × 3**: the per-track 3-band EQ (there is an EQ screen) | S3 |
| **8** | `0x203B8` | 1.8 KB / 203 | **per-track channel strip** (filter, amp, limit, pan) | S3 |
| 1 each | `0x0F3FC` HYPERSYNTH (9.1 KB / 2038), `0x15144` SAMPLER (5.9 KB / 756), `0x0D990` FMSYNTH (2.9 KB / 514), `0x18574` WAVSYNTH (1.5 KB / 193), `0x122CC` MACROSYNTH, `0x6003EA2C` EXTERNAL (flash) | | **one node per engine type** — matched by constructor source span | S3 |
| 1 | `0x22720` | 402 B / 44 | **sequencer clock** | S1 |
| 1 | `0x1F8F0` (obj `0x20010620`) | 308 B / 0 | **USB audio output**: 24 inputs (the main pair from `0x2001D854`, then MFX, delay and reverb pairs on 18–23). *Corrected:* first read as the I2S output. Walked on a Model:02 through the nodes' destination lists | S1 |
| 1 | `0x1E9C8` (obj `0x2001D2CC`) | | **I2S output**: the end of soft clip `0x2001DA34` → `0x2001DA7C` → `0x20037A90` → `0x2001BE9C` | S1 |
| 1 | `0x09328` (obj `0x20021F18`) | 3.3 KB / 561 | **REVERB**: the effects setter writes size, decay, mod depth, mod freq, width and shimmer to its `+0x98..+0xB0` | S1 |
| 1 | `0x08CD8` (obj `0x2001DD14`) | | **MODFX**: MOD TYPE (chorus/phaser/flanger) lands at `+0x30`; depth/freq/width are globals at `0x20021BD4..0x20021BE4` | S2 |
| 1 + 1 | `0x05C50` (obj `0x2001BF40`), `0x070D8` (obj `0x20021D4C`) | | **DELAY**: feedback and stereo width go to these two nodes; the delay time is set through the clock object (`0x6009A5F0`/`0x6009A69C`, next to `setTempo`), so the time is tempo-synced | S2 |
| 1 | `0x0AEB0` (obj `0x2000C780`) | 112 B / 0 (calls `0x0A068`) | **OTT** (three-band compressor). Its amount setter `0x6003DB74` treats 0 as bypass (`+0x35`/`+0x40` flags). TIME (`0x6003D628`) sets an attack/release pair for each of three bands (`+0x88/+0x8C`, `+0xC8/+0xCC`, …). COLOR (`0x6003D2DC`) is a bipolar crossover tilt. Effects `+1A` TIME, `+1B` COLOR and `+1F` amount, edited on the LIMITER SCOPE screen. *Corrected:* first read as the DJ filter | S2 |
| 2 | `0x041A8` (objs `0x20037840`, `0x20037C9C`) | 4.6 KB / 872 | receive the **MODFX→reverb and delay→reverb send** levels (effects `+06`, `+10`) | S3 |
| 1 | `0x0AF20` (obj `0x2001D6DC`) | 952 B / 156 | **LIMITER**: its attack setter `0x6003A5FC` and release setter `0x6003A650` write `+0x80..+0x94`; release 0 sets the `+0xA8` flag (`LIM RELEASE:AUTO`). Called from the MIXER and LIMITER SCOPE screens | S1 |
| 1 | `0x1FB44` (obj `0x2001D854`) | 400 B / 21 | the master-bus object that holds the **DJ FILTER** parameters at `+0x164` (`0x2001D9B8`): TYPE 0–2 (LP/HP, LP/BS, BS/HP), a 0x80-centred cutoff and resonance, set and smoothed by `0x60099BB4`. It also holds the **SOFT CLIP** block at `+0x1E0` (`0x2001DA34`): on/off at `+0x44` (`0x6003A6B8`), level via `0x60099D88`. Its `update()` is mostly a copy (`0x1BA1C`); the filter maths runs in the helpers `0x001A4`/`0x001B0` that the effect nodes call | S2 |
| 1 | `0x228C8` (obj `0x2001D548`) | 700 B / 36 | the **scope tap**: the LIMITER SCOPE screen reads it 35 times (`+0x78..+0x15C`) for the MIX / LIMITER scopes | S2 |
| 1 each | `0x061F4` (3.1 KB), `0x05E20`, `0x053AC`, `0x20B08` | | not yet named: internal stages (the bus EQs and the input path's processing are what is left to place) | — |
| 1 each | `0x1E9C8`, `0x22510` | < 200 B / 0 | receive-only taps; `0x22510` is the **audio-input** path (`USB INPUT DISABLED`, `DUAL MONO INPUT MODE`) | S3 |
| 1 | `0x600A5C24` (flash) | 26 B | the **USB-audio** interface object (84 users, USB-input settings) | S3 |

How the effects were named: the EFFECT SETTINGS screen applies a field through one setter, `0x60050ADC`.
That setter's `switch(field)` writes each field's value, under `AudioNoInterrupts()`, straight into a node
object. Each object maps to its class, and each class to its `update()` (`re.objects`). *Withdrawn:* `0x09328` as
the sample-audition player.

- The block-I/O helpers are `0x1BD50` (`receiveReadOnly`, called by 22 nodes), `0x1BCF4` (`release`) and
  `0x1BDBC`/`0x1BD0C` (`allocate`/`transmit`); the AudioStream base constructor is `0x600B4C78`
  `(this, num_inputs, input_queue)`.
- **The engine voices and the clock call none of the block helpers**: they don't pass `AudioStream` blocks;
  most likely they render into per-track buffers that the 8 channel strips pick up.
- Engine ownership comes from the linker placing each engine's source in name order (EXTERNAL `0x6003E270` <
  FMSYNTH `0x6003F270` < HYPERSYNTH `0x6003FBD8` < MACROSYNTH `0x60044DC0` < MIDI OUT `0x6004552C` < SAMPLER
  `0x60046B38` < WAVSYNTH `0x6004713C`); MIDI OUT, correctly, owns no audio node.
- *Withdrawn:* the earlier "USB audio" reading of `0x1FE64`/`0x203B8` (they are ×24 and ×8 per-track nodes) and
  "EXTERNAL input" for `0x09328` (EXTERNAL's voice is `0x6003EA2C`).
- To confirm the S2/S3 effect readings **on hardware**: `software_isr` keeps a per-node CPU-cycle count, so
  toggling an effect and watching which node's count moves checks each reading in minutes. (The graph is wired
  at run time in loops over the node arrays, so the edges are not constants a static pass can read.)

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
| `0x60098000..0x600A8000` | **USB device, audio graph, instrument base, touch, controllers** | USB setup requests `0x600992B8`, graph builder `0x6009A9F4`, instrument / receiver base methods `0x6009B9xx`, per-engine instrument methods `0x6009C..0x600A3` (destination counts, …), static initializers `0x600A4694..0x600A6500` (screens, receivers), touch engine `0x600A5E60`, Launchpad Pro, NONE instrument |
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

| LPUART6 / LPUART2 / LPUART7 | **serial ports** (Teensy `Serial1`/`Serial3`/`Serial7` — MIDI TRS among them) | init `0x600895F8`; `0x600A6EC8`, `0x600AD6B8` |
| LPI2C (`Wire`) | **I²C** for three devices: touch controller, audio codec, buttons (I/O expander) | `0x600A79FC`/`0x600A7A80` (next to touch), `0x600A8AFC`/`0x600A8B20` (next to SAI setup), `0x6007B0A0`/`0x6007B58C` (next to the button IRQ) |

The serial and I²C drivers reach the peripheral through Teensy's hardware-descriptor structs in `.data`
(LPUART6 `0x2000A980`, LPUART2 `0x2000A9E0`, LPUART7 `0x2000AA40`, LPI2C1 `0x2000AAA0`, LPSPI4 `0x2000A870` —
only ports actually used are linked in), not by constant addresses, which is why the first pass missed them.
The display SPI driver is partly in ITCM too (`0x600222E8..0x600233B0`).

## 8. Classes (92 vtables)

| class family | vtables | interface |
|---|---|---|
| **View** (screens) | 26 × 8 slots, 5 × 32 slots | `+0x00` enter, `+0x08` input action, `+0x0C/+0x10` view-specific, `+0x14` leave, `+0x18/+0x1C` queries |
| **Instrument** (7 engines) | WAVSYNTH `0x601DFE18`, MACROSYNTH `0x601E0220`, SAMPLER `0x601E07EC`, MIDI OUT `0x601DFBBC`, FMSYNTH `0x601DF97C`, HYPERSYNTH `0x601E0058`, EXTERNAL `0x601E0A14` (102–109 slots) | the parameter interface (`+0xBC` descriptor, `+0x0F8`/`+0x104` LFO destinations, `+0x108` default, `+0x10C` value — [hooks/static-m8-params.md](hooks/static-m8-params.md)); FX-command name `+0xA4`, count `+0xD4`, value text `+0xC8` |
| **MIDI / controller receivers** | NONE `0x601E0E34`, Launchpad Pro `0x601E0D20`, three MIDI-input/record modes (`0x601E0F18`, `0x601E103C`, `0x601E10FC`) — 46 slots | the shared event interface the instruments also derive from (`+0x88/+0x90/+0x94` — *corrected*: first read as a parameter interface) |
| **AudioStream nodes** | ~30 classes, 1–4 slots, ~105 instances | slot 0 = `update()` in ITCM (§4) |
| **MIDI handlers** | 3 × 38 slots (objects `0x20013E10`, `0x20013ECC`, `0x200177D4`) | a 38-method MIDI-message interface; `0x20013ECC` is MIDI input with MIDI-map support (`ASSIGNED MIDIMAP`), built next to the `Serial1` user `0x600A6EC8` |
| SD card | 1 × 26 slots (`0x601E1220`) | all ITCM |

**Instruments are type singletons.** There is exactly one object per engine (SAMPLER `0x2000EAA0`, WAVSYNTH
`0x20037DB8`, MACROSYNTH `0x20038DE4`, MIDI OUT `0x2003AA94`, FMSYNTH `0x2003B97C`, HYPERSYNTH `0x2003DAAC`,
EXTERNAL `0x2003EC88`, NONE `0x20014064`): the 128 instruments of a song are data records, and the singleton
for their type interprets them — matching one audio node per engine.

### Screens (`set_view` ids)

All 29 ids are named. **T** = the screen's own 40 × 24 text template (`EFFECT SETTINGS …`) is loaded by one
of its vtable methods, or by code next to them in the same source file. **D** = dialogs without a template,
named from their input handler.

| id | screen | id | screen | id | screen |
|---|---|---|---|---|---|
| `0x00` | **SONG** (T; live mode, bookmarks) | `0x0A` | file browser | `0x14` | hardware settings page (T: `BOOT MENU`, `HP PROTECTION`, `DISABLE CHARGING`, `KEY DELAY:REPEAT`, `SD CARD TEST`) |
| `0x01` | **GROOVE** (T) | `0x0B` | **EFFECT SETTINGS** (T) | `0x15` | create directory (T: `CREATE DIRECTORY`) |
| `0x02` | **CHAIN** (T) | `0x0C` | OK/CANCEL confirm dialog (D: left/right cursor; select returns to the caller, `+0x0D` = OK) | `0x16` | **INSTRUMENT MODS** (T) |
| `0x03` | **PHRASE** (T) | `0x0D` | **MIXER** (T) | `0x17` | **TIME STATS** (T: play/work/powered time, file date) |
| `0x04` | **TABLE** (T) | `0x0E` | **MIDI SETTINGS** (T) | `0x18` | **INSTRUMENT POOL** (T) |
| `0x05` | **INSTRUMENT** (T) | `0x0F` | **MIDI MAPPING** (T) | `0x19` | **EQ EDITOR** (T) |
| `0x06` | **PROJECT** (T) | `0x10` | **THEME SETTINGS** (T) | `0x1A` | **LIMITER SCOPE** (T: mix scope, limiter attack/release, soft clip, DJ filter) |
| `0x08` | text keyboard (T: the `{c c c …}` grid; `QWERTY>` / `ABC>`) | `0x11` | **RENDER AUDIO** (T) | `0x1B` | grid picker dialog (D: 2-D cursor, returns the cell or `0xFF` on cancel; shares the keyboard's grid code) |
| `0x09` | **FX command help** (T: `>SEQUENCER FX`, `>CURRENT INSTRUMENT`, `>INSTRUMENT MODS`, `>MIXER/EFFECTS` pages) | `0x12` | **SAMPLE RECORD** / sample editor (T; one 38 KB class, saves `.wav`) | `0x1C` | **SYSTEM SETTINGS** (T) |
| | | `0x13` | **SCALE** (T) | `0x1D` | USB disk mode (T: `USB DRIVE MODE ACTIVATED`) |

*Corrected:* `0x0B` was "MIDI mapping" (that is `0x0F`), `0x11` "name entry", `0x14` "SYSTEM SETTINGS" (that
is `0x1C`), `0x1C` "firmware update". Method: each id's singleton → its class (`re.objects`) → its vtable slots;
each template's loader → the view whose methods it sits among. For 12 ids the loader *is* one of the view's
methods; for the rest it lies within a few hundred bytes of them, in the same source file. The names also agree with the navigation groups `set_view` assigns, and with the screens
the touch engine serves.

## 9. Data model

- **Parameters**: 8 descriptor tables, 256 parameters, 28-byte records (name, label, 3-char code, help,
  flags + **default**, min, max, **UI grid slot**, **UI page**, **index**). The index is both the byte offset in
  the instrument's data record and the instrument FX-command number (`0x80|index`, mnemonic = the 3-char code),
  so **the descriptor table is also the instrument-command table**. Reached only through the instrument's
  virtual `getParamDescriptor` (`+0xBC`). See [hooks/static-m8-params.md](hooks/static-m8-params.md).
- **Instrument data record**: engine parameters at `data[0x00..]`, the **four modulator slots at
  `data[0x30..0x47]`** (6 bytes each); every engine's parameter set ends with FILTER, AMP, LIMIT, PAN, DRY and
  the **MODFX/DELAY/REVERB sends**.
- **LFO destinations**: per engine, a count (`vt+0x104`, 14–15) and a name table (`vt+0x0F8`) in `.data` —
  OFF, VOLUME, PITCH, 4 engine-specific, CUTOFF, RES, AMP, PAN, MOD AMT/RATE/BOTH/BINV. **No engine offers the
  sends** — the extended-destinations mod's exact gap. (*Corrected:* "DEST is byte `+0x02`" was a misread of
  the UI grid slot.)
- **The song** is one 109 KB object in OCRAM at **`0x2025A570`** laid out exactly like the `.m8s` file
  (RAM offset = file offset − `0x82`): grooves, 256 × 8 song rows, 255 phrases × 16 × 9 B, 255 chains, 256
  tables, **128 instruments × 215 B**, effects settings, MIDI mappings, 16 scales, 128 EQs. Accessors
  `0x600A6142` (phrase), `0x600A6130` (chain), `0x600A617E` (instrument), `0x600A6190` (EQ). Details:
  [hooks/static-m8-song.md](hooks/static-m8-song.md).
- **Transport**: the clock object `0x2000D218` — `setTempo` `0x6009A6C0`, `setPlaying` `0x6009A528`, `stop`
  `0x6009A55C`, `getTicks` `0x6009A51C`; **192 sub-ticks per beat at 44.1 kHz** (K = 192/(60·44100)); 8 track
  players at `0x2000D270` (8 × 688 B).
- **LFO apply**: each engine has a `switch(dest)` in ITCM that writes per-destination values into the voice —
  **Path B**. The switches: FMSYNTH `0x0C9D0`, HYPERSYNTH `0x0E552`, MACROSYNTH `0x1185A`, WAVSYNTH `0x171BA`,
  SAMPLER `0x1439E` plus a specialised copy at `0x12800` (used for its modulator 0), and EXTERNAL `0x0B324`.
  All six audio engines are now pinned ([hooks/static-m8-params.md](hooks/static-m8-params.md)).
- **Mixer and effects settings** live in two blocks of the song:
  - **Mixer:** `song + 0x4C + n`, accessor `0x600A611E`. It is read with field numbers 0–31 by the MIXER and
    LIMITER SCOPE screens and by `0x6008A880` (not yet read).
  - **Effects:** `song + 0x1A53C + n`, accessor `0x600A6124`. The EFFECT SETTINGS screen maps its 16 value
    fields through the table at `0x20004D04`. The fields, offsets in hex:

| field | MODFX | DELAY | REVERB |
|---|---|---|---|
| type | MOD TYPE `+1C` | | |
| mod depth : freq | `+03` : `+04` | | `+16` : `+17` |
| time L : R | | `+0C` : `+0D` | |
| feedback | | `+0E` | |
| size, decay : shimmer | | | `+14`, `+15` : `+19` |
| stereo width | `+05` | `+0F` | `+18` |
| reverb send | `+06` | `+10` | |

  - The INPUT EQ rows pick EQs `0x81`, `0x82` and `0x83`, so the song holds 4 bus EQs after its 128 user EQs.
  - The song upgrader at `0x6008B074` converts old songs' delay and reverb filter bytes (`+0A`/`+0B`,
    `+12`/`+13`) into EQ bands, and copies EQs `0x80..0x83` into `0x20..0x23`.
  - Effects bytes `+1A`/`+1B` belong to the master chain: **OTT** TIME and COLOR, with `+1F` its amount (§4). That
    is why the MIXER and LIMITER SCOPE screens read them, and the EFFECT SETTINGS screen does not show them.
  - The effects setter `0x60050ADC` also takes ids `0xC8..0xE0`. These drive the input sends (per-bus send
    functions `0x60039144` MODFX, `0x6003938C` DELAY, `0x60038DE4` REVERB, matching the MX/DE/RE columns,
    for source 8 INPUT and 9 USB). The mixer's own fields `+10..+12`, `+14..+16` and `+18..+1A` drive the
    same three functions.
- **Effects architecture** (from the mixer/effects UI): MODFX = CHORUS / PHASER / FLANGER; send effects MODFX,
  DELAY (time in steps), REVERB; **EQ banks** assignable per bus (`MIX EQ`, `MODFX EQ`, `DELAY EQ`, `REVERB EQ`);
  master chain **LIMITER (+ scope) → SOFT CLIP → DJ FILTER (LP/HP, LP/BS, BS/HP) → OTT (time, color)**.
- **FX commands**: 78 global (`0x00..0x4D`) + instrument commands (`0x80|n`, from the descriptor tables).
- **Views**: 30 ids (`0x00..0x1D`, 7 unused), current at `ui+0x15` — named in §8.

### The theme (core 0.7's THEME command, the shop's theme picker)

The **system settings** are one 0xCC-byte struct, kept in Teensyduino's EEPROM emulation: loaded at boot,
saved by `settings_save(struct)`, which writes a checksum of the first 0xC8 bytes at `+0xC8` and then
`eeprom_write_byte` only for the bytes that differ. THEME SETTINGS calls it when you leave it after an edit,
and so do eleven other places, so a change in RAM can reach the EEPROM without anyone asking (seen on the unit).

| | Headless 6.6.4A | Model:02 6.6.2A |
|---|---|---|
| settings struct | `0x2001C70C` | `0x200159C0` |
| `+0x24`: the 13 colours, R G B (`.m8t` order) | `0x2001C730` | `0x200159E4` |
| `+0x4B`: the theme name, 13 bytes | | |
| `settings_save(struct)` | `0x6009C986` | `0x600A7318` |
| `set_pal(_, index, r, g, b)`: one RGB565 entry (b on the stack; the first argument is unused) | `0x6009AF28` | `0x600A5654` |
| the palette (13 words) | `0x2000B590` | |
| `redraw(obj, 1)`: every view again, in the new palette | `0x600496B8`, obj `0x2001A4F4` | `0x6004AF18`, obj `0x200137F8` |
| apply: the colours from the struct into the palette, then the redraw | `0x60075CF0` | the loop at `0x600770EA` |
| `.m8t` load (fs, path) | `0x6007CB8C` | `0x6007F548` |
| `eeprom_read_byte` / `eeprom_write_byte` | `0x600A2640` / `0x600A26BC` | `0x600ADD94` / `0x600ADE10` |

The screen draws from the palette, not from the struct: writing the struct alone changes nothing until the
palette is set again. A `.m8t` is `M8VERSION `, four version bytes (read and ignored), then the 39 colour bytes:
53 bytes. At boot the firmware writes its nine stock themes to `/Themes` from a table at `0x601D42A4` (Model:02).

### How a cell gets its colour (core's extended theme)

The screen is a 40 × 24 grid of characters (`grid + 0x10 + row·40 + col`) with an **attribute byte** per cell beside
them (`grid + 0x3D1 + row·40 + col`). Screens write both (`0x18FAC`/headless, `0x18C24`/Model:02: text with an
attribute) or copy a template's attribute array; the refresh's draw loop (headless ITCM `0x1902A`, Model:02 `0x18B84`)
turns each attribute into a palette index and sets the text colours (grid `+0x12DE` fg, `+0x12E0` bg) before
`write(c)` (headless `0x19240` → `0x190A6`, which skips a cell whose character and colour haven't changed):

| attribute | index | |
|---|---|---|
| `.` `/` `0`…`7` | 0…9 | BACKGROUND, EMPTY, INFO, DEFAULT, VALUE, TITLES, PLAY, CURSOR, SELECTION, SCOPE |
| `8`…`C` | 1…12 | (`A` `B` `C`: the meters) |
| `5`, `6` | 7, 8 | fg and bg swapped: the cursor and selection blocks |
| `0xAE` | | skipped |
| `D`…`R` | **13…27** | past the 13-entry palette: no screen uses them |

The loop loads the palette's address from a literal in ITCM: headless run `0x190A0`, Model:02 run `0x18C1C` (both
`FW_ATTR_PAL_LIT`). Core 0.7 points it at a 28-entry table: the firmware's 13 copied in before each refresh, then 15
of its own, and writes `D`… into the cells it recolours (see LOADER.md, THEMEX). The frame refresh draws only after
32 ms (headless, last time `0x200206BC`) or 16 ms (Model:02, `0x2001B4DC`).

## 10. Libraries recognised

Teensy 4 core (startup, `yield`/EventResponder, SysTick, USB device, `attachInterrupt`), **Teensy Audio**
(`AudioStream` graph, I2S, `AudioNoInterrupts`), **SdFat** (SDIO driver, exFAT), **newlib** (`printf`/`dtoa`,
`malloc`, `assert`; built by a Jenkins GNU toolchain). The synth engines are Dirtywave's own classes; the
MACROSYNTH and wavetable data are consistent with Braids-style oscillator tables but that is not confirmed.

## 11. What is still rough

Everything below is leaf level: each subsystem, thread, class family, screen, data block and engine has a place
in the map. What remains is naming the last few nodes and data blocks, and checking S2/S3 readings on hardware.

- **Audio nodes:** the whole master chain is named: LIMITER `0x0AF20`, OTT `0x0AEB0`, and the DJ FILTER and SOFT CLIP
  blocks inside `0x2001D854`. Still unnamed are internal stages among `0x061F4`, `0x05E20`, `0x053AC`,
  `0x228C8` (read by the LIMITER SCOPE screen: the scope tap) and `0x20B08`. The per-node CPU counters on
  hardware confirm the S2 readings.
- The engine↔voice mapping is S3 (by source order).
- **Oscillator data:** the first, smooth block is WAVSYNTH's 60 named wavetables (§2). The remaining
  ~340 KB of 8-bit and ~145 KB of 16-bit data are unassigned.
  - No literal, no `movw`/`movt` pair and no `.data` table holds a bank base. The engines' render functions
    (`0x18574`, `0x122CC`, `0x0D990`) hold no region address either, so voices reach their tables through
    pointers set up at run time.
  - The `HRM:PLAITS01/02` and `VOX:BRAIDS` names suggest Mutable Instruments-derived tables (not confirmed).
  - The per-table stride of the WAVSYNTH block is not confirmed (6 KB × 60 fits the block size).
  - The next step is the WAVSYNTH setup code around `0x6004712C`, or a watchpoint on hardware.
- **Drawing has no single View slot.** The frame refresh `0x6004B514` calls only the views' `+0x18`/`+0x1C`
  queries. Each screen paints its 40 × 24 template from its own methods: `+0x10` for SONG, GROOVE, FX help,
  EFFECT SETTINGS, MIDI SETTINGS and the hardware page; `+0x0C` or `+0x14` for others. So `ev_draw` stays at
  the frame push (`0x6004B6DE`), as designed.

*Resolved since the first pass:*
- the EXTERNAL apply switch (`0x0B324`, §9)
- the effects-settings layout, including `+1A`/`+1B` (§9)
- the eight screens without strings (§8)
- the send effects and the whole master chain: REVERB, MODFX, DELAY, LIMITER, SOFT CLIP, DJ FILTER, OTT (§4)

## How this map was made (and how to redo it for a new firmware)

```
python -m dirtyloader.re.memmap   <stock.bin>          # runtime memory map from the startup copies
python -m dirtyloader.re.layout   <stock.bin>          # code / text / tables / fill regions
python -m dirtyloader.re.switches <stock.bin>          # every tbb/tbh switch, bound + bias
python -m dirtyloader.re.vtables  <stock.bin>          # C++ class hierarchy (flash + ITCM methods)
python -m dirtyloader.re.params   <stock.bin>          # parameter descriptor tables
python -m dirtyloader.re.objects  <stock.bin> <work>/fwmap.json   # every global C++ object -> its class
python -m dirtyloader.re.ghidra_map <stock.bin> <work> # ONE Ghidra pass, runtime memory map, seeded, saved
python -m dirtyloader.re.fwmap    <stock.bin> <work>/fwmap.json   # tag + label the whole image offline
python -m dirtyloader.re.ghidra_map decompile <work> <addr...>    # cheap follow-ups on the saved project
```

The byte-level tools take seconds; the single Ghidra pass about a minute; decompiles from the saved project a
second each. The method that made it fast: get the **memory map** right first (ITCM, `.data`), seed functions
from **vtables, veneers and code pointers**, analyse **once**, and answer questions offline from the export.
