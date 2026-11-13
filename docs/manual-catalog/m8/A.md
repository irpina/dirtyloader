# Hook targets A: panel, key shortcuts, project, settings, theme, MIDI, render, sample editor, USB (Dirtywave M8 (Model:02), OS 6.5.2)

Source: m8.txt lines 330-610, 1598-1944, 2152-2236, 2480-2660, 3965-4052 (all read). Key-combination diagrams in the Key Shortcuts appendix are two-column scrambled; entries were reassembled by reading each column separately. The physical-layout diagrams (lines 335-373) and the View Layout and USB Audio Routing diagrams are images and give no text; the USB MAIN OUT routing options cannot be read.

Assumptions behind the coverage ratings:
- Rated only against baseline.md: the sole event is TICK (observer, no arguments, no firmware state readable, no calls). No key, draw, MIDI, audio, parameter, row or FX event exists.
- No tables and no calls are exposed, so nothing can be read, set, vetoed or replaced from a mod.
- Static patching counts only for the located label strings (parameter labels, modulation destination names, send names, scale names, the input/track routing name list). Every other string or value is `none (site not located)` or plain `none`.
- Screen rows are `none` unless the exact text is a located site.
- Behaviour behind a located label is never reachable; only a same-size rename is.

## Overview, Physical Layout and Power

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Power button hold times: 1 s on, 2 s off, 7 s forced power-down for a crash | re-range | settings/boot | none (no boot or input event; hardware button path not located) | Shorter or longer off hold; confirm-before-off |
| Battery level and charging indicator at top right of the display, animated while charging | draw | ui-leds | none (no draw event) | Percentage readout; low-battery warning |
| Header status items: current song tempo, track note monitor, screen-position mini-map | draw | ui-screen | none (no draw event) | Per-track VU in the note monitor; larger mini-map |
| Charging allowed while operating, 500 mA USB source assumed | observe / replace | settings/boot | none (no power or USB event) | Show charge current; block play while charging |
| Startup output volume recall: ceiling of F0 at power-up regardless of previous setting | re-range / veto | settings/boot | none (no boot event, no state access) | Remember last volume above F0 behind a switch; lower cap |
| Built-in speakers cut when an output connector is plugged in | replace | render-master | none (no audio or jack event) | Keep speakers on alongside headphones |
| OUTPUT VOL setting in the Mixer view, edited with EDIT plus direction | re-range | param-tables | none (no parameter range located) | Finer steps; wider range above F0 |
| Playback halted with a CPU TOO BUSY message when SD reads cannot keep up | observe / replace | sampling | none (no state, no draw) | Show SD load meter; soft-degrade instead of halting |
| Samples streamed from the SD card, not held in memory, with read cost doubling per octave up | replace | sampling | none (no audio or storage event) | Preload short samples into RAM; warn about costly notes |

## Getting Started (Introduction and Song Structure)

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Track count: eight functionally identical monophonic tracks | re-range | sequencer-transport | none (no count located) | More or fewer tracks |
| Instrument count: up to 128 instruments per song, one per track note | re-range | param-tables | none (no limit located) | Raise instrument slots to 256 |
| Per-track independent play position through a list of chains, looping back to the start at an empty entry | replace | sequencer-transport | none (no transport event) | Stop-at-end option; ping-pong song rows |
| Song > Chain > Phrase hierarchy where phrases hold notes, velocity, instrument and FX commands | extend | sequencer-edit | none (no sequencer event) | Extra per-step column; a fourth FX column |

## Navigation

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| SHIFT plus direction moves between views; the view map layout decides what each direction reaches | replace / extend | ui-input | none (no input event, no view call) | Add a new view in the grid; rebind direction jumps |
| Mini-map drawn bottom right showing the current view position | draw | ui-screen | none (no draw event) | Highlight modified views; extra view icons |
| SHIFT alone does nothing | extend | ui-input | none (no input event) | Tap SHIFT for a quick menu |

