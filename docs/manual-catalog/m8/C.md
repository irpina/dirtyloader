# Hook targets C: instrument and modulation views, wavsynth, macrosynth, sampler, FM, hypersynth, external instrument, MIDI out, instrument FX commands (Dirtywave M8 (Model:02), OS 6.5.2)

Source: `manuals/m8.txt` lines 834-1061, 1945-2151, 2237-2479, 2988-3294, 3342-3964 (all read; the wave table index is a scrambled multi-column hex list, read as one list per page).

Assumptions behind the coverage ratings:
- Rated only against `baseline.md`: one observer-only TICK event, no calls, no tables, no draw/input/param/note/FX/MIDI/audio events.
- Static patching is coverage only for the located label strings: modulation destination short names, send parameter names, modulator type names, filter type names, scale names, input/track routing names. Everything else is `none`.
- Instrument-type names, LIM names, LFO shape names, trigger names, play-mode names, FM shape names and the Macrosynth model names are not on the located-label list, so they rate `none (site not located)`.
- Screen rows are `none` unless a located label string is the whole point of the row.
- The manual does not give value ranges for most parameters; where a range is unstated the row says so rather than guessing. The 6.5.2 manual may differ from firmware 6.6.2.

## Instrument View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Instrument type list (NONE, Wavsynth, Macrosynth, Sampler, FM Synth, Hypersynth, MIDI Out, External Instrument): add an eighth engine or hide one | extend / re-range | param-tables | none (no enum table exposed; type names not a located label) | A custom engine type; a "lite" build hiding unused types |
| Per-song instrument count of 128 slots, each holding settings, four modulators and a table | re-range | param-tables | none (no limit located) | 256 instrument slots; reduced slots for memory |
| TYPE change: the moment an instrument slot goes from NONE to a type and its parameters initialise | observe / replace | param-edit | none (no parameter-change event) | Custom per-type default patches on creation |
| Default type NONE doubling as the "slot unused" marker | observe | param-tables | none (no state readable) | Slot-usage report; auto-clean unused slots |
| LOAD / SAVE instrument preset to SD card | observe / replace / extend | storage | none (no storage call or event) | Preset browser with tags; save in a custom format |
| NAME field for the instrument, also used when bundling a song | re-range / replace | param-edit | none (no edit path; name length not stated in this range) | Longer names; auto-naming from type and wave |
| TRANSP. flag: per-instrument switch ignoring scale, chain-transpose and project transpose | observe / veto | notes | none (no note-path event) | Force transpose off on drum kits; a "partial transpose" amount |
| TABLE TIC default (01 = one tick per table step), overridable by the TIC command | re-range / replace | sequencer-timing | none (no table or timing hook) | Fractional table speeds; tempo-synced table rate |
| EQ slot assignment per instrument, with edit key and SHIFT+RIGHT jumping to the EQ editor | re-range / extend | render-master | none (no mixer or EQ hook) | More EQ slots; per-instrument EQ presets |
| Shortcut: SHIFT+LEFT or RIGHT from the instrument view jumps to phrase or table and seeds the default FX command with the highlighted parameter | observe / replace | ui-input | none (no key event) | Seed a different command; remember last parameter per instrument |
| Navigation shortcuts: OPTION+LEFT/RIGHT previous or next instrument, OPTION+UP/DOWN steps 16 | re-range / extend | ui-input | none (no key event) | Step 8 or 32; jump to next used instrument |
| Playing shortcuts: PLAY, EDIT+PLAY preview instrument, SHIFT+PLAY continue from chain position, mute and solo chords | observe / veto / extend | ui-input | none (no key event) | Preview at a chosen note; toggle audition latch |
| Editing shortcuts: EDIT+UP/DOWN large step, EDIT+LEFT/RIGHT small step, EDIT+OPTION reset to default | re-range / replace | param-edit | none (no edit path) | Change large step size per parameter; custom reset value |
| Copy instrument (SHIFT+OPTION), paste or undo paste (SHIFT+EDIT) | observe / veto / extend | sequencer-edit | none (no key event or clipboard hook) | Paste-special that keeps the name; multi-slot clipboard |
| Touchscreen: EDIT+touch sets a slider value by finger position; OPTION+touch assigns the touch axis to the parameter | replace / extend | ui-input | none (no input event) | Curve on the touch axis; assign both axes |
| Slider widgets drawn for parameter values in the instrument view | draw | ui-screen | none (no draw event) | Numeric overlay on sliders; custom meter style |
| Bottom-of-screen help text shown while editing a parameter | draw / replace | ui-screen | none (no draw event; help strings not located) | Show value in Hz or ms; translated help |

