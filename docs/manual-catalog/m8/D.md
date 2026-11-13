# Hook targets D: mixer, EQ editor, limiter and mix scope, effect settings, mixer and effects FX commands (Dirtywave M8 (Model:02), OS 6.5.2)

Source: `manuals/m8.txt` lines 1304-1597 (Mixer View, EQ Editor View, Limiter & Mix Scope View, Effect Settings View) and 2873-2987 (Mixer & Effects Commands). Read in full; some bullet glyphs came out as replacement marks, no content was unreadable.

Assumptions behind the coverage ratings:
- Rated only against `baseline.md`: only the TICK event (observer, no state access, no calls) and static label patching exist.
- The baseline lists no located label for mixer rows (MX, DE, RE, MIX, LIM, DJF, OTT), EQ types/modes or scope parameters, so none are rated `partial (static patch: rename only)`.
- No FX-command dispatch, parameter-edit, key, draw, audio or MIDI event exists, so every row is `none`.
- The manual is for OS 6.5.2; the target firmware is 6.6.2, so ranges and lists may differ.

## Mixer View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Per-track volume faders for the 8 tracks in the mixer, applied to the track outputs on top of instrument volume | observe / re-range | render-master | none (no mixer state or audio event) | Per-track gain trim beyond stock range; fader-linked ducking |
| Rule that a track's mixer volume also scales its three effect send levels | replace | render-master | none (no audio or mixer hook) | Decouple sends from the track fader; pre-fader vs post-fader sends |
| Send-effect return volumes "MX", "DE", "RE" as mixer cells | observe / re-range | render-fx | none (no mixer state) | Return level boost past stock max; automate returns from a mod |
| Analog line-input monitor volume and its routing into the three send effects | observe / replace | render-master | none (no input path hook) | Input gain trim; route input to a custom effect |
| USB input (host audio) level in the mix for monitoring and send routing | observe / replace | render-master | none (no USB or audio hook) | Extra USB gain stage; USB-to-send patching |
| Master signal chain order: tracks, inputs and effects, then OTT, main EQ, limiter, DJ filter, main volume | replace / extend | render-master | none (no master-stage hook) | Insert a custom master effect; reorder stages |
| Red clip bar on the graphical meter when clipping occurs | draw / re-range | ui-screen | none (no draw event) | Different clip threshold or colour; peak-hold meter |
| Limiter engages only when LIM is above 00 | replace | render-master | none (no limiter hook) | Always-on safety limiter; swap limiter algorithm |
| White compression-activity line drawn on the MIX indicator | draw | ui-screen | none (no draw event) | Gain-reduction numeric readout |
| DJ filter mode set: low-pass/high-pass, low-pass/band-stop, band-stop/high-pass | extend / replace | render-master | none (no filter hook) | Add a comb or formant DJ mode; different slopes |
| DJ filter cutoff convention: 80 is off, below is low-pass or band-stop, above is high-pass | re-range | param-tables | none (no range or curve access) | Finer sweep resolution; log curve; custom centre |
| Pressing EDIT on the DJF value opens extra options in the scope view | extend | ui-input | none (no key event) | Add a shortcut to toggle DJ filter type in the mixer |
| OTT parallel multiband compression: mix grows 00 to 80, above 80 the main mix fades out | replace / re-range | render-master | none (no master-stage hook) | Alternate compressor; change the fade-out point |
| Dual-mono input mode, switched on by setting the "--" cell beside the input volume | extend / veto | render-master | none (no input path or state) | Per-channel input gain; link or unlink channels |
| Clearing the dual-mono cell with EDIT+OPTION turns the mode off | observe | param-edit | none (no edit path) | Confirm prompt before leaving dual-mono |
| EDIT or SHIFT+RIGHT on EQ opens the EQ editor | veto / extend | ui-input | none (no key event, no view change) | Open a custom EQ or analyser view instead |
| EDIT or SHIFT+RIGHT on MIX or LIM opens the Limiter / Mix Scope view | veto / extend | ui-input | none (no key event, no view change) | Open a custom metering view |
| PLAY and SHIFT+PLAY both start or stop all tracks from the mixer | observe / replace | sequencer-transport | none (no transport event) | Make SHIFT+PLAY a different transport action |
| OPTION+SHIFT mutes the current track, hold applied if OPTION is released first | observe / replace | performance | none (no key or mute event) | Mute groups; latching mute toggle |
| OPTION+PLAY solos the current track with the same release-order hold rule | observe / replace | performance | none (no key or solo event) | Exclusive-solo or momentary-solo variants |
| OPTION+SHIFT+PLAY clears all mutes and solos | observe / extend | performance | none (no key event) | Panic that also resets mixer levels |
| EDIT with UP/DOWN edits the selected mixer value in large steps, LEFT/RIGHT in small steps | re-range | param-edit | none (no edit path) | Change step sizes; accelerating steps |
| EDIT+OPTION sets the selected mixer parameter to its default | re-range / veto | param-edit | none (no defaults accessible) | Custom defaults per parameter; lock a parameter |
| SHIFT+OPTION stores a temporary song snapshot of the whole song | extend / replace | performance | none (no key or state access) | Multiple snapshot slots; snapshot to SD |
| SHIFT+EDIT recalls the snapshot taken with SHIFT+OPTION | extend / veto | performance | none (no key event) | Undo stack; quantised recall |
| OPTION plus touchscreen assigns a touchscreen axis to the selected parameter | extend | ui-input | none (no touch or key event) | Extra axes; XY pad for master filter |
| OPTION plus a MIDI CC assigns that CC to the selected parameter | extend | midi-in | none (no MIDI event) | Learn mode with scaling or range clamp |