## Global Key Shortcuts

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Direction keys move the cursor | observe / replace | ui-input | none (no input event) | Wrap-around cursor; jump-by-16 |
| EDIT starts editing a value and acts as YES or ENTER in prompts | observe / veto | ui-input | none (no input event) | Confirm-lock for destructive prompts |
| OPTION acts as NO or EXIT and varies by context | observe / replace | ui-input | none (no input event) | Context menu on OPTION hold |
| EDIT plus OPTION resets a parameter to default, or cuts on grid views | replace | ui-input | none (no input event) | Reset to a per-user default; cut with undo |
| PLAY starts or stops from the cursor in Song view, or plays the current chain, phrase or instrument in those views | observe / replace | sequencer-transport | none (no transport or input event) | Play-from-bookmark; play only soloed chain |
| SHIFT plus PLAY plays all tracks from the song cursor regardless of view | observe / replace | sequencer-transport | none (no transport event) | Play-from-row-0 variant |
| Fine versus coarse editing: EDIT plus left or right small steps, EDIT plus up or down large steps | re-range | param-edit | none (no edit path or step size located) | Custom step sizes; accelerated repeat |
| EDIT on an empty cell inserts the last edited or deleted value as default | replace | param-edit | none (no edit path) | Insert a fixed default note or smart-previous value |
| EDIT plus UP or DOWN on a command column opens the Effect Help view | observe / veto | ui-input | none (no input event) | Open custom command picker |
| SHIFT plus OPTION on any grid view enters selection mode | observe | sequencer-edit | none (no input event) | Add extra selection modes |
| OPTION in selection mode copies the selection and exits | replace | sequencer-edit | none (no edit event) | Multi-slot clipboard |
| SHIFT plus EDIT on any grid pastes the copied contents | replace / extend | sequencer-edit | none (no edit event) | Paste-special: transpose or invert on paste |
| EDIT plus OPTION in selection mode cuts into the copy buffer | replace | sequencer-edit | none (no edit event) | Cut that keeps a ghost undo |

## Hexadecimal

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Hex value entry and display for 00-FF everywhere, with signed relative reading in places | replace | param-edit | none (no edit or value-text path) | Decimal display toggle; signed display everywhere |
| Help line at the screen bottom showing decimal equivalent and messages while editing | draw | ui-screen | none (no draw event) | Show note names, Hz or ms next to the value |
| Counts-of-16 parameters where the first digit selects a phrase and the second a row | re-range | param-edit | none (no edit path) | Longer phrases beyond 16 rows |
| Two-nibble FX commands where left and right digits control separate aspects | extend | fx-commands | none (no FX dispatch hook) | Commands that read both nibbles differently |

## Firmware Updates

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Firmware update flow over USB from a host computer, with recovery via an internal reset button | observe / veto | settings/boot | none (no boot event; bootloader outside the mod) | Block updates when a mod is installed; version check |
| Firmware version shown at the bottom left of the Song screen for a few seconds after boot | draw | ui-screen | none (no draw event; text site not located) | Append the loader version to the banner |

## Loading a Demo Song

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| A demo song loaded by default on first use, with the /DEMOS folder on the SD card | replace | storage | none (no storage event) | Ship a mod showcase song |
| Project view sits above Song view in the view layout | extend | ui-input | none (no view call) | Add a view above Project |
| File browser opens at /Songs on load, entries starting with / are directories, /.. goes up | replace | storage | none (no storage event) | Remember last folder; add bookmarks |
| File browser LEFT to top and RIGHT to bottom of the list | replace | ui-input | none (no input event) | Page-jump or letter-jump |
| File browser OPTION plus UP or DOWN skips 8 entries | re-range | ui-input | none (no input event) | Change skip count |
| File browser PLAY previews a song, sample or instrument | extend | sampling | none (no input or audio event) | Preview waveform before loading |
| File browser SHIFT plus OPTION sorts an unsorted directory by name | replace | storage | none (no input event) | Sort by date or size; auto-sort |
| File browser OPTION exits the browser | observe | ui-input | none (no input event) | Return to last folder state |
| File browser OPTION plus EDIT deletes a file | veto | storage | none (no input event, no storage event) | Move to trash folder instead of deleting |
| Queued Song Loading: while playing, a newly loaded song starts after the current chain ends | replace | sequencer-transport | none (no transport event) | Switch at song end or on bar; crossfade between songs |