## Instrument Modulation View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Modulation view reached by SHIFT+UP from the instrument view | observe / extend | ui-input | none (no key event, no view change) | Extra modulation page; direct key to the view |
| Number of modulation slots per instrument (four) | re-range | render-voice | none (no limit located) | Six or eight modulators per instrument |
| Modulator type list (AHD, ADSR, DRUM, LFO, TRIG, TRACKING): add or replace a type | extend / replace | param-tables | partial (static patch: rename only for type names; no list or behaviour) | Step-sequencer modulator; random-walk or slew modulator |
| Modulator DSP per type: envelope curve shapes and time-to-tick mapping | replace | render-voice | none (no voice or modulator hook) | Exponential envelopes; sample-accurate attack |
| DEST list per engine: which parameters each modulator may target, and its count | extend / re-range | param-tables | none (destination list not located; only labels renamable) | Modulate mixer sends, track volume, tempo, a table position |
| Destination label names (CUTOFF, RES, AMP, PAN, CCA to CCD, VOL, PITCH ...) | draw | ui-screen | partial (static patch: rename only) | Rename destinations to a personal vocabulary |
| How a modulator value is applied to its destination: scale, add or multiply, clamp | replace | render-voice | none (apply path not located) | Bipolar modulation of unipolar parameters; logarithmic depth |
| Modulation of modulators: DEST MOD AMT, MOD RATE, MOD BOTH; each slot affects the next (1 to 2, 2 to 3, 3 to 4, 4 to 1) | extend / replace | render-voice | none (no modulator hook) | Reverse the ring order; allow a modulator to hit any slot |
| MOD AMT scale of 0 to 100 percent and MOD RATE as a time multiplier | re-range | param-tables | none (no range located) | Allow amount above 100 percent; negative rate |
| SRC field: source of a modulation, where the type offers one | extend / re-range | param-tables | none (no list located) | Add MIDI CC, mod wheel or aftertouch as sources |
| Modulator slot copy (SHIFT+OPTION) and paste (SHIFT+EDIT) | observe / extend | sequencer-edit | none (no key event) | Copy a modulator to all instruments; swap two slots |
| Modulation view navigation and playing shortcuts (instrument step, +/-16, preview, mute, solo, SHIFT+LEFT/RIGHT to phrase or table) | observe / extend | ui-input | none (no key event) | Jump to the table with the destination seeded |
| Help text at the bottom of the screen while editing a modulation parameter | draw | ui-screen | none (no draw event) | Show seconds rather than ticks |
| AHD envelope: ATK, HOLD, DEC and AMT; times in ticks relative to song tempo | re-range / replace | render-voice | none (tick-to-time mapping not located) | Times in milliseconds; longer maximum times |
| ADSR envelope: ATK, DEC, SUS, REL; release only starts on an OFF note, OFF FX or MIDI note release | veto / replace | render-voice | none (no note-off event) | Auto-release after a set time; release on next note |
| DRUM envelope: PEAK shapes both duck amount and peak time; BODY hold, DEC decay | replace / re-range | render-voice | none (no modulator hook) | Separate duck and peak parameters; longer duck |
| LFO OSC shape list: 10 shapes (TRI, SIN, RAMP DN/UP, EXP DN/UP, SQU DN/UP, RANDOM, DRUNK), each with a tick-rate T variant | extend / replace | param-tables | none (shape names not located) | Add S&H, smooth-random, user-drawn shapes |
| LFO TRIG behaviour: FREE, RETRIG, HOLD, ONCE | extend / replace | render-voice | none (no modulator hook) | Add a "sync to song position" mode; reset on every row |
| LFO FREQ in steps (16th notes) or in ticks for T shapes | re-range / replace | param-tables | none (no range located) | Triplet or dotted rates; Hz rates |
| TRIG envelope: bipolar AHD triggered by another source; SRC is an instrument 00 to 7F or all instruments on a track 80 to 87 | extend / re-range | render-voice | none (no trigger event) | Trigger from MIDI input or a table row; track 9 and above |
| TRACKING modulator: SRC NOTE, VELOCITY or VELOCITY TAKEOVER with LVAL and HVAL, reversible for inversion | extend / replace | render-voice | none (no note or velocity event) | Add CC or pitch-bend as a source; curve between LVAL and HVAL |
| VELOCITY TAKEOVER: disables velocity scaling of instrument volume | veto / replace | notes | none (no note-path event) | Velocity-to-filter-only mode; velocity curves |
| Modulation type names shown in the MOD[1-4] field | draw | ui-screen | partial (static patch: rename only) | Rename the type labels |

