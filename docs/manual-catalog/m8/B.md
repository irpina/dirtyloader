# Hook targets B: song, live mode, chain, phrase, instrument pool, table, groove, scale views and the sequencer FX commands (Dirtywave M8 (Model:02), OS 6.5.2)

Source: `manuals/m8.txt` lines 611-833, 1062-1303, 2661-2872, 3295-3341 (all read; the key-combination bullets came out readable, only bullet glyphs are replacement marks).

Assumptions behind the coverage ratings:
- Rated only against `baseline.md`: the single TICK event (observer, no payload, no firmware state access), no calls, no tables, no input/draw/row/FX events.
- Every row is `none` unless the baseline lists the exact text as a located static-patch site; only scale name strings qualify here (`partial (static patch: rename only)`).
- Screen elements (grayed chains, asterisk, help text, pop-ups, time readout) have no draw event, so they are `none`.
- Manual describes OS 6.5.2; firmware is 6.6.2, so counts and ranges may differ. Hex ranges are quoted as the manual states them.
- Mute/solo and selection/copy shortcuts are listed once, at first mention, even though they repeat in later views.

## Song View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Per-track song-position advance through the chain list, looping back at the first empty slot | observe / replace | sequencer-transport | none (no song-row event) | Song-position display for external lighting; random-next-chain arrangement |
| Song length limit of 256 rows | re-range | sequencer-transport | none (limit not located) | Longer songs; shorter songs for a smaller save |
| Track count of 8 across the song grid | re-range / extend | sequencer-transport | none (count not located) | Ten-track variant; fewer tracks for more voices each |
| Chains of different lengths drift out of alignment per track | observe / replace | sequencer-transport | none (no song-row event) | Force-resync tracks at each song row |
| Empty or filler chain (00 or FE) used to keep a silent track in step | observe | sequencer-fire | none (no chain event) | Auto-insert a filler chain; flag unplayed chains |
| Gray-out of chains with no notes | draw | ui-screen | none (no draw event; site not located) | Colour chains by density; highlight chains using one instrument |
| Song-time readout (min:sec) shown by holding option while stopped | draw / observe | ui-screen | none (no draw event) | Show bars and beats; show total song time |
| Cursor movement and 16-row jump with option plus up or down | veto / replace | ui-input | none (no key event) | Jump by phrase length; bookmark jump |
| Play/stop all tracks and cue-song-row-for-playback key combination | observe / veto / replace | sequencer-transport | none (no key or transport event) | Start only selected tracks; confirm before stopping |
| Solo tracks left or right of cursor; hold-mute and hold-solo via option; clear all mute and solo | observe / replace | performance | none (no key event) | Mute groups; MIDI-controlled mute |
| Edit key on an empty slot inserts the last edited or deleted chain | replace | sequencer-edit | none (no key event) | Insert next free chain instead; insert a clone |
| Edit plus direction changes the chain number at the cursor; moves selection when selecting | replace / re-range | param-edit | none (no edit path) | Step by 16; skip empty chains |
| Double-tap edit inserts a new unused empty chain | replace | sequencer-edit | none (no key event) | Pick next unused by naming convention |
| Delete/cut chain with edit plus option, and cut into the copy buffer in selection mode | observe / veto | sequencer-edit | none (no key event) | Undo stack; confirm deleting a used chain |
| Selection mode for moving, copying, cutting chains, and the shared copy buffer paste | observe / extend | sequencer-edit | none (no key event) | Multi-slot clipboard; paste-special |
| Clone chain into a new chain number | replace / extend | sequencer-edit | none (no key event) | Clone with transpose; clone with rename |
| Deep clone chain plus all its phrases into new chain and phrases | replace / extend | sequencer-edit | none (no key event) | Deep clone including tables; deep clone with instrument remap |
| Bookmark a chain with a triple option press | extend | ui-input | none (no key event) | Several named bookmarks; jump-to-bookmark key |
| Track reordering mode (double up on row 00, edit plus left or right moves a track) | veto / replace | ui-input | none (no key event) | Swap track contents only; lock a track |
| Render selected song rows to a new instrument (edit twice in selection mode, stopped) | extend / replace | sampling | none (no event) | Render with effects tail; render each track to its own sample |

