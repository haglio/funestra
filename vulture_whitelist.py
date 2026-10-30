"""Names the dead-code scan reports that are not dead: callers it cannot read.

The family's dead-code gate fails on an entry that no longer suppresses anything,
so an entry leaves with the code it names.
"""


# --- called by Python or a library, never by our code ---
_.redirect_request  # tools/harvest_eroscripts.py: urllib asks a redirect handler
newurl  # the redirect urllib offers redirect_request, which declines it
_.ab_loop_a  # mpv_engine: python-mpv sets mpv's ab-loop-a property on assignment
_.ab_loop_b  # mpv_engine: python-mpv sets mpv's ab-loop-b property on assignment
_.vo  # mpv_engine: python-mpv sets mpv's vo option on assignment, which builds a new video output
__getattr__  # hud_panel: Python asks a module's __getattr__ for a name it does not have
