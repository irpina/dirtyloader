# Dirtywave M8 (Model:02): hook targets from the manual

Manual: M8 Operation Manual v20260421, which describes **OS 6.5.2** (the mods target firmware 6.6.2A).
Rated against: **dirtyloader core 0.1.0** (`baseline.md`). Readers: four Claude Sonnet agents in parallel,
one per part, with the Elekloader kit's brief. Date: 2026-11-13.

## The numbers

**600 targets**: full 0, partial 8 (1%), raw-only 0, none 592 (99%).

| part | covers | targets |
|---|---|---|
| A | panel, navigation, project, settings, theme, MIDI, render, sample editor, USB | 228 |
| B | song, live mode, chains, phrases, tables, groove, scales, sequencer FX commands | 139 |
| C | instruments, modulation, the five synth engines, external/MIDI out, instrument FX commands | 116 |
| D | mixer, EQ, limiter and scope, send effects, mixer and effects FX commands | 117 |

By area (from `stats.json`): Sequencer editing 52, Sampling 48, Parameter tables 43, UI input 42, Screen 35,
Voice render 34, Parameter editing 30, Transport 29, Mixer and master 27, MIDI in 26, Storage 26, Tick timing
24, Send effects 23, Notes 22, Settings 18, Row fire 16, MIDI out 14, Performance 12, USB 9, Indicators 2,
and **FX commands 69**, the M8-specific layer and the largest single area.

By kind: replace 312, extend 192, re-range 172, observe 118, veto 46, draw 33.

## What they say

- **Coverage is ~0 and that is the finding.** The core today is one TICK observer with no calls into the
  firmware, so it reaches nothing a manual describes. The 8 partial rows are all "rename a located label",
  the only static-patch sites located so far. This matches how the thin Elektron cores (the Models) rated.
- **The M8 is mostly about replacing and extending**, not observing: replace 312 and extend 192 out of 600.
  Modders want new commands, destinations, effect stages and views far more than they want to watch events.
- **The FX command system is the M8's biggest hook surface** (69 rows in its own layer, and every part named an
  FX-command dispatch primitive). One dispatch hook plus a command table would serve more targets than any
  other single site.

## Work list: the primitives that unlock the most

The readers' cross-cutting sections converge on the same handful of core hooks (ordered by how many parts named
them and how many rows hang off them):

1. **FX command table + dispatch** (command id + value + track + column -> effect, relative/absolute flag).
   All four parts named it. Unlocks the 69 fx-commands rows, plus new sibling commands.
2. **Parameter descriptor table + parameter-change event** (id, label, min, max, default, step, value text;
   old/new value with veto). Named by A, C, D. Unlocks param-tables, param-edit and most re-range rows.
3. **Key/input event with view context** (key chord, modifiers, view, cursor; touch axis). Named by all four.
   Unlocks UI input, performance and the touchscreen rows.
4. **Draw hook per view.** Named by A, B, C, D. Unlocks the 33 draw rows and every mod that needs a UI.
5. **Modulator destination table per engine** (C022, C024): destination id, label, apply function. This is
   the extended-LFO-destinations mod's exact target; extending it to the mixer sends is listed as the key
   extend.
6. **Master-chain stage list** (tracks, inputs, sends, OTT, EQ, limiter, DJ filter, soft clip, main volume;
   insert, bypass, reorder, replace) plus **touch-axis mapping** (A117, C030, D040: the stock OPTION+touch
   assigns a touch axis to a parameter). Together these are the KAOSS master-FX mod's targets.
7. Row-fire, tick/groove and transport events for the sequencer rows; MIDI in/out events; storage and boot
   events.

## The two planned mods, in catalog terms

- **Extended LFO destinations** (C022 DEST list per engine, extend; C024 apply rule, replace; C023 labels,
  partial today). Needs primitive 5. The firmware RE (`docs/MODULATION.md`) found the destination labels but
  not the list or the apply code; the catalog confirms those two are the decision points to locate.
- **KAOSS master FX** (D006 master chain order; D010 DJ filter modes; D013 OTT; D048 soft clip; D061-D081 the
  send effects; D040 and A117 touch-axis mapping). Needs primitives 3 and 6 (plus 4 for an XY display).

## Checks and caveats

- Merge is clean (no vocabulary or format problems). All 8 partial rows were read against `baseline.md`: each
  correctly cites a located label site and rates rename-only. 25 random none rows were sampled: all consistent.
- One row dropped (A119, a help-line restatement the brief excludes; the reader flagged it).
- Readers were Sonnet, not Opus, to save usage; the Elektron catalogs mostly used Opus 5.5. Expect some
  difference in row granularity.
- The manual is OS 6.5.2; behaviour may differ slightly in 6.6.2.
- pdftotext scrambles key-combination diagrams and wide tables; readers noted where text was unreadable.
- Re-rate (Coverage cells only) whenever the core gains an event, table or call: rows do not change.
