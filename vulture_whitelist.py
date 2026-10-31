"""Names the dead-code scan reports that are not dead: callers it cannot read.

tests/test_dead_code.py fails on an entry that no longer suppresses anything,
so an entry leaves with the code it names.
"""
# ruff: noqa: F821, B018 -- a whitelist is names, not statements

# --- called by Python or a library, never by our code ---
_.redirect_request  # tools/harvest_eroscripts.py: urllib asks a redirect handler
newurl  # the redirect urllib offers redirect_request, which declines it
_.ab_loop_a  # mpv_engine: python-mpv sets mpv's ab-loop-a property on assignment
_.ab_loop_b  # mpv_engine: python-mpv sets mpv's ab-loop-b property on assignment
_.vo  # mpv_engine: python-mpv sets mpv's vo option on assignment, which builds a new video output
_.__signature__  # renamed: inspect reads it for the keywords an old checkout still hands a call
