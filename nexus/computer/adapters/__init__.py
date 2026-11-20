"""pywinauto backend (Final Build Plan §9.3, MODE A «USE»).

BSD-3-Clause · upstream pywinauto/pywinauto · pinned 18d2a95 ·
optional ``[computer]`` extra · imported lazily behind the Computer
API — never a hard dependency, never imported at module load.
"""

from __future__ import annotations

from . import pywinauto_backend

__all__ = ["pywinauto_backend"]