## EQ Editor View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| EQ instances: one 3-band parametric EQ per instrument plus main mix, ModFX, Delay and Reverb | extend / replace | render-master | none (no EQ stage hook) | Add EQ on individual tracks or master out; swap EQ DSP |
| 128 assignable instrument EQ banks shared via bank number on Instrument and Instrument Pool views | re-range | param-tables | none (no limit or table access) | Raise bank count; per-track EQ banks |
| Band names LOW, MID, HIGH as labels matching default settings | draw / re-range | param-tables | none (site not located) | Rename bands; different default frequencies |
| Band GAIN in dB, boost or cut | re-range | param-tables | none (no range access) | Wider gain range; non-linear gain curve |
| Band FREQ, the centre or corner frequency | re-range | param-tables | none (no range or curve access) | Extended frequency range; finer low-end steps |
| Band Q (bandwidth) | re-range | param-tables | none (no range access) | Steeper Q for notch use |
| Band TYPE list: LOWCUT, LOWSHELF, BELL, BANDPASS, HI.SHELF, HI.CUT, ALLPASS | extend / replace | param-tables | none (no enum list or DSP access) | Add tilt or notch type; replace shelf curve |
| Band MODE list: STEREO, MID, SIDE, LEFT, RIGHT | extend | param-tables | none (no enum list access) | Add a per-band stereo-width mode |
| Per-band filter DSP applied to the stereo signal under each MODE | replace | render-master | none (no audio hook) | Linear-phase or analog-modelled EQ |
| OPTION exits the EQ editor back to the mixer | veto / replace | ui-input | none (no key event) | Return to the view that opened the EQ |
| EDIT+EDIT double tap mutes or unmutes the current EQ | observe / extend | performance | none (no key event) | Per-band bypass; A/B compare |
| PLAY here starts or stops all tracks, or previews the instrument when opened from Instrument Pool | observe / replace | sequencer-transport | none (no transport or key event) | Audition with a fixed test note |
| SHIFT+OPTION copies the EQ bank | extend | param-edit | none (no edit path) | Copy to several banks at once |
| SHIFT+EDIT pastes the EQ bank | veto / extend | param-edit | none (no edit path) | Paste only selected bands |

