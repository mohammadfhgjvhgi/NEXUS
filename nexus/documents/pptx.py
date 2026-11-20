"""PPTX support (New Plan §18.4) — create · slides · images · layout ·
sources · save · verify.

A ``.pptx`` is an OOXML ZIP package.  This engine builds a *real*
minimal package — presentation, one slide master, one slide layout,
theme, slides, media — that PowerPoint and LibreOffice open, using
only the standard library.  Slides carry a title placeholder and a
content placeholder (bullets), plus optional embedded images with
explicit EMU placement; ``sources()`` extracts per-slide text so the
pipeline can index and cite where every line came from.

Scope, stated honestly: the core OOXML surface.  Smart art, charts,
animations and the full layout gallery ride the §18.1 docling engine
when installed — this floor never pretends to cover them.

دعم PPTX — الأفعال السبعة حرفيًا فوق حزمة OOXML مبنية بمكتبة قياسية.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .contracts import (
    DocumentKind,
    DocumentSource,
    DocumentVerification,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StructureNode,
    TextBlock,
    UnsupportedDocumentError,
    VerifyError,
)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)

_REL_LAYOUT = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
)
_REL_MASTER = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
)
_REL_THEME = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
)
_REL_IMAGE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)

#: 16:9 widescreen, EMU (914400 per inch) — the modern default slide size.
EMU_16X9_WIDTH = 12_192_000
EMU_16X9_HEIGHT = 6_858_000

_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

_THEME_XML = (
    _XML_DECL
    + f'<a:theme xmlns:a="{A_NS}" name="NEXUS"><a:themeElements>'
    + '<a:clrScheme name="Nexus"><a:dk1><a:srgbClr val="000000"/></a:dk1>'
    + '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="44546A"/></a:dk2>'
    + '<a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="4472C4"/></a:accent1>'
    + '<a:accent2><a:srgbClr val="ED7D31"/></a:accent2>'
    + '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>'
    + '<a:accent4><a:srgbClr val="FFC000"/></a:accent4>'
    + '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>'
    + '<a:accent6><a:srgbClr val="70AD47"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink>'
    + '<a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
    + '<a:fontScheme name="Nexus"><a:majorFont><a:latin typeface="Calibri Light"/>'
    + '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont>'
    + '<a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
    + '</a:minorFont></a:fontScheme>'
    + '<a:fmtScheme name="Nexus"><a:fillStyleLst>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
    + '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    + '<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    + '<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
    + '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
    + '<a:effectStyle><a:effectLst/></a:effectStyle>'
    + '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
    + '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
    + '</a:fmtScheme></a:themeElements></a:theme>'
)

# ------------------------------------------------------------ image sniff


def sniff_image_format(data: bytes) -> str:
    """Magic-byte image detection — honest, never extension-guessed."""
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    raise ValueError("unsupported image format (png · jpeg · gif · bmp only)")


# ------------------------------------------------------------------ model


@dataclass
class PptxImage:
    """One image placed on a slide — real bytes at create, EMU placement."""

    data: bytes
    x_emu: int = 0
    y_emu: int = 0
    width_emu: int = 3_048_000  # ~2.5 in defaults
    height_emu: int = 3_048_000
    #: set by :func:`read` — the package part the image came from
    part: str = ""

    @property
    def format(self) -> str:
        return sniff_image_format(self.data) if self.data else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "x_emu": self.x_emu,
            "y_emu": self.y_emu,
            "width_emu": self.width_emu,
            "height_emu": self.height_emu,
            "part": self.part,
            "size_bytes": len(self.data),
        }


@dataclass
class PptxSlide:
    """One slide — title, bullets, optional image."""

    title: str = ""
    bullets: list[str] = field(default_factory=list)
    image: PptxImage | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "bullets": list(self.bullets),
            "image": self.image.as_dict() if self.image else None,
        }


@dataclass
class PptxPresentation:
    """The PPTX model — slides plus the §18.4 *layout* (slide size)."""

    slides: list[PptxSlide] = field(default_factory=list)
    width_emu: int = EMU_16X9_WIDTH
    height_emu: int = EMU_16X9_HEIGHT

    # ------------------------------------------------------------ create

    def add_slide(
        self, title: str = "", bullets: list[str] | None = None
    ) -> PptxSlide:
        """§18.4 *create* + *slides* — append one titled slide."""
        slide = PptxSlide(title=title, bullets=list(bullets or []))
        self.slides.append(slide)
        return slide

    def add_image(
        self,
        slide_index: int,
        data: bytes,
        *,
        x_emu: int = 6_858_000,
        y_emu: int = 3_429_000,
        width_emu: int = 3_048_000,
        height_emu: int = 3_048_000,
    ) -> PptxImage:
        """§18.4 *images* — embed real image bytes on one slide."""
        if not -len(self.slides) <= slide_index < len(self.slides):
            raise IndexError(f"slide index {slide_index} out of range")
        idx = slide_index if slide_index >= 0 else slide_index + len(self.slides)
        image = PptxImage(
            data=data, x_emu=x_emu, y_emu=y_emu, width_emu=width_emu, height_emu=height_emu
        )
        self.slides[idx].image = image
        return image

    # ------------------------------------------------------------ sources

    def sources(self) -> list[dict[str, Any]]:
        """§18.4 *sources* — per-slide text provenance (what came from where)."""
        return [
            {
                "slide": i,
                "title": slide.title,
                "bullets": list(slide.bullets),
                "has_image": slide.image is not None,
            }
            for i, slide in enumerate(self.slides, start=1)
        ]

    # -------------------------------------------------------------- save

    def save(self, path: str | Path) -> Path:
        """§18.4 *save* — write a real OOXML package to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, xml in self._package_parts()[0]:
                zf.writestr(name, xml)
            for name, blob in self._package_parts()[1]:
                zf.writestr(name, blob)
        return target

    def to_bytes(self) -> bytes:
        """The package bytes — exactly what :meth:`save` writes."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, xml in self._package_parts()[0]:
                zf.writestr(name, xml)
            for name, blob in self._package_parts()[1]:
                zf.writestr(name, blob)
        return buf.getvalue()

    # ------------------------------------------------- package assembly

    def _package_parts(
        self,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, bytes]]]:
        """All package parts — XML text parts then binary parts."""
        n = len(self.slides)
        content_types = [
            _XML_DECL,
            f'<Types xmlns="{CT_NS}">',
            '<Default Extension="rels" ContentType='
            '"application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Default Extension="png" ContentType="image/png"/>',
            '<Default Extension="jpeg" ContentType="image/jpeg"/>',
            '<Default Extension="gif" ContentType="image/gif"/>',
            '<Default Extension="bmp" ContentType="image/bmp"/>',
            '<Override PartName="/ppt/presentation.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
            '<Override PartName="/ppt/theme/theme1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.theme+xml"/>',
        ]
        for i in range(1, n + 1):
            content_types.append(
                f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType='
                '"application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            )
        content_types.append("</Types>")

        pres_rels = [
            _XML_DECL,
            f'<Relationships xmlns="{REL_NS}">',
            f'<Relationship Id="rId1" Type="{_REL_MASTER}"'
            ' Target="slideMasters/slideMaster1.xml"/>',
        ]
        for i in range(1, n + 1):
            pres_rels.append(
                f'<Relationship Id="rId{i + 1}" '
                f'Type="{DOC_REL_TYPE.rsplit("/", 1)[0]}/slide"'
                f' Target="slides/slide{i}.xml"/>'
            )
        pres_rels.append(
            f'<Relationship Id="rId{n + 2}" Type="{_REL_THEME}"'
            ' Target="theme/theme1.xml"/>'
        )
        pres_rels.append("</Relationships>")

        sld_ids = "".join(
            f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, n + 1)
        )
        presentation = (
            _XML_DECL
            + f'<p:presentation xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
            + '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            + f"<p:sldIdLst>{sld_ids}</p:sldIdLst>"
            + f'<p:sldSz cx="{self.width_emu}" cy="{self.height_emu}"/>'
            + '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
        )

        xml_parts: list[tuple[str, str]] = [
            ("[Content_Types].xml", "".join(content_types)),
            (
                "_rels/.rels",
                _XML_DECL
                + f'<Relationships xmlns="{REL_NS}">'
                + f'<Relationship Id="rId1" Type="{DOC_REL_TYPE}" Target="ppt/presentation.xml"/>'
                + "</Relationships>",
            ),
            ("ppt/presentation.xml", presentation),
            ("ppt/_rels/presentation.xml.rels", "".join(pres_rels)),
            ("ppt/slideMasters/slideMaster1.xml", _SLIDE_MASTER_XML),
            (
                "ppt/slideMasters/_rels/slideMaster1.xml.rels",
                _XML_DECL
                + f'<Relationships xmlns="{REL_NS}">'
                + f'<Relationship Id="rId1" Type="{_REL_LAYOUT}"'
                + ' Target="../slideLayouts/slideLayout1.xml"/>'
                + f'<Relationship Id="rId2" Type="{_REL_THEME}"'
                + ' Target="../theme/theme1.xml"/>'
                + "</Relationships>",
            ),
            ("ppt/slideLayouts/slideLayout1.xml", _SLIDE_LAYOUT_XML),
            (
                "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
                _XML_DECL
                + f'<Relationships xmlns="{REL_NS}">'
                + f'<Relationship Id="rId1" Type="{_REL_MASTER}"'
                + ' Target="../slideMasters/slideMaster1.xml"/>'
                + "</Relationships>",
            ),
            ("ppt/theme/theme1.xml", _THEME_XML),
        ]
        for i, slide in enumerate(self.slides, start=1):
            xml_parts.append((f"ppt/slides/slide{i}.xml", _slide_xml(slide)))
        for i, slide in enumerate(self.slides, start=1):
            rels = [
                _XML_DECL,
                f'<Relationships xmlns="{REL_NS}">',
                f'<Relationship Id="rId1" Type="{_REL_LAYOUT}"'
                ' Target="../slideLayouts/slideLayout1.xml"/>',
            ]
            if slide.image is not None and slide.image.data:
                rels.append(
                    f'<Relationship Id="rId2" Type="{_REL_IMAGE}"'
                    f' Target="../media/image{i}.{slide.image.format}"/>'
                )
            rels.append("</Relationships>")
            xml_parts.append((f"ppt/slides/_rels/slide{i}.xml.rels", "".join(rels)))
        binary_parts: list[tuple[str, bytes]] = []
        for i, slide in enumerate(self.slides, start=1):
            if slide.image is None or not slide.image.data:
                continue
            fmt = slide.image.format
            binary_parts.append((f"ppt/media/image{i}.{fmt}", slide.image.data))
        return xml_parts, binary_parts


# ----------------------------------------------------------- slide parts


def _a_p(text: str, *, lvl: int = 0) -> str:
    return (
        f'<a:p><a:pPr lvl="{lvl}"/><a:r><a:rPr lang="en-US" dirty="0"/>'
        f"<a:t>{_esc(text)}</a:t></a:r></a:p>"
    )


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


_PLACEHOLDER = (
    '<p:sp><p:nvSpPr><p:cNvPr id="{id}" name="{name}"/>'
    '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="{ph}"{idx}/></p:nvPr>'
    "</p:nvSpPr><p:spPr/>"
    '<p:txBody><a:bodyPr/><a:lstStyle/>{paragraphs}</p:txBody></p:sp>'
)


def _slide_xml(slide: PptxSlide) -> str:
    title_sp = _PLACEHOLDER.format(
        id=2, name="Title", ph="title", idx="", paragraphs=_a_p(slide.title)
    )
    body_paragraphs = "".join(_a_p(b) for b in slide.bullets) or _a_p("")
    body_sp = _PLACEHOLDER.format(
        id=3, name="Content", ph="body", idx=' idx="1"', paragraphs=body_paragraphs
    )
    pic = ""
    if slide.image is not None and slide.image.data:
        rid = "rId2"
        img = slide.image
        pic = (
            f'<p:pic><p:nvPicPr><p:cNvPr id="10" name="Picture"/>'
            '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/>'
            f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f"<p:spPr><a:xfrm><a:off x=\"{img.x_emu}\" y=\"{img.y_emu}\"/>"
            f'<a:ext cx="{img.width_emu}" cy="{img.height_emu}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        )
    return (
        _XML_DECL
        + f'<p:sld xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
        + '<p:cSld><p:spTree>'
        + '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
        + title_sp
        + body_sp
        + pic
        + "</p:spTree></p:cSld>"
        + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


_SLIDE_MASTER_XML = (
    _XML_DECL
    + f'<p:sldMaster xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">'
    + '<p:cSld><p:spTree>'
    + '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
    + '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title Placeholder"/>'
    + '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    + '<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
    + '<p:spPr><a:xfrm><a:off x="838200" y="182562"/><a:ext cx="10515600" cy="1325563"/></a:xfrm>'
    + '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>'
    + '<a:p/></p:txBody></p:sp>'
    + '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Body Placeholder"/>'
    + '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    + '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
    + '<p:spPr><a:xfrm><a:off x="838200" y="1825625"/><a:ext cx="10515600" cy="4351338"/></a:xfrm>'
    + '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>'
    + '<a:p/></p:txBody></p:sp>'
    + "</p:spTree></p:cSld>"
    + '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    + 'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" '
    + 'folHlink="folHlink"/>'
    + '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    + "</p:sldMaster>"
)

_SLIDE_LAYOUT_XML = (
    _XML_DECL
    + f'<p:sldLayout xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}" '
    + 'type="obj" name="Title and Content">'
    + '<p:cSld name="Title and Content"><p:spTree>'
    + '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
    + '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title Placeholder"/>'
    + '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    + '<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
    + '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'
    + '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder"/>'
    + '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    + '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
    + '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'
    + "</p:spTree></p:cSld>"
    + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
)


# ------------------------------------------------------------------- read


def read(path: str | Path) -> PptxPresentation:
    """§18.4 *sources* over a real package — slides in presentation order."""
    target = Path(path)
    try:
        with zipfile.ZipFile(target) as zf:
            return _parse_package(zf)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ParseError(f"unreadable PPTX package: {exc}") from exc


def read_bytes(data: bytes) -> PptxPresentation:
    """Read a PPTX package from memory — same logic, no temp files."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return _parse_package(zf)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ParseError(f"unreadable PPTX package: {exc}") from exc