## Live Mode

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Enter or exit live mode with shift plus left from the song view | observe / veto | performance | none (no key event) | Auto-enter live mode on load; lock live mode |
| Cue a track for a chain; waits for the playing chain to finish by default | replace / re-range | sequencer-transport | none (no transport event) | Launch on the next beat instead; launch at a fixed bar count |
| Live Quantize choice in the Project View deciding when a cue activates | re-range / extend | sequencer-transport | none (quantize list not located) | Add a quantize of two chains; quantize to phrase |
| Stop a cued or playing track with shift plus play in live mode | replace | sequencer-transport | none (no key event) | Stop at end of phrase; fade out the track |
| Cue the selected song row with left plus play from any place in the song | replace / observe | sequencer-transport | none (no key event) | Cue a row on all tracks; cue by MIDI note |
| Live-mode cue state shown per track (cued versus playing) | draw | ui-leds | none (no draw event; indicator not located) | Pulse an LED on a pending launch |

## Chain View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Chain holds 1 to 16 phrase rows, so up to 256 steps | re-range | sequencer-transport | none (limit not located) | Longer chains of 32 rows |
| First empty phrase slot ends the chain and the song moves to the next chain | replace / observe | sequencer-transport | none (no chain event) | Loop chain N times; conditional chain end |
| Per-row transpose in semitones (TSP column) applied to the phrase notes | replace / re-range | notes | none (no note event) | Quantize the transpose to a scale; wider range |
| Edit key on an empty row inserts last edited or deleted phrase; double tap inserts a new unused phrase | replace | sequencer-edit | none (no key event) | Insert the next phrase in order |
| Edit plus direction changes the phrase number at the cursor | replace | param-edit | none (no edit path) | Skip phrases that are empty |
| Clone a phrase to a new number from the chain view | replace / extend | sequencer-edit | none (no key event) | Clone and apply transpose |
| Play chain at cursor (play) and continue song at cursor (shift plus play) | observe / replace | sequencer-transport | none (no key or transport event) | Loop-play a chain; start from selected row |
| Navigate to previous or next chain or track with option plus direction | replace | ui-input | none (no key event) | Navigation across projects pages |
| Delete, selection, copy and paste of phrase rows within a chain | observe / veto | sequencer-edit | none (no key event) | Paste with offset; duplicate-range |

## Phrase View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Phrase length of 16 steps, each step a 16th note by default | re-range | sequencer-timing | none (length not located) | 32-step phrases; 12-step phrases |
| Note column spanning 128 MIDI notes over 11 octaves; semitone and octave editing | re-range / replace | param-edit | none (no edit path) | Edit by scale degree; clamp to a range |
| Note-off inserted by clearing a note with option plus edit | replace | sequencer-edit | none (no key event) | Different off symbol; legato tie |
| Note trigger at a step: which note, instrument and volume fire when the row plays | observe / veto / replace | sequencer-fire | none (no note or row event) | Per-row humanize; note filter; echo to another track |
| Volume column 00 to 7F with default 64 | re-range / replace | param-tables | none (range not located) | Extended velocity curve; volume offset |
| Instrument column: empty means change note without retriggering instrument | replace | sequencer-fire | none (no row event) | Always retrigger; sticky instrument |
| Edit twice on instrument column picks a new unused instrument; shift-option edit clones the instrument | replace / extend | sequencer-edit | none (no key event) | Prompt for name; clone including table |
| Three FX columns per step | re-range / extend | fx-commands | none (no FX event) | Four FX columns; per-column chance |
| Commands offered depend on the instrument type currently in use | replace / re-range | fx-commands | none (no command table) | Add a command only for a new instrument type |
| Effect Command Help view opened with edit plus up or down on an FX column | extend / draw | ui-screen | none (no draw event) | Searchable command list; mod-added commands shown |
| Asterisk next to the phrase number when the phrase is used elsewhere | draw | ui-screen | none (no draw event) | Show use count and where it is used |
| Edit on empty cell inserts last edited or deleted value; large and small step editing | replace | param-edit | none (no edit path) | Scale-aware step; fixed default value |
| Edit twice on a TBL, TBX, GRV or GGR value picks a new unused table or groove number | replace | sequencer-edit | none (no key event) | Pick next free table with a name |
| Cut or delete of cell, selection mode, copy and paste of phrase blocks | observe / veto | sequencer-edit | none (no key event) | Block paste with transposition; multi-slot copy |
| Shift of selected multi-column block up or down with edit plus up or down in selection mode | replace | sequencer-edit | none (no key event) | Rotate steps; shift by a bar |
| Randomize note value or fill mode in selection mode with option plus direction on the note column | replace / extend | sequencer-edit | none (no key event) | Euclidean fill; scale-aware randomize |
| Randomize note and instrument triggers with option plus right in selection mode | replace / extend | sequencer-edit | none (no key event) | Weighted trigger density |
| Interpolate a selected single-column range with shift plus edit | replace / extend | sequencer-edit | none (no key event) | Curve-shaped interpolation |
| Clone the instrument or table number in a command column with shift-option edit | replace / extend | sequencer-edit | none (no key event) | Clone with rename |
| Play phrase, continue song at chain position, option mute and solo while editing | observe / replace | sequencer-transport | none (no key or transport event) | Loop a bar; audition from cursor |
| Navigate to previous or next phrase in chain or track with option plus direction | replace | ui-input | none (no key event) | Jump to the matching phrase on the next track |