## Limiter & Mix Scope View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Scope histogram of volume and limiter compression over time, reached from MIX, LIM, DJF or OTT | draw / replace | ui-screen | none (no draw event) | Spectrum or loudness view |
| MIX selection shows main mix volume at bottom and limiter activity on top; LIM shows limiter input below | draw | ui-screen | none (no draw event) | Add a post-limiter trace |
| ZOOM sets the lower dB limit of the scope histogram | re-range | param-tables | none (no range access) | Deeper floor; auto-zoom |
| PEAK readout of current main-mix peak dB, auto-reset when MIX or LIM change | observe / replace | render-master | none (no audio or meter access) | True-peak or hold-forever peak |
| OPT+EDIT on PEAK clears the peak value | observe / extend | param-edit | none (no edit path) | Clear on transport start |
| Main song volume MIX (applied after the limiter) | re-range / replace | render-master | none (no master volume access) | Master fader curve; fade-out mod |
| SOFT CLIP saturation after the limiter, exaggerated by raising MIX | replace / extend | render-master | none (no master-stage hook) | Alternate saturation curve; drive amount |
| Limiter amount LIM as a value | re-range | param-tables | none (no range access) | Finer threshold steps |
| Limiter attack ATK, 0 to 100 ms with on-screen conversion help text | re-range | param-tables | none (no range or help text access) | Sub-millisecond attack; lookahead |
| Limiter release REL, 4 to 1000 ms | re-range | param-tables | none (no range access) | Longer release range |
| REL value 00 selects AUTO release, adapting 100 to 900 ms to compression amount | replace | render-master | none (no limiter hook) | Different auto-release law |
| DJF cutoff control in the scope view (00-80 low-pass, 80-FF high-pass) | re-range | param-tables | none (no range access) | Alternative cutoff mapping |
| DJ filter TYPE parameter, three combinations | extend | param-tables | none (no enum list access) | Add a fourth filter combination |
| DJ filter RES (resonance) | re-range / replace | render-master | none (no filter hook) | Self-oscillating resonance |
| OTT mix amount in the scope view, fade-out of main mix at 80 and above | re-range | param-tables | none (no range access) | Separate wet and fade controls |
| OTT TIME, compressor envelope time as 10% to 1000% | re-range | param-tables | none (no range access) | Extend range; tempo-synced time |
| OTT COLOR shifts band edges and low/high gains, above 80 toward treble, below toward bass | replace / re-range | render-master | none (no compressor hook) | Custom band split; per-band gain |
| OPTION exits the scope view back to the mixer | veto | ui-input | none (no key event) | Return to the originating row |