## Project View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| TEMPO in BPM with tap-tempo by rhythmic EDIT presses | re-range / replace | sequencer-transport | none (no tempo state or event) | Wider BPM range; averaging tap algorithm |
| TRANSPOSE in semitones, only affecting instruments with TRANSP. enabled, applied on EDIT release | re-range / replace | notes | none (no note path) | Apply on next bar; per-track transpose |
| GROOVE song default, taking effect when EDIT is released | replace | sequencer-timing | none (no timing event) | Apply on bar boundary |
| SCALE song default, taking effect when EDIT is released | replace | notes | none (scale name strings only are located; partial for renaming a scale, behaviour unreachable) | Per-track default scale |
| LIVE QUANTIZE cue-waiting behaviour when playing a chain in live mode | extend / re-range | sequencer-transport | none (no transport event) | Add quantize-to-bar options |
| MIDI: SETTINGS and MIDI: MAPPINGS entries leading to sub-views | extend | ui-screen | none (no view call) | Extra MIDI sub-view |
| NAME entry for the current song using the naming screen | replace | ui-screen | none (no draw or input event) | Autoname with date; longer names |
| LOAD, SAVE and NEW for songs | veto / replace | storage | none (no storage event) | Autosave on SAVE; backup copy; confirm overwrite |
| RENDER entry to the Render view | extend | ui-screen | none (no view call) | Quick-render shortcut |
| BUNDLE creating a /Bundles sub-folder with project, samples and instruments | extend / replace | storage | none (no storage event) | Zip bundle; include theme |
| CLEAR UNUSED freeing unused chains, phrases, instruments, EQs and tables | veto / replace | storage | none (no storage event) | Dry-run listing before clearing; protect marked items |
| INST. POOL and SETTINGS entries navigating to their views | extend | ui-screen | none (no view call) | Add a mod settings page |
| USB_DRIVE entry putting the M8 into USB drive mode to copy SD files | replace | usb | none (no USB event) | Read-only drive mode; auto-return when idle |
| Project file contents: song data, instruments, MIDI mappings and settings, but not samples | extend | storage | none (no storage event) | Store mod data inside the project |
| Output volume, speaker volume and theme colours stored internally rather than in the project | replace | storage | none (no storage event) | Per-project volume memory |
| Samples referenced by path; moving or deleting them breaks loading | replace | storage | none (no storage event) | Relink missing samples; search by name |
| Mute current track: OPTION plus SHIFT, latch by releasing OPTION first | replace | performance | none (no input event) | Mute groups; momentary mute only |
| Solo current track: OPTION plus PLAY, latched on early OPTION release | replace | performance | none (no input event) | Multi-solo; solo with fade |
| Clear all mutes and solos: OPTION plus SHIFT plus PLAY | extend | performance | none (no input event) | Restore previous mute set |
| SHIFT plus OPTION creates a song snapshot held temporarily | extend | sequencer-edit | none (no input or storage event) | Several snapshot slots; named snapshots |
| SHIFT plus EDIT recalls the song snapshot | replace | sequencer-edit | none (no input event) | Undo-style snapshot ring |
| OPTION plus touchscreen on Tempo or Transpose assigns a touchscreen axis | extend | midi-in | none (no input event) | Map more axes or more parameters |
| OPTION plus a MIDI CC on Tempo or Transpose assigns that CC | extend | midi-in | none (no MIDI event) | MIDI learn on any parameter |

## System Settings View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| BACKLIGHT brightness of the display | re-range | settings/boot | none (no settings access) | Auto-dim after idle; extra low range |
| FONT OPTIONS including a large font mode | extend | settings/boot | none (no draw event) | Custom font; mid-size font |
| THEME entry leading to the Theme view | extend | settings/boot | none (no view call) | Theme randomiser |
| NOTE PREVIEW toggle for previewing notes when editing in phrase view | replace | notes | none (no note or input event) | Preview with chosen instrument or length |
| REC. COUNT IN of phrases or measures before sample or selection recording | re-range | sampling | none (no recording event) | Count-in in beats; visual count-in |
| METRONOME VOL | re-range | render-master | none (no parameter range located) | Accent level; separate click output |
| Metronome sound taken from /System/Metronome.m8i | replace | sampling | none (no storage or audio event) | Alternative click sets |
| SONG TEMPLATE setting the open song as the new-song template | replace | storage | none (no storage event) | Multiple templates by genre |
| USB AUDIO MODE: stereo or multi-channel (8 tracks and effects, 12 stereo channels) | extend / re-range | usb | none (no USB event) | Add a subset-of-tracks mode |
| USB MAIN OUT routing behaviour of USB audio | extend | usb | none (no USB event; diagram not readable in text) | Pre-limiter send; custom bus pairs |
| LINE-IN GATE threshold from -70 dB to -10 dB | re-range | render-master | none (no parameter range located) | Lower floor; hysteresis control |
| SPLASH SCREEN enable and disable of the logo and sound at power-on | replace | settings/boot | none (no boot event) | Custom splash image or sound |
| HP PROTECTION limiting headphone volume to F0 after reinserting a plug | veto / re-range | settings/boot | none (no jack or settings access) | Change the cap value |
| KEY DELAY:REP key repeat delay and rate in milliseconds | re-range | ui-input | none (no input event) | Faster repeat floor; per-key repeat |
| BATT. CHARGING enable or disable charging while on and connected | extend | settings/boot | none (no power event) | Charge only below a threshold |
| Settings stored internally, not in the project | extend | settings/boot | none (no storage event) | Persist mod-specific settings |