## Instrument Pool View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Overview list of all instrument slots in the song, with per-instrument mixer columns | extend / draw | ui-screen | none (no draw event) | Extra columns such as tags or last used |
| Ways into the view: shift plus up above modulation view, project view shortcut, edit plus down on instrument 00 | replace / extend | ui-input | none (no key event) | Dedicated key; open at the last used slot |
| Load an instrument or sample by pressing edit on an empty slot | observe / extend | storage | none (no event) | Browse favourites; preset packs |
| Reorder instruments by edit plus up or down on the name column | replace / veto | sequencer-edit | none (no key event) | Auto-fix phrase references after reorder |
| Edit mixer-related values in the pool at large and small steps; option plus edit resets to default; copy and paste values | replace | param-edit | none (no edit path) | Finer step; batch edit all rows |
| Clear instrument with edit plus option; copy and paste a whole instrument with shift combinations | observe / veto | sequencer-edit | none (no key event) | Confirm clearing used instruments |
| Preview an instrument with play while stopped | observe / replace | sequencer-fire | none (no note event) | Preview at a chosen note and velocity |
| Navigation shortcuts: 8-instrument jump, first or last page, shift plus left to the phrase view with default insert note set, shift plus right to instrument view | replace | ui-input | none (no key event) | Page by 16; jump to the instrument used by this track |

## Table View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Table count: one per instrument plus 128 freely assigned tables | re-range | sequencer-fire | none (count not located) | More shared tables |
| Table length of 16 rows | re-range | sequencer-fire | none (length not located) | 32-row tables |
| Table play head loops to the top at the bottom by default | replace | sequencer-fire | none (no row event) | One-shot tables; ping-pong |
| Table row advance at its own speed (set by the table tic rate) rather than at tempo and groove | replace | sequencer-timing | none (no event) | Tempo-synced table rate; swing in tables |
| Transpose column applied to the instrument for the duration of the step | observe / replace | notes | none (no note event) | Scale-quantized table transpose |
| Table volume column multiplied with the phrase volume | replace / re-range | sequencer-fire | none (no row event) | Additive volume mode; curved scaling |
| Table FX columns identical to phrase columns, but some commands behave differently | replace / extend | fx-commands | none (no FX event) | Table-only commands |
| Independent per-column speed using TIC commands, or TIC on last row to affect all rows | extend | sequencer-timing | none (no FX event) | Per-column swing |
| TIC00: row increments on each instrument trigger | replace / extend | sequencer-timing | none (mode not located) | Increment on every Nth trigger |
| TIC01 to TICFB: number of ticks per row | re-range | sequencer-timing | none (range not located) | Finer than one tick per row |
| TICFC octave map: playing octave selects the row | extend | sequencer-timing | none (mode not located) | Map by scale degree |
| TICFD velocity map: velocity selects the row | extend | sequencer-timing | none (mode not located) | Curve-shaped velocity-to-row mapping |
| TICFE note map: note selects the row (HOP00 on row 0C limits to 12 notes) | extend | sequencer-timing | none (mode not located) | Microtonal 19-note maps |
| TICFF: row advance at 200 Hz | re-range | sequencer-timing | none (rate not located) | Faster 400 Hz mode |
| Table navigation (previous or next table, plus or minus 16) and play from table view | replace | ui-input | none (no key event) | Jump to the table of the current instrument |
| Table edit, interpolation in selection mode, shift of blocks, copy, cut and paste | replace / extend | sequencer-edit | none (no key event) | Table presets library |
| Clone a table from a TBL, TBX, GRV or GGR value | replace | sequencer-edit | none (no key event) | Clone with rename |

