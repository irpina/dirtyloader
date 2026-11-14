# M8 firmware map (6.6.2A, Model:02)

A rough but complete picture of the whole 2 MB image: what is where, what runs when, and how the pieces
connect. Built statically (nothing here has run on hardware) with the `dirtyloader.re` tools listed at the end.
Detail docs: [hooks/MAPPING.md](hooks/MAPPING.md) (backlog), [hooks/SITES.md](hooks/SITES.md) (hook sites),
[hooks/static-m8-ui.md](hooks/static-m8-ui.md), [hooks/static-m8-loop.md](hooks/static-m8-loop.md),
[hooks/static-m8-fxcmd.md](hooks/static-m8-fxcmd.md), [hooks/static-m8-params.md](hooks/static-m8-params.md),
[hooks/static-m8-song.md](hooks/static-m8-song.md),
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
| 1 | `0x1F8F0` | 308 B / 0 | **I2S output** (receive + release only — a sink) | S2 |
| 2 | `0x041A8` | 4.6 KB / 872 | a heavy stereo pair (reverb-like) | S3 |
| 1 each | `0x09328` (3.3 KB), `0x061F4` (3.1 KB), `0x070D8`, `0x08CD8`, `0x0AF20`, `0x05E20`, `0x053AC`, `0x228C8`, `0x20B08`, `0x1FB44`, … | | send effects and master chain (MODFX, delay, reverb, EQ, limiter, OTT, DJ filter) — **not yet told apart** | — |
| 1 each | `0x1E9C8`, `0x22510` | < 200 B / 0 | receive-only taps; `0x22510` is the **audio-input** path (`USB INPUT DISABLED`, `DUAL MONO INPUT MODE`) | S3 |
| 1 | `0x600A5C24` (flash) | 26 B | the **USB-audio** interface object (84 users, USB-input settings) | S3 |
| 1 | `0x09328` | 3.3 KB / 561 | likely the **sample-audition player** (file browser: `Samples`, `Songs`, `Instruments`) | S3 |

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
- Telling the effects apart is cheapest **on hardware**: `software_isr` keeps a per-node CPU-cycle count, so
  toggling reverb / delay / MODFX and watching which node's count moves names each one in minutes. (The graph is
  wired at run time in loops over the node arrays, so the edges are not constants a static pass can read.)

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

| id | screen | id | screen | id | screen |
|---|---|---|---|---|---|
| `0x00` | **SONG** (live mode, bookmarks) | `0x0A` | file browser | `0x14` | SYSTEM SETTINGS |
| `0x01` | **GROOVE** | `0x0B` | MIDI mapping (S3) | `0x16` | INSTRUMENT MODS |
| `0x02` | **CHAIN** | `0x0D` | **MIXER** | `0x18` | instrument pool (S3) |
| `0x03` | **PHRASE** | `0x0E` | settings (MIDI?) | `0x19` | **EQ** |
| `0x04` | **TABLE** (S2) | `0x10` | THEME | `0x1C` | firmware update / template |
| `0x05` | **INSTRUMENT** | `0x11` | name entry | `0x1D` | USB disk mode |
| `0x06` | **PROJECT** | `0x12` | sample editor | | |
| | | `0x13` | SCALE | | |

Unnamed (no strings): `0x08 0x09 0x0C 0x0F 0x15 0x17 0x1A 0x1B`. Names come from each screen class's own
strings (`LIVE (SEL+LEFT TO EXIT)`, `TOTAL TICKS`, `CREATE A PHRASE TO PROCEED`, `FILL: RANDOM PATTERN`, …),
and agree with the navigation groups `set_view` assigns and with which screens the touch engine serves (EQ gets
x/y, the sample editor x/y + axis, the mixer gestures).

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
- **LFO apply**: per-engine `switch(dest)` in ITCM writing into a float array at `voice+0x8C` — **Path B**
  (FMSYNTH `0x0C9D0`, HYPERSYNTH `0x0E552`, MACROSYNTH `0x1185A`, SAMPLER `0x1439E`, WAVSYNTH `0x171BA`).
- **Effects architecture** (from the mixer/effects UI): MODFX = CHORUS / PHASER / FLANGER; send effects MODFX,
  DELAY (time in steps), REVERB; **EQ banks** assignable per bus (`MIX EQ`, `MODFX EQ`, `DELAY EQ`, `REVERB EQ`);
  master chain **LIMITER (+ scope) → SOFT CLIP → DJ FILTER (LP/HP, LP/BS, BS/HP) → OTT (time, color)**.
- **FX commands**: 78 global (`0x00..0x4D`) + instrument commands (`0x80|n`, from the descriptor tables).
- **Views**: 30 ids (`0x00..0x1D`, 7 unused), current at `ui+0x15` — named in §8.

## 10. Libraries recognised

Teensy 4 core (startup, `yield`/EventResponder, SysTick, USB device, `attachInterrupt`), **Teensy Audio**
(`AudioStream` graph, I2S, `AudioNoInterrupts`), **SdFat** (SDIO driver, exFAT), **newlib** (`printf`/`dtoa`,
`malloc`, `assert`; built by a Jenkins GNU toolchain). The synth engines are Dirtywave's own classes; the
MACROSYNTH and wavetable data are consistent with Braids-style oscillator tables but that is not confirmed.

## 11. What is still rough

- Which send-effect / master-chain node is which (MODFX, delay, reverb, EQ, limiter, OTT, DJ filter) — the
  KAOSS mod's targets. The graph is wired in run-time loops, so the fastest route is the per-node CPU counters
  on hardware (§4).
- Which EXTERNAL apply switch is which (`0x0B384` vs `0x1286C`) — the other five engines are pinned.
- The effects-settings struct field layout (reached through a passed pointer; the community parser documents
  the file side).
- The engine↔voice mapping is S3 (by source order).
- The 950 KB oscillator data: which bank belongs to which engine (reached by computed offsets).
- Eight screens without strings (`0x08 0x09 0x0C 0x0F 0x15 0x17 0x1A 0x1B`) and which view slot draws.

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
