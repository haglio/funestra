import sys

from . import hud_marks as _real

sys.modules[__name__] = _real