def _parse_package(zf: zipfile.ZipFile) -> PptxPresentation:
    names = set(zf.namelist())
    if "ppt/presentation.xml" not in names:
        raise ParseError("the package has no ppt/presentation.xml — not a PPTX")
    pres_root = ET.fromstring(zf.read("ppt/presentation.xml"))
    rel_for = _parse_rels(zf.read("ppt/_rels/presentation.xml.rels"))
    width, height = EMU_16X9_WIDTH, EMU_16X9_HEIGHT
    sz = pres_root.find(f"{{{P_NS}}}sldSz")
    if sz is not None:
        width = int(sz.get("cx", str(width)))
        height = int(sz.get("cy", str(height)))
    slides: list[PptxSlide] = []
    for sld in pres_root.findall(f"{{{P_NS}}}sldIdLst/{{{P_NS}}}sldId"):
        rid = sld.get(f"{{{R_NS}}}id", "")
        part = rel_for.get(rid, "")
        if not part:
            continue
        # rels targets are relative to ppt/ (or absolute "/ppt/…")
        part = part.lstrip("/")
        if not part.startswith("ppt/"):
            part = f"ppt/{part}"
        slide = _parse_slide(zf, part)
        slides.append(slide)
    return PptxPresentation(slides=slides, width_emu=width, height_emu=height)


