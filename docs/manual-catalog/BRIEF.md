# The reader brief (template), M8 edition

`python tools/catalog.py brief m8` fills the template below for each part in devices.json and writes
`m8/prompts/<part>.md`. A reader's whole prompt is then one line: "Read <that file> and do what it says."

Taken from the Elekloader manual-catalog kit's BRIEF.md (digitaktresearch/notes/manual-catalog), with the same
unit, kinds, coverage words and output format so the M8 counts compare with the Elektron devices. Changed for
dirtyloader: the loader's name; the screen rule (dirtyloader has no draw event, so there is nothing to "draw
over"); and `raw-only` (dirtyloader has no raw input event yet, so it can only apply if the baseline gains one).

<!-- TEMPLATE -->
# Manual catalog: {device_name}, part {part} ({part_title})

You are one of several readers cataloguing "hook targets" for dirtyloader, an Elekloader-style mod loader for
the Dirtywave M8. Device: **{device_name}**, operation manual for OS {os}. Read your range of the manual and
list every place where a mod author might want to observe, veto, replace, re-range or extend what the stock
firmware does. This is manual-only analysis: do not invent firmware addresses and do not open any code
repository or firmware file.
{device_notes}

## Your range

File: `{text_path}` (pdftotext -layout of the manual, {n_lines} lines).
Read EVERY line of these ranges with the Read tool (offset/limit, about 300 lines at a time):
{ranges}

The other readers: {others}. If your range mentions a feature another part explains in full, still list
what YOUR range states about it.

Text quirks: page numbers and headers repeat; key-combination diagrams and wide tables may be scrambled; some
characters (arrows, degree signs) come out as replacement marks. Where the text cannot be read, say so in the
section instead of guessing.

## What a hook target is

One row = one **decision point** a mod could want to hook on its own: an input, a piece of state the
firmware reads, a rule it applies, a range or limit, or an output (screen, audio, MIDI, stored data).
One feature usually yields several rows.

Your lens: {lens}

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

Read `{baseline_path}` first, all of it. It is everything {release} gives a mod on this device. Rate every
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

Write `{out_path}` (one file; create it with the Write tool, extend it as you go if that is easier).

1. First line: `# Hook targets {part}: {covers} ({device_name}, OS {os})`. Then a `Source:` line with the
   line ranges you read, then a short list of the assumptions behind your coverage ratings.
2. One section per manual section, headed with the manual's own section title
   (`## Phrase View`, `## Sequencer FX Commands`), each with this table and exactly these five columns:

   `| Hook target | Kind | Layer | Coverage today | Example mods |`

   - **Hook target**: the decision point in your own words, about 25 words at most. Paraphrase; never copy
     a passage. No `|` character inside a cell.
   - **Kind**: one or more of `observe`, `veto`, `replace`, `re-range` (limits, counts, scales, curves),
     `extend` (add a mode, row, page, type, destination, command), `draw` (screen), joined by ` / `.
   - **Layer**: exactly ONE of these slugs, the place in the firmware a hook would have to sit:
{layers}
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
