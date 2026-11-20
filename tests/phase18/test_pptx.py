"""Phase 18 · §18.4 PPTX — create · slides · images · layout · sources ·
save · verify."""

from __future__ import annotations

import pytest
from fixtures import PNG_1X1

from nexus.documents import (
    DocumentSource,
    ParseError,
    UnsupportedDocumentError,
    VerifyError,
)
from nexus.documents.pptx import (
    PptxParseBackend,
    PptxPresentation,
    read,
    sniff_image_format,
    verify,
)


def _pres() -> PptxPresentation:
    pres = PptxPresentation()
    pres.add_slide("NEXUS Documents", ["docx pptx pdf", "stdlib floor"])
    pres.add_slide("Pipeline", ["parse structure extract"])
    return pres


def test_create_save_read_titles_roundtrip(tmp_path) -> None:
    path = _pres().save(tmp_path / "r.pptx")
    back = read(path)
    assert [s.title for s in back.slides] == ["NEXUS Documents", "Pipeline"]


def test_bullets_roundtrip(tmp_path) -> None:
    back = read(_pres().save(tmp_path / "b.pptx"))
    assert back.slides[0].bullets == ["docx pptx pdf", "stdlib floor"]


def test_slides_add_and_order(tmp_path) -> None:
    pres = _pres()
    pres.add_slide("Third", [])
    back = read(pres.save(tmp_path / "s.pptx"))
    assert len(back.slides) == 3
    assert back.slides[2].title == "Third"


def test_image_embedded_and_found(tmp_path) -> None:
    pres = _pres()
    pres.add_image(0, PNG_1X1)
    back = read(pres.save(tmp_path / "i.pptx"))
    assert back.slides[0].image is not None
    assert back.slides[0].image.part == "/ppt/media/image1.png"
    assert back.slides[1].image is None


def test_image_format_sniffing() -> None:
    assert sniff_image_format(PNG_1X1) == "png"
    assert sniff_image_format(b"\xff\xd8\xff\xe0jpegdata") == "jpeg"
    assert sniff_image_format(b"GIF89a......") == "gif"
    with pytest.raises(ValueError):
        sniff_image_format(b"not an image")


def test_layout_slide_size_roundtrip(tmp_path) -> None:
    pres = PptxPresentation(width_emu=9_144_000, height_emu=6_858_000)  # 4:3
    pres.add_slide("sized", [])
    back = read(pres.save(tmp_path / "l.pptx"))
    assert (back.width_emu, back.height_emu) == (9_144_000, 6_858_000)


def test_sources_provenance(tmp_path) -> None:
    back = read(_pres().save(tmp_path / "src.pptx"))
    sources = back.sources()
    assert sources[0] == {
        "slide": 1,
        "title": "NEXUS Documents",
        "bullets": ["docx pptx pdf", "stdlib floor"],
        "has_image": False,
    }
    pres = _pres()
    pres.add_image(0, PNG_1X1)
    assert pres.sources()[0]["has_image"] is True


def test_verify_ok(tmp_path) -> None:
    path = _pres().save(tmp_path / "v.pptx")
    verdict = verify(path, expect_titles=["NEXUS Documents", "Pipeline"])
    assert verdict.ok
    assert verdict.checks["master_layout_theme"] and verdict.checks["slides_parse"]


def test_verify_catches_title_drift(tmp_path) -> None:
    path = _pres().save(tmp_path / "t.pptx")
    assert verify(path, expect_titles=["wrong"]).ok is False


def test_verify_rejects_corruption(tmp_path) -> None:
    path = _pres().save(tmp_path / "c.pptx")
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 3])
    with pytest.raises(VerifyError):
        verify(path)


def test_backend_kind_law() -> None:
    with pytest.raises(UnsupportedDocumentError):
        PptxParseBackend().parse(
            DocumentSource(data=b"%PDF-1.4 fake", name="x.pdf")
        )


def test_backend_parses_bytes(tmp_path) -> None:
    data = _pres().to_bytes()
    parsed = PptxParseBackend().parse(DocumentSource(data=data, name="r.pptx"))
    assert parsed.kind == "pptx" and parsed.parser == "native.pptx"
    assert [s.name for s in parsed.structure] == ["NEXUS Documents", "Pipeline"]
    assert parsed.metadata["slides"] == "2"


def test_read_rejects_non_pptx(tmp_path) -> None:
    bogus = tmp_path / "bogus.pptx"
    bogus.write_bytes(b"PK\x03\x04 not a presentation")
    with pytest.raises(ParseError):
        read(bogus)
