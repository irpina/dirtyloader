# Manual catalog: Dirtywave M8 (Model:02), part A (Panel, navigation, system, storage, MIDI, USB, sampling)

You are one of several readers cataloguing "hook targets" for dirtyloader, an Elekloader-style mod loader for
the Dirtywave M8. Device: **Dirtywave M8 (Model:02)**, operation manual for OS 6.5.2. Read your range of the manual and
list every place where a mod author might want to observe, veto, replace, re-range or extend what the stock
firmware does. This is manual-only analysis: do not invent firmware addresses and do not open any code
repository or firmware file.
The M8 is a tracker: eight monophonic tracks, a Song > Chain > Phrase hierarchy, tables, three FX-command columns per row, instruments with four modulators each, and a mixer with send effects. The manual describes OS 6.5.2; the firmware the mods target is 6.6.2.

## Your range

File: `C:\Users\zacha\Documents\dirtyloader\manuals\m8.txt` (pdftotext -layout of the manual, 4053 lines).
Read EVERY line of these ranges with the Read tool (offset/limit, about 300 lines at a time):
- lines 330-610: Conventions; Overview; Physical layout; Power; Audio out; microSD; Getting started; Navigation; Key shortcuts; Hexadecimal; Firmware updates; Demo song
- lines 1598-1944: Project; System Settings; Theme; MIDI Mapping; MIDI Settings; Time Stats; Render; Selection to Sample; Effect Command Help
- lines 2152-2236: Sample Editor
- lines 2480-2660: USB Features; Troubleshooting; Key Shortcuts appendix
- lines 3965-4052: Hexadecimal Table; Specifications

The other readers: B = The tracker: song, live mode, chains, phrases, tables, groove, scales, sequencer FX commands; C = Instruments, modulation and the synth engines; D = Mixer, EQ, limiter and send effects. If your range mentions a feature another part explains in full, still list
what YOUR range states about it.

Text quirks: page numbers and headers repeat; key-combination diagrams and wide tables may be scrambled; some
characters (arrows, degree signs) come out as replacement marks. Where the text cannot be read, say so in the
section instead of guessing.

## What a hook target is

One row = one **decision point** a mod could want to hook on its own: an input, a piece of state the
firmware reads, a rule it applies, a range or limit, or an output (screen, audio, MIDI, stored data).
One feature usually yields several rows.

Your lens: Settings, storage, MIDI, USB and the system. Every menu row is a candidate (its options, its default, when it takes effect). Project, song, instrument and theme management and their confirmations; file browsing; MIDI sync, ports, channels, mapping, what each incoming and outgoing message does; USB modes; display and theme options; startup, firmware update, technical limits. Also the panel material in this range: key combinations, navigation, hex entry. Also read the panel material here as the panel lens would: every key combination and navigation rule, hex entry, and the troubleshooting behaviours. The Sample Editor and Render/Selection-to-Sample are sampling targets: use the sampling layer for them.

Rules for the unit, so every device counts the same way:
- Split a feature into its decision points; do not write one row for a whole chapter, nor one per sentence.
- List a target once, at its first mention in your range. A later mention gets no new row.
- A table or list (an FX-command appendix entry list, a list of models or waves, a hex table) is one row per
  table, or per distinct behaviour it states, never one row per entry: "which commands are relative and which
  absolute" is a target, "VOL is relative" is not. EXCEPTION for the M8: each FX command whose behaviour the
  manual describes gets its own row (a command is a decision point, like a parameter).
- Every stated limit (a count, a range, a timing), every key combination, every mode, every pop-up, every
  menu row and every parameter is a candidate.
- Not targets: safety, warranty and legal text, marketing, credits, tips that only restate a feature,
  connector and electrical specifications (unless a mod could change the number, like track count or
  phrase length).

## What the core gives a mod today (to rate coverage)

Read `C:\Users\zacha\Documents\dirtyloader\docs\manual-catalog\m8\baseline.md` first, all of it. It is everything dirtyloader core 0.1.0 (branch core-ghidra) gives a mod on this device. Rate every
row against that sheet and nothing else: not against what you think the firmware could do, and not against
other devices or other loaders.

The "Coverage today" cell starts with exactly one of these words:
- `full`: something on the sheet does it cleanly for every Kind you listed. Name it.
- `partial`: something on the sheet touches it but part is missing. Say what is missing.
- `raw-only`: the only way is to take a raw input event and redo the stock logic in the mod. Name the raw
  event. (The sheet lists no raw input event today, so this word should not be needed; use it only if the
  sheet names one.)