## Effect Settings View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Opening the effect settings view with SHIFT+DOWN from the mixer | extend / veto | ui-input | none (no key event, no view change) | Extra effects page; shortcut from other views |
| Three send effects (ModFX, Delay, Reverb) fed by the instrument MFX/DEL/REV sends and by audio and USB inputs | extend / replace | render-fx | none (no send or audio hook) | Add a fourth send; route sends in series |
| ModFX type select: Chorus, Phaser, Flanger | extend / replace | render-fx | none (no enum list or DSP access) | Add a vibrato or rotary type |
| ModFX INPUT EQ (EQ before the effect) | observe / replace | render-fx | none (no EQ hook) | Fixed high-pass before the chorus |
| ModFX MOD DEPTH | re-range | render-fx | none (no range access) | Deeper depth than stock |
| ModFX MOD FREQ (modulation speed) | re-range / extend | render-fx | none (no range access) | Tempo-synced LFO rate |
| ModFX WIDTH, 00 mono to FF stereo | re-range | render-fx | none (no range access) | Over-wide stereo |
| ModFX REVERB SEND | re-range | render-fx | none (no range access) | Pre-reverb ducking send |
| Delay INPUT EQ | observe / replace | render-fx | none (no EQ hook) | Filter the repeats |
| Delay TIME L:R, first digit beats, second digit fraction of a beat (for example 40 is 4 beats) | re-range / replace | render-fx | none (no range or tempo access) | Free millisecond times; triplet or dotted values |
| Delay FEEDBACK | re-range | render-fx | none (no range access) | Feedback above stock max with limiter |
| Delay WIDTH, 00 mono to FF stereo | re-range | render-fx | none (no range access) | Narrow-to-mono ping-pong |
| Delay REVERB SEND | re-range | render-fx | none (no range access) | Series delay into reverb |
| Delay ping-pong algorithm bouncing between left and right | replace | render-fx | none (no DSP hook) | Tape delay model; multi-tap |
| Reverb INPUT EQ | observe / replace | render-fx | none (no EQ hook) | Dark or bright reverb input |
| Reverb SIZE (room size) | re-range | render-fx | none (no range access) | Larger spaces |
| Reverb DECAY | re-range | render-fx | none (no range access) | Infinite-decay range |
| Reverb SHIMMER, pitched feedback for octave-up shimmer | extend / replace | render-fx | none (no DSP hook) | Choose shimmer interval |
| Reverb MOD DEPTH | re-range | render-fx | none (no range access) | Heavier modulation |
| Reverb MOD FREQ | re-range | render-fx | none (no range access) | Slow-drift LFO |
| Reverb WIDTH, 00 mono to FF stereo | re-range | render-fx | none (no range access) | Mono-compatible reverb |
| Reverb algorithm (simple modulated reverb tuned against metallic ringing) | replace | render-fx | none (no DSP hook) | Plate or spring model |

