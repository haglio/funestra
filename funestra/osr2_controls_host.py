import sys

from . import device_panel as _real

sys.modules[__name__] = _real
