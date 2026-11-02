import sys

from . import console as _real

sys.modules[__name__] = _real
