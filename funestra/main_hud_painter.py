import sys

from . import console_hud as _real

sys.modules[__name__] = _real
