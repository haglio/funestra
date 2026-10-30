# funestra — Project-Specific Instructions

Shared rules are in the global `~/.claude/CLAUDE.md`. This file contains only
funestra-specific overrides.

**Keep this file short.** No redundancy with the global CLAUDE.md. One bullet
per rule. If editing this file, remove or consolidate — never just append.

## Running tests

This repo has no venv of its own. Use Fun Time's, with this checkout first on
the path: that venv holds the release Fun Time pins, not this checkout, and
`--import-mode=append` stops pytest putting the venv back in front of it when it
collects the checks app_support ships from there.

```bash
PYTHONPATH="C:/path/to/funestra" "C:/path/to/fun_time/.venv/Scripts/python.exe" -m pytest -x --import-mode=append tests/
```

## Installing

Always `--config-settings editable_mode=compat`; the README says why, and
`tests/test_install.py` goes red if a venv is ever reinstalled without it.

## Where the DLL is

`libmpv-2.dll` is fetched, not tracked, into `%USERPROFILE%\.haglio\libmpv\`
(`python tools/fetch_libmpv.py`), and `libmpv_loader` finds it there from any
install -- so a worktree of this repo needs nothing copied in. A checkout's own
`vendor/` is looked in first and still wins where one exists.

- **Never put that copy under `AppData`.** Every agent's shell runs inside a
  packaged app whose `AppData\Local`, `Roaming` and `LocalLow` are private to it,
  so a DLL fetched there is found by every suite and by nothing the user
  launches. That is how his Fun Time previews came up with dead Funestras from
  2026-09-22 to 09-26.
- A worktree of this repo from before 2026-09-26 still looks under `AppData`, so
  a Fun Time session pinning one gets the DLL copied into its `vendor/` at launch.

## What belongs here

- **Only what a second repo needs.** A module earns a place here once two
  sibling apps — whichever two — import it. Until then it stays with the app that
  owns it — a "core" that accumulates one app's code is the coupling this repo
  exists to undo. Genau's engine moved in whole on 2026-09-04 ahead of its second
  consumer (Fun Time's headset, item 52), so its modules are the standing
  exception until that lands.
- **No module keeps an `__all__`.** Every name without a leading underscore is
  one the apps may use, as Python reads it. An `__all__` would also count the
  names it lists as used and hide them from the dead-code check, so a module
  that hands on a name it imports marks that import `# noqa: F401` instead.
- **No app knows another app exists.** Nothing here may import `main_funestra`,
  `satellite` or `fun_time`, and nothing here may be shaped around one caller's
  needs. `StatusWriter` takes a `fields` callable rather than hardcoding either
  Funestra's keys for exactly this reason.

- **A Player is a Funestra, and what ran on a Player runs on a Funestra.** A
  Funestra is a window (`funestra.Funestra`) that plays what it is handed and
  draws the HUD, in Fun Time and in a Standalone Origenerator alike. The Main,
  Portrait and Landscape Players became Funestras, and Kino (Fun Time's Video
  mode), Genau and an Origenerator Slideshow run on them exactly as they ran on
  the Players. What is wrong is a
  third thing between the two -- a Player that "runs on" or "has" a Funestra,
  a Funestra under a Player -- and so is the opposite over-correction, that
  nothing runs on a Player; he has had to correct both. The near miss that
  still counts: "the satellites run on a Funestra" -- the satellite program is
  the window, so each satellite is a Funestra, and Kino runs on it. The code
  says so too: the repo, its folder and the package are `funestra` (since
  2026-10-11; `player_core` until 2026-10-10, then `funestra_core` for a day),
  and the mpv object a Funestra plays through is its engine (`MpvEngine`),
  never a player.
- **What a Funestra draws over what it plays is its HUD, never its panel.** The
  user's word, and the code's since 2026-10-29: `funestra.hud` (`Hud`, the slab
  every HUD is painted on), `HudLayout`, `hud_width`, a Funestra's `hud=`,
  `hud_surface=`, `hud_edge` and `hud_minimized`. The block Origenerator paints
  at a HUD's foot (`PaintedFoot`) is its Job Queue. `funestra/hud_panel.py` answers the HUD module's old
  name for the Fun Time branches still importing it; nothing new may use it.
  The OSR2 part keeps its
  name (`DevicePanel`), and `BORDER_PANEL` is shared_ui's.

