"""The Funestra, and everything its programs share.

A Funestra is a window of Fun Time: it plays what it is handed, draws the HUD,
and is driven through files by whatever runs on it.  Fun Time opens three (the
Main, Portrait and Landscape Funestras, or draws them into the headset), and a
Standalone Origenerator opens one for its Slideshow.  Everything those programs
had to agree on lives here — the engine, the Funestra contract (the playlist,
the verbs, the paused flag, the status a Funestra publishes, the HUD a source
hands it), the T-Code wire, the motion, and the chrome the HUDs are drawn on —
so no application has to import another application's internals to get it.

Nothing app-specific belongs in this package.  A module earns a place here only
once a second repo needs it; until then it stays with the app that owns it.
"""