## Wavsynth

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Wave table generation: 8-bit buffer built in real time from a base shape, then repeated, skewed, mirrored, filtered and overdriven | replace | render-voice | none (no voice hook) | Higher bit depth buffer; add a new processing stage |
| SHAPE list: four pulse widths (12 to 75 percent), SAW, TRIANGLE, SINE, NOISE PITCHED, NOISE, then WT tables | extend / replace | param-tables | none (shape list not located) | Add supersaw, custom hand-drawn shapes |
| Base shapes count of 9 and 61 built-in wave tables, each of 64 waveforms morphed by SCAN | re-range / extend | param-tables | none (table store not located) | Load tables from SD card; more than 64 frames |
| SIZE: waveform length in samples, which also sets PWM smoothness with PULSE 50 and MIRROR | re-range | param-tables | none (no range located) | Larger sizes for cleaner aliasing; free-run size |
| MULT, WARP and SCAN parameters; SCAN is a mirror position from 0 to 200 percent on shapes 0 to 8 and a frame scan on wave tables | re-range / replace | render-voice | none (no voice hook) | Different mirror law; interpolated frame scan |
| Wavsynth FILTER list: LP, HP, BP, BS, LP>HP, ZDF LP, ZDF HP, and the four WAV filters applied into the waveform | extend / replace | param-tables | partial (static patch: rename filter type names only) | Add a ladder or comb filter; rename WAV LP |
| Filter DSP: CUTOFF and RES mapping and the filter itself | replace / re-range | render-voice | none (no voice hook) | Cutoff curve in semitones; self-oscillating resonance |
| AMP and LIM list: CLIP, SIN, FOLD, WRAP, POST, POST:AD, POST:W1 to W3 | extend / replace | render-voice | none (LIM names not located; no DSP hook) | Add a tube or tape saturator; a bitcrush limit mode |
| Gain stage order: amp pre-filter versus POST modes applied after the filter | replace | render-voice | none (no voice hook) | Choose position per instrument |
| Per-instrument mixer parameters DRY, MFX, DEL, REV feeding the mixer channel and the three sends | re-range / extend | render-master | partial (static patch: rename send names only; no level hook) | Add a fourth send; pre-fader sends |

## Macrosynth

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| SHAPE list of 44 models, one engine selection per instrument | extend / replace | param-tables | none (model list not located) | Add a model; hide unwanted models |
| TIMBRE and COLOR: two generic parameters whose meaning depends on the model | re-range / replace | render-voice | none (no voice hook) | Per-model scaling; model-specific labels |
| DEGRADE (sample-rate reduction) and REDUX (bit reduction) effects | replace / re-range | render-voice | none (no voice hook) | Noise-shaped bit reduction; anti-aliased decimation |
| Macrosynth filter, AMP/LIM and DRY/MFX/DEL/REV parameter blocks (same set as the other engines) | observe | render-voice | none (no voice hook; only label rename possible) | Shared filter replacement across all engines |