## Changing this repo changes three apps

- A change here reaches an app when that app moves its pin, not before: each
  names a tag of this repo in its `[project.dependencies]`. Landing is two
  commits — this repo's, which tags a version, then the app's, which takes it
  and which this repo's landing opens in every app as a pull request that ships
  by itself once the app's checks pass (`app_support.newest_pins`).
- This repo pins app_support and shared_ui only in its `dev` extra, for its own
  suite: every app pins both itself, and a pin here, where installing this asks
  for one, made every app wait for this repo's next release to take a new copy.
- A change that takes out a module or a name another repo's main or open pull
  request still uses is refused at the gate (`app_support.taken_out`): keep it
  until that work has moved off it, then take it out.
- **To try a change here inside an app**, install this checkout over the pin in
  that app's venv (`pip install -e ../funestra --config-settings
  editable_mode=compat`), and reinstall the app afterwards to put its pin back.
- **Run all three suites before merging**: this one, genau's unit suite, and
  fun_time's unit *and* hidden-desktop integration suites (the last is what
  actually launches `MpvEngine` against the real DLL).
- **The dead-code check reads the apps.** The family's dead-code gate, asked to
  by `apps-are-callers` in pyproject, runs vulture over this package with its
  own tests and the tracked code of every checkout beside it that imports it,
  found rather than named, so what it reports is what nothing anywhere uses. It
  skips with no such checkout beside it, which only a public clone has; the
  merge gate clones fun_time and origenerator beside the checkout for it. A
  name whose caller the scan cannot read, because Python or a library calls it,
  goes in `vulture_whitelist.py` with who calls it, and leaves when its caller
  does.

## libmpv changes: mandatory pre-flight

`MpvEngine` is the one place this family touches libmpv. Before modifying any
mpv property or command, state the mechanism (why the approach works, citing the
specific mpv behavior), verify it rather than guessing, and name which of the
three apps' run loops the change touches. If you cannot, stop and say so — do
not submit a speculative fix.

## Test fixtures must be fabricated, never copied from the real library

Every fixture value that stands in for library data — a video title, a filename,
a performer or studio name, prompt text — must be **invented**. Never paste a
real one out of the media library to make a test feel realistic.

This is not a style note. It is the single thing that has actually leaked private
data into these repos: an agent writing a test reached for a real filename or
performer name because it was handy, and it rode into a public commit. Nothing in
the app's *design* pulls library text into source — the library lives outside
every repo, read at runtime through the git-ignored overlays — so this habit is
the only remaining path for a real name to get committed, and the only thing
stopping it is you following this rule.

Do not lean on the sanitize guard to catch it. `app_support.sanitize` fails
the suite when a **known** blocked term appears in the tracked tree, but a brand-
new performer name it has never seen passes every check and lands. The guard is a
backstop for names already known; it cannot see the next one.

So fabricate fully. Use `Jane Doe`, `Example Studio`, `scene one`, the
`alpha`/`beta`/`gamma` act placeholders the committed `content.example.json`
already uses. The near miss that still counts: taking a real filename and
changing a character or two — it is still that clip, still that performer. Make
it up from scratch, don't lightly edit a real one.

## Landing — GitHub merge queue, not local ff-merge

This repo is public at `github.com/haglio/funestra` with a merge-queue ruleset on
`main`, so the global "ff-merge into the primary checkout under
`.git/agent-merge.lock`" flow does NOT apply here:

- **Land through a pull request.** From your worktree: commit, `git fetch origin
  && git rebase origin/main`, `git push -u origin <branch>`, then
  `gh pr create --fill`. Auto-merge arms itself; the queue rebases your PR onto
  `main`, runs the required check, and merges it when green. Don't ff-merge into
  the primary checkout, don't push `main` directly, and never force-push `main`.
- **The `.git/agent-merge.lock` is retired here** — the GitHub queue serializes.
- **The production updater moves the primary checkout; never pull it yourself.**
  `main` advances only on origin (via the queue), and app_support's production
  updater brings the primary checkout up to it within a few minutes, so
  worktrees update with `git rebase origin/main` and the primary is never
  pulled, reset or merged into by hand.
- **A red required check** (`.github/workflows/merge-gate.yml`) can't land.

Everything else in the global CLAUDE.md — work in a worktree, green tests before
you push, clean handoff — still applies.
