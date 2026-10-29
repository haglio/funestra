# funestra

The Funestra, and everything the programs that open one share. The package is
`funestra`, as this repo is; it was `player_core` until 2026-10-10 and
`funestra_core` until 2026-10-11, and `player_core.<module>` and
`funestra_core.<module>` still import, as the very same module, for every
branch written before then. A Funestra is the window its users run on: it
plays what it is handed, draws the HUD, and is driven, in its own process or
through its files, by whatever runs on it. Its users are Kino and Genau, which
run on Fun Time's Main Funestra, and Origenerator's Slideshow, which runs on a
Funestra both in a Standalone Origenerator and inside Fun Time, where
Origenerator hands it to one of Fun Time's Satellite Funestras.

| Consumer | Repo | What it takes |
| --- | --- | --- |
| Genau | `../genau` | the flick folder's layout, which its contract publishes |
| Fun Time's Main Funestra | `../fun_time` | a Funestra, with Kino or Genau running on it, and the flick engine for its genau mode |
| Fun Time's satellites | `../fun_time` | a Funestra, on each satellite's window |
| Fun Time's headset | `../fun_time` | the same three Funestras over the offscreen engine, drawn into the headset |
| Fun Time itself | `../fun_time` | the file channel, the playlist, the status line |
| Origenerator | `../origenerator` | a Funestra for a Standalone Slideshow, and the console and drive readout over its shows |

Everything they had to agree on lives here, so none of them has to import
another application's internals to get it. By what it is:

- **the engine** — `mpv_engine`, its offscreen twin `render_engine`, the
  `libmpv_loader` that puts the vendored DLL on `%PATH%` first, which is the
  only way python-mpv finds it on Windows, and `audio_outputs`, which says
  which of the machine's outputs a session means by the device name it
  configures.
- **the Funestra contract** — what a content source hands a Funestra and what
  it gets back, each format written and read in one module; see below.
  `session_quit` is beside them (a close on one window of a session asks the
  session).
- **the device** — `tcode` and `tcode_driver` for the wire, `funscript` for a
  script and the questions asked of one, and for a motion of this family's own:
  `robot_hand` (the waveform), `robot_hand_beat` (the phase it runs at),
  `robot_hand_driver` (the motion on the wire, and the device changing hands),
  `learned_motion` (phrases of real scripting in place of the waveform),
  `broker_feed` (the beat the OSR2 broker publishes when it has the room).
- **Genau** — wherever it runs. A flick is one of the
  short looping videos Genau scrubs to wherever the OSR2 is; the apps show and
  hear it under the word the settings all of Haglio share give it
  (`genau_flick_words` in `~/.haglio/settings.json`), which is library
  vocabulary and so never in source. `flick_folder`,
  `flick_decode`, `flick_cache`, `flick_loader`, `flick_sequence`,
  `flick_selection`, `flick_advance`, `flick_flip`, `flick_renderer`,
  `flick_scrub` and `flick_overlay` get a flick from a folder to the frame the
  motion is at, and `genau_controls`, `genau_refresh`, `genau_readout`,
  `genau_status`, `genau_notifier` and `genau_arrival` are its verbs, its tick,
  and what it publishes. A shell — Fun Time's Main Funestra, its headset —
  supplies the surface and the loop.