## Theme View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| MODE toggle between RGB and HSV colour editing | extend | settings/boot | none (no input or draw event) | Add a hex or palette picker |
| Hue shift icon: EDIT plus direction rotates the whole theme hue | replace | settings/boot | none (no input event) | Saturation and brightness shift |
| Per-property colour list (what each theme colour controls) | extend | settings/boot | none (no theme data access) | New theme properties for added UI |
| Display colour depth limiting visible minor adjustments | re-range | ui-screen | none (no draw event) | Warn on no-visible-change edits |
| LOAD and save of preset themes from the SD card for sharing | extend / replace | storage | none (no storage event) | Theme packs; auto-theme by project |
| Default theme set shipped on the SD card | extend | storage | none (no storage event) | Bundle extra themes |
| Theme shortcuts: reset to default, coarse and fine editing, OPTION exits | replace | param-edit | none (no edit path) | Per-colour reset undo |

## MIDI Mapping View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Mapping capacity of up to 128 mappings per song | re-range | midi-in | none (no limit located) | Raise to 256; per-view mapping banks |
| One mapping per destination parameter, but one control may drive many parameters | replace | midi-in | none (no MIDI event) | Many-to-one mixing; macro knobs |
| Learn by holding OPTION and turning a CC or sliding on the touchscreen | extend | midi-in | none (no MIDI or input event) | Learn from pitch bend or aftertouch |
| Per-mapping range editing (min and max) | re-range | param-edit | none (no edit path) | Response curves; inverted ranges |
| Mapping removal via OPTION plus EDIT | veto | param-edit | none (no input event) | Confirm before deleting |
| Mappings stored in the song file | extend | storage | none (no storage event) | Mapping presets across songs |
| Incoming CC value applied to the destination parameter | replace | midi-in | none (no MIDI event) | Smoothing; soft takeover; 14-bit CC |

## MIDI Settings View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| SYNC IN options: clock, transport, clock plus transport, transport plus SPP, clock plus transport plus SPP | extend / replace | midi-in | none (no MIDI event) | External clock divider; swing from clock |
| SYNC OUT options with the same set | extend / replace | midi-out | none (no MIDI event) | Clock out ratio; send start on a delay |
| Song position pointer handling for control of song position | replace | sequencer-transport | none (no MIDI or transport event) | Map SPP to song rows or phrase-aware |
| CTRL SURFACE selection, only Novation Launchpad Pro MK3 supported | extend | midi-in | none (no MIDI event) | Support another grid controller |
| RECORD NOTE CHANNEL for incoming notes recorded into a phrase | re-range | midi-in | none (no MIDI event) | Omni channel; per-track channels |
| RECORD VELOCITY toggle for recording note velocity | replace | midi-in | none (no MIDI event) | Velocity curve or fixed velocity |
| RECORD DELAY/KILL recording DEL and KIL FX commands with incoming notes | extend | midi-in | none (no MIDI event) | Quantise on record; record other commands |
| CONTROL MAP CHANNEL for incoming CCs used by MIDI mapping | re-range | midi-in | none (no MIDI event) | Several mapping channels |
| SONG ROW CUE CHANNEL for incoming notes that cue song rows | extend / replace | midi-in | none (no MIDI event) | Notes cue chains or phrases |
| Recording incoming notes into the phrase when a note column is highlighted during playback, timed to when played | replace | midi-in | none (no MIDI event) | Step recording; overdub quantise |
| Preview of notes and instruments when the cursor is outside the note column | replace | midi-in | none (no MIDI event) | Preview instrument per channel |
| Track MIDI Input: the M8 as a sound module with independent control of each track | extend | midi-in | none (no MIDI event) | Velocity layers by channel; MPE mapping |
| Per-track CHAN selection | re-range | midi-in | none (no MIDI event) | Allow multiple channels per track |
| Per-track INST# selection | re-range | midi-in | none (no MIDI event) | Instrument by bank |
| PG CHANGE toggle selecting the instrument by MIDI program change | replace | midi-in | none (no MIDI event) | Bank select; program map table |
| Per-track MODE: MONO, LEGATO, POLY | extend | midi-in | none (no MIDI event) | Add unison-detune or round-robin mode |
| Poly mode allocation across tracks sharing a MIDI channel | replace | midi-in | none (no MIDI event) | Smarter voice stealing |
| Mono mode playing all tracks of a channel in unison | replace | midi-in | none (no MIDI event) | Stack with detune |
| Legato mode suppressing retrigger on overlap | replace | midi-in | none (no MIDI event) | Portamento on legato |
| MIDI settings stored in the song, with save and load of the default new-song configuration | extend | storage | none (no storage event) | Multiple MIDI configs |