- `none`: nothing on the sheet reaches it.

Be strict. `full` needs a named event, table or call on the sheet. When you are unsure, rate lower and say
why in the parenthesis.

Two cases rated the same way everywhere:
- Screen rows: the sheet has no draw event, so a screen element is `none` unless the sheet lists the specific
  text as a located static-patch site; then it is `partial (static patch: rename only)`.
- A row the sheet's static patching could only reach if its site were located first is `none (site not
  located)`: static patching is a means, not coverage, until the sheet lists the site.

## Output

Write `C:\Users\zacha\Documents\dirtyloader\docs\manual-catalog\m8\A.md` (one file; create it with the Write tool, extend it as you go if that is easier).

1. First line: `# Hook targets A: panel, key shortcuts, project, settings, theme, MIDI, render, sample editor, USB (Dirtywave M8 (Model:02), OS 6.5.2)`. Then a `Source:` line with the
   line ranges you read, then a short list of the assumptions behind your coverage ratings.
2. One section per manual section, headed with the manual's own section title
   (`## Phrase View`, `## Sequencer FX Commands`), each with this table and exactly these five columns:

   `| Hook target | Kind | Layer | Coverage today | Example mods |`

   - **Hook target**: the decision point in your own words, about 25 words at most. Paraphrase; never copy
     a passage. No `|` character inside a cell.
   - **Kind**: one or more of `observe`, `veto`, `replace`, `re-range` (limits, counts, scales, curves),
     `extend` (add a mode, row, page, type, destination, command), `draw` (screen), joined by ` / `.
   - **Layer**: exactly ONE of these slugs, the place in the firmware a hook would have to sit:
  - `ui-input`: the eight keys, key combinations, the modes and views keys enter, navigation between views
  - `ui-screen`: views, pages, lists, pop-ups, the naming screen, scopes, what is drawn
  - `ui-leds`: any LED or status indicator
  - `param-edit`: the path from an edit key press to a stored value: step size, coarse/fine, reset, value text, hex entry
  - `param-tables`: a parameter's range, default, enum list, curve; destination, type, shape and model lists
  - `sequencer-fire`: what happens as a phrase or table row plays: the note, the instrument, volume, and the commands it fires
  - `sequencer-timing`: groove, ticks per step, delay and retrigger at play time, table tick rate
  - `sequencer-transport`: play/stop, tempo and clock, song rows, chains, phrase advance, live mode queueing and launching
  - `sequencer-edit`: entering notes, instruments and commands; clone, deep clone, selection, copy/paste/delete of song, chain, phrase and table data
  - `fx-commands`: the effect-command set used in phrases and tables: which commands exist, their value ranges, what each does when it fires, relative vs absolute; adding a command
  - `notes`: the note path between a source and a voice: transpose, scales, the keyjazz/note entry, voice behaviour per track
  - `render-voice`: per-instrument DSP: the engines (wavsynth, macrosynth, sampler, FM, hypersynth), filter, amp, the four modulators (envelopes, LFOs, trackers)
  - `render-fx`: chorus/modfx, delay, reverb and their sends
  - `render-master`: the mixer, EQ, limiter, inputs, routing, the outputs
  - `midi-in`: what the unit does with incoming MIDI, MIDI mapping
  - `midi-out`: what the unit sends: MIDI out and external instruments, CC/program changes, clock and transport out
  - `storage`: projects, songs, instruments, tables, themes, the microSD card, the file browser
  - `sampling`: recording audio, the sample editor, slicing, render and selection-to-sample
  - `settings/boot`: system settings, themes as settings, startup, firmware update
  - `usb`: USB audio and MIDI, display/headless and host features
  - `performance`: live mode, mute and solo, performance-oriented mixer controls
   - **Coverage today**: one of the four words, then a short parenthesis: which event, or what is missing.
   - **Example mods**: one or two short ideas that would use the hook.

   A section with nothing to hook: the heading and the line `Prose only; no hook targets.`
3. A last section `## Cross-cutting primitives`: the reusable core-level hooks your range implies (for
   example "FX command dispatch: command id + value + track -> effect"), each with the targets that would use
   it. Ten to twenty lines.
4. A final line: `Targets: N` (the number of table rows you wrote).

Be thorough rather than brief: every distinct behaviour your range describes. Before you finish, check that
every Layer cell is one slug from the list and every Coverage cell starts with one of the four words.
Reply with only the output path and the target count.
