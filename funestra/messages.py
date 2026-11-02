import sys

from . import notices as _real

sys.modules[__name__] = _real
