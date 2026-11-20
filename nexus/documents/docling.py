"""Docling (New Plan §18.1) — docling-project/docling behind the NEXUS contract.

Integration mode, per the plan: **MODE A/B** — the engine is used
*directly* when it is installed (MODE A), and always *through* the
NEXUS :class:`ParseBackend` adapter (MODE B), so the §18.2 pipeline
never sees a vendor type.  When docling is absent the adapter says so
honestly (:class:`BackendUnavailableError`) and the native stdlib
floors keep the document flowing — availability is probed, never
assumed.

The pin follows the house pinning law (llama.cpp b10829, qdrant-client
``>=1.19,<2``): one documented, bounded range — installable via the
``[documents]`` extra.

Docling (§18.1) — MODE A مباشرة عند التثبيت وMODE B عبر عقد NEXUS دائمًا؛
وعند غيابه يقول الصدق ويتدفق المستند فوق الأرضية القياسية.

Stdlib only (docling itself is the optional MODE A extra).
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    BackendUnavailableError,
    DocumentKind,
    DocumentSource,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StructureNode,
    TextBlock,
)

#: The documented §18.1 pin — bounded, installable, never floating.
DOCLING_PINNED_SPEC = "docling>=2.25,<3"

_PROBE_RESULT: DoclingAvailability | None = None


@dataclass(frozen=True, slots=True)
class DoclingAvailability:
    """The honest probe result — installed? which version? what failed?"""

    installed: bool
    version: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "installed": str(self.installed),
            "version": self.version,
            "detail": self.detail,
        }


def docling_available(*, refresh: bool = False) -> DoclingAvailability:
    """Probe the host for docling — truth only, no assumptions.

    The result is cached (the probe imports a heavy package); pass
    ``refresh=True`` to re-probe after an install.
    """
    global _PROBE_RESULT  # noqa: PLW0603 — one cached probe, refreshed on demand
    if _PROBE_RESULT is not None and not refresh:
        return _PROBE_RESULT
    try:
        import importlib.util

        spec = importlib.util.find_spec("docling")
        if spec is None:
            _PROBE_RESULT = DoclingAvailability(
                installed=False,
                detail=f"not installed — install with: pip install {DOCLING_PINNED_SPEC!r}",
            )
            return _PROBE_RESULT
        import docling  # type: ignore[import-not-found]

        version = str(getattr(docling, "__version__", "") or "unknown")
        _PROBE_RESULT = DoclingAvailability(installed=True, version=version)
        return _PROBE_RESULT
    except Exception as exc:  # noqa: BLE001 — any import failure is honest absence
        _PROBE_RESULT = DoclingAvailability(
            installed=False, detail=f"present but unusable: {type(exc).__name__}: {exc}"
        )
        return _PROBE_RESULT


class DoclingParseBackend(ParseBackend):
    """§18.1 — the docling engine behind the NEXUS parse contract."""

    name = "docling"
    kinds = (DocumentKind.DOCX, DocumentKind.PPTX, DocumentKind.PDF)

    def __init__(self, *, timeout_seconds: float = 120.0) -> None:
        self._timeout = timeout_seconds

    def parse(self, source: DocumentSource) -> ParsedDocument:
        availability = docling_available()
        if not availability.installed:
            raise BackendUnavailableError(
                f"docling is not available on this host ({availability.detail})"
            )
        if source.kind not in self.kinds:
            raise ParseError(f"docling backend does not serve {source.kind!r}")
        text = self._convert_to_text(source)
        blocks = [
            TextBlock(text=line.strip(), locator=f"section {i}", role="body")
            for i, line in enumerate(
                (ln for ln in text.splitlines() if ln.strip()), start=1
            )
            if line.strip()
        ]
        structure = (StructureNode(name=source.name or "document", node_type="section"),)
        return ParsedDocument(
            kind=source.kind,
            uri=source.uri,
            title=blocks[0].text[:80] if blocks else (source.name or "document"),
            sha256=hashlib.sha256(source.data).hexdigest(),
            size_bytes=len(source.data),
            structure=structure,
            blocks=tuple(blocks),
            metadata={"docling_version": availability.version},
            parser=self.name,
        )

    # ----------------------------------------------------------- plumbing

    def _convert_to_text(self, source: DocumentSource) -> str:
        """MODE A direct use — bytes → temp file → DocumentConverter → text.

        The Windows law (an open handle keeps the file locked,
        WinError 32), learned on the real box in phase 17 and again in
        phase 18: ``mkstemp`` opens an OS handle — close it *before*
        conversion, and remove the file in a ``finally``.
        """
        try:
            from docling.document_converter import (  # type: ignore[import-not-found]
                DocumentConverter,
            )
        except Exception as exc:  # noqa: BLE001 — honest absence at call time
            raise BackendUnavailableError(
                f"docling vanished between probe and use: {exc}"
            ) from exc
        import os

        suffix = Path(source.name).suffix if source.name else ".pdf"
        fd, name = tempfile.mkstemp(suffix=suffix, prefix="nexus-docling-")
        os.close(fd)  # the handle must not outlive creation — real-Windows law
        tmp = Path(name)
        try:
            tmp.write_bytes(source.data)
            converter = DocumentConverter()
            result = converter.convert(str(tmp))
            document = getattr(result, "document", None)
            if document is None:
                raise ParseError("docling returned no document")
            for export in ("export_to_text", "export_to_markdown"):
                method = getattr(document, export, None)
                if callable(method):
                    text = str(method())
                    if text.strip():
                        return text
            raise ParseError("docling produced no text")
        except BackendUnavailableError:
            raise
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001 — the engine failed, say how
            raise ParseError(f"docling conversion failed: {type(exc).__name__}: {exc}") from exc
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass  # best effort — never mask the real outcome

    def describe(self) -> dict[str, Any]:
        """Capability-matrix rows — proven facts only."""
        availability = docling_available()
        return {
            "backend": self.name,
            "pin": DOCLING_PINNED_SPEC,
            "kinds": list(self.kinds),
            **availability.as_dict(),
        }