def _parse_rels(raw: bytes) -> dict[str, str]:
    root = ET.fromstring(raw)
    out: dict[str, str] = {}
    for rel in root:
        out[rel.get("Id", "")] = rel.get("Target", "")
    return out


def _parse_slide(zf: zipfile.ZipFile, part: str) -> PptxSlide:
    root = ET.fromstring(zf.read(part))
    slide = PptxSlide()
    for sp in root.iter(f"{{{P_NS}}}sp"):
        ph = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}nvPr/{{{P_NS}}}ph")
        texts = [t.text or "" for t in sp.iter(f"{{{A_NS}}}t")]
        joined = " ".join(s for s in texts if s)
        if ph is not None and ph.get("type") == "title":
            slide.title = joined
        elif ph is not None and ph.get("type") == "body":
            slide.bullets = [s for s in texts if s]
    for pic in root.iter(f"{{{P_NS}}}pic"):
        blip = pic.find(f"{{{P_NS}}}blipFill/{{{A_NS}}}blip")
        if blip is None:
            continue
        rid = blip.get(f"{{{R_NS}}}embed", "")
        rel_path = f"{part.rsplit('/', 1)[0]}/_rels/{part.rsplit('/', 1)[1]}.rels"
        try:
            rels = _parse_rels(zf.read(rel_path))
        except KeyError:
            rels = {}
        target = rels.get(rid, "")
        if not target:
            continue
        base = part.rsplit("/", 1)[0]
        while target.startswith("../"):
            target = target[3:]
            base = base.rsplit("/", 1)[0]
        media_part = f"{base}/{target}" if base else target
        info = zf.getinfo(media_part)
        # inventory only — bytes stay on disk; size is the honest fact
        slide.image = PptxImage(
            data=b"", x_emu=0, y_emu=0, width_emu=0, height_emu=0, part="/" + media_part
        )
        slide.image.width_emu = info.file_size
    return slide


