# Changelog

Dated notes on work that changes what is in this package rather than what it
does. Behavior-preserving changes are recorded here when they remove a public
name, when they move a number the family is measured by, and when they turn up a
defect that is being left alone rather than fixed.

The comment ratio below is `(radon raw Comments + Multi) / SLOC` over
`funestra/` (`player_core/` until 2026-10-10, `funestra_core/` until 2026-10-11) and `tools/`, the measure `audit/findings/player_core.md` set its
baseline with: **0.7692** over 3,661 SLOC, with 28 of 29 files above 0.25.

## 2026-10-23 — a host in the same process drives its Funestra as a session drives one

`Funestra.apply` takes one verb as a line of the command file is taken,
`Funestra.take_the_list` a list as a line-by-line read of the playlist file is
taken, and `Funestra.status_fields` is what the status file says, so a host
running a Funestra in its own process can hand it the very verbs and list a
session's Funestra drains from its files and read it back the same way. The
status carries `loads` and `idle`, so a source sees the same file opened again
and one that would not open. A pace of nought holds a clip that finishes as it
holds a picture, without locking it.

## 2026-10-23 — the radio and a picture's row come back

The change of 2026-10-17 is back, with the apps' halves (fun_time#468,
origenerator#444) shipping beside it: `Funestra.clip_row` is
`Funestra.item_row` again, and `picture_time`, `seek_picture`, `radio`,
`MpvStation` and `HOLD_PICTURE` return. A still the engine ends on its own
clock is ended only by the clock started for the file on screen, so a picture
mpv rolls onto by itself at the end of a clip stays up until the Funestra
follows the roll. Ended by the clip's clock instead, it asked mpv to move on
from the last entry of its playlist, which mpv refuses: the error that closed
Fun Time's room twice on 2026-10-20.

A host that builds its Funestra in its own process, as standalone Origenerator
builds its Slideshow's, can hand it the radio it plays (`radio=`, anything a
`radio.Tuner` describes), be told the volume whenever the viewer moves it on
the panel (`on_volume_moved=`), and set that volume itself (`set_volume`).
`Radio(together=True)` tunes every station in while a picture is up, which is
how Standalone's three play at once.

## 2026-10-21 — every Funestra runs ahead of background work through one piece of code

`funestra_priority.ahead_on_the_processor` moves here from Fun Time's
`main_funestra`, where the Main Funestra, the satellites and the headset ran
inside it. Origenerator's Slideshow Funestra is the one that did not: beside a
busy computer its picture's move was pushed two to four times in 0.3 s instead
of eighteen. It now runs inside the same block.

## 2026-10-20 — a source can name an item to come up next

`PLAY_NEXT <playlist line>` puts an item right after the one on screen without
taking the screen from it: moved there when it is listed already, the funscript
column taken as its script, and waiting behind a held item until the hold is let
go. Fun Time sends it for whatever arrives in a Funestra's library while that
Funestra plays its Latest list. Genau's flick sequence takes the same placement
(`FlickSelectionController.play_next`), and both lists put an item next through
`up_next.put_up_next`, which `PLAY_FILE`'s splice now goes through too.

## 2026-10-19 — the radio and a picture's row are taken back out

The change of 2026-10-17 (a picture keeps its row, timed on the engine's own
clock; a picture held short of its pace; a Funestra plays a radio) is reverted
whole. It asked the engines the apps hand a Funestra for `picture_time` and
`radio_station`, Origenerator's half never shipped, and so Origenerator could
take no release after v0.1.520. It comes back together with the apps' halves
(fun_time#468, origenerator#444). `Funestra.item_row` is `Funestra.clip_row`
again, and `picture_time`, `seek_picture`, `radio` and `MpvStation` are gone.

## 2026-10-19 — a window builds a new video output when its graphics card goes

A graphics driver restart took every Funestra window's picture for the rest of
the session: mpv's d3d11 output went on failing on the device Windows had taken
away. A windowed engine (`MpvEngine`) now hears that in mpv's own log (DXGI's
codes for a device that is gone) and two seconds later has mpv build it a new
output (`lost_gpu.LostGpu`), on which the clip plays on where it was, its
overlays with it, and a track mpv gave up on meanwhile is picked up again. An
output that does not come up, or goes again within half a minute, is built again
after twice the wait, up to half a minute. `screenshot_bgra` gives None when mpv
cannot take a frame, as it said it would, rather than raising. The headset's
engine (`MpvRenderEngine`) draws in its host's OpenGL context, which a driver
restart takes with it and which nothing of mpv's can bring back, so it is as it was.

## 2026-10-19 — no module keeps an `__all__`, and the dead-code check reads the apps

Every module's `__all__` is gone, and `tests/test_consumer_imports.py`, which
held each one against what the apps import, with them: a name without a
leading underscore is one the apps may use. The dead-code check is now
`tests/test_dead_code.py`, the family's vulture scan read with this repo's
tests and the apps beside it as its callers (app_support v0.1.247), and
`vulture_whitelist.py` names the callers it cannot read. Taken out first,
since nothing but this repo's own tests reached them: `loading_mark` whole,
`RobotHandTCodeDriver.ease_in`, `status.stamp_the_playhead`, and
`Funestra.OVERLAY_IDS` with `Funestra.PANEL_OVERLAY_ID`. `file_channel` and
`flick_folder` hand on what they import from app_support as before, and
`test_hud_drawers` reads the apps through app_support too.

## 2026-10-17 — a picture keeps its row, and a Funestra plays a radio

A picture no longer takes the row off its panel: the row's track and readout
are the picture's time on screen, read off the engine (`picture_time`), and a
press along the track moves that time (`seek_picture`), its slow zoom with it.
For that the engine keeps a still's time itself: mpv holds every still up
(`image-display-duration` is `inf`) and the engine ends it at its pace, as it
ended a swapped-in still before. Gone with that: the engine's `eof`, which
nothing read, and the four-second pace mpv opened on, which the first load
always overwrote. `Funestra.clip_row` is `Funestra.item_row`, and the panels'
`clip_row` arguments are `item_row`, since a picture carries the row too.
`HOLD_PICTURE` holds the picture on screen for less than its pace, its move
still made at the pace, so a source that moves a picture on early lets the
Funestra do it and the scrubber count it down.

