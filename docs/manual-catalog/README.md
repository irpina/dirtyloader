# Manual catalog: the M8's hook targets

What a mod author could want to hook on the Dirtywave M8, counted from its operation manual, and how much of
it dirtyloader's core covers today. It is the same method and unit as the Elekloader manual-catalog kit
(`digitaktresearch/notes/manual-catalog`), so M8 numbers compare with the Elektron devices'.

A **target** is a decision point the manual describes (an input, a state, a rule, a limit, an output). It is
NOT a hook site and NOT an event: one hook site usually serves many targets. Never set a target count beside a
site or event count.

## What is here

| | |
|---|---|
| `tools/catalog.py` | the kit's tool, copied; only the manual-text path changed (see its docstring) |
| `vocab.json` | kinds, coverage words, layers, lenses: the Elektron vocabulary, plus `fx-commands` for the M8 |
| `devices.json` | the M8 entry: manual, OS, the four parts and their line ranges |
| `BRIEF.md` | the readers' brief template (the kit's, with the dirtyloader-specific rating rules) |
| `m8/baseline.md` | written by hand: everything dirtyloader core 0.1.0 gives a mod; every rating is against it |
| `m8/prompts/<part>.md` | generated: each reader's whole prompt |
| `m8/<part>.md` | the readers' catalogs (the source of truth; fix rows here) |
| `m8/merged.json`, `m8/stats.json` | generated |
| `m8/SUMMARY.md` | the synthesis, written by hand |

The manual itself and its text (`manuals/m8_operation_manual_v20260421.pdf`, `manuals/m8.txt`) are
Dirtywave's and stay local: `manuals/` is gitignored. Rebuild the text with
`pdftotext -layout manuals/m8_operation_manual_v20260421.pdf manuals/m8.txt`.

## Running it

From this folder, plain Python:

```
python -I tools/catalog.py brief m8      # m8/prompts/<part>.md
python -I tools/catalog.py merge m8      # m8/merged.json + rows that break the vocabulary
python -I tools/catalog.py stats m8      # area x coverage table, m8/stats.json
```

Readers: one agent per part, in parallel, each prompted only "Read the file m8/prompts/<part>.md with the Read
tool and do exactly what it says."

## When the core grows

Rows do not change when the core changes; only the Coverage cells do. A re-rate is a pass over `m8/<part>.md`
with a new `m8/baseline.md`, not a new reading of the manual.