## Sampler

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Sample source: stereo or mono PCM .wav only, loaded or recorded from the instrument | extend / veto | storage | none (no storage hook) | Accept 24-bit or float wav; accept flac |
| Upper pitch limit enforced from bit depth and channel count because of SD streaming | re-range / veto | render-voice | none (limit not located) | Raise the limit with a RAM cache; warn when exceeded |
| SLICE: equal-length slicing mapped from the lowest octave (C-1) upward | extend / re-range | notes | none (no note-path hook) | Transient-detected slices; slice-to-key mapping from C0 |
| PLAY mode list: FWD, REV, FWDLOOP, REVLOOP, FWD PP, REV PP, OSC, OSC REV, OSC PP, REPITCH/BPM | extend / replace | param-tables | none (mode names not located) | Granular play mode; one-shot gate mode |
| OSC modes ignoring start and not restarting on retrigger | replace | render-voice | none (no voice hook) | Phase-reset option for OSC modes |
| REPITCH/BPM pitching a sample to song tempo with a STEPS/BPM correction | replace / extend | sequencer-timing | none (no tempo or voice hook) | Time-stretch instead of repitch |
| START, LOOP ST. and LEN positions | re-range | param-edit | none (no ranges located) | Finer positioning; negative loop start |
| DETUNE centred at 80, high digit in semitones and low digit in sixteenths of a semitone | re-range / replace | param-edit | none (no edit path) | Cent steps; wider than the stated span |
| DEGRADE: any value above 00 also turns off sample interpolation | replace | render-voice | none (no voice hook) | Separate interpolation switch; hermite or sinc quality |
| Sampler filter, AMP/LIM and DRY/MFX/DEL/REV parameter blocks | observe | render-voice | none (no voice hook) | Per-sample filter replacement |

## FM Synth

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Four operators with a 12-entry algorithm list (ALGO); the last is additive mode | extend / replace | param-tables | none (algorithm table not located) | Algorithms with feedback loops; six-operator routing |
| Operator count of four (A, B, C, D) | re-range | render-voice | none (no limit located) | Six operators |
| Operator shape list (12 base shapes: SIN, SW2 to SW6, TRI, SAW, SQU, PUL, IMP, NOISE, then wavetable shapes from W) | extend / replace | param-tables | none (shape list not located) | Add additional operator waves |
| RATIO per operator (for example 2.00 is an octave up) | re-range / replace | param-edit | none (no edit path; range not stated) | Fixed-frequency operators; subharmonic ratios |
| LEV/FB: operator level and feedback | re-range / replace | render-voice | none (no voice hook) | Different feedback law; negative feedback |
| MOD slots per operator (two) assigning MOD1 to MOD4 to LEV, RAT, PIT or FBK | extend / re-range | param-tables | none (destination list not located) | More slots; more destinations such as shape or pan |
| MOD amounts: RAT adds 0.00 to +16.00, PIT adds semitones, LEV and FBK scale down from the set value | re-range / replace | param-tables | none (ranges not located) | Bipolar RAT; wider pitch range |
| MOD1 to MOD4 source values shared by all operators | extend | render-voice | none (no modulator hook) | Let FM mods read other instruments' modulators |
| Operator copy (SHIFT+OPTION) and paste (SHIFT+EDIT) when the cursor is in an OP region | observe / extend | sequencer-edit | none (no key event) | Swap operators; paste only ratio |
| Algorithm and shape diagrams drawn on the instrument screen | draw | ui-screen | none (no draw event) | Animated signal flow; larger diagrams |
| FM Synth filter, AMP/LIM and DRY/MFX/DEL/REV parameter blocks | observe | render-voice | none (no voice hook) | Shared filter replacement |

## Hypersynth

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Chord engine: six intervals, each two detuned saws, plus a square sub-oscillator | replace / re-range | render-voice | none (no voice hook) | Eight voices; supersaw with more saws |
| CHORD: 16 banks of up to six intervals, editable with copy and paste (SHIFT+OPTION, SHIFT+EDIT) | extend / re-range | param-tables | none (chord bank not located) | Load chord banks from a file; more banks |
| SCALE selection: one of the song scales or 00 for the song/track scale | veto / extend | notes | none (no scale hook; scale names only renamable) | Quantise chord notes to a custom scale |
| SHIFT: cross-fade between first three and second three intervals | replace | render-voice | none (no voice hook) | Per-interval level; morph between banks |
| SWARM detune and WIDTH stereo spread (00 mono to FF full stereo) | re-range / replace | render-voice | none (no voice hook) | Wider than full stereo; random phase per note |
| SUBOSC: mix of a sub two octaves down below 80 or one octave down above 80 | re-range / replace | render-voice | none (no voice hook) | Selectable sub waveform; sub of the chord root |
| Hypersynth filter, AMP/LIM and DRY/MFX/DEL/REV parameter blocks | observe | render-voice | none (no voice hook) | Shared filter replacement |

