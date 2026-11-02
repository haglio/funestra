import sys

from . import timeline as _real

sys.modules[__name__] = _real