## Time Stats View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| PLAYING time since playback started | observe / draw | ui-screen | none (no state access, no draw) | Per-session play stats |
| WORK TIME on the current song | observe / draw | ui-screen | none (no state access, no draw) | Idle-aware work timer |
| SYS. POWERED time since power on | observe / draw | ui-screen | none (no draw event) | Clock display |
| SYS. BATTERY time since a full charge, possibly offset by about 30 minutes | observe / draw | ui-screen | none (no draw event) | Battery estimate |
| SYS. TOTAL lifetime power-on | observe | settings/boot | none (no storage or state access) | Maintenance reminder |
| FILE DATE setting date and time used when saving files; not kept while powered off | extend / replace | storage | none (no storage event, no RTC access) | Sync date from USB host or MIDI |

## Render View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| SONG ROW START and SONG ROW LAST selecting the range | re-range | sampling | none (no state or edit path) | Render by loop markers |
| REPEAT SONG count | re-range | sampling | none (no limit located) | Tail length control |
| TRACKS selection of which tracks to render | extend | sampling | none (no state access) | Render groups |
| MODFX, DELAY and REVERB toggles including them in the render | replace | render-fx | none (send parameter names are located only for rename; render path unreachable) | Wet-only stem; effect tail render |
| LIMITER toggle for the render | replace | render-master | none (no audio event) | Render with a different ceiling |
| MODE bit depth 16 or 32-bit | extend | sampling | none (no storage or audio event) | Add 24-bit output |
| Output format fixed at 44.1 kHz stereo wav in /Renders | extend | storage | none (no storage event) | 48 kHz output; flac; other folder |
| NAME of the rendering | replace | ui-screen | none (no input or draw event) | Autoname from song and date |
| MIXED versus STEMS, one file per enabled track that has chains in range | extend | sampling | none (no storage event) | Stems for sends too |
| EDIT plus OPTION deleting or resetting a render parameter | replace | param-edit | none (no edit path) | Reset all |

## Selection to Sample

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Double-tap EDIT in Song view after a selection opens the create-sample dialog; OPTION cancels | observe / veto | sampling | none (no input event) | Add dialog option; veto on empty selection |
| QUICK RENDER offline render of the selection, not recording line-in or USB | replace | sampling | none (no audio event) | Include send tails |
| REALTIME mode recording all selected tracks and line-in or USB from the Mixer | replace | sampling | none (no audio event) | Include external inputs gain |
| EXTERNAL ONLY recording the first External Instrument found, else line-in plus USB mix | replace | sampling | none (no audio event) | Choose which external to record |
| New instrument created from the result and made the default instrument for new notes | replace | sequencer-edit | none (no edit or storage event) | Auto-slice or auto-name; keep default instrument unchanged |

## Effect Command Help View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Open via EDIT plus UP or DOWN on any FX command column in phrase or table view | observe / veto | ui-input | none (no input event) | Open a search or filter |
| Selection of a command by direction keys and insertion on EDIT release | replace | sequencer-edit | none (no edit event) | Favourites; insert on EDIT press |
| Command list and description text shown at the top for the highlighted effect | extend / draw | fx-commands | none (no command table; descriptions not located) | Add descriptions for new commands |