## Groove View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Groove sets ticks per phrase step for 16 steps | replace / re-range | sequencer-timing | none (no timing event) | Per-step micro-timing; humanize |
| Groove 00 as default for all 8 tracks; each track can use its own groove | replace | sequencer-timing | none (no event) | Per-instrument groove |
| Tick resolution 24 PPQN default, selectable 24, 48, 96 or 192 | re-range / extend | sequencer-timing | none (no clock or timing event) | 384 PPQN; per-groove rate |
| Default of two rows of 06; recommended 96 ticks per phrase | observe | sequencer-timing | none (no event) | Warn when groove length does not sum to 96 |
| Groove loops to the start at an empty row; a row of 00 skips the phrase step | replace | sequencer-timing | none (no event) | Reverse groove; skip with probability |
| Help message at the bottom summing groove ticks | draw | ui-screen | none (no draw event) | Show bar alignment |
| Editing a row with edit plus up or down changes it and its neighbour at once (swing) | replace | param-edit | none (no edit path) | Swing percent entry; single-row edit |
| Groove count, navigation and edit actions (previous or next, plus or minus 16, copy, interpolate) | re-range / replace | sequencer-edit | none (count not located) | More than the stock number of grooves |

## Scale View

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| What scale quantizing applies to: project and chain transpose, note entry, ARP, PIT, FM PIT modifier, MIDIOUT CHD and ADD | replace / extend | notes | none (no note event) | Scale-aware modulation; add quantize to another command |
| Up to 16 user scales per project; scale 00 default for all tracks | re-range | notes | none (count not located) | 32 scales |
| Per-track scale choice via SCA, global via SCG, and for Hypersynth | replace | notes | none (no FX event) | Scale follows song section |
| Per-instrument enable or disable of scale quantizing through the TRANSP. option | replace / extend | notes | none (no event) | Per-track enable |
| Key (root) as a global setting for the default scale, overridable per track | replace | notes | none (no event) | Key follows MIDI input |
| Each of 12 note intervals enabled with EN and an optional detune of minus 24.00 to plus 24.00 semitones | re-range / extend | notes | none (range not located) | Wider microtonal range; more than 12 degrees |
| Name, load and save scales; 92 factory scales preloaded to the SD card at /Scales/Factory | extend / observe | storage | partial (static patch: rename only; scale name strings located, file loading not) | Rename factory scales; custom scale pack |
| Scale view navigation, editing with large and small steps, reset to default | replace | param-edit | none (no edit path) | Edit by cents |

## Relative and Absolute FX Commands

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Relative command mode adds to the parameter current value instead of setting it | replace / extend | fx-commands | none (no FX event) | Convert a command to absolute; add per-command mode flag |
| Relative values 01 to 7F add, FF to 80 subtract (signed byte) | re-range | fx-commands | none (no FX event) | Wider or finer relative step |
| Relative changes persist until a new trigger by RET or an instrument number resets all parameters | replace / veto | sequencer-fire | none (no row or note event) | Keep modifications across retrigger |
| Absolute command mode sets the value outright, ignoring the instrument setting | replace | fx-commands | none (no FX event) | Absolute command for a parameter that is relative |