## External Instrument

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| External instrument as a hybrid: MIDI notes and FX out, audio returned through the instrument's filter and amp stage | replace / extend | midi-out | none (no MIDI or audio hook) | Insert FX on return audio; software-synth bridge |
| Audio return routed to the instrument's playing track, with a warning about doubling mixer input volumes | observe / replace | render-master | none (no routing hook) | Auto-mute the matching mixer input |
| Render and selection-render are impossible for this instrument because of real-time input; recording works only via the Sample Editor with the track as input | veto / extend | sampling | none (no render hook) | Offline render with a synthetic input; record-all-tracks |
| INPUT selection: line-in stereo/left/right, USB stereo/left/right, or line-in plus USB | extend / re-range | render-master | partial (static patch: rename routing names only; no routing hook) | Per-instrument input gain; add a mic option |
| PORT: MIDI and USB, MIDI only, USB only, or Internal (for track MIDI input and global MIDI CCs) | extend / re-range | midi-out | none (no MIDI hook) | Add a second USB port; a network MIDI target |
| CHANNEL selection 1 to 16 | re-range | midi-out | none (no limit located) | Channel per note; omni send |
| BANK:PG optional bank select and program change, also available as an FX command | replace / extend | midi-out | none (no MIDI hook) | Program list names; bank/program sweep per row |
| CC[A-D] CC:VAL: four user CC numbers with optional default values sent with note-on after the program change | re-range / extend | midi-out | none (no MIDI hook) | More than four CCs; send defaults on song load |
| Ordering rule: program change, then default CC values, then note-on | replace | midi-out | none (no MIDI hook) | Insert a delay between bank change and note-on |
| External instrument filter, AMP/LIM and DRY/MFX/DEL/REV parameter blocks | observe | render-voice | none (no voice hook) | Shared filter replacement |

## MIDI Out

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| MIDI Out instrument: sends through USB MIDI and the TRS type A output | replace / extend | midi-out | none (no MIDI hook) | Route to a second TRS port; MIDI filter |
| PORT choices: MIDI and USB, MIDI only, USB only, Internal | extend | midi-out | none (no MIDI hook) | Add an Internal-loopback mode per track |
| CHANNEL selection 1 to 16 | re-range | midi-out | none (no limit located) | Per-note channel; MPE channel rotation |
| BANK:PG optional bank select and program change, also as an FX command | replace / extend | midi-out | none (no MIDI hook) | Program name lookup for hardware synths |
| CC[A-J] CC:VAL: up to 10 user CC numbers with default values per MIDI instrument | re-range / extend | midi-out | none (no MIDI hook) | 16 CC slots; per-CC curve and range |

## Instrument FX Commands

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Rule that almost every instrument parameter has an FX command, with a per-instrument command help list | extend / observe | fx-commands | none (no FX dispatch hook or command table) | Add commands for new parameters automatically |
| Default FX command set to the highlighted instrument parameter when navigating to phrase or table | observe / replace | fx-commands | none (no key event or command table) | Choose a different default; recent-command memory |
| VOL XX: offset to instrument volume | replace / re-range | fx-commands | none (no FX dispatch hook) | Absolute-volume variant; volume curve |
| PIT XX: note pitch offset in semitones | replace / re-range | fx-commands | none (no FX dispatch hook) | Microtonal offsets; scale-aware pitch offset |
| FIN XX: fine pitch offset from -1 to +1 semitone | re-range | fx-commands | none (no FX dispatch hook) | Wider fine range; cents steps |
| EA1/EA2 XX: offset envelope amount for modulators one and two | replace | fx-commands | none (no FX dispatch hook) | Targets for modulators three and four |
| AT1/AT2 XX: offset envelope attack time | replace | fx-commands | none (no FX dispatch hook) | Scale in milliseconds |
| HO1/HO2 XX: offset envelope hold time | replace | fx-commands | none (no FX dispatch hook) | Hold in steps |
| DE1/DE2 XX: offset envelope decay time | replace | fx-commands | none (no FX dispatch hook) | Decay by tempo fraction |
| ET1/ET2 XX: retrigger the envelope when XX is above 00 | veto / replace | fx-commands | none (no FX dispatch hook) | Use XX as retrigger velocity or depth |
| LA1/LA2 XX: offset LFO amount | replace | fx-commands | none (no FX dispatch hook) | Cover slots three and four |
| LF1/LF2 XX: offset LFO frequency | replace | fx-commands | none (no FX dispatch hook) | Tempo-fraction rates |
| LT1/LT2 XX: retrigger LFO with XX as the start phase | replace / extend | fx-commands | none (no FX dispatch hook) | Retrigger with random phase |
| Command naming pattern [1-2] covers only modulators one and two, though four slots exist | extend / re-range | fx-commands | none (no command table) | Commands for modulators three and four |