# ----------------------------------------------------------------- verify


def verify(path: str | Path, *, expect_titles: list[str] | None = None) -> DocumentVerification:
    """§18.4 *verify* — re-open what was saved and prove it holds."""
    target = Path(path)
    checks: dict[str, bool] = {}
    try:
        with zipfile.ZipFile(target) as zf:
            checks["zip_integrity"] = zf.testzip() is None
            names = set(zf.namelist())
            checks["main_part"] = "ppt/presentation.xml" in names
            checks["master_layout_theme"] = (
                "ppt/slideMasters/slideMaster1.xml" in names
                and "ppt/slideLayouts/slideLayout1.xml" in names
                and "ppt/theme/theme1.xml" in names
            )
            parsed = _parse_package(zf)
            checks["slides_parse"] = True
            if expect_titles is not None:
                got = [s.title for s in parsed.slides]
                checks["titles_roundtrip"] = got == list(expect_titles)
            media = [n for n in names if n.startswith("ppt/media/")]
            checks["media_present"] = bool(media) == any(
                s.image is not None for s in parsed.slides
            )
    except (ParseError, zipfile.BadZipFile) as exc:
        raise VerifyError(f"verification failed on {target}: {exc}") from exc
    ok = all(checks.values())
    detail = " · ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in checks.items())
    return DocumentVerification(ok=ok, path=str(target), checks=checks, detail=detail)