## Sequencer FX Commands

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| ARP XY: three-note arpeggio, X and Y semitone intervals from the played note (scale-quantized) | replace / re-range / extend | fx-commands | none (no FX dispatch hook; natural sibling) | Four-note ARP2; chord-shape table |
| ARC XY: arpeggio config, mode X and speed Y in ticks | extend / re-range | fx-commands | none (no FX dispatch hook; natural sibling) | Extra arpeggio modes such as random or pedal |
| CHA XY: phrase probability to the left (X) or right (Y), 0 to F; in a table one value 00 to FF for everything to the left | replace / re-range | fx-commands | none (no FX dispatch hook) | Finer probability; seeded probability |
| DEL XX: delay the whole row by XX ticks in a phrase; delay table play head in a table | replace | sequencer-timing | none (no timing event) | Delay in subtick units; humanize |
| GRV XX: set groove number for the current track, held until changed | replace / observe | sequencer-timing | none (no FX dispatch hook) | Groove per phrase; groove crossfade |
| GGR XX: set groove number for all tracks | replace | sequencer-timing | none (no FX dispatch hook) | Song-wide groove sweep |
| HOP XY: in a phrase jump to row Y of the next phrase; HOPFF stops the track; in a table jump to row Y X times | replace / extend | sequencer-transport | none (no FX dispatch hook) | Conditional hop; hop to any phrase |
| INS XX: set or change the instrument as an FX command | replace | sequencer-fire | none (no FX dispatch hook) | Instrument layering; random instrument from a bank |
| KIL XX: stop the playing instrument after XX ticks | replace | sequencer-fire | none (no FX dispatch hook; natural sibling to OFF) | Kill with fade; kill-all tracks |
| RND XY: randomize the previous FX command, left and right range 0 to F | replace / re-range | fx-commands | none (no FX dispatch hook) | Different distributions; per-command depth |
| RNL XY: randomize the command to its left; in first column randomize note and instrument (phrase) or note and velocity (table) | replace / extend | fx-commands | none (no FX dispatch hook) | Scale-aware note randomization |
| RET XY: retrigger with volume ramp; Y non-zero is retrig interval and X ramp (0-7 down, 8-F up), Y zero is a single delayed retrig | replace / extend | sequencer-timing | none (no FX dispatch hook) | Ratchet rolls; pitch-ramping retrig |
| REP XX: repeat the last command incrementing by XX per step, persists until stopped, kept across instrument triggers and phrases | replace | fx-commands | none (no FX dispatch hook) | Wrap or ping-pong increment |
| REP active indicator shown as a double caret next to the FX lane | draw | ui-screen | none (no draw event) | Show the stepped value |
| RTO XX: min or max value where a REP stops | re-range | fx-commands | none (no FX dispatch hook) | Wrap instead of stop |
| RMX XY: set phrase play-head position Y of tracks to the left; X picks tracks | replace / extend | sequencer-transport | none (no FX dispatch hook) | Resync tracks to the right as well |
| NTH XY: conditional trigger based on loop count, skips left (X) or right (Y) side in phrase, left (XX) in table | replace / extend | fx-commands | none (no FX dispatch hook) | More ratio patterns; polymeter conditions |
| PSL XX: portamento on the playing instrument, value in ticks | replace | notes | none (no FX dispatch hook) | Time-based glide in ms; legato-only glide |
| PBN XX: continuous pitch slide up (00-7F) or down (80-FF) | replace / re-range | notes | none (no FX dispatch hook) | Exponential bend curve |
| PVB XY: vibrato, speed X depth Y | replace | notes | none (no FX dispatch hook) | Tempo-synced vibrato |
| PVX XY: extreme vibrato with higher depth and rate | extend / re-range | notes | none (no FX dispatch hook; natural sibling to PVB) | Even wider depth |
| SCA XY: key signature X and scale number Y for the track | replace | notes | none (no FX dispatch hook) | Key-change helper |
| SCG XY: key signature X and scale number Y for the song | replace | notes | none (no FX dispatch hook) | Modulate all tracks |
| SNG XX: set the track play position to a relative song row; ignored if the row is not playable | replace | sequencer-transport | none (no FX dispatch hook) | Absolute song jump; conditional jump |
| SED XX: set the random seed for the current track | replace / re-range | fx-commands | none (no FX dispatch hook) | Wider seed; shared seed across tracks |
| TBL XX: set the table number for the current instrument | replace | sequencer-fire | none (no FX dispatch hook) | Switch table per phrase |
| THO XX: hop to a table position 0X; hops all columns inside a table | replace | sequencer-fire | none (no FX dispatch hook) | Per-column hop |
| TIC XX: set the table tick rate for the instrument; per-column in tables; on last row for all rows | replace / re-range | sequencer-timing | none (no FX dispatch hook) | Slow-down command |
| TBX XX: assign an auxiliary table in parallel with instrument tables; 00 stops it; TIC in the same row sets its rate | replace / extend | sequencer-fire | none (no FX dispatch hook) | Second aux table; table crossfade |
| TPO XX: set song tempo in BPM, help text shows hex to decimal | replace / re-range | sequencer-transport | none (no tempo or FX hook) | Tempo ramps; fractional BPM |
| TSP XX: global song transpose, same as the Project View transpose | replace | notes | none (no FX dispatch hook) | Transpose a single track only |
| NXT XX: trigger instrument XX on the next track with current note and velocity; not on track 8 | replace / extend | sequencer-fire | none (no FX dispatch hook) | Wrap track 8 to track 1; trigger previous track |
| OFF XX: stop the instrument after XX ticks, triggering ADSR release if configured | replace | sequencer-fire | none (no FX dispatch hook; natural sibling to KIL) | Release-time units in ms |
| MTT XX: row timing shift in sub-ticks of 1/8 tick; negative not on the first row; no action in tables | replace / extend | sequencer-timing | none (no timing event) | Enable in tables; humanize amount |
| Overall FX command set and parsing: command id plus X/Y or XX value per column, three columns per row | extend / replace | fx-commands | none (no command table or dispatch hook) | Add a custom command ID; replace a stock command |
| Command help text shown at the bottom while editing a value (hex to decimal, NTH help) | extend / draw | ui-screen | none (no draw event) | Show text for mod-added commands |

