import sys

from . import drive_readout as _real

sys.modules[__name__] = _real
