"""Names the dead-code scan reports that are not dead: callers it cannot read.

tests/test_dead_code.py fails on an entry that no longer suppresses anything,
so an entry leaves with the code it names.
"""
# ruff: noqa: F821, B018 -- a whitelist is names, not statements

# --- called by Python or a library, never by our code ---
_._missing_  # modes.LengthMode: Enum asks it about a value it does not know, an old "shorts"
_.create_module  # renamed: importlib asks the loader an old package name answers with
_.redirect_request  # tools/harvest_eroscripts.py: urllib asks a redirect handler
newurl  # the redirect urllib offers redirect_request, which declines it
_.ab_loop_a  # mpv_engine: python-mpv sets mpv's ab-loop-a property on assignment
_.ab_loop_b  # mpv_engine: python-mpv sets mpv's ab-loop-b property on assignment
_.vo  # mpv_engine: python-mpv sets mpv's vo option on assignment, which builds a new video output

# --- reached only by checkouts from before haglio/fun_time#391, until none is open ---
lower_edge_height  # playhead: the headset's old copies of the row
readout_xy  # playhead: the headset's old copies of the row
on_readout  # playhead: the headset's old copies of the row
time_at  # pointer: the headset's old copies of the row
cache_dir_for_flicks_folder  # flick_folder, through clip_folder's cache_dir_for_clips_folder