# ----------------------------------------------------- §18.1 native floor


class PptxParseBackend(ParseBackend):
    """The native PPTX floor — always present, stdlib only."""

    name = "native.pptx"
    kinds = (DocumentKind.PPTX,)

    def parse(self, source: DocumentSource) -> ParsedDocument:
        if source.kind != DocumentKind.PPTX:
            raise UnsupportedDocumentError(
                f"native.pptx parses pptx only, got {source.kind!r}"
            )
        try:
            pres = read_bytes(source.data)
        except ParseError:
            raise
        blocks: list[TextBlock] = []
        structure: list[StructureNode] = []
        for i, slide in enumerate(pres.slides, start=1):
            if slide.title.strip():
                blocks.append(
                    TextBlock(text=slide.title, locator=f"slide {i}", role="title")
                )
            for b, bullet in enumerate(slide.bullets, start=1):
                blocks.append(
                    TextBlock(text=bullet, locator=f"slide {i} bullet {b}", role="bullet")
                )
            structure.append(
                StructureNode(name=slide.title or f"slide {i}", node_type="slide")
            )
        title = pres.slides[0].title if pres.slides else ""
        return ParsedDocument(
            kind=DocumentKind.PPTX,
            uri=source.uri,
            title=title,
            sha256=hashlib.sha256(source.data).hexdigest(),
            size_bytes=len(source.data),
            structure=tuple(structure),
            blocks=tuple(blocks),
            metadata={
                "slides": str(len(pres.slides)),
                "slide_width_emu": str(pres.width_emu),
                "slide_height_emu": str(pres.height_emu),
            },
            parser=self.name,
        )