A Funestra whose playlist has a radio file beside it (`radio.radio_file_for`)
plays the stations it deals (`radio.Radio`, each an `mpv_engine.MpvStation`
opened from the engine's `radio_station`), one heard while a picture is up.
`radio_file_for`, `write_radio`, `MpvStation` and `HOLD_PICTURE` are for the
app that deals the stations and paces the pictures, and are declared in
`__all__` once it imports them.

## 2026-10-17 — a picture's move starts when the engine puts it up

An engine starts a picture's Ken Burns move when it opens a clip (`load`) and
when it settles on the clip mpv advanced onto, and never on mpv's report of a
new file, which skipped a list coming round to the file it left. The engine's
`drop_consumed` is `settle_on_the_next`, so a host's fake engine standing in
under `Playback` answers to the new name.

## 2026-10-16 — a locked picture punches in on its places

A playlist line can carry the places in a picture worth a close-up, after a
second TAB (`PlaylistItem.points_of_interest`), and a locked picture's move,
each time it comes round, goes to one of them picked at random or to the whole
picture, the whole picture as often as all the places together
(`KenBurns.set_points_of_interest`, `Moves.stop_among`, `Moves.close_up`): each
close-up is framed as close as its window fits the place (`Fit.framing`), and
makes one of the three ordinary moves on top of that framing, so it zooms and
pans across the window as far as a move over the whole picture does however
close it is. Origenerator fills the column with the places an enhancement's
fixes found. The item stays the pair it was, the places riding beside it.

`Fit`, `CLOSEST` (once `CLOSEST_AIM`) and the window-size readers the aim took
with it on 2026-09-28 are back, framing these close-ups.

## 2026-10-13 — cruise control is gone

Human-inspired motion outclassed it, and Fun Time and Origenerator took it out
of every control they had for it. What went from here: the dice and the summed
waves (`cruise_control`'s `CruiseControlState`, `enable_cruise_control`,
`disable_cruise_control` and `tick_cruise_control`; `wave_stack`'s `bars`,
`position`, `position_ahead` and `trace_window`), Genau's `TOGGLE_CRUISE`,
`CRUISE_ON` and `CRUISE_OFF`, the status file's `cruise` line, the drive
readout's picture of the stack, the driver's stack position, the cc button on
`aim_row`, and `GenauControls`' `cruise_control_state` and `set_motion_phase`,
whose one caller was cruise control letting go. So did the verb-name
constants nothing has read since the crossing a second Genau made went on
2026-10-10 (`HAND_SPEED`, `HAND_AMP`, `HAND_CENTER`, `LEARNED_ON`,
`LEARNED_OFF`).

A branch from before then still spells all of it, and runs on whatever this
package an app's venv holds, so it keeps working with cruise control as
nothing: `cruise_control` keeps a `CruiseControlState` that never turns on and
three functions that do nothing, `wave_stack` stays an empty module, and
`GenauControls`, `RobotHandTCodeDriver` and `aim_row` drop the arguments it
still hands them (`renamed.drops_retired_arguments`). Its keys and words for
cruise reach Genau as verbs it refuses and logs. None of those is declared;
they go once no checkout names them.

## 2026-10-12 — the console draws the host's list and bar itself

Only a Funestra draws a HUD, and the console's `host_block` let a host paint
its own block into it, which FunTimeVR's headset did for its projection list
and Angle bar. `host_block` is gone. A Funestra takes `host_controls` instead
(`host_controls.HostControls`): something that says what its list and bar
show now (`hud()`, a `HostControlsHud` naming what is chosen, the list in
order and an optional `BarHud` with its label, value, ends and unit), and is
handed back the row picked (`pick(index)`) and the value the bar is set to
(`set_bar(value)`). `HostControlsSection` paints them at the console's foot,
exactly as the headset did, and `HostControlsPress` keeps the list open or
the bar held and places each press; the console offers every press to them
first, as before, and `ConsolePainter.host_controls_layout` says where the
field, the bar and the list's rows landed. The field and the list are
`shared_ui.dropdown_pil`'s, the dropdown the headset's dashboard draws, and
the bar's track is `hud_panel.draw_track`, which the volume chip's slider now
draws with too.

## 2026-10-11 — the repo, its folder and its package are all funestra

The package `funestra_core` is `funestra`, the repository `haglio/player_core`
is `haglio/funestra`, and the distribution `player-core` is `funestra`. The
"core" had meant the part all the players shared, and a Funestra has none.
`funestra_core` answers as an old package name exactly as `player_core` does,
and both are kept by one finder in `funestra/renamed.py` (`answer_as`), so a
module reached through either is the very module `funestra` holds. `timeline`
no longer declares `bar_track_x`: only this package's own `hud_row` and
`pointer` reach it now, so the consumer gate called it published for nobody.

## 2026-10-10 — the console makes room for a block its host paints

`ConsolePainter.rgba` and `bgra` take a `host_block`: anything with a `height`,
a `least_width` and a `draw(image, rect)`, compared by value. The console widens
to its `least_width`, gives its `height` a section of its own at its foot, under
the clip's row, has it draw itself there before any tooltip, and says where in
`host_block_rect`, which the host reads to place a press. A control only one
host has goes inside that host's one panel this way, rather than on a second
panel beside it: FunTimeVR's projection list and angle bar are the first.
A Funestra takes the same as `host_block`, something that says what it draws
now (`drawing()`) and takes the presses on it (`press`, `drag_to`, `holding`,
`release`, each in the panel's own pixels with the rect it landed in); its
console offers every press to it before anything of its own.

## 2026-10-10 — a flick's track runs its time on screen, a dial beside it goes round with the loop, and the row is one line

A flick has two senses of time, and its row at the console's foot showed the
wrong one on the track: how far round its loop the motion had taken it, counted
in frames. The track is a scrubber, so it now runs the time the flick has had of
its turn on screen -- filled left to right over the seconds the flick gets, and
round again while the flick is held, since the count runs under the lock too
and the lock only decides whether the next flick comes at the end -- and a
press along it puts the flick that far into its interval. The loop has no start
or end to scrub between, so it is a dial at the row's left end: a clock hand
going round once per turn, a mark at twelve o'clock at the loop's A end and a
dot at six at its B end, and a press on it puts the loop (and the device, whose
picture the frame is) at that point.

Both rows read the same way, the frame of how many and then the time, "frame
7 / 20 · 0:04 / 0:10" for a flick and "frame 1260 / 5850 · 0:42 / 3:15" for a
video (which used to read "0:42 / 3:15 · frame 1260"), so a flick's row differs
from a video's by its dial alone, and its frames sit beside the dial and its
time beside the track. `framed_playhead` says it, and `video_playhead` says it
for a video whose frame rate is known. The frame counts up in the room its last
frame takes, right-aligned behind figure spaces (`FIGURE_SPACE`, as wide as a
digit in the readout's face), so nothing after it moves as it gains a digit,
as the clock already held still by taking its length's fields; `flick_playhead`
pads its frame the same way.

The row is one line now wherever it is drawn: a flick's dial, the readout, the
track, and the volume chip, 64 pixels wide where it was 112, flush with the
row's right end as the first part is with its left, a few pixels between each.
A video's track is what the heatmap and a seek need room on, so a panel too
narrow to leave it at least as long as everything else on the line widens
until it does, sized for a video of under an hour so it keeps one width from
one to the next. A flick's track has no heatmap and nothing to find along it,
so it is at most 96 pixels and no panel widens for it past the 60 it needs to
be pressed. `bar_track_x` now starts a track after a readout wider than half
the row, where it used to start it at the middle, under the readout.
A console held to one width, as the headset holds its own, is held at least as
wide as the widest row it can carry (`RowSection.least_width_for_any_row`), so
it keeps that one width whichever row it carries, or none.
The row used to stack the time above the track on a panel narrower than 518
pixels, start a wide row's track at a fixed 193, and keep a margin at each end.
The time and the frame count are words alone, no longer in a pill like the
chip's.

`loop_dial` (new, private): the dial and what a press on it names.
`RowHud.loop` is a flick's frames played of how many, which the dial goes round
with; `RowLayout`, from `row_layout`, is where each
part of the row landed, and `row_part`, `scrub_to`, `turn_to`, `volume_to` and
`RowPress` read it, as do the panels (`ConsolePainter.row`, `HudTargets.row`)
and the overlays (`ConsoleOverlay.row`, `HudOverlay.row`) in place of a rect.
`bar_track_x(left=)` takes where the track starts, `progress_bar_bgra` takes the
track, and `HeatmapStrip.update` is handed the track's width rather than the
row's. `readout_width` is the room a readout takes, and `volume.TRACK_GAP` the
gap between the track and the chip, which `MARGIN` was. `FlickAdvanceState`'s
`elapsed` and `set_elapsed` are the track's two halves,
`FlickRenderController.playhead` the dial's and the readout's frame, and
`GenauRefreshController.seek_the_time_on_screen` the press reaching the engine;
`set_locked` and `toggle_lock` are gone, the flag being all that was left of
them, and nothing outside this package ever called them. A `Picture` a User
puts up carries both senses -- `played` and `count`, `elapsed_ms` and
`interval_ms`, with `seek_time` and `seek_loop` for the two presses -- and
still takes `seek` for `seek_loop`. `READOUT_SLOT_W`, `readout_shares_the_row`
and `BAR_INSET_X` are gone with the stacked line and the margins;
`lower_edge_height`, `readout_xy`, `on_readout`, `timeline_x`, `timeline_bgra`,
`pointer.time_at`, `HudOverlay.row_rect` and `ConsolePainter.row_rect`, which
only the headset's old copies of the row and Genau's old console panel reached,
keep answering in their old shapes for the checkouts from before
haglio/fun_time#391 still open on this machine.

## 2026-10-10 — `console.shape_label` is no longer offered

Fun Time takes the row that aims the device from here too now (fun_time #394),
so no consumer names the waveform itself any more, and `shape_label` leaves
`console.__all__`. It stays defined, since the row names the waveform with it
and branches made before the move still import it.

## 2026-10-10 — the Player is the Funestra, and the mpv object inside one is its engine

The Player became the Funestra on 2026-10-07, and the code now says so. The
package is `funestra_core`. The mpv object a Funestra plays through is its
engine, the word Fun Time's startup alert already uses: `mpv_player.MpvPlayer`
is `mpv_engine.MpvEngine`, `render_player.MpvRenderPlayer` is
`render_engine.MpvRenderEngine`, and `Playback`, `HudOverlay` and the rest take
`engine`. The verbs are `funestra_verbs`, the record every status file leads
with is `status.FunestraStatus`, a panel names its Funestra in
`HudModel.funestra` and `ConsoleModel.funestra` (published under `funestra`
beside the old `player` key), and `console.kino_shows` is what
`main_player_displays` was. The prose says Funestra where it meant one, and
Kino where it meant the Main Funestra's video.

Nothing from before the rename stops working yet, the same way the flicks
rename set out: `player_core` is a package whose finder hands back the very
module `funestra_core` holds for each old dotted name, `mpv_player`,
`render_player` and `player_verbs` forward their old names, `status` answers to
`PlayerStatus`, and `Playback`, `HudOverlay`, `HudModel` and `ConsoleModel` take
`player=` and answer to `.player`. `answers_to_old_names` now lets an old
keyword win over the new one beside it, which is what `dataclasses.replace`
hands it. `tests/test_old_names.py` and `tests/test_renamed.py` hold each of
them. The distribution and the repository keep the name player_core for now.

## 2026-10-09 — the minus sits where the plus does

A panel's minus is in its corner nearest the window's, on the very spot the
plus takes once the panel is minimized, so a second click without moving the
mouse opens it again. In an upper corner the title moves over to make room; in
a lower corner the console's last block does, and a satellite panel's map leaves
that corner free already. The minimized plus, and the plus a corner shows, sit
that far in from the window's corner too.

`hud_minimize.minimize_rect` is gone for `corner_button_rect(corner, panel=,
inset=)`; `hud_placement.hud_origin` takes an `inset` and `block_x` a
`reserve`; `HudPlace` carries the panel's `inset`; `satellite_hud.MINUS_INSET`
is the satellite panel's. `HudOverlay(minus_on_the_panel=False)`,
`ConsolePainter(minus_on_the_panel=False)` and `HudRenderer.render(...,
minus_on_the_panel=False)` leave the minus off for a host that hangs it outside
the panel (FunTimeVR's), and an overlay that does draws nothing while minimized.

## 2026-10-09 — a click in any corner sends the HUD there

`hud_corners` (new, private to this package): a press in a corner of a
Funestra's picture that its HUD is not in asks for
`<player>_hud_restore_at|<corner>` wherever the panel's own presses go -- the
room, or the program running on the window -- which moves the HUD there and
opens it if it was minimized; the pointer in such a corner puts a plus where
the minimized HUD would sit, named "Move this HUD here", or "Show this HUD
here" beside a minimized one. A press anywhere else on the picture is still a
press on the picture, and so is one in the HUD's own corner. `Funestra.leave()`
is the pointer leaving the window, which takes the plus down and the panel's
tooltip with it.

A panel says where its HUD sits as a `HudPlace` (whose HUD, which corner, how
far in from the edges, whether minimized): `HudOverlay.hud_place`, and
`ConsolePainter.hud_place` for the console. `plus_button` and `plus_bgra` draw
the plus for a corner or a side, which is what the headset hangs beside its
players.

`console_hud._MARGIN` is `MARGIN` and `hud_minimize._mark_font` is `mark_font`
now that the corners read them, and `hud_placement._corner` is `corner_at`.

## 2026-10-10 — `console.aim_row` is declared

Origenerator takes the row that aims the device from here now (origenerator
#383), so `aim_row` joins `console.__all__`. `shape_label` stays offered until
Fun Time, which still names its waveform with it, takes the row too.

## 2026-10-10 — Genau's clips are flicks

The word "clip" now means a video cut out of a whole one, so Genau's short
looping videos needed a name of their own. The apps show and hear them in the
word each one's content overlay gives under `genau_flick_words`, which is
library vocabulary and so never in source; in source they are flicks. The eleven
`clip_*` modules are `flick_*` modules, and every name in them and in the
`genau_*` modules that said clip says flick: `FlickAdvanceState`,
`FlickCacheStore`, `FlickLoadController`, `FlickRenderController`,
`FlickSelectionController`, `FlickSequenceController`, `FlickFlip`,
`FlickScrub`, `FlickPicture`, `flat_flicks_in`, `vr_flicks_in`, `scan_flicks`,
`load_flick_frames`, `move_flick_to_weird`, `playhead.flick_playhead`, and the
keyword names and attributes of each. Genau's seconds verbs are
`FLICK_SECONDS_DOWN`, `FLICK_SECONDS_UP` and `FLICK_SECONDS`; its status says
the flick on screen as `flick=`; its audio companion hears `FLICK <stem>`.

Nothing from before the rename stops working yet. Every open branch of an app
runs out of that app's one venv, and the everyday checkout goes on running the
old spellings until the main verifier moves it, so the old names stay: each
`clip_*` module forwards its old names to the `flick_*` one, the renamed
classes take their old keyword names and answer to their old attribute names
(`player_core.renamed`), the old seconds verbs are still answered, the status
still carries `clip=` beside `flick=`, and the notifier says `CLIP <stem>` after `FLICK <stem>`. `tests/test_renamed.py` holds
each of them, and `tests/test_consumer_imports.py` counts a name a consumer
imports under its old spelling as reaching the name it became. They go, in one
change, once no checkout of fun_time, genau or origenerator names them.

## 2026-10-10 — the row that aims the device is built here, and its waveform button wears the waveform

Fun Time and Origenerator each declared the same row of buttons for the OSR2 --
cruise, human inspired, the waveform, the quarter offset and the four control
states -- so it is built once, as `console.aim_row`. The waveform button on it
wears the waveform the motion is in, sine, triangle, square or sawtooth, from
shared_ui's marks, where it wore the sine for all four; the sine keeps the mark
named `wave`, which every version of shared_ui draws. `aim_row` is declared
once a consumer imports it, in the landing after that one.

## 2026-10-10 — the crossing a second Genau made into the room is gone

Genau has no window of its own since v0.1.414, so nothing arrives beside the
Genau that has the room any more. `crossing.py` and `genau_arrival.py` are
gone with the tests that drove them; `GenauRefreshController` no longer takes
`arriving`, `let_go`, `present_scene`, `set_hud_mode`, `console_file` or
`set_console` (the Funestra draws the console now, off the console file);
`GenauReadout` no longer takes `console_file`, `set_console`, `current_clip` or
`publishing`, and keeps the `DriveHud` it last built as `drive`;
`GenauNotifier` no longer takes `held` and has no `let_go`; `ClipSelection.follow`
and `Flag.moved` are gone with their callers. No sibling reached any of these.

## 2026-10-09 — a console can be drawn as the device's section alone

`ConsolePainter(device_only=True)` draws the rows that aim the device, the line
naming who has it, and the readout, and nothing else: no minus, no status line
or file name, none of the source's rows and no clip row. It is for a console a
host sets into its own window with nothing playing under it -- Origenerator's
main window, whose console drew a minus that did nothing and a status line about
a slideshow that was not open.

## 2026-10-09 — a locked picture makes a new move each time it comes round

A locked picture made the one move it was dealt over and over: the move changed
only when its host opened the picture again, which a Funestra holding a lock
never does. Locked, a picture is now dealt the next move each time its move has
run its course -- never the kind it just made, as between two pictures -- and
its rounds keep time from when it came up. Letting go of the lock finishes the
round it is in, where it used to jump to the end of its move.

`KenBurns` takes `looping` when it is made, and `set_looping` takes the time
like every other change to it, so a lock let go just after a round ended still
starts that round's move.
## 2026-10-09 — a Funestra wears the panel its own program hands it

A standalone Origenerator's Slideshow runs on a Funestra now (step 4 of the
plan): the one Funestra that app activates for a Slideshow, on a window of its
own, with no room publishing a panel for it. So a Funestra takes `panel=`, a
callable answering the `HudModel` to wear, and draws it where a session would
have published one; its presses come back through `apply_command`, the way the
window's file verbs do, and a press on the picture asks what runs on the window
to pause (`OMNIPAUSE_TOGGLE`) where there is no room to ask. `HudOverlay` takes
the same pair (`panel=`, `post=`) beside its file pair, keeps the readout a
program composes into its model (a session's panel never carries one, and the
room's motion file fills it in), and hands the pointer on the block its source
paints at the foot back to that source -- `foot_press`, `foot_drag`,
`foot_release` and `foot_wheel`, each with where it landed in the block's own
pixels -- since only the source knows what it drew there; `HudTargets.foot` is
where that block landed. A Funestra opens heard when told (`muted=False`,
through `on_window` and `VolumeControl`), takes the wheel (`wheel`), and
`Playback` lets go of its item (`let_go`, for a file about to be moved) and says
when the player has nothing up (`idle`). `Pointer` (package-internal) takes what
a press on the picture does rather than the dashboard file, and no longer takes
the window size it never read. `Funestra.press` and `motion` keep their
`window=` for the consumers that pass it. The four foot verbs are declared once
origenerator reaches for them, in the landing after that one.

## 2026-10-09 — the Funestra declares what the Main Player reaches, and the second window's verbs go

Fun Time's Main Player runs Kino and Genau on one Funestra now (fun_time #379,
genau #152), so what it reaches is declared: `player_verbs.SHOW`, `clip_picture.Picture`
and `funestra.User`. What served the second window goes: `DISPLAY_ON`/`DISPLAY_OFF`
(nothing sends them -- the desktop's switch says SHOW, and the headset's main role
answers SHOW), the `hud=` line of Genau's status (its one reader was the main-slot
handover that swapped the windows), `clip_preload` (the window's first-clip preload,
imported by nothing), and the genau package's entry among the known HUD drawers
(there is no genau package). `genau_controls` keeps its `hud` flag: the desktop's
Genau sets it when it loses the window, and the engine stops rendering on it.
## 2026-10-08 — a window follows its playlist file, and fifteen HUD names are declared again

`PlaylistFollower` (new, private to this package): a window takes the list its
playlist file holds whenever that file changes, and `RELOAD_PLAYLIST` only brings
that read forward. Until now the verb was the only way a new list ever reached a
window: the host writes the file and queues one line, `append_command` drops that
line when the queue is held for longer than 25ms and tells nobody, and the window
then played what it had with the new list sitting on disk beside it for the rest
of the session. Fun Time's flake gate caught it twice on the landscape player,
coming back into Origenerator mode.

Declared, fifteen names the apps already import: `hud_row`'s `MUTE`, `SCRUBBER`,
`VOLUME`, `RowHud`, `row_part`, `scrub_to` and `volume_to`; `hud_panel`'s
`draw_button`, `fit_text` and `text_width`; `satellite_hud`'s `BLOCK_GAP`,
`CTRL_BTN` and `MAP_THUMB_H`; `volume`'s `MAX_VOLUME` and `MIN_VOLUME`. A module
lands here private and is declared once an app reaches for it, and that second
half had not happened for the row, the panel or the two HUDs.

A defect left alone: the merge gate does not catch an undeclared name. Its
`prepare` step clones genau, fun_time and origenerator next to the checkout so
`tests/test_consumer_imports.py` has consumers to read, and the run for `e58de4e`
reported that test as skipped -- which is what it does when it finds no sibling
importing this package. The clones are not landing where the scan looks, so that
gate has never once held this surface.

## 2026-10-08 — the clip's row is a block of the panel, and nothing is drawn along a lower edge

A Funestra laid the track, the time readout and the volume chip along the lower
edge of its video while the panel it wears sat above them: two panels on one
screen, and in the headset a wrapped video smears such a row round the nadir.
The row is a block of whichever panel the window wears now -- the room's
console on the main slot, else the published HUD -- so `Funestra` draws exactly
one thing over its picture, plus the loop's two frames hanging under it.

Gone: `Funestra.SCRUBBER_OVERLAY_ID`, `VOLUME_OVERLAY_ID` and
`READOUT_OVERLAY_ID`, with `OVERLAY_IDS` down to the panel and the loop's two
frames; `VolumeControl.press_at` / `drag_at` and `RoomVolume.press_at` /
`drag_at`, the panel placing the press on the chip instead; and
`ConsoleOverlay.tick`'s `lower_edge`, there being nothing down there to clear.

New: `hud_row.RowPress`, the one placement of a press on the row, which both
panels hold and hand `seek` / `set_volume` / `toggle_mute`; `RoomVolume` grows
the `toggle_mute` and `set_level` `VolumeControl` already had, so both answer
the same two verbs. Each panel reports `row_rect`, the row in its own
coordinates, and `row_track`, the track's two ends and the y under the panel in
the window's -- `hud_row.track_on_screen` and `UNDER_THE_PANEL_GAP`.
`loop_thumbnail_xys` takes `top` in place of `win_h` and hangs the frames
there. `HudOverlay.tick` takes `heatmap` where it took `funscript`: a panel is
as wide as what is on it, so its host measures the track and builds the colors
across it, and `hud_row.fitting` drops a fill of the wrong length rather than
letting `timeline.progress_bar_bgra` raise -- which took mpv's render loop with
it and left a window showing no picture at all. `HeatmapStrip.update` builds
nothing for a width of 0, which is a host that has not measured a track yet.

## 2026-10-08 — a HUD is divided into sections, and the console's device rows ride apart

Both painters lay their panel down as a stack of sections with a line across
the slab between each (`hud_sections.stack`, `HudPanel.divide`). A player's
panel stacks its status, its declared buttons with the speed row, the clip's
row, the device, the source's foot block and the map; the main console stacks
its status, its declared buttons, the device and the clip's row.
`satellite_hud.FAMILY_GAP` is gone, `panel_layout` takes the status section's
height as `status_h` and a foot's as a plain `foot_h`, and the console's
`_ROW_GAP` is `_BLOCK_GAP`, the gap between the device's own parts.

`ConsoleModel.osr2_rows` is new and published as `osr2_rows`: the rows that aim
the device, drawn at the head of the device's section as `HudModel.osr2_rows`
already were. A console older than this one drops the key, so a source that
publishes its aim row there waits until every app drawing its console runs
this version.

## 2026-10-08 — the Funestra draws the main slot's console, and everything else the Main Player drew

Everything Fun Time's Main Player painted over its video is the Funestra's drawing
now, so the Main Player can become the Main Funestra in the fun_time landing that
follows: the console the room publishes for the main slot (`console_overlay`,
read off the console file and the drive file the same way the satellite panel is,
its presses and the drive readout's drags posted on the dashboard's channel), the
scrubber with a scripted item's colors, the zoom while a stretch is marked and the
two frames of a running A/B range (`scrubber`, which is the Main Player's
`overlay` module moved here whole), the room's volume chip beside a Funestra's own
(`volume_control.RoomVolume`), and the black a Funestra shows when the room gives
its rectangle to another window (`display`).

`Playback` carries what every User of a Funestra shares and the Main Player kept
to itself: it can open holding its item, seek by a step, owe a seek mpv will not
take yet, keep a mark no seek may rewind before and an A/B range mpv goes round
(the loop *recording* stays with Kino; these are the stretches it marks and
repeats), say where in the list it is, whether its item is portrait, and how
many items it has opened.  The Funestra answers TOGGLE_LOCK, SET_VOLUME (when
its sound is the room's) and DISPLAY_ON/DISPLAY_OFF, names its ten-second seek
step `SEEK_STEP_MS` for the players that have to seek alike, publishes
`portrait`, and takes a `User` that runs on it in the same process: its verbs are
asked before the Funestra's own, it takes a pass of its own each frame before
the playback advances, its lines ride in the status file and it heads the
console.  New names stay undeclared until fun_time imports them; the follow-up
declares them.  `heatmap.ScriptColors` went: the strip does its job.

## 2026-10-08 — `wave_stack.bars` is declared, and the dials are no longer offered

Origenerator now reads the Robot Hand's Amp, Speed and Center as
`wave_stack.bars`, and its hold no longer puts them back through
`robot_hand.set_dials`, so `bars` joins `wave_stack.__all__` in place of
`dials`, and `set_dials` leaves `robot_hand.__all__`.

Both old names stay defined, `dials` as a second name for `bars`, until no
Origenerator branch names them: the machine's one venv runs every open branch,
and branches made before the rename still import `set_dials` and read
`wave_stack.dials`.

## 2026-10-07 — the mode called Video is Kino

`MainMode.KINO` and `SatellitesMode.KINO` replace the two `VIDEO` entries, and
the word they put on the wire is `kino`. "Video" stays the word for a video
file; only the mode was renamed, so that its name can mean nothing else. A
reader that does not know `kino` falls back on its default, which is this mode
at every reader the family has, so an app still pinned to an older release
reads a new file right; and a file still saying `video` reads as kino here, the
same way.

`VIDEO` stays on both as a second name for `KINO` until no Fun Time branch names
it. The machine's one venv runs every open branch, and 38 Fun Time worktrees
still said `MainMode.VIDEO` the day this shipped: without the second name each
of them would die on import the moment that venv took this release.

## 2026-10-07 — a Funestra: the window that draws its own HUD, and the gate on who else draws one

`funestra.Funestra` is the satellite program's run loop moved here without its
window: built on a way of playing and the files its User drives it through
(`Channels`), it plays what it is handed, answers the verbs, publishes the
status, and draws the published panel, the scrubber, the volume chip and the
playhead readout as mpv overlays.  With it come fun_time's `satellite/session.py`
(`playback.Playback`), `satellite/runtime.py` (`funestra_controls`),
`satellite/status.py` (`funestra_status`), `satellite/versions.py` (the
`NEXT_VERSION` / `PREV_VERSION` verbs, in `player_verbs`), `satellite/hud_overlay.py`,
`satellite/volume.py` (`volume_control.VolumeControl`), `satellite/pointer.py`
(`pointer`), and the main_player modules the satellites borrowed: `play_points`,
`seeking`, `scripted_device` and `heatmap`.  Every name is declared in
`__all__` once fun_time's import of it has landed.

`tests/test_hud_drawers.py` fails the build on any consumer package that imports
a painter out of this one except the drawers still to move onto a Funestra,
listed in `KNOWN_DRAWERS`, and on a listed one that has stopped drawing.

## 2026-10-07 — Genau's clips folder forks into 2D and VR, and the weird pile follows it

`scan_clips` walks into the folders inside the ones it is given, so a 2D folder
split into `AI` and `non_AI` plays as one. `flat_clips_in` and `vr_clips_in`
name the `2D` and `VR` folders inside Genau's clips folder, and
`weird_folder_for` is where a condemned clip goes: the same place in the weird
pile beside the clips folder that it had in the clips folder. The three are
declared in `__all__` once an app that imports them has landed.

## 2026-10-07 — Genau plays a clip it is named, keeps a flip in the clip's record, and decodes every clip itself

`PLAY_FILE <clip>` puts a named clip up in Genau the way it does in every other
player: jumped to where the clip is in the order, or spliced in after the clip on
screen when it is not, and refused when the file is not on disk. Hosts wire it
as `GenauControls.play_file`, which `ClipSelectionController.play` answers.
Genau's drain now folds only a line's keyword to upper case, so a path arrives
as it was written.

`ClipFlip(metadata_root)` keeps a flip as `genau.flipped` in the clip's own
metadata record, under the record's lock, in place of `flipped.txt` beside the
clips folder; `flipped_record_for_clips_folder` is gone. A host that names no
metadata folder gets a flip that lasts the session and a log line saying so.

`load_clip_frames` no longer reads `.rhcache` frame caches: ffmpeg decodes a
clip three to six times faster than the caches load, and nothing has written
one since April. Its second argument and `cache_dir_for_clips_folder` stay
until no branch of genau or fun_time still passes or imports them.

## 2026-10-06 — the Robot Hand's Amp, Speed and Center are bars, not dials

The console draws them as bars, and the code called them dials, a word the
screen never shows. So
`wave_stack.bars` and `wave_stack.Bars` are what `wave_stack.dials` and
`wave_stack.Dials` were, `RobotHandState.exact_bars` is `exact_dials`, and the
internal names and the prose follow. `wave_stack.dials` stays as a second name
for `bars` until Origenerator's tests, the one consumer reaching it, have moved,
and `robot_hand.set_dials` stays until Origenerator's hold stops calling it;
both go then.

## 2026-09-28 — a HUD button whose mark is missing says so on hover

shared_ui draws a stand-in, a rounded square with a question mark in it, for a
mark its installed version does not have, where it used to raise `KeyError`
inside the paint. `Button.tooltip_on_hover` is what a HUD shows for a button: the
source's own `tooltip`, and when the button's face is one of the family's marks
that shared_ui lacks, shared_ui's `tooltip_for` explanation on the lines under it.
`console.tooltip_at` and `satellite_hud.button_tooltip` answer with it, and the
satellite map's own loop, strike, expand and favorite controls ask `tooltip_for`
with their marks, which now sit beside their tooltips in `satellite_hud`
(`LOOP_MARK`, `EXPAND_MARK`, `FAVORITE_MARK`, `WRONG_ACTION_MARK`). A HUD tooltip
starts a new line wherever its text does, where it used to fold a line break into
a space.

## 2026-09-28 — a frame swapped in carries the still's move, and the aim is gone

`swap_still(path)` puts a picture up in place of the one on screen and carries
on that one's move and its time: the move is not dealt afresh, and the swapped-in
picture ends when the one it replaced would have -- onto the staged next clip, or
as `eof` where nothing is staged. It is how a host shows the frames of a picture
still being made with the same move every other picture gets.

The aim leaves with the one feature that used it: `aim_still` on the players,
`KenBurns.aim`, `Aim`, `Fit` and `CLOSEST_AIM` in `ken_burns`, and `AIM_STILL`,
`aim_still` and `aim_of` in `player_verbs`, none of which was ever in `__all__`.
The players stop reading their windows' size off Windows (`GetClientRect`), which
only an aim needed.

## 2026-09-26 — a still makes one of three moves, and a host can aim one

`push_still` no longer only creeps into the middle of a picture. Each picture
is dealt a move by `ken_burns.Moves` (which `still_push.StillPush` became, as
`ken_burns.KenBurns`): a zoom in about a spot anywhere in it, a zoom out from
one, or a pan from a corner to the opposite one at a steady `ZOOMED_IN`, never
the kind the picture before had. A view reaches mpv as `video-zoom` and
`video-align-x/-y`, with `video-recenter` on for every player: mpv then places
the picture itself, against the window and the file actually on screen, from
flush with one edge at -1 to flush with the other at +1 along a side it
overhangs, and centered along a side it fits inside, so no view and no pair of
properties half-set ever shows the window past the picture's edge. A windowed
player reads its window's size off Windows (`GetClientRect`), an offscreen one
off the target it last rendered; only an aim needs it.

`aim_still(part, seconds)` is new: from wherever the picture's move had got to
it eases, over *seconds*, onto the part `(x0, y0, x1, y1)` given in fractions
of the picture -- as close as the window fits it, never nearer than
`CLOSEST_AIM` -- and holds there until the next file; on a player laying the
picture out in tiles it aims at the middle tile.

Four defects of the old creep went with it. A room told twice that it was
frozen moved the picture on by the time between the two. A picture stepped to
while the room was frozen came up partway through its move. The move, whose
clock starts when the file does, a little before its first frame, ran out a
little before mpv ended the file and started over for those last frames; a
picture whose hold has run out now waits at the end of its move for the next
file, and only a locked picture, which repeats, makes its move again
(`set_loop_file` tells the move which it is). And between two files, while mpv
reports no video track, the last picture was put back to its fitted size for
the frames before the next one came up; it is now left where it was. A pace of
nought holds a moving picture where it is rather than snapping it back to its
fitted size, and a picture held since it came up sets off with a zoom in from
that size.

## 2026-09-26 — the scrubber's frame is no longer published piece by piece

`framed_track`, `draw_border`, `draw_track_marks`, `BAR_BORDER` and `BORDER_W`
leave `__all__`. Fun Time's main player drew its funscript strip out of them;
it now asks `progress_bar_bgra(..., heatmap=)` for the whole bar like every
other player, so no app reaches for the pieces. They keep their names and
signatures, so a checkout still drawing the strip the old way runs as before.

## 2026-09-26 — a satellite HUD holds one size

The panel `satellite_hud_paint.HudRenderer` draws is laid out top down by
`satellite_hud.panel_layout`, and the nav map is its last block, under the
clip's row, the device and a source's own block, set off from them by
`FAMILY_GAP` (which `DEVICE_GAP` was). The map is one fixed box whatever it
shows: three cells a side are always kept, every cell is a slot
`slot_width(player)` wide (the widest shape a side's clips take at full height,
4:5 or 16:9) with the picture centered in it and shrunk when it is wider, the
row-label gutter is `ROW_LABEL_GUTTER` wide, and the loop and "more seeds"
buttons stand past the axes' fixed ends. The box is kept before the first clip,
and the line under the status is kept while it is empty. A note after the file
name shortens the name rather than widening the panel (`name_line`), and a status
line too long for the panel is drawn at the largest size that fits
(`largest_size_that_fits`) rather than widening it.

Gone, having nothing left to do: `panel_height`, `thumbnail_rects`, `map_reach`,
`map_column_height`, `cell_width` and `CELL_W`, `MIN_GUTTER` and `MAX_GUTTER`,
`FILTER_ROOM`, `friendly_action_label`, and the painter's `gutter_width_for`.
None was in an `__all__`.

## 2026-09-26 — Genau says whether the clip on screen is portrait

`genau_status.txt` gains a `portrait=` line: `1` for a clip taller than it is
wide, `0` for any other, empty until a clip's frames are in hand. It comes from
`ClipRenderController.portrait`. Fun Time reads it to give Genau most of the
secondary monitor when the main player has the crown. `write_status_file` now
takes the text `build_status_text` makes, rather than repeating every one of its
arguments.

## 2026-09-25 — a player can lay a portrait picture side by side across a wide window

`tile_to_fill(width, height)`, called with the window's size every frame, shows
as many copies of a portrait picture as fit across a window wider than it is
tall, and one of anything else. mpv does it on the GPU: `tiles.glsl` widens the
picture by the count and `video-aspect-override` letterboxes the widened shape,
so hardware decoding stays on. `source_dims` is the picture's own shape, which
the override does not change. Fun Time's main player and portrait player call
it; nothing else does.

## 2026-09-25 — Genau's picture goes where the room holds the device

`PARK` and `RETRACT` are new verbs on `genau_cmd.txt`: the room is holding the
OSR2 at home, or at the far end. Neither stops the hand; `PAUSE` still does
that, and a hold the hand plays on under (output switched off) is a hold all
the same. From the verb until the hand drives the device again, the frame shown
is the device on the broker's own schedule: held where the picture was for
`device_walk.BROKER_HOLD_DELAY_MS` (the broker's `HoldScheduler.DELAY_SECONDS`),
then walked to that end over `PARK_SETTLE_MS`. When the hand takes the device
back, the picture eases from wherever it was onto the motion over the handoff
glide, as the device does, rather than jumping there. `PAUSE` alone still leaves
the picture where the hand let go. `GenauControls.room_hold` is built by
default, so no shell wires anything.

Where each hold keeps the device is `console.HELD_HEIGHT` now, one table the
readout's dot and the picture both read.

`clip_renderer.display_index_for_phase` is now only the phase-to-frame
arithmetic. Whether the picture holds still is the tick's to decide, since only
the tick knows the room is holding the device.

## 2026-09-25 — every player's scrubber can carry its funscript's colors

`progress_bar_bgra(..., heatmap=colors)` fills the track with a funscript's
colors, one RGB per track pixel, in place of the dark fill; the frame, the
cursor and the marks are the plain bar's. The main player drew that strip with
a copy of this frame of its own, and nothing else could draw it at all, so Fun
Time's side screens and headset could not show a script's colors. The panel
row's `heatmap` was handed to the bar as its loop bounds, which crashed the
first draw a host gave it; it now reaches the bar as its colors.

## 2026-09-25 — a source can put the newest frame of a picture being made over the one on screen

`SHOW_FRAME <path to an image>` asks a player to draw that picture over what it
is showing, and `CLEAR_FRAME` to take it off; a player drops it by itself when
its list moves on. Origenerator sends them for a picture ComfyUI is still making
-- a generation, or an enhancement of the picture on screen -- so a show on a
satellite shows the work as it comes in, the way its own window does. Neither
name is in `__all__` yet: the consumer gate calls a declared name no sibling
imports a name published for nobody, so they are declared once Fun Time's
players answer them.

## 2026-09-25 — a source can say something about the clip on screen, after its name

`HudModel.item_note` is published and parsed with the rest of the panel, and the
renderer draws it on the line under the status, after the file name and the same
` · ` the status line joins its slots with -- alone on that line where the player
names no file. What it is for: Origenerator's shows say there which version of a
picture is on screen and whether a better one is being made or waiting to be,
which a satellite playing one of its shows had no way to show. Unset, nothing any
panel draws moves.

## 2026-09-22 — a Genau clip can be flipped half a loop, for good

`FLIP_ENDS` turns the clip on screen over: its frames are shown half a loop on
from where the device is (or from the broker's beat), the bar's seek goes back
through the same half loop, and `genau_status.txt` says `flipped=1` while it is.
The flip is remembered in `flipped.txt` beside the clips folder, one clip name a
line, so the next session and the headset show that clip the same way.
`GenauControls.clip_flip` is built by default; no shell wires anything.

## 2026-09-21 — the clip's row is a block a panel hosts

`hud_row` draws the scrubber, the volume chip and the playhead readout into a
panel at its own width — the same track, chip and pill this package already
paints — and `row_part` / `scrub_to` / `volume_to` say what a press on it is on
and what it asks for. Both panels host it: `satellite_hud_paint.render` takes
`clip_row=` (with a `heatmap` for a host that has a funscript) and reports
`HudTargets.row`; `ConsolePainter.bgra` / `.rgba` take the same and report
`row_rect`. A panel narrower than the row is widened for it, the way it is
widened for its own rows, rather than letting the chip sit over the track.

Both take it from the PLAYER rather than from the published model, the way the
file name is taken: what is decoding is the player's own, not what the source
published.

What it is for: every player here laid that row along the last rows of its own
video, which on a screen that already carries a HUD is a second panel — and on a
wrapped video it is smeared round the nadir, which is why the headset already
draws it on the console. Nothing a panel already draws moves: 864 made-up panels
are byte for byte identical with `clip_row` unset.

## 2026-09-21 — a source may hang a block of its own at the panel's foot

`HudModel.foot` is anything with `size()` and `paint(image, x, y, width,
pointer)`: the satellite panel measures it, widens to hold it, sets it off from
its own blocks with the break the device block already takes, and paints it
under everything it draws itself, taking back the `(rect, Button)` targets its
controls occupy so a press posts that button's verb and a hover names it. It is
never published — like the device half, it is the drawing host's own, and a
panel parsed out of a file has none.

What it is for: a host that is more than a player has things to report that no
satellite does, and the only place for them was a second panel over the same
video. Origenerator's shows floated their generation queue that way.

Nothing a player draws moves: 864 made-up panels — both orientations, three clip
shapes, with and without a map, a device line, a readout, a file name, a rate
and a hover — come out byte for byte identical from v0.1.296 and from this
version with `foot` unset, targets included.

## 2026-09-20 — a source names the camera words its rows carry

The words the library writes in front of an act to say how a clip was shot
were two literals in `satellite_hud` (`_ACT_MODIFIERS`, `_ACTION_ACRONYMS`),
which is this package knowing one app's library. They are library vocabulary,
the same as the acts they prefix, so they arrive the way everything else the
panel draws arrives: in the model its source publishes. `HudModel` carries
`camera_words`, written as the library writes them; `hud_text` and `parse_hud`
carry the key, and a panel from a publisher that never wrote it reads as naming
none. Fun Time fills it from its content overlay. A hosted Origenerator names
none, because its rows are folders the user named rather than the library's
acts, so a row's first word is never set apart there.

The functions that read a row's label take the words from their caller:
`label_is_filtered(label, filter_query, camera_words)` is the one the siblings
reach, and `act_is_filtered`, `split_acts`, `action_label_blocks`,
`friendly_action_label` and `satellite_hud_paint.gutter_width_for` inside the
package. None has a default, so a painter that forgets to pass them fails
rather than quietly lighting a camera word with its act. The gutter is
measured with a camera word written as it will be drawn, since an initialism
is wider in capitals than in title case.

Nothing a player draws changes: 112 made-up panels, both orientations, every
pairing of eight row labels with seven filters, come out byte for byte the
same from v0.1.288 with its literals and from this version handed the same
two words.

## 2026-09-19 — every source declares its own buttons, so the stock ones go

Fun Time's players and Origenerator's shows and console now declare every
button they draw, so the fixed rows a panel declaring none was drawn from are
gone: `satellite_hud.standard_rows` with its tables (`CONTROL_GROUPS`,
`MODE_BUTTONS`, `MODE_TOOLTIPS`, `CONTROL_TOOLTIPS`, the faces), and
`console.console_rows` with `osr2_row`, `CONSOLE_VERBS`, the glyphs it typed
and the marks it named. So are the panel fields only those rows read, which no
source writes: `HudModel`'s `favorites_filter`, `enhanced_filter`, `latest` and
`satellites_mode`; `ConsoleModel`'s `broker`, `loop_state`, `scripted_filter`,
`cruise`, `learned`, `shape`, `plays_vr`, `plays_flat` and both filters;
`ModeHud`'s `has_compilation`, `has_other_versions` and `jump_to`; and
`ConsoleHud.modes_row`. A reader passes those keys over when a publisher on an
older release still writes them, so a mixed-version room still reads its
panels.

What the stock rows said now lives beside what answers it — Fun Time's
`fun_time.console_buttons` and `fun_time.satellite_buttons`, Origenerator's
`origenerator.gui.console_buttons` and `origenerator.gui.show_buttons` — and
the tests of what each button offers, lights and says moved with them when
those sources started declaring; about a hundred here that held the stock rows
go with the rows. What the painters do with a declared button is tested here as
before, from a made-up band (`tests/satellite_rows.py`, `tests/console_rows.py`)
in place of the stock one. `console.shape_label` is declared, Origenerator's
console naming its waveform with it. The satellite's speed row, the one pair a
player still draws for itself, builds its own buttons (`satellite_hud.speed_row`)
rather than reading the deleted tooltip table. And the OSR2 line no longer
holds a group gap open before its label when no source put a control on it.

## 2026-09-16 — a named output is the device, not a driver sharing its name

New module `audio_outputs` (`Output`, `pick_output`, declared once Fun Time's
audio companion imported them): a session names the output it wants by a
fragment of its name, and a headset maker's own software installs
outputs carrying that name too — a wireless streaming driver Windows enumerates
under `ROOT`, with no device of its own. Which one the fragment lands on was the
order Windows happened to list them in, so the sound could go to the driver
nobody is listening to. `pick_output` prefers the output a real device answers,
reading which is which from Windows' own endpoint registry, and still takes the
streaming one when it is the only one named. `mpv_player.set_audio_device_matching`
routes through it; Fun Time's audio companion is the second caller.

## 2026-09-16 — the names the siblings reach are declared

Fun Time now imports the buttons contract, so each module a sibling reaches
through declares its API in `__all__`: `hud_button` (`Button`, `BUTTON`,
`FIT_THE_WORD`), `hud_marks` (the shared-mark and app-mark names), `hud_panel`
(`SYMBOL_FONT`, `load_font`), and `console`'s layout names (`GAP`, `GROUP_GAP`,
`ROW_LABEL_W`, `VALUE_W`, `place_rows`, `hit_test`, `parse_console`). The OSR2
control states a console consumer reaches, `robot_hand`'s two hold centers and
`drive_readout.publish_drive` are declared for the same reason; `console` drops
`CONSOLE_VERBS` from its list, which no consumer imports. The fixed fallback
rows stay until Origenerator declares its own buttons. Nothing here does
anything differently.

## 2026-09-13 — a picture is an item a player shows

A playlist item can be a still picture, and every player shows one with what
libmpv already does for an image: `image-display-duration` holds the frame, and
then the file ends as a finished video ends, so no player's advance, lock or
pause had to learn anything. `mpv_player` gained `set_pace` (0 holds; a player
opens at 4 seconds) and `showing_picture`, observed off
`current-tracks/video/image`; `player_verbs` gained `SET_PACE` and
`pace_seconds`, the one reader of its value; `PlayerStatus` leads with a seventh
line, `picture`. `PlaylistItem` gained no column: mpv says whether an item is a
picture once it opens the file, the still a HUD map draws is the cell's
`thumb`, and an id is nothing a player needs until a source answers presses
about one.

## 2026-09-13 — the buttons a source declares

A satellite's HUD drew a fixed band (`CONTROL_GROUPS`, `MODE_BUTTONS`,
`CONTROL_TOOLTIPS`) and the console fixed rows (`console_rows`), each lit
off the panel's switches. A source now declares its buttons — rows of
`hud_button.Button` on `HudModel.rows` and `ConsoleModel.rows` (with the
OSR2 line's controls on `osr2_controls`), published by `hud_text` and
`console_text` — and the players draw from them and nothing else, posting
each one's verb verbatim. The two numbers on the console only the drawing host
knows, the video's rate and a clip's pace, are read-outs that name their
number (`host_value`) for the painter to fill; that fixed the clip-seconds
read-out in Genau's window and the headset, which read the pace off the
published panel and so always said "0s". Both painters draw a button through
one `hud_panel.draw_button`; the minimize bar is the satellite's nine pixels
on the console too, and hovering a console button no longer recolors its edge.

The fixed rows stay for now, as `satellite_hud.standard_rows` and
`console.console_rows`, drawing a panel that declares none — Fun Time's move
onto declaring its own is the next landing, and they go with it.

## 2026-09-13 — the player contract, written where it is read

What a content source hands a player and what it gets back was spread across
two repos: Fun Time wrote the playlist line, the console's JSON and each
player's verbs by hand, and this package read them. Each format is now one
pair in one module — `playlist` (`PlaylistItem`, `write_playlist`,
`item_line` / `item_from_line`), `player_verbs`, `status` (`PlayerStatus`,
`status_fields` / `parse_status`), `satellite_hud.hud_text`,
`console.console_text` / `parse_console` — and `control_registry.look_up`
folds the keyword alone, so every player can dispatch through it. README's
"The player contract" says what each carries and what is left for the steps
that first draw a picture or a source-declared button.

The names went into `__all__` once Fun Time's move onto them landed, the same
day: the consumer gate calls a name published for nobody until a sibling
imports it. The playlist item is a `NamedTuple` so that a checkout between the
two landings still unpacked it as the `(video, funscript)` pair it was.
`control_registry.act` left `__all__` with the main player's private lookup,
its one consumer; `playlist.item_line` is reached only through `write_playlist`
and `player_verbs.play_file`, so it is package-internal.

## 2026-09-04 — Genau's engine moves in, for the headset

Everything Genau does that is not its pygame window now lives here, so Fun
Time's VR player can run the same clip player in-process for its genau mode
and GenauVR, a second copy of most of it, can go. Twenty-one modules and their
tests came over from `../genau`; nothing already here changed but `robot_hand`,
which took the hand's control limits. The names moved with the responsibility:

| was, in `genau/` | is, here |
| --- | --- |
| `engine` (`PlaybackEngine`, `update_engine`), `refresh_logic.Beat` | `robot_hand_beat` (`BeatEngine`, `advance_beat`, `Beat`) |
| `tcode` (`RateLimitedTCodeSender`), `device_handoff` | `robot_hand_driver` (`RobotHandTCodeDriver`, `DeviceHandoff`) |
| `limits` | `robot_hand` (`ControlLimits`, `control_limits`) |
| `state` (`SharedState`), `refresh_logic.read_shared_state_snapshot` | `broker_feed` (`BrokerFeed`, `BrokerSnapshot`, `snapshot`) |
| `controls`, `runtime_commands` | `genau_controls` (registry, `VERBS`, `KEYS`, `apply_runtime_command`) |
| `refresh_controller` | `genau_refresh` |
| `drive_readout` (`DriveReadout`) | `genau_readout` (`GenauReadout`) |
| `status_writer` | `genau_status` (with the status file's name) |
| `notifier` | `genau_notifier` |
| `video`, `weird` | `clip_folder` (the scan, and the piles beside the folder) and `clip_decode` (ffmpeg, and the frame cache) |
| `frame_cache` | `clip_decode`, reading WebP through Pillow rather than cv2 |
| `clip_runtime`, `cache_utils` | `clip_cache` |
| `refresh_logic.display_index_for_phase` | `clip_renderer` |
| `first_clip` | `clip_preload` |
| `control_registry`, `flags`, `tick_failures` | `control_registry`, `flag`, `tick_failures` |
| `clip_advance`, `clip_sequence`, `clip_selection`, `clip_loader`, `clip_renderer` | the same names |

The two class renames say what the things are beside what was already here:
the engine is the beat the hand moves to, not playback, and its sender is the
Robot Hand's T-Code driver, the mirror of the funscript's.

**Two dependencies moved with it.** cv2 did not come: `.rhcache` frames are
WebP and Pillow reads them, so the one reader that needed OpenCV is gone from
the family's shared code. `app_support` now is imported at run time, for the
first time here — `clip_decode` launches ffmpeg through its hidden-subprocess
kwargs — where before only the test plugin reached it; every consumer's venv
already has it, and the merge gate already installs it.

**The consumer gate carries 61 waiting names.** Nothing imports the engine from
here until genau's window switches to it and Fun Time's VR player takes it up;
both are the next landings on this branch line, and each takes its lines out
of `tests/no_consumer_imports.txt` as it does.

**The comment ratio falls because the denominator grew: 0.7704 → 0.6416** over
`player_core/` and `tools/`, SLOC 3,310 → 4,897, files 29 → 50. The engine
arrives at the density genau kept it at, and nothing measured before this
changed.

## 2026-08-31 — the sanitize toolchain leaves `tools/` (item 44 stage 2)

`tools/sanitize_guard.py` and `tools/__init__.py` are gone; the guard is
`app_support.sanitize`, installed with the package, and `tools/githooks/` holds
the two shims that run it. `tests/test_sanitize_guard.py` is gone too -- its
fifty-nine unit cases live in app_support now, and the one case whose subject is
this checkout arrives from `app_support.sanitize.pytest_plugin`, named once in
`pyproject.toml`. The merge gate installs app_support for that line; nothing
under `player_core/` imports it.

**The comment ratio moves because its denominator did: 0.7447 → 0.7532** over
`player_core/` and `tools/`, SLOC 3,415 → 3,270, files 31 → 29. Not a comment
was added or removed here; the two files that left were the least-commented in
the measured set. The 0.7692/3,661 in this file's header is the audit's baseline
and predates both this and the harvester's removal.

**One behaviour change, in the hooks.** The `[ -n "$python" ] || exit 0` escape
is gone. While the guard was a file in this repo it ran off any interpreter, so
"cannot run" meant "no python at all"; as an installed package it means "not
installed in the interpreter this hook found", which is a checkout that has
silently stopped being guarded. Measured through a real `git commit`: with no
python on PATH the old hooks committed a blocked term (exit 0), these refuse it.
The four cases that matter -- a staged term, a term in the message, a clean
commit, a checkout with no blocklist -- behave exactly as before.

## 2026-08-25 — the painters pinned, the unadopted helpers deleted

**Pins.** All seven mutation survivors the audit recorded against this suite are
now killed: the two tooltip-bounds tests, the satellite's reset button, the drive
readout's numbers, the funscript park glide and lead-in boundary, cruise
control's stalled-clock cap, and `adjust_center`'s low edge with `HudClicks`'
double-click window. Each was confirmed by re-running the audit's own mutation in
a throwaway worktree, first against the old test (green, as recorded) and then
against the new one (red).

The audit's suggested fix for the drive readout — asserting `TEXT_PRIMARY` is
absent from the section's set of colours — does not work and was not used: the
values are 8px text, so no pixel of a digit lands on the ink exactly and the
section's brightest pixel with the numbers forced white is 235. The test reads
the number's own pixels instead.

**Deletions.**

| what went | source lines | comment ratio |
|---|---:|---|
| `Funscript.trace` / `trace_window` / `_grid` / `planned_trace` | −60 | 0.7692 → 0.7663 |
| `Funscript._window` and its now-constant `tail`, left over by the above | −7 | 0.7663 → 0.7656 |
| `console.shares_the_device`, with three imports ruff F401 flagged | −13 | 0.7656 → 0.7648 |
| `timeline.rgba_to_bgra`, a third copy of a swizzle with no reference at all | −4 | 0.7648 → 0.7654 |
| `drive_readout._LESS`/`_MORE`, five unread re-exports, a stale `noqa`, a seven-line blank gap | −16 | 0.7654 → 0.7659 |
| Four keyword parameters no caller varies: `HudPanel(alpha=)`, `draw_icon(fill=)`, `_value(left=, right=)` with `label_pair_x(right=)`, `drive_layout.controls(prefix=)` | −9 | 0.7659 → 0.7668 |
| `drive_layout.hit` and two of the three `Rect` declarations, **adopted** into a new `geometry` module that four inline point-in-rect tests now call | −2 | 0.7668 → 0.7678 |
| `console_hud.DOT` and both hand-drawn active dots, **adopted** into `hud_panel.draw_active_dot` | −8 | 0.7678 → 0.7658 |
| `hud_panel.BG_BUTTON_ACTIVE` — **kept**, and the whole mirrored palette pinned against `shared_ui.colors` instead | 0 | 0.7658 → 0.7658 |
| Three spellings of the T-Code position range, **adopted** into `tcode.POSITION_MAX` and `tcode.to_tcode_position` | +8 | 0.7658 → 0.7646 |
| Both hand-written BOM strips in `file_channel`, **adopted** into `_read_command_text` | +2 | 0.7646 → 0.7656 |
| An unreachable fallback return, an empty `pass` branch and two function-local `numpy` imports | −6 | 0.7656 → 0.7669 |

Net: 3,661 → 3,616 SLOC, 0.7692 → 0.7669. Two helpers the audit called
unadopted were adopted rather than deleted, which is why the line count moves
less than the deletion list suggests.

`tools/` was untouched throughout the item itself: `sanitize_guard.py` and
`githooks/install.py` are maintained byte-identical across eleven checkouts, so
their stale `noqa` and their comment ratios (0.55 / 0.31) belong to the
cross-repo consolidation rather than to this repo on its own. The third file
there, `harvest_blocklist.py`, was deleted afterwards on the owner's
instruction — see below.

**Comments.** Worked file by file against the retained-comments list in
`audit/findings/player_core.md`, which is the floor: every range it marks *keep*
is still there, whole. Nothing was stripped off opaque code — each cut either
corrected a statement that was false, deleted a second copy of a rule stated
elsewhere, replaced a section-heading comment with a function of that name, or
kept the invariant a war story was protecting and dropped the story.

| what changed | comment ratio |
|---|---|
| Stale docs: `mpv_player` "not unit-tested", "three applications", the README's six-of-27 module list | 0.7669 → 0.7658 |
| Six comments describing things that are not there (see the commit for each) | 0.7658 → 0.7630 |
| The symbol face named once in `hud_panel` instead of three times, and the glyph notes that named the wrong glyphs | 0.7630 → 0.7590 |
| `funscript`'s three bounds explained by the incident that set them | 0.7590 → 0.7579 |
| `HudRenderer.render`'s section headings became `_draw_status_band` and `_draw_mode_row` | 0.7579 → 0.7528 |
| `ConsolePainter._paint`'s top block became `_draw_top_block` (CC 18 → 15) | 0.7528 → 0.7525 |
| The console's eight histories cut to the rules they guarded | 0.7525 → 0.7439 |
| The drive readout's five attempts, and `drive_layout`'s and `tcode`'s | 0.7439 → 0.7403 |
| The satellite explaining itself by the dashboard it replaced, thirteen times | 0.7403 → 0.7364 |
| Seventeen more across nine files with one war story each | 0.7364 → 0.7267 |

**Where it ended: 0.7692 → 0.7267 over 3,626 SLOC.** The audit counted 21 "used
to" lines across seven modules; four remain, and three of those are on the
retained list or state a live fact about Qt rather than about this code.

Every rendered panel is byte-identical to `bb4c790`, the commit the audit
measured: 22 of them — three console modes with and without hover, both
satellite sides across the mode row and the subtitle, and both empty shells.
Every comment-only commit was checked by parsing the file before and after and
comparing the syntax trees with docstrings stripped, so no expression, constant
or branch moved in any of them.

**The floor held, with four deliberate exceptions.** Of the 278 retained ranges,
269 are word-for-word what they were. Four were reworded because a *different*
finding in the same bundle required it, and each keeps its mechanism:

- `drive_layout.py:11-15` — "kept apart from the painters" is singular now, and
  "both toolkits' panels" is gone, because `dead/011` established there is one
  painter. The reason the layout is kept apart — a wrong hit target still looks
  right — is untouched.
- `drive_layout.py:182-189` — the `prefix` paragraph went with the parameter
  (`dead/008`); the rest of the docstring stands.
- `direct_control.py:33` — the "A T-Code motion position" note moved to
  `tcode.py` with `POSITION_MAX` itself (`design/010`).
- `wave_stack.py:142-147` — the reference to `player_core`'s own
  `_recompute_center` from inside `player_core` went (`dead/013`); what it
  described, the centre giving way as the amplitude opens past it, stays.

The other five the checker flags are boundary artifacts: a range that begins
mid-sentence in a narrative the audit separately asked to delete, or one whose
note already said *first sentence* or *minus the genau reference*.

### The blocklist harvester, removed

`tools/harvest_blocklist.py` and `tests/test_harvest_blocklist.py` are gone, on
the owner's instruction and outside the scope of item 13.

The blocklist is a curated list of domain terms, written by hand to keep the
nature of this suite out of a public repo. The harvester learned terms off the
media library instead and merged them in, which is how the machine-generated
list now sitting in these checkouts came to exist — and that list is why
publication is frozen. A tool that rewrites a hand-curated secret is not a tool
whose first-run crash wants fixing.

That crash was `player_core/all/dead/025`, filed in the audit's bugs register
and recorded here as found-and-not-fixed while the item ran. It is moot: the
file is gone. The finding should be closed as withdrawn rather than carried into
the cross-repo consolidation, and item 44's plan to publish `tools/` from
`app_support` should drop `app_support/app_support/sanitize/harvest.py` with it.

`tools/sanitize_guard.py` is untouched and unweakened. It never referenced the
harvester: it reads the blocklist and refuses a staged term, which is the half
that does the protecting.

### Still open from this item

The ratio is reported here, not gated, and `player_core` still has no dead-code
scan, by design. What this arc did not take from the bundle: the test-suite
findings beyond the seven mutation survivors — the private names asserted on
across seven files, the near-duplicate tests, the missing `tests/conftest.py`,
and the two guard tests coupled to the real checkout. Those are the suite's
shape rather than its trustworthiness; the seven probes that could not fail
now do.
