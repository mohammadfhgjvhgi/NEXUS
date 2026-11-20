"""Phase 18 · §18.1 Docling — MODE A/B adapter, honest availability.

The real docling engine is a heavy MODE A install; these tests prove
the adapter contract either way: honest absence when it is not
installed, direct use through the NEXUS contract when it is (via an
injected fake module — the adapter logic is what's under test, and
the live proof + the device are the judges for the real engine).
"""

from __future__ import annotations

import importlib.machinery
import sys
import types

import pytest

from nexus.documents import (
    BackendUnavailableError,
    DoclingParseBackend,
    DocumentSource,
    ParseError,
    docling_available,
)
from nexus.documents.docling import DOCLING_PINNED_SPEC


def test_pin_is_bounded_and_documented() -> None:
    assert DOCLING_PINNED_SPEC == "docling>=2.25,<3"


def test_probe_is_honest_without_docling() -> None:
    availability = docling_available(refresh=True)
    assert availability.installed is False
    assert "docling" in availability.detail
    assert availability.as_dict()["installed"] == "False"


def test_backend_raises_honest_unavailable() -> None:
    backend = DoclingParseBackend()
    src = DocumentSource(data=b"%PDF-1.4 x", name="x.pdf")
    if docling_available().installed:
        pytest.skip("docling is installed on this host — absence cannot be tested")
    with pytest.raises(BackendUnavailableError):
        backend.parse(src)


def test_mode_a_direct_use_through_the_contract(monkeypatch) -> None:
    """Fake docling in sys.modules — the adapter logic under real use."""
    fake_docling = types.ModuleType("docling")
    fake_docling.__version__ = "2.99.0-fake"
    fake_docling.__spec__ = importlib.machinery.ModuleSpec("docling", None)
    fake_docling.__path__ = []  # package marker — submodule imports resolve via sys.modules

    fake_converter_mod = types.ModuleType("docling.document_converter")
    fake_converter_mod.__spec__ = importlib.machinery.ModuleSpec(
        "docling.document_converter", None
    )

    class FakeDocument:  # noqa: D401 — the vendor shape, minimally
        def export_to_text(self) -> str:
            return "docling parsed this line.\nAnd this second line.\n"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def __init__(self) -> None:
            self.calls = 0

        def convert(self, path: str) -> FakeResult:
            self.calls += 1
            assert path.endswith(".pdf")
            return FakeResult()

    fake_converter_mod.DocumentConverter = FakeConverter
    fake_docling.document_converter = fake_converter_mod
    monkeypatch.setitem(sys.modules, "docling", fake_docling)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_converter_mod)

    availability = docling_available(refresh=True)
    assert availability.installed is True and availability.version == "2.99.0-fake"

    backend = DoclingParseBackend()
    parsed = backend.parse(DocumentSource(data=b"%PDF-1.4 fake-bytes", name="m.pdf"))
    assert parsed.parser == "docling"
    assert [b.text for b in parsed.blocks] == [
        "docling parsed this line.",
        "And this second line.",
    ]
    assert parsed.metadata["docling_version"] == "2.99.0-fake"

    describe = backend.describe()
    assert describe["pin"] == DOCLING_PINNED_SPEC and describe["installed"] == "True"


def test_backend_rejects_unserved_kind() -> None:
    backend = DoclingParseBackend()
    src = DocumentSource(data=b"garbage bytes", name="x.bin")  # kind: unknown
    # the kind check gates before conversion — rejected honestly either way
    with pytest.raises((BackendUnavailableError, ParseError)):
        backend.parse(src)


def test_temp_file_never_survives(monkeypatch, tmp_path) -> None:
    """The WinError-32 law: the temp file is gone after parse (or failure)."""

    seen: list[str] = []

    class FakeConverter:
        def convert(self, path: str) -> object:
            seen.append(path)
            raise RuntimeError("boom")

    fake = types.ModuleType("docling")
    fake.__version__ = "2.99.0-fake"
    fake.__spec__ = importlib.machinery.ModuleSpec("docling", None)
    fake.__path__ = []
    conv_mod = types.ModuleType("docling.document_converter")
    conv_mod.__spec__ = importlib.machinery.ModuleSpec("docling.document_converter", None)
    conv_mod.DocumentConverter = FakeConverter
    fake.document_converter = conv_mod
    monkeypatch.setitem(sys.modules, "docling", fake)
    monkeypatch.setitem(sys.modules, "docling.document_converter", conv_mod)
    docling_available(refresh=True)
    try:
        backend = DoclingParseBackend()
        with pytest.raises(ParseError):
            backend.parse(DocumentSource(data=b"%PDF-1.4 bytes", name="f.pdf"))
        from pathlib import Path

        assert seen, "conversion was attempted"
        assert not Path(seen[0]).exists(), "the temp file did not survive"
    finally:
        docling_available(refresh=True)  # restore the honest cache
