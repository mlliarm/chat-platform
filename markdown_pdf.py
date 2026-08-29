"""Renders Markdown text into reportlab flowables for PDF export.

Mirrors the marked.js rendering used in the browser (headings, bold/italic,
links, lists, tables, fenced code blocks) so an exported chat shows the same
formatted output the user sees on screen, not raw Markdown syntax.
"""

import os
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import markdown as md_lib
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, HRFlowable, ListFlowable, ListItem, Paragraph, Preformatted, Table, TableStyle

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "nl2br", "sane_lists"]

# The PDF standard fonts (Helvetica, Courier, ...) only cover Latin-1, so any
# reply containing Greek, APL symbols, or other non-Latin-1 Unicode renders
# those characters as blank boxes. DejaVu Sans/Mono (bundled in fonts/) cover
# a much wider Unicode range and are used for every PDF-export style instead.
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
FONT_ITALIC = "DejaVuSans-Oblique"
FONT_BOLD_ITALIC = "DejaVuSans-BoldOblique"
FONT_MONO = "DejaVuSansMono"
pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(_FONTS_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(_FONTS_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont(FONT_ITALIC, os.path.join(_FONTS_DIR, "DejaVuSans-Oblique.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD_ITALIC, os.path.join(_FONTS_DIR, "DejaVuSans-BoldOblique.ttf")))
pdfmetrics.registerFont(TTFont(FONT_MONO, os.path.join(_FONTS_DIR, "DejaVuSansMono.ttf")))
pdfmetrics.registerFontFamily(
    FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD, italic=FONT_ITALIC, boldItalic=FONT_BOLD_ITALIC
)

_NORMAL = getSampleStyleSheet()["Normal"]
_ACCENT = colors.HexColor("#7c5cff")
_MUTED = colors.HexColor("#555555")
_BORDER = colors.HexColor("#d8d0ea")
_CODE_BG = colors.HexColor("#f3edfa")

STYLES: dict[str, ParagraphStyle] = {
    "body": ParagraphStyle("md-body", parent=_NORMAL, fontName=FONT_REGULAR, spaceAfter=8, leading=15),
    "h1": ParagraphStyle("md-h1", parent=_NORMAL, fontName=FONT_BOLD, fontSize=18, leading=22, spaceBefore=10, spaceAfter=8),
    "h2": ParagraphStyle("md-h2", parent=_NORMAL, fontName=FONT_BOLD, fontSize=15, leading=19, spaceBefore=10, spaceAfter=6),
    "h3": ParagraphStyle("md-h3", parent=_NORMAL, fontName=FONT_BOLD, fontSize=13, leading=17, spaceBefore=8, spaceAfter=6),
    "h4": ParagraphStyle("md-h4", parent=_NORMAL, fontName=FONT_BOLD, fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4),
    # backColor/borderPadding aren't set here: reportlab's Preformatted flowable
    # (unlike Paragraph) ignores them when drawing, so the shaded "bubble" behind
    # a code block is instead drawn by wrapping it in a Table — see _code_bubble().
    "code": ParagraphStyle("md-code", parent=_NORMAL, fontName=FONT_MONO, fontSize=8.5, leading=11),
    "quote": ParagraphStyle("md-quote", parent=_NORMAL, fontName=FONT_REGULAR, textColor=_MUTED, leftIndent=12, spaceAfter=8, leading=15),
    "table_cell": ParagraphStyle("md-table-cell", parent=_NORMAL, fontName=FONT_REGULAR, fontSize=9, leading=12),
    "table_header_cell": ParagraphStyle("md-table-header-cell", parent=_NORMAL, fontName=FONT_BOLD, fontSize=9, leading=12),
}
STYLES["h5"] = STYLES["h4"]
STYLES["h6"] = STYLES["h4"]

_BLOCK_TAGS = {"p", "ul", "ol", "pre", "blockquote"}

# Reasoning models (e.g. some OpenRouter models in "thinking" mode) sometimes
# leave a <think>...</think> block — or, as observed, a stray closing
# </think> with no opening tag — in the stored reply text. Markdown passes
# literal "<...>"-looking text through as raw HTML, and an unmatched tag
# breaks the XML parse below, silently falling back to one unformatted
# paragraph for the whole message. Strip these before conversion.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_STRAY_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)


def markdown_flowables(text: str) -> list[Flowable]:
    """Converts Markdown text into a list of flowables for a reportlab story."""
    if not text.strip():
        return []

    text = _THINK_BLOCK_RE.sub("", text)
    text = _STRAY_THINK_TAG_RE.sub("", text)
    if not text.strip():
        return []

    html = md_lib.markdown(text, extensions=MARKDOWN_EXTENSIONS)
    try:
        root = ET.fromstring(f"<div>{html}</div>")
    except ET.ParseError:
        # Shouldn't normally happen (python-markdown emits well-formed output),
        # but fall back to plain text rather than losing the message.
        return [Paragraph(xml_escape(text).replace("\n", "<br/>"), STYLES["body"])]

    flowables: list[Flowable] = []
    for el in root:
        flowables.extend(_render_block(el))
    return flowables or [Paragraph(xml_escape(text).replace("\n", "<br/>"), STYLES["body"])]


def _inline_markup(el: ET.Element) -> str:
    """Renders an element's inline content into reportlab's Paragraph mini-markup."""
    parts: list[str] = [xml_escape(el.text)] if el.text else []
    for child in el:
        tag = child.tag
        inner = _inline_markup(child)
        if tag in ("strong", "b"):
            parts.append(f"<b>{inner}</b>")
        elif tag in ("em", "i"):
            parts.append(f"<i>{inner}</i>")
        elif tag in ("del", "s", "strike"):
            parts.append(f"<strike>{inner}</strike>")
        elif tag == "code":
            parts.append(f'<font face="{FONT_MONO}" size="9">{xml_escape("".join(child.itertext()))}</font>')
        elif tag == "a":
            href = child.get("href", "")
            parts.append(f'<a href="{xml_escape(href)}" color="#7c5cff">{inner}</a>' if href else inner)
        elif tag == "br":
            parts.append("<br/>")
        else:
            parts.append(inner)
        if child.tail:
            parts.append(xml_escape(child.tail))
    return "".join(parts)


def _render_block(el: ET.Element, body_style: ParagraphStyle | None = None) -> list[Flowable]:
    style = body_style or STYLES["body"]
    tag = el.tag

    if tag == "p":
        markup = _inline_markup(el)
        return [Paragraph(markup, style)] if markup.strip() else []

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        markup = _inline_markup(el)
        return [Paragraph(markup, STYLES[tag])] if markup.strip() else []

    if tag in ("ul", "ol"):
        return [_render_list(el)]

    if tag == "pre":
        code_el = el.find("code")
        code_text = "".join((code_el if code_el is not None else el).itertext())
        return [_code_bubble(code_text.rstrip("\n"))]

    if tag == "blockquote":
        flowables: list[Flowable] = []
        for child in el:
            flowables.extend(_render_block(child, body_style=STYLES["quote"]))
        return flowables

    if tag == "hr":
        return [HRFlowable(width="100%", color=_BORDER, spaceBefore=4, spaceAfter=10)]

    if tag == "table":
        return [_render_table(el)]

    # Unrecognized block element — flatten its inline content into a paragraph.
    markup = _inline_markup(el)
    return [Paragraph(markup, style)] if markup.strip() else []


def _code_bubble(code_text: str) -> Table:
    """Wraps a fenced code block in a shaded, rounded box (a Table, since
    Preformatted itself can't draw a background) — matching the code block
    "bubble" the browser shows via marked.js."""
    pre = Preformatted(code_text, STYLES["code"])
    table = Table([[pre]], hAlign="LEFT", spaceBefore=2, spaceAfter=8)
    style_cmds: list[tuple[object, ...]] = [
        ("BACKGROUND", (0, 0), (-1, -1), _CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, _BORDER),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    # See the matching note on _render_table's TableStyle call below.
    table.setStyle(TableStyle(style_cmds))  # type: ignore[arg-type]
    return table


def _render_list(el: ET.Element) -> ListFlowable:
    items: list[ListItem] = []
    for li in el:
        if li.tag != "li":
            continue
        items.append(ListItem(_render_li_content(li), leftIndent=6))
    is_ordered = el.tag == "ol"
    # reportlab-stubs types ListFlowable's argument as Iterable[Flowable | Sequence[...]],
    # but ListItem (not a Flowable subclass) is the documented, correct element type here.
    return ListFlowable(
        items,  # type: ignore[arg-type]
        bulletType="1" if is_ordered else "bullet",
        bulletFormat="%s." if is_ordered else None,
        leftIndent=18,
        bulletFontSize=9,
        spaceBefore=2,
        spaceAfter=8,
    )


def _render_li_content(li: ET.Element) -> list[Flowable]:
    """A list item may hold plain inline content (tight list) or block children
    (loose list, or a nested list/blockquote/code block inside the item)."""
    block_children = [c for c in li if c.tag in _BLOCK_TAGS]
    if not block_children:
        markup = _inline_markup(li)
        return [Paragraph(markup, STYLES["body"])] if markup.strip() else [Paragraph("", STYLES["body"])]

    flowables: list[Flowable] = []
    if li.text and li.text.strip():
        flowables.append(Paragraph(xml_escape(li.text.strip()), STYLES["body"]))
    for child in block_children:
        flowables.extend(_render_block(child))
    return flowables


def _render_table(el: ET.Element) -> Table:
    header_rows: list[list[str]] = []
    thead = el.find("thead")
    if thead is not None:
        header_rows = [[_inline_markup(cell) for cell in tr] for tr in thead.findall("tr")]

    tbody = el.find("tbody")
    body_source = tbody if tbody is not None else el
    body_rows = [[_inline_markup(cell) for cell in tr] for tr in body_source.findall("tr")]

    cell_flowables = [[Paragraph(cell, STYLES["table_header_cell"]) for cell in row] for row in header_rows] + [
        [Paragraph(cell, STYLES["table_cell"]) for cell in row] for row in body_rows
    ]

    table = Table(cell_flowables, hAlign="LEFT")
    style_cmds: list[tuple[object, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header_rows:
        style_cmds.append(("BACKGROUND", (0, 0), (-1, len(header_rows) - 1), _CODE_BG))
    # reportlab-stubs types each TableStyle command tuple with a strict per-command
    # literal shape; a dynamically built list of well-formed commands doesn't fit that.
    table.setStyle(TableStyle(style_cmds))  # type: ignore[arg-type]
    return table
