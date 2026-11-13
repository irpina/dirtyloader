# Sites log (M8)

Every firmware hook site found for a dirtyloader hook bus, in one place. Same method and confidence scale as
the Elekloader kit's `notes/manual-catalog/events/SITES.md`: code-only hunts log their sites here, and a core
PR takes its sites from this log and confirms them in one batch (on the Teensy). Targets come from
`docs/manual-catalog/m8/SUMMARY.md`.

Firmware: **M8 6.6.2A Model02** (stock sha256 `fbc15296…`). Addresses are flash addresses (image base
`0x60000000`); file offset = address - 0x60000000 + 0x200.

**Confidence:** **E** seen firing (emulator: none for the M8); **H** on hardware (only when the user says so);
**S1** decompile + strings + callers agree and a second independent line of evidence (e.g. the case-count
fingerprint) agrees; **S2** decompile, strings and callers agree; **S3** a lead. Never raise a row without new
evidence; mark contradicted rows `superseded`.

## `ev_fx_command`: the FX-command bus ([static-m8-fxcmd.md](static-m8-fxcmd.md))

Command encoding (from the name lookup): `0xFF` empty; `0x00..0x4D` the 78 global commands (sequencer, mixer,
send effects, master); `0x80 | n` instrument command `n`, routed through the current instrument object's
vtable.

### Data and calls (not sites)

| what | address | conf | notes |
|---|---|---|---|
| global command name table | 0x601D6FD8 | S1 | 78 x 4-byte slots, ids 0x00 ARP .. 0x4D MTT; long-name/help table follows at 0x601D7118 |
| command name lookup | 0x6008C4A4 | S2 | (_, cmd) -> name; 0xFF none; cmd < 0x4E -> table; 0x80+ -> instrument vtable +0xA4 (count at +0xD4) |
| command help/long-name lookups | 0x6008C578, 0x6008C658 | S2 | same split; the second is used by the help view path |
| command value formatter | 0x6005ED66 | S2 | (_, cmd, value, rel) -> display text; 78-case `tbh` at 0x6005EE1E; instrument cmds via vtable +0xC8. UI only, NOT the executor |
| total command count | 0x60029B3C | S2 | 0x4E + instrument vtable +0xD4 |
| command property helpers | 0x60029B5C, 0x60029B7C, 0x60029BB4, 0x60029BDC | S3 | instrument cmds via vtable +0x118 / +0xC0; pitch-command (0x0C..0x0F) handling; exact meaning unread |
| **executor** (global/track cmds) | **0x600287A4** | **S1** | the 78-way dispatch: `cmp r8,#0x4D` + `tbh [pc,r8]` at 0x60028802; cmd id in r8/r2. 26 cmds handled in-function, 52 route to default 0x60028BCA (sibling executors). Full map: [static-m8-fxcmd.md](static-m8-fxcmd.md) |
| per-command jump table | 0x60028806 | S1 | 78 × u16; `target = 0x60028806 + 2·entry`; decoded |
| per-slot FX scan loop | 0x60029AA4 | S2 | walks a track's command column (body from 0x60029AD2); per slot calls the ratchet + the dispatch wrapper |
| command dispatch wrapper | 0x60029270 | S3 | called per slot by the scan loop; presumed direct caller of the executor (edge unconfirmed) |
| ratchet / retrigger tick | 0x60028700 | S2 | per-slot counter at +0x78; resets slot on cmd==0x10. **NOT** the executor (supersedes the earlier lead) |
| second table branch | 0x60029C08 | S3 | `tbb [pc,r12]` in the same region — a smaller byte-offset switch; likely a sibling executor, unread |

### Sites

| site | event / call | conf | notes | report |
|---|---|---|---|---|
| 0x600287A4 | `ev_fx_command`: a global/track command fires | S1 | detour the executor entry; handler gets the command id (r8/r2) before the 78-way `tbh`. observe / veto / re-range / extend. Exact `bl` detour site pends confirming 0x60029270→0x600287A4. [static-m8-fxcmd.md](static-m8-fxcmd.md) | (HW pending) |

## `loop()` per-frame subsystems ([static-m8-loop.md](static-m8-loop.md))

`main()` (0x600AE04C) confirmed: `setup(); while(1){ loop(); yield(); }`. `loop()` (0x60081BD4) is a
cooperative scheduler — subsystem groups behind timing gates, not a flat list.

### Data and calls (not sites)

| what | address | conf | notes |
|---|---|---|---|
| main engine (TICK-rate) | 0x600A5E60 | S2 | unconditional each frame; 24 subsystem calls. Sequencer / transport / voice-follow; subtree unmapped (row-fire/transport live here) |
| ~5 ms service group | 0x60081A90 | S2 | 6 subsystems (0x6007CBFC, 0x6007D23C, 0x6007C9E4, 0x6007BFB8, 0x60079A7C, 0x60039964) |
| UI-frame gate | 0x6008196C | S2 | returns a byte behind a ~10 ms gate; `loop()` branches on it for the UI frame |
| µs/elapsed read | 0x6007BBB4 | S2 | tiny, 1 peripheral ref (a micros()-style timer) |
| view draw vtable slot | +0xA0 | S2 | per-view render method, called from the display driver's 8-item loop |

### Sites

| site | event / call | conf | notes | report |
|---|---|---|---|---|
| 0x6004B514 | `ev_render`: display refresh (whole frame) | S2 | the display driver: NVIC-guarded framebuffer (ISER/ICER 0xE000E100/180), per-view vtable `+0xA0` draw, ~15 ms gate. Detour `bl 0x6004B514` in `loop()`, or wrap the view `+0xA0` for a per-view hook. [static-m8-loop.md](static-m8-loop.md) | (HW pending) |
| 0x6004C6C8 | `ev_input`: UI event / view-update | S3 | runs just before the flush; event code in r1 (`==0xE4`), key/state at ctx+0x15, bitmask dispatch. Input-routing vs. view-build not yet certain | (HW pending) |