## Macrosynth Models

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| The model list of the Macrosynth (Braids-derived models from CSAW through DIGITAL MOD, each with its own TIMBRE and COLOR meaning): add, replace or retune a model | extend / replace | render-voice | none (model table and DSP not located) | Plaits models; swap in a different physical model |
| Per-model TIMBRE and COLOR meaning and value text, for example COLOR 80 as the no-feedback point on SAW COMB or the 00/40/80 interpolation steps on WAV LINE | re-range / replace | param-tables | none (no parameter table located) | Show model-specific labels; reshape the response curve |
| Triggered models (for example BOWED needs a trigger or gate) and models using the main pitch as a filter or carrier frequency | veto / replace | render-voice | none (no voice or note hook) | Retrigger policy per model; tune the bridged filter |

## Wavsynth: Wave Table Index

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| The wave table list: indices 09 to 45 in groups OSC, BNK, HRM, EFX, VOX, each table with frame positions 00 to FF (diagram only; text scrambled, some tables show fewer frame rows) | extend / replace | param-tables | none (table data and list not located) | Load tables from SD card; replace a table with a custom set |
| Frame position steps within a table (steps of 04 up to 50, then roughly 04 to FF) used by the SCAN parameter and FM wave shapes | re-range | param-tables | none (no range located) | Finer scan resolution; more than 64 frames |

## Cross-cutting primitives

- Parameter-change dispatch: parameter id + instrument + new value, to observe or veto or rescale any edit (Instrument View, all engines, modulation fields, FM operator fields).
- Parameter descriptor table: id, label, min, max, default, step, value-text formatter; feeds range, default, large and small step, and help text rows across every engine.
- Enum list table: instrument types, filter types, LIM modes, LFO shapes, trigger modes, play modes, FM algorithms and shapes, Macrosynth models, wave tables; add and replace entries.
- Modulator destination table per engine: destination id, label, apply function; the key extend point for new targets such as mixer sends and track volume.
- Modulator type table: type id, parameter set, update function; allows new modulator types and replacement of envelope, LFO and tracker behaviour.
- Modulator evaluation hook: per voice per tick, read modulator output, adjust it, or redirect it to another destination (covers MOD AMT, MOD RATE ring and slot count).
- Voice render hook: per-engine process function (wavsynth, macrosynth, sampler, FM, hypersynth) with replaceable stages: oscillator, filter, amp/LIM, degrade/redux.
- Filter and limiter stage replacement: one filter-type enum and one LIM enum shared by all engines, so one hook serves every instrument type.
- FX command dispatch: command id + value + track + instrument, with the command table adding or replacing commands such as VOL, PIT, FIN and the EA/AT/HO/DE/ET/LA/LF/LT families.
- Note-to-voice path: note, velocity and instrument id before the voice starts (TRANSP., slice mapping, velocity takeover, tracking sources, SCALE for Hypersynth).
- Instrument lifecycle events: type change, load, save, copy, paste, clear; used for presets, initial defaults and per-type slot logic.
- Key and view events for the instrument and modulation views: shortcuts, view jumps with FX-command seeding, previews, touch input.
- Draw hook for instrument pages: sliders, help text, algorithm diagrams, labels.
- MIDI-out instrument events: note, program change and CC sends with port and channel, before they leave the device.
- External audio return routing: input selection and the track the returned audio is mixed to.
- Sample streaming limits: bit depth, channel count and pitch cap enforced by the sampler.
- Per-instrument send levels (DRY, MFX, DEL, REV): read and write path to the mixer, also a destination target for modulators.
- Static label patching list: destination, modulator type, filter type and send names are the only located sites today.

Targets: 116
