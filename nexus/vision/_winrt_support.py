"""WinRT OCR support (Plan §12.5 — the OS-native engine path).

Device-only marshaling for ``Windows.Media.Ocr`` through the
``winsdk``/``winrt`` Python projection: decode the PNG into a
``SoftwareBitmap``, run the engine (user-profile language with an
explicit ``en`` fallback — the §12.5 requirements are English,
numbers, UI labels, documents), and map every ``OcrLine``'s word
rects onto one pixel box.

Imported lazily by :class:`nexus.vision.ocr.WinrtOcrEngine` — this
module is never imported on non-win32 runtimes (CI stays stdlib
green) and reports its failures honestly.

جسر ويندوز للتعرف الضوئي — لغة الجهاز أولًا ثم الإنجليزية،
والفشل صادق.

Stdlib only here; the projection is the caller's [ocr] extra.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .models import OcrLine, OcrResult


def _imports() -> tuple[Any, ...] | None:
    """Resolve the projection via importlib (Windows-only wheels —
    static resolution would fail CI's Linux venv; dynamic import is
    the honest probe, same as any optional backend)."""
    import importlib

    try:
        ocr = importlib.import_module("winsdk.windows.media.ocr")
        globalization = importlib.import_module("winsdk.windows.globalization")
        imaging = importlib.import_module("winsdk.windows.graphics.imaging")
        streams = importlib.import_module("winsdk.windows.storage.streams")
    except ImportError:
        try:  # the newer split winrt-* packages
            ocr = importlib.import_module("winrt.windows.media.ocr")
            globalization = importlib.import_module("winrt.windows.globalization")
            imaging = importlib.import_module("winrt.windows.graphics.imaging")
            streams = importlib.import_module("winrt.windows.storage.streams")
        except ImportError:
            return None
    return ocr, globalization, imaging, streams


def create_engine(
    ocr: Any, globalization: Any
) -> Any:
    """Pick the engine: user-profile languages, else explicit en-US."""
    engine = ocr.OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        language = globalization.Language("en-US")
        engine = ocr.OcrEngine.try_create_from_language(language)
    return engine


async def _decode(png: bytes, imaging: Any, streams: Any) -> Any:
    stream = streams.InMemoryRandomAccessStream()
    writer = streams.DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    decoder = await imaging.BitmapDecoder.create_async(stream)
    return await decoder.get_software_bitmap_async()


async def _recognize(png: bytes, engine: Any, imaging: Any, streams: Any) -> Any:
    bitmap = await _decode(png, imaging, streams)
    return await engine.recognize_async(bitmap)


def _line_box(line: Any) -> tuple[int, int, int, int]:
    """One OCR line's pixel box = the union of its word rects."""
    left = top = None
    right = bottom = None
    for word in line.words:
        rect = word.bounding_rect
        x, y = float(rect.x), float(rect.y)
        w, h = float(rect.width), float(rect.height)
        left = x if left is None else min(left, x)
        top = y if top is None else min(top, y)
        right = x + w if right is None else max(right, x + w)
        bottom = y + h if bottom is None else max(bottom, y + h)
    if left is None or top is None or right is None or bottom is None:
        return 0, 0, 0, 0
    return (
        int(left),
        int(top),
        int(right - left),
        int(bottom - top),
    )


def recognize_png(png: bytes) -> OcrResult:
    """One PNG → :class:`OcrResult` through Windows.Media.Ocr."""
    modules = _imports()
    if modules is None:
        from .ocr import OcrError

        raise OcrError("no winsdk/winrt projection installed ([ocr] extra)")
    ocr, globalization, imaging, streams = modules
    engine = create_engine(ocr, globalization)
    if engine is None:
        from .ocr import OcrError

        raise OcrError(
            "Windows.Media.Ocr found no installed language (add English)"
        )
    try:
        result = asyncio.run(_recognize(png, engine, imaging, streams))
    except RuntimeError as exc:  # no running loop / projection failure
        from .ocr import OcrError

        raise OcrError(f"winrt OCR failed: {exc}") from exc
    lines: list[OcrLine] = []
    for line in result.lines:
        text = str(line.text).strip()
        if not text:
            continue
        x, y, width, height = _line_box(line)
        lines.append(
            OcrLine(text=text, x=x, y=y, width=width, height=height)
        )
    text = "\n".join(line.text for line in lines)
    return OcrResult(text=text, lines=lines, engine="winrt")


__all__ = ["create_engine", "recognize_png"]
