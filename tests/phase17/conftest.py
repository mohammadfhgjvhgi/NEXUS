"""Phase-17 conftest — the shared surface server fixture."""

from __future__ import annotations

import pytest
from fixtures import SurfaceServer


@pytest.fixture()
def server() -> SurfaceServer:
    surface = SurfaceServer().start()
    yield surface
    surface.stop()
