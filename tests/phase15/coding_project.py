"""Shared temp-project factory for the phase-15 pytest suite.

One deliberately buggy micro-project: ``divide`` multiplies instead
of dividing — exactly one failing pytest-style test plus one passing
test, so the §15.1 test/debug/review operations have a deterministic
target. stdlib + pytest only.
"""

from __future__ import annotations

from pathlib import Path

from nexus.coding import EditAction

MAIN_BUGGY = "def divide(a, b):\n    return a * b\n"
MAIN_FIXED = "def divide(a, b):\n    return a / b\n"

TEST_FILE = (
    "from main import divide\n"
    "\n"
    "\n"
    "def test_divide_correct():\n"
    "    assert divide(6, 3) == 2\n"
    "\n"
    "\n"
    "def test_divide_zero():\n"
    "    assert divide(0, 3) == 0\n"
)

#: The failing test node id, exactly as pytest reports it.
FAILING_TEST = "test_main.py::test_divide_correct"

#: The recipe that repairs the project.
GOOD_FIX = EditAction(
    path="main.py",
    old="return a * b",
    new="return a / b",
    description="multiply is wrong; divide must divide",
)

#: A recipe that applies but does not repair (the permanent-bug path).
BAD_FIX = EditAction(
    path="main.py",
    old="return a * b",
    new="return a + b",
    description="a plausible but wrong fix",
)


def make_buggy_project(root: Path) -> Path:
    """Write the buggy micro-project; returns the root."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(MAIN_BUGGY, encoding="utf-8")
    (root / "test_main.py").write_text(TEST_FILE, encoding="utf-8")
    return root
