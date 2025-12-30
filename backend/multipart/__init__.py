"""Compatibility shim for python-multipart imports used by Starlette."""

import python_multipart as _python_multipart
from python_multipart import *  # noqa: F403

multipart = _python_multipart.multipart
__version__ = _python_multipart.__version__

__all__ = list(getattr(_python_multipart, "__all__", []))
if "__version__" not in __all__:
    __all__.append("__version__")
if "multipart" not in __all__:
    __all__.append("multipart")
