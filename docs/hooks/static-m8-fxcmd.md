# `ev_fx_command` — the FX-command executor (static hunt, M8 6.6.2A Model02)

Where an FX command actually *fires on a track*. This is the M8's single biggest hook surface
(`docs/manual-catalog/m8/SUMMARY.md`: 69 fx-command rows, named by all four manual readers). Addresses in this
doc are **load** addresses in the flash image (file offset = address − `0x60000000` + `0x200`).

> **All of this is ITCM code.** It sits in the ITCM image (`0x60001680..0x6002CF50`) and runs at
> `load − 0x60001680` — the executor runs at **`0x00027124`**, the scan loop at `0x00028424`
> ([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §1). Patch it at the load address; but a detour from here cannot
> `bl` to the flash cave (out of range from `0x0002xxxx`) — use a long veneer or free ITCM. And it all runs
> **inside the audio interrupt**: the sequencer is an `AudioStream` node (clock `0x22720`), so a handler here
> runs in the audio thread with its time budget.

| role | load | run |
|---|---|---|
| sequencer clock node (`update()`) | `0x60023DA0` | `0x22720` |
| row fire / note trigger | `0x60026460` | `0x24DE0` |
| **row-fire FX applier**, FX columns 0..2 (72-case, cmds `0x00..0x47`) | `0x60025ED4` | `0x24854` |
| per-tick track update | `0x600276A8` | `0x26028` |
| per-slot scan loop | `0x60029AA4` | `0x28424` |
| dispatch wrapper | `0x60029270` | `0x27BF0` |
| **per-tick executor** (78-case) | `0x600287A4` | `0x27124` |
| ratchet / retrigger tick | `0x60028700` | `0x27080` |

**Confidence S1.** The executor's 78-way table branch, its `cmp #0x4D` bound, and the decoded jump table all
agree, and the command count `0x4E` (78) independently matches the name table (`0x601D6FD8`), the value
formatter (`0x6005ED66`), and the total-count helper (`0x60029B3C`) already mapped in `SITES.md`. The caller
edge is **confirmed**: the dispatch wrapper `0x60029270` calls `0x600287A4` (Ghidra call reference).

## The dispatch chain

```
per-slot FX scan loop        0x60029AA4   push {r4-r9,lr}; walk a track's command column downward
  │   loop body from         0x60029AD2   ldrb.w r2,[r8,#-1]!   ; read each slot's command byte
  ├── bl 0x60028700   ratchet/retrigger tick  (per-slot counter at +0x78; resets slot on cmd==0x10)
  └── bl 0x60029270   command dispatch wrapper  ──►  the executor below
                                              0x600287A4   the 78-way executor
```

- **`0x60028700` is the ratchet/retrigger tick, not the executor** (a 160-byte function; it just advances the
  per-slot counter at `+0x78` and clears slot fields on `cmd==0x10`). The earlier `SITES.md` lead that put the
  "78-case tbh" at `0x60028700` was conflating two adjacent functions; this supersedes it.
- **`0x60029AA4`** is the per-slot scan loop (body from `0x60029AD2`): for each command slot of a track it calls
  the ratchet and the dispatch wrapper.
- **`0x60029270`** (1416 bytes, 16 calls) is the dispatch wrapper the loop calls per slot, and it **calls the
  executor `0x600287A4`** (confirmed). The `bl` inside it is the precise detour site.

## The executor function (`0x600287A4`)

Standard entry `push {r4,r5,r6,r7,r8,r9,r10,lr}` at `0x600287A4`; a preset alt-entry at `0x600287A0`
(`adr r5,[0x60028964]; movs r0,#0x25`) falls through into it. The command id arrives in **r2** (moved to
**r8**); r0/r1/r3 and a `[sp,#0x38]` stack arg carry the track/slot/value context.

```
0x600287C0  mov r8,r2            ; r8 = command id
... special cases before the switch:  r2==0xFF none ->0x600288A2,  ==6 ->0x600288C6,
                                       ==9 ->0x60028966,  ==4 ->0x60028974
0x600287FA  cmp.w r8,#0x4D       ; 0..0x4D are the 78 global commands
0x600287FE  bhi.w 0x60028BCA     ; out of range -> default
0x60028802  tbh [pc,r8]          ; 78-entry halfword jump table at 0x60028806
```

### The jump table (`0x60028806`, 78 × u16)

Decoded straight from the payload: `target = 0x60028806 + 2 × table[id]`. 26 commands dispatch to their own
handler **in this function**; the other 52 route to the shared default `0x60028BCA`, i.e. they are *not*
sequencer-track commands and are processed by sibling executors (mixer/send/DJ/I2C/OTT), the pitch path
(`0x0C..0x0F`, see `SITES.md` property helpers), or the song/table paths.

Handled here (id · name · handler):

| id | name | handler | id | name | handler |
|---|---|---|---|---|---|
| 0x00 | ARP | 0x60028EDA | 0x18 | TPO | 0x60028DD8 |
| 0x01 | CHA | 0x60028E86 | 0x19 | TSP | 0x60028ED0 |
| 0x02 | DEL | 0x60028F2C | 0x1A | OFF | 0x60028D14 |
| 0x03 | GRV | 0x60028EEC | 0x1B | VMV | 0x60028D24 |
| 0x05 | KIL | 0x60028CB8 | 0x41 | EQM | 0x60028D30 |
| 0x08 | RET | 0x60028CC8 | 0x42 | EQI | 0x60028D54 |
| 0x09 | REP | 0x60028C14 | 0x43 | INS | 0x60028D60 |
| 0x0A | RMX | 0x60028F1A | 0x44 | RTO | 0x60028C14 |
| 0x0B | NTH | 0x60028C90 | 0x45 | ARC | 0x60028D88 |
| 0x10 | SCA | 0x60028E20 | 0x46 | GGR | 0x60028D90 |
| 0x11 | SCG | 0x60028E3A | 0x47 | NXT | 0x60028DA8 |
| 0x12 | SED | 0x60028E4C | 0x4D | MTT | 0x60028C8C |
| 0x16 | TIC | 0x60028E66 | | | |
| 0x17 | TBX | 0x60028DBA | | | |

Routed to the default `0x60028BCA` (handled elsewhere): `HOP RND RNL` · pitch `PSL PBN PVB PVX` · `SNG TBL THO`
· mixer/send `XMM XMF XMW XMR XDT XDF XDW XDR XRS XRD XRM XRF XRW XRZ XRH XMT` · volume `VMX VDE VRE VT1..VT8`
· DJ `DJC DJR DJT` · inputs/I2C `VIN IMX IDE IRE VI2 IM2 ID2 IR2 USB` · `OTT OTC OTI`.

(`REP` 0x09 and `RTO` 0x44 share `0x60028C14`.)

## Hook recommendation

A Core `ev_fx_command` detour at the **executor entry `0x600287A4`** sees every sequencer/master command on
every track, with the command id in `r8`/`r2` before the switch — the broadest single FX hook. A handler can
**observe** (log/meter), **veto** (skip to the epilogue), **re-range** a value, or **extend** the set by adding
a case for an id the stock table sends to `0x60028BCA`. Adding a *new* sibling command is cleanest via a new
id + a cave handler the dispatcher routes to.

## Open items (next static passes / hardware)

1. ~~Byte-confirm `0x60029270 → 0x600287A4`~~ — **done.**
2. The 52 default-routed commands. Resolved so far (via the switch census, [static-m8-switches.md](static-m8-switches.md)):
   - the `tbb` at **`0x60029C08`** is the **pitch-command helper** (bias `0x0C`, 4 cases = PSL/PBN/PVB/PVX), not
     a sibling executor;
   - **no** switch in the image is biased by `0x1C` / bounded at 37 cases, so the mixer/send commands
     (`0x1C..0x40`) are not switch-dispatched — most likely data-indexed;
   - **`0x60025ED4`** (run `0x24854`) is the **row-fire FX applier**: row fire `0x24DE0` calls it once per FX
     column (0, 1, 2) with the column's command and value (72-case switch, ids `0x00..0x47`; per-slot state at
     track `+0x1A4..`; RND and REP re-dispatch the stored command). *Corrected:* first guessed to be the
     per-tick side; it is the opposite — the 78-case executor is the per-tick slot processor.
   Next: decompile the executor's default path (`0x60028BCA`) and `0x60025ED4`'s cases.
3. Decode a couple of the in-function handlers (e.g. `ARP 0x60028EDA`, `DEL 0x60028F2C`) to confirm the arg
   layout a handler would receive.
4. Who calls the scan loop `0x60029AA4`: not `loop()` — most likely the audio-update interrupt (attached at
   runtime, so invisible to static call graphs).
5. Confirm on a spare Teensy once hooking is validated; nothing here has run on hardware.