## Sample Editor

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Entry to the editor from a Sampler instrument via REC. or EDIT, exit by OPTION | extend | sampling | none (no view call) | Open from file browser |
| START recording by EDIT, or the power button to avoid key clicks | replace / extend | sampling | none (no input or audio event) | Any key as record trigger; pedal trigger over MIDI |
| SRC input source list: L&R, MIC (Model:02), USB, INL, INR, U-L, U-R, ALL, TR1-8 | extend / re-range | sampling | partial (static patch: rename only; routing name list located, the source set and routing are not) | Rename a source; add a bus source |
| VOL input volume | re-range | sampling | none (no parameter range located) | Add gain above unity |
| ARM threshold to arm and start recording from input level | re-range / replace | sampling | none (no audio event) | Hysteresis; pre-roll buffer |
| PLAY starting song playback at the indicated song row for recording external gear | replace | sampling | none (no transport event) | Start from any row with count-in |
| REC. COUNT IN interaction with recording when song playback is on | replace | sampling | none (no recording event) | Count-in with click on separate output |
| Post-recording process, naming and saving before leaving the view | veto | sampling | none (no storage event) | Warn on unsaved sample |
| SELECT start and end range with coarse, fine zoomed, and tempo-snapped beat steps | re-range / replace | param-edit | none (no edit path) | Snap to zero crossing |
| LOOP REGION start and end, stored inside the wav file | extend | sampling | none (no storage event) | Loop-point presets |
| SLICE MARKER: up to 128 markers stored in the wav, played from C-1 when SLICE is 01 FILE and cued by SLI | re-range / extend | sampling | none (no limit located) | 256 markers; slice-to-key map |
| PROCESS CROP | replace | sampling | none (no audio or edit event) | Crop with fade |
| PROCESS DELETE | replace | sampling | none (no audio or edit event) | Ripple-delete |
| PROCESS DUPLICATE | replace | sampling | none (no audio or edit event) | Duplicate with crossfade |
| PROCESS NORMALIZE to the maximum without clipping | replace | sampling | none (no audio event) | Normalize to a set dB level |
| PROCESS SILENCE | replace | sampling | none (no audio event) | Fade-based silence |
| PROCESS REVERSE | replace | sampling | none (no audio event) | Reverse with slices |
| PROCESS INVERT flipping the waveform vertically | replace | sampling | none (no audio event) | Phase-aware invert per channel |
| PROCESS FADE IN/OUT | replace / extend | sampling | none (no audio event) | Curve choice; custom fade shapes |
| PROCESS XFADE LOOP creating a crossfade loop | replace | sampling | none (no audio event) | Equal-power crossfade |
| PROCESS SQUISH (OTT) using the song's OTT colour and time mixer settings | extend / replace | sampling | none (no audio or mixer access) | Alternate multiband processor |
| PROCESS MONO MIX, LEFT, RIGHT conversion | replace | sampling | none (no audio event) | Mid-only or side-only |
| PROCESS DOWNSAMPLE halving the sample rate | replace / extend | sampling | none (no audio event) | Arbitrary sample rate; better filter |
| PROCESS 16-BIT and 8-BIT bit reduction | extend | sampling | none (no audio event) | Dithered reduction; other depths |
| PROCESS SLICE AUTO using transient detection | replace | sampling | none (no audio event) | Better detector; sensitivity control |
| PROCESS SLICE SILENC using silence detection | replace / re-range | sampling | none (no audio event) | Threshold control |
| PROCESS SLICE 0-128 evenly distributed divisions | re-range | sampling | none (no limit located) | Beat-aware or tempo-based divisions |
| Process list selected with EDIT plus left or right then tapping EDIT | extend | sampling | none (no input or list access) | Add a new process |
| NAME the sample before saving | replace | ui-screen | none (no input or draw event) | Autoname from source |
| SAVE or OVERWRITE of the current sample | veto / replace | storage | none (no storage event) | Backup before overwrite |
| OPTION plus UP or DOWN edit by 4 steps and OPTION plus LEFT or RIGHT single steps (tempo-based) | re-range | param-edit | none (no edit path) | Other beat divisions |
| EDIT or OPTION plus touchscreen edits the selected value | extend | param-edit | none (no input event) | Pinch-zoom waveform |
| Lazy chop: PLAY plus EDIT taps add slice markers at the play-head during playback | extend | sampling | none (no input or audio event) | Snap chops to grid; undo last chop |

## USB Features

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| USB audio input at 24-bit stereo | extend | usb | none (no USB or audio event) | Input metering; gain |
| USB audio output as 24-bit stereo or 12 channels in multi-channel mode | extend / re-range | usb | none (no USB event) | Choose which tracks map to which channels |
| Host operation with iOS, Android and computers as long as USB provides 500 mA | observe | usb | none (no USB event) | Host detection indicator |
| USB audio monitored in the Mixer view under USB volumes, recordable via Sample Editor and Selection to Sample | replace | render-master | none (no mixer access; the USB name label is located only as part of the routing name list) | Pan and EQ on USB input |
| USB input and output routing configuration in System Settings | extend | usb | none (no USB event) | Custom routing matrix |
| USB MIDI behaving like TRS MIDI for sync, remote control and sequencing | replace | midi-in | none (no MIDI event) | Separate channel filter per port |
| USB MIDI output of the MIDI OUT instruments | replace | midi-out | none (no MIDI event) | Route to USB only or both ports |
| Remote host display streaming the M8 screen over USB | replace / extend | usb | none (no draw or USB event) | Higher frame rate; theme-adapted capture |