- **the chrome and what is drawn on it** — `hud_panel`, `hud_marks`,
  `geometry`, `timeline`, `volume`, `hud_status`, and then a model and a
  painter per HUD: `console` / `console_hud`, `drive_layout` / `drive_readout`,
  `satellite_hud` / `satellite_hud_paint`.  Two of those are sections rather
  than panels — the drive readout and `hud_osr2`'s device line — because a host
  that both browses a set and drives the OSR2 (Origenerator's shows) says all of
  it on ONE panel rather than stacking a console under a lock HUD.
- **the Funestra** — the window: `funestra` builds one on a way of
  playing (`Funestra.on_window` opens mpv on a window handle; the base takes
  any engine with the same interface) and the files its User drives it through
  (`Channels`), plays what it is handed (`playback`, with `funestra_controls`
  answering the verbs, `funestra_status` publishing the status, `play_points`,
  `seeking` and `scripted_device` under it), and draws the published panel —
  a satellite's (`hud_overlay`) or the main slot's console (`console_overlay`),
  whichever file it was given — the scrubber (`scrubber`: a scripted item's
  colors, the zoom while a stretch is marked, the frames of a running A/B
  range), the volume chip (`volume_control`: its own level, or the room's,
  asked for on the dashboard's channel, `dashboard`), the playhead readout and
  the black it shows when the room gives its rectangle away (`display`),
  placing a press against them (`pointer`).  A User runs on a Funestra in the
  same process (`funestra.User`: its verbs, a pass of its own each frame, its
  lines in the status file, the console's top block) or drives it through its
  files from another; none draws on it.  `tests/test_hud_drawers.py` holds the
  consumers to that: a package that imports a painter out of here is drawing a
  HUD itself, and only the ones still to move onto a Funestra are listed.
- **the window** — `sdl_hints`, the SDL facts every Funestra here has to get
  right before it opens one (its taskbar identity it claims through
  `app_support.win32`, like every other process in the family).
- **the loop** — `control_registry` (how anything that answers verbs declares a control and the
  verbs that move it), `flag` (a bit two parts of an app share, with its
  edge), `tick_failures` (a frame loop's fault, said once).

Nothing app-specific belongs here. A module earns a place only once a second
repo needs it; until then it stays with the app that owns it. Genau's engine is
here because two shells run it: Fun Time's Main Funestra on the desktop, and the
same Funestra in the headset, whose genau mode runs the same tick against a
headset texture.

## The Funestra contract

A Funestra shows what a content source hands it and tells the source what it is
showing. Fun Time is the source for its Main, Portrait and Landscape Funestras
and their headset twins, and the contract is what lets a second source drive
the same Funestras: Origenerator, running as part of Fun Time, hands a
Slideshow to one of them. Every part of it is a pair — a writer
and a reader in one module — so the two sides cannot spell a thing differently:

| The source hands the Funestra… | …through | …and reads back |
| --- | --- | --- |
| a playlist: one `PlaylistItem` per line, a video and its funscript, or an image | `playlist` (`write_playlist` / `read_playlist`; `item_line` / `item_from_line` is the line, and `PLAY_FILE`'s value) | |
| verbs on its command file, spelled in `funestra_verbs` | `file_channel` (`append_command` / `consume_command_file`); the Funestra answers the ones it declares in a `control_registry` | |
| the pace an image holds the screen for: `SET_PACE <seconds>`, 0 holding it | `funestra_verbs.pace_seconds` reads the value, `set_pace` hands it to mpv | |
| the paused flag | `app_support.file_channel.write_flag` / `file_channel.read_paused_state` | |
| its HUD: a `HudModel` for a satellite, a `ConsoleModel` for the main slot, each carrying the buttons the source declares — rows of `hud_button.Button`: the verb a press posts, the face, the tooltip, lit or dim, where a group starts | `satellite_hud` (`hud_text` / `parse_hud`), `console` (`console_text` / `parse_console`) | |
| | `status` (`status_fields` / `parse_status`, published by `StatusWriter`) | a `FunestraStatus`: the item on screen, the playhead, paused, locked, the rate it plays at, whether the item is an image — and after those seven lines, whatever that Funestra adds of its own |

A Funestra answers the verbs it can (`TRASH` is a satellite's, `TOGGLE_LOCK` the
main slot's) and refuses the rest on its log. It draws the buttons its source
declared and nothing else, and posts each one's verb verbatim; a read-out
whose number only the drawing host knows (the video's rate, a flick's pace)
names it in `host_value` and the painter fills it in. A panel declaring no
buttons is drawn with none.

An image is shown by libmpv itself: it holds the frame for the pace and then
ends the file the way a finished video ends, so an image moves on, holds under
a lock and waits out a pause exactly as a video does, and a Funestra opens at 4
seconds until a source sets a pace. Whether an item is an image is mpv's to
say once the file is open (`showing_image`), so a playlist line carries no
kind; the still a HUD map draws for one is its cell's `thumb`, as for a video.
While it holds, an image makes one slow move, carried on a frame at a time by
`push_still`: a zoom in toward a spot, a zoom out from one, or a pan across it
held a little closer -- never the same kind twice in a row, and never showing
the window past the image's edge. `aim_still(part, seconds)` takes it onto a
part of the image instead and holds it there until the next file.

`flick_decode` reaches `app_support.subprocess_utils` for the one Windows fact
about launching ffmpeg (no console window), so `../app_support` has to be
installed in any venv that imports this package — every consumer's already is.

## Install

Each consuming project names a tag of this repo in its own
`[project.dependencies]`, and pip fetches it:

```toml
"funestra @ git+https://github.com/haglio/funestra@v0.1.480",
```

Every landing here is tagged (`tag-the-landing`, called from this repo's
merge gate), and the version this package reports is that tag, read by
setuptools-scm. A consumer moves to a newer one in its own commit, with its
own suite to answer for it.

## Working across this repo and a consumer

A consumer names a tag of this repo, so a change here does not reach it until
that consumer moves its pin. To try a change here inside one, install this
checkout over the pin in that consumer's venv and put it back after:

```bash
# from the consumer
".venv/Scripts/python.exe" -m pip install -e ../funestra --config-settings editable_mode=compat
# ...and back to the tag the consumer names: reinstalling the consumer
# replaces the checkout with its pin
".venv/Scripts/python.exe" -m pip install -e . --config-settings editable_mode=compat
```

Landing is two commits, in this order: this repo's, which tags a new version,
then the consumer's, which moves its pin to that tag. Between them the consumer
is untouched -- which is the whole point.


**`editable_mode=compat` is required, not cosmetic.** This repo's directory is
named `funestra`, the same as its package, and the directory that holds all
these repos is itself on `sys.path` in fun_time's venv (via its
`shared_ui.pth`). Setuptools' *default* editable install resolves the top-level
name through a meta-path finder that `PathFinder` never reaches, so the repo
root wins as an implicit namespace package: `funestra/__init__.py` never runs,
and nothing under it imports.
`compat` mode puts the repo root on `sys.path` instead, where a real package
beats a namespace portion. `tests/test_install.py` fails loudly if this is ever
reinstalled the other way.

## libmpv

`libmpv-2.dll` (~117 MB) is **not committed**. Fetch it once; it lands in
`%USERPROFILE%\.haglio\libmpv\`, and every install of this package finds it
there -- an app's pinned copy, an editable checkout and a fresh worktree alike.
`libmpv_loader` looks in a checkout's own `vendor/` first, so a copy fetched
there by hand still wins for that checkout.

Not under `AppData`, on purpose: a packaged Windows app -- Claude Desktop, which
every agent's shell runs inside -- is given a private copy of `AppData\Local`,
`Roaming` and `LocalLow`, so a DLL an agent fetches there exists for that app
alone and for nothing the user launches. The user's own folder, `Temp` and
`ProgramData` are the real ones for both (measured 2026-09-26).

```bash
python tools/fetch_libmpv.py
```

`tools/libmpv.lock` names the build: source repository, release tag, asset and
its SHA-256. The script verifies that digest and refuses a mismatch, so this
machine and the merge gate link the same DLL and both can say which one. Upstream
keeps about a month of releases; once the pinned tag is gone the script says so,
names the lock file and takes the newest build instead, which is what every run
did before the pin. Bumping the pin is one pull request, and it is where a
version change gets a reason written down.

## Tests

```bash
".venv/Scripts/python.exe" -m pytest tests/
```

There is no venv in this repo — run the suite with a consumer's venv, each of
which has this package installed. The half of `mpv_engine` that drives an mpv
handle is unit-tested against a fake; what needs the DLL and a real window is
constructing an `MpvEngine`, and that is exercised by Fun Time's hidden-desktop
integration suite, which launches the real Funestras.