## Common Groove Examples

| Hook target | Kind | Layer | Coverage today | Example mods |
|---|---|---|---|---|
| Stock example grooves: Swing 1 (07,05), Swing 2 (08,04), triplets (08,08,08,00), 2x speed (03), 3/4 time (twelve 06 then 00s), swing last step (07,05 at end) | extend | storage | none (no table or file hook; defaults not located) | Ship a groove pack; preset grooves in a new project |
| Row of 00 used to drop steps (3/4 time, triplets) | observe | sequencer-timing | none (no timing event) | Skip steps with a gate pattern |

## Cross-cutting primitives

- FX command dispatch: command id + value + track + column -> effect, with phrase/table context flag; used by every row in Sequencer FX Commands.
- FX command table: the list of command ids, names, value formats (XY or XX), relative/absolute flags; used by ARP, ARC, CHA, new sibling commands, Relative and Absolute FX Commands, and the help view.
- Per-instrument-type command availability list: used by "commands depend on the instrument type" and any new instrument type.
- Row fire event: track + phrase row + note + velocity + instrument + three FX cells before play; used by note filter, humanize, INS, NXT, retrig, CHA, NTH.
- Note path hook: note + transpose chain (project, chain TSP, table, TSP command) -> scale quantize -> voice; used by ARP, PIT, SCA/SCG, scales, vibrato, portamento.
- Tick and groove clock hook: ticks per step, PPQN, groove row, MTT sub-tick, DEL, TIC rates; used by Groove View, Table TIC modes, RET, DEL.
- Table runner hook: table row advance, loop, hop, aux table, TIC mode (00, 01-FB, FC, FD, FE, FF); used by TIC modes, THO, HOP, TBX.
- Song/chain/phrase cursor event: position change per track with row numbers; used by SNG, HOP, RMX, song display, live-mode launch.
- Live-mode queue hook: cue, quantize point, launch, stop per track; used by Live Quantize and launch rules.
- Key event with view context and modifier state: used by every shortcut row (clone, deep clone, selection mode, bookmark, track reorder).
- Cell edit path: value + step size + view + column -> stored value; used by the edit-key rows in every view.
- Selection and clipboard operations (copy, cut, paste, interpolate, shift, randomize fill): used by sequencer-edit rows across song, chain, phrase, table and groove views.
- Screen draw hook for tracker views: cell colour, extra columns, markers (asterisk, caret, gray-out), help line; used by every draw row.
- Limit constants (256 song rows, 16 chain rows, 16 phrase steps, 16 table rows, 128 tables, 16 scales, 12 intervals, 8 tracks): used by every re-range row.
- Random source and seed (SED, RND, RNL, CHA, NTH): one hook for the shared per-track RNG.
- Scale store: load/save and 16-slot scale data; used by Scale View rows.

Targets: 139