## Troubleshooting

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Recovery boot via internal reset button and TyUploader labelled HalfKey | observe | settings/boot | none (no boot event; recovery bootloader is outside the mod) | Loader safe-mode flag |
| USB data cable and hub restrictions during flashing | observe | usb | none (no USB event) | Not a mod target; none beyond update gating |
| SD card not working, stuck card and format requirements | observe / draw | storage | none (no storage event) | Show a card-health message |
| Samples not listed because the wrong browser (sample load versus instrument preset) is open | replace | storage | none (no storage event) | Show both in one list |
| Sample note range above C-4 limited by bit depth and channel count | re-range | sampling | none (no audio or limit access) | Lift the cap; warn at note entry |
| Sample load failure rules: 8, 16, 24, 32-bit mono or stereo PCM, path under 128 characters | re-range / replace | sampling | none (no storage event) | Longer path; reject message with reason |
| CPU TOO BUSY message source | observe / draw | ui-screen | none (no draw event; text site not located) | Display the offending track |
| Start-up sound from the STARTUP song in /System, deleting it skips the intro | replace | settings/boot | none (no boot or storage event) | Alternative intro per theme |

## Key Shortcuts appendix (Song, Chain, Phrase, Instrument, Table, Mixer, File Browser, Selection)

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Song view: cue row while playing with LEFT plus PLAY | extend / replace | sequencer-transport | none (no input or transport event) | Cue on bar; cue by chain name |
| Song view: create new chain by double-tapping EDIT on an empty cell | replace | sequencer-edit | none (no edit event) | Create chain with presets |
| Song view: clone and paste chain alone with SHIFT plus OPTION then EDIT | replace | sequencer-edit | none (no edit event) | Clone with transpose |
| Song view: clone and paste chain with phrases via SHIFT plus OPTION then double-tap EDIT (deep clone) | replace | sequencer-edit | none (no edit event) | Deep clone with instrument remap |
| Song view: solo tracks left or right with OPTION plus LEFT or RIGHT | replace | performance | none (no input event) | Solo groups |
| Song view: jump 16 rows with OPTION plus UP or DOWN | re-range | ui-input | none (no input event) | Configurable jump size |
| Song view: move selection with EDIT plus UP or DOWN in selection mode | replace | sequencer-edit | none (no edit event) | Move across tracks |
| Song view: render selection with double-tap EDIT in selection mode | extend | sampling | none (no input event) | Separate stem render shortcut |
| Chain view: create new phrase by double-tapping EDIT | replace | sequencer-edit | none (no edit event) | Create from template phrase |
| Chain view: clone and paste phrase | replace | sequencer-edit | none (no edit event) | Clone with variation |
| Chain view: jump to track via OPTION plus LEFT or RIGHT | replace | ui-input | none (no input event) | Remember cursor row per track |
| Chain view: jump to previous or next chain via OPTION plus UP or DOWN | replace | ui-input | none (no input event) | Jump to next used chain |
| Phrase view: create new instrument by double-tapping EDIT on the instrument column | replace | sequencer-edit | none (no edit event) | Create from a preset |
| Phrase view: clone and paste instrument | replace | sequencer-edit | none (no edit event) | Clone including table |
| Phrase view: jump to track and previous or next phrase | replace | ui-input | none (no input event) | Jump to next non-empty phrase |
| Phrase view: interpolate over a single-column selection with SHIFT plus EDIT | replace / extend | sequencer-edit | none (no edit event) | Curved interpolation modes |
| Phrase view: nudge within a selection with EDIT plus UP or DOWN | replace | sequencer-edit | none (no edit event) | Nudge in sub-steps |
| Phrase view: note fill in selection mode with FILL modes (OPTION plus LEFT), random fill (OPTION plus RIGHT), random note pitch (OPTION plus UP or DOWN) | extend | sequencer-edit | none (no edit event) | Euclidean fill; scale-aware random |
| Instrument view: preview with EDIT plus PLAY | observe / replace | ui-input | none (no input event) | Hold to sustain preview |
| Instrument view: copy with SHIFT plus OPTION and paste with SHIFT plus EDIT | replace | sequencer-edit | none (no edit event) | Paste modulators only |
| Instrument view: jump to previous or next instrument via OPTION plus LEFT or RIGHT | replace | ui-input | none (no input event) | Jump to next used instrument |
| Instrument view: touchscreen EDIT plus swipe edits, OPTION plus swipe maps | extend | midi-in | none (no input event) | Map via XY pad |
| Table view: interpolate values in selection mode with SHIFT plus EDIT | replace | sequencer-edit | none (no edit event) | Curved interpolation modes |
| Table view: jump to previous or next table via OPTION plus LEFT or RIGHT | replace | ui-input | none (no input event) | Jump by usage |
| Mixer view: create or recall a snapshot with SHIFT plus OPTION or SHIFT plus EDIT | extend / replace | render-master | none (no input or mixer access) | Multiple mixer snapshots; fade between snapshots |
| Selection: tap OPTION to cycle selection modes | extend | sequencer-edit | none (no input event) | Add a column-wide or track-wide mode |
| Selection: copy with OPTION (exits) and paste with SHIFT plus EDIT | replace | sequencer-edit | none (no edit event) | Persistent clipboard across projects |
| Key shortcuts printed on a card and in the appendix; no on-device shortcut help | extend / draw | ui-screen | none (no draw event) | In-device help overlay listing mod key combos |