## Mixer & Effects Commands

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Rule that mixer and effect commands write the same stored value shown in the Mixer or Send Effects view | observe / veto | fx-commands | none (no FX-command or parameter event) | Make commands transient, not overwriting the view value |
| EQM XX: assign the main song EQ to an EQ slot | observe / replace | fx-commands | none (no FX-command dispatch hook) | Bank morph; EQ switch per section |
| EQI XX: assign the current instrument's EQ to a slot | observe / replace | fx-commands | none (no FX-command dispatch hook) | Per-note EQ switching |
| VMV XX: set main song volume | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Master fade commands; ramp over time |
| XMT XX: ModFX type and phase position | extend / re-range | fx-commands | none (no FX-command dispatch hook) | Extra ModFX types reachable by command |
| XMM XX: ModFX mod depth | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Slewed modulation depth |
| XMF XX: ModFX mod frequency | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Tempo-synced rate by command |
| XMW XX: ModFX stereo width | observe | fx-commands | none (no FX-command dispatch hook) | Width sweep |
| XMR XX: ModFX to reverb send | observe | fx-commands | none (no FX-command dispatch hook) | Gated reverb send |
| XDT XY: delay left (X) and right (Y) times in large increments | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Fine time values; sync to groove |
| XDF XX: delay feedback | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Throw or kill feedback commands |
| XDW XX: delay stereo width | observe | fx-commands | none (no FX-command dispatch hook) | Width automation |
| XDR XX: delay to reverb send | observe | fx-commands | none (no FX-command dispatch hook) | Delay-into-reverb throws |
| XRS XX: reverb room size | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Size morph |
| XRD XX: reverb decay | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Decay ducking |
| XRM XX: reverb mod depth | observe | fx-commands | none (no FX-command dispatch hook) | Depth automation |
| XRF XX: reverb mod frequency | observe | fx-commands | none (no FX-command dispatch hook) | Rate automation |
| XRW XX: reverb stereo width | observe | fx-commands | none (no FX-command dispatch hook) | Width automation |
| XRZ XX: freeze reverb when value above 00, otherwise off | observe / replace | fx-commands | none (no FX-command dispatch hook) | Freeze with release fade; momentary freeze |
| VMX XX: ModFX return volume (Mixer view value) | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Return level sweeps |
| VDE XX: delay return volume | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Delay throw volume |
| VRE XX: reverb return volume | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Reverb swell |
| VT1 to VT8 XX: per-track volume (one command per track number, Mixer view value) | observe / extend | fx-commands | none (no FX-command dispatch hook) | Track fade commands; ducking from another track |
| DJC XX: DJ filter cutoff | observe / re-range | fx-commands | none (no FX-command dispatch hook) | Filter sweep commands with interpolation |
| DJR XX: DJ filter resonance | observe | fx-commands | none (no FX-command dispatch hook) | Resonance accents |
| DJT XX: DJ filter type | observe / extend | fx-commands | none (no FX-command dispatch hook) | Extra filter types by value |
| IVO XX: analog line input volume | observe | fx-commands | none (no FX-command dispatch hook) | Input mute or ducking in song |
| IMX XX: analog input send to ModFX | observe | fx-commands | none (no FX-command dispatch hook) | Rhythmic input sends |
| IDE XX: analog input send to delay | observe | fx-commands | none (no FX-command dispatch hook) | Input delay throws |
| IRV XX: analog input send to reverb (the manual's prose spells it IRE; the heading says IRV) | observe | fx-commands | none (no FX-command dispatch hook) | Accept both spellings |
| IV2 XX: second input (dual-mono right channel) volume | observe | fx-commands | none (no FX-command dispatch hook) | Independent right-channel mute |
| IM2 XX: second input send to ModFX | observe | fx-commands | none (no FX-command dispatch hook) | Per-channel sends |
| ID2 XX: second input send to delay | observe | fx-commands | none (no FX-command dispatch hook) | Per-channel sends |
| IR2 XX: second input send to reverb | observe | fx-commands | none (no FX-command dispatch hook) | Per-channel sends |
| USB XX: USB input volume | observe | fx-commands | none (no FX-command dispatch hook) | Song-driven USB ducking |
| Rule that the second-input commands only apply while dual-mono input mode is on | veto | fx-commands | none (no FX-command dispatch hook) | Warn when used outside dual-mono |

## Cross-cutting primitives

- FX command dispatch hook (command id + value + track, able to replace or add): XMT to XRZ, VMV, VMX/VDE/VRE, VT1-8, DJC/DJR/DJT, IVO..IR2, USB, EQM, EQI, and the set-stored-value rule.
- Mixer/effect parameter registry (id, range, default, step sizes, value text, enum list): all EQ band parameters, scope parameters, ModFX/Delay/Reverb parameters, DJ filter and OTT ranges.
- Parameter-edit event (view, parameter id, old/new value, large/small step, default reset), able to veto: the EDIT+arrows, EDIT+OPTION, PEAK clear and dual-mono clear rows.
- Master-chain stage list (tracks, inputs, sends, OTT, EQ, limiter, DJ filter, soft clip, main volume): insert, bypass, reorder or replace a stage; used by master effects and the limiter/OTT/soft-clip rows.
- Send-effect DSP replace/extend (ModFX, Delay, Reverb algorithms, type enum, input EQ stage, reverb-send routing): effect rows plus MX/DE/RE returns.
- EQ DSP and bank table (128 banks, band type/mode enums, per-instrument and per-effect instances): all EQ editor rows.
- Meter and scope data feed (peak, limiter gain reduction, input level) plus a draw event for the scope, clip bar and MIX indicator.
- Key event with view context (key combo, current view, cursor row), able to veto or consume: view-open shortcuts, mute/solo/snapshot, copy/paste EQ bank, EQ mute double-tap.
- View-change request call (open EQ editor, scope view, effect settings from a mod): all entry-point rows.
- Mute/solo and snapshot state access (read/set, hold-on-release rule): the performance rows.
- MIDI CC and touchscreen mapping table (assign, scale, range clamp): the OPTION+touch and OPTION+CC rows.
- Tempo and groove read access for delay time in beats and tempo-synced rates.
- Parameter smoothing/interpolation helper for ramped master and effect changes by command.
- Label table access for renaming mixer and EQ labels (MX, DE, RE, LOW/MID/HIGH, EQ types) once their sites are located.

Targets: 117