## Hexadecimal Table and Specifications

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Absolute values 00-FF versus relative values -128 to +127 interpreted by a command | re-range | fx-commands | none (no FX dispatch or table hook) | Percent-based commands; wider relative ranges |
| Sequencer limit: 255 phrases and chains | re-range | sequencer-edit | none (no limit located) | Raise chain and phrase counts |
| Sequencer limit: 128 instruments per song | re-range | param-tables | none (no limit located) | More instrument slots |
| Sequencer limit: 256 instrument tables | re-range | sequencer-edit | none (no limit located) | More tables |
| Eight monophonic tracks and voices | re-range | sequencer-transport | none (no count located) | Additional voices per track |
| Sample length unlimited because samples are streamed from SD | replace | sampling | none (no audio or storage event) | Cache hot samples |
| MIDI Output engine with 10 user-defined CCs per instrument | re-range / extend | midi-out | none (no MIDI event, no parameter range located) | More CC slots |
| Storage on FAT32 or exFAT SDHC cards | extend | storage | none (no storage event) | Long-file-name handling; new folder layout |
| Hardware-dependent features: Model:02 microphone, 3.5-inch screen, 4300 mAh battery | observe | settings/boot | none (no hardware query) | Model-aware mod behaviour |

## Cross-cutting primitives

- Key and input event: raw key press and release with modifier state and view id (SHIFT and OPTION and EDIT chords): all shortcut rows, key repeat, selection, mute and solo, File Browser keys, view navigation.
- View registry and view-change call: add, replace or veto a view and its neighbour map: new views, Project entries, mod settings page, mini-map.
- Draw hook per view with text, colour and region primitives: help line, status header, battery icon, Time Stats, Theme, CPU TOO BUSY, version banner.
- Parameter edit event: view id, parameter id, old and new value, step size, coarse or fine; with veto and replace: value ranges, default reset, hex entry, text display.
- Parameter table access: read and rewrite range, default, enum list and step for system, project, render and MIDI settings rows.
- Settings store: read, write and persist system settings, and add new mod settings rows: backlight, key repeat, HP PROTECTION, USB modes, splash.
- Storage event and call set: file browse, load, save, delete, bundle, clear unused, theme load, sample list, with veto and replace: songs, themes, bundles, templates, renders, samples.
- Boot and shutdown event: power-on volume cap, splash, startup song, loader banner, power-button hold times.
- MIDI in event: raw message with port, channel, type and data, with consume or replace: CC mapping, note recording, program change, SPP, cue channel, per-track channel and mode.
- MIDI out call and event: clock, transport, SPP and note or CC emission with filter: sync out, USB versus TRS routing, Control surface.
- Transport event and call: play, stop, tempo, song row position, queue and cue: queued song load, live quantize, SPP, snapshots, tap tempo.
- Edit event on grids: insert, clone, deep clone, cut, copy, paste, fill, interpolate, nudge with veto and replace: Key Shortcuts rows and Effect Help insertion.
- FX command table and dispatch: command id, value, track to effect, and help text: Effect Help view, nibble-based commands, relative versus absolute interpretation.
- Audio block hook on the main bus and USB bus: USB routing, multi-channel output, line-in gate, metronome, headphone cap, render with limiter.
- Sample buffer access and process registry: Sample Editor process list, slice detection, recording arm and source list, Selection to Sample, Render.
- Limit table: counts for tracks, instruments, phrases, chains, tables, mappings, slice markers, path length.
- USB mode and drive call: drive mode, audio mode, display streaming, host detection.

Targets: 228
