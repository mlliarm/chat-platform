"""Renders Markdown text into reportlab flowables for PDF export.

Mirrors the marked.js rendering used in the browser (headings, bold/italic,
links, lists, tables, fenced code blocks) so an exported chat shows the same
formatted output the user sees on screen, not raw Markdown syntax.
"""

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import markdown as md_lib
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.style import Style
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    Table,
    TableStyle,
    XPreformatted,
)

# math_items entries are (latex_source, is_display) pairs collected by
# _extract_math(); every render function threads them through (together with
# the temp dir math images are rasterized into) so a placeholder anywhere in
# the parsed HTML tree can be turned back into an <img> tag.
MathItems = list[tuple[str, bool]]

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

# Syntax-highlighting for code blocks, mirroring the highlight.js coloring
# already used for code blocks in the browser. Only token color is applied
# (not Pygments' bold/italic flags) since that would need bold/italic variants
# of the monospace font registered too, for no real gain over a color-only look.
_PYGMENTS_STYLE: type[Style] = get_style_by_name("default")

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
    "math_display": ParagraphStyle("md-math-display", parent=_NORMAL, alignment=TA_CENTER, spaceBefore=6, spaceAfter=10),
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

# Unlike marked.js/CommonMark (used in the browser), python-markdown's classic
# parser won't let a list interrupt a paragraph — a "- item" line right after
# prose, with no blank line between them, is treated as a lazy continuation of
# that paragraph instead of the start of a new list. Only fires for a
# zero-indent list item directly after zero-indent, non-list prose, so it
# won't touch a wrapped continuation line inside an existing list item (those
# are indented) or fenced code content that happens to start with "- ".
_FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_TOP_LEVEL_LIST_MARKER_RE = re.compile(r"^([-*+]|\d+[.)])\s+\S")


def _ensure_blank_line_before_lists(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    for i, line in enumerate(lines):
        is_fence_line = bool(_FENCE_LINE_RE.match(line))
        if (
            not in_fence
            and not is_fence_line
            and i > 0
            and _TOP_LEVEL_LIST_MARKER_RE.match(line)
            and lines[i - 1].strip()
            and not lines[i - 1][:1].isspace()
            and not _TOP_LEVEL_LIST_MARKER_RE.match(lines[i - 1])
        ):
            out.append("")
        out.append(line)
        if is_fence_line:
            in_fence = not in_fence
    return "\n".join(out)


# Mirrors the delimiters MathJax renders in the browser (see the
# `mathTokenizer()`/MATH_SPAN_RE pair in static/script.js): `$$…$$`/`\[…\]`
# for display math, `\(…\)`/`$…$` for inline. Extracted before python-markdown
# ever sees the text, for the same reason the browser claims math as its own
# token before markdown's inline rules run — markdown's backslash-escape and
# emphasis rules would otherwise mangle `\[`, `\\` row breaks, and `_`/`*`
# inside an expression. Code spans are matched first and passed through
# untouched, matching marked's codespan tokenizer running before math there.
_CODE_SPAN_RE = re.compile(r"(`+)([\s\S]*?)\1")
_MATH_SPAN_RE = re.compile(
    r"\$\$(?P<disp_dollar>[\s\S]+?)\$\$"
    r"|\\\[(?P<disp_bracket>[\s\S]+?)\\\]"
    r"|\\\((?P<inline_paren>[\s\S]+?)\\\)"
    r"|\$(?!\s|\$)(?P<inline_dollar>(?:\\.|[^\\$\n])+?)(?<!\s|\\)\$(?!\d)"
)
# A Private Use Area pair (valid, essentially never-occurring-naturally XML
# characters) marking where a math span was pulled out of the text, so it
# survives the python-markdown -> XML round trip as inert plain text and can
# be swapped for a rendered <img> tag afterwards.
_MATH_PLACEHOLDER_RE = re.compile("(\\d+)")
_SOLE_MATH_PLACEHOLDER_RE = re.compile(r"^(\d+)$")


def _scan_math_spans(text: str, math_items: MathItems) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        code_m = _CODE_SPAN_RE.match(text, i)
        if code_m:
            out.append(code_m.group(0))
            i = code_m.end()
            continue
        math_m = _MATH_SPAN_RE.match(text, i)
        if math_m:
            display = math_m.group("disp_dollar") is not None or math_m.group("disp_bracket") is not None
            body = (
                math_m.group("disp_dollar")
                or math_m.group("disp_bracket")
                or math_m.group("inline_paren")
                or math_m.group("inline_dollar")
            )
            math_items.append((body, display))
            out.append(f"{len(math_items) - 1}")
            i = math_m.end()
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _extract_math(text: str) -> tuple[str, MathItems]:
    """Pulls LaTeX math spans out of raw Markdown, replacing each with a
    placeholder and returning the (latex, is_display) items alongside. Fenced
    code blocks are skipped line-by-line (same fence tracking as
    _ensure_blank_line_before_lists) so a `$` inside a code sample is never
    mistaken for math, matching the browser leaving `pre`/`code` untouched.
    """
    math_items: MathItems = []
    out_parts: list[str] = []
    run: list[str] = []
    in_fence = False

    def flush_run() -> None:
        if run:
            out_parts.append(_scan_math_spans("\n".join(run), math_items))
            run.clear()

    for line in text.split("\n"):
        if _FENCE_LINE_RE.match(line):
            flush_run()
            in_fence = not in_fence
            out_parts.append(line)
        elif in_fence:
            out_parts.append(line)
        else:
            run.append(line)
    flush_run()
    return "\n".join(out_parts), math_items


_INLINE_MATH_FONT_SIZE = 10.5
_DISPLAY_MATH_FONT_SIZE = 13.5
_MATH_RASTER_DPI = 200


def _math_img_tag(latex: str, display: bool, tmp_dir: str, math_index: int) -> str | None:
    """Rasterizes a LaTeX span to a PNG via matplotlib's mathtext (a
    self-contained TeX-like math renderer that needs no system LaTeX install)
    and returns a reportlab Paragraph `<img>` tag for it. Width/height are set
    in points from mathtext's own metrics, so the image matches the
    surrounding text size regardless of the raster's dpi. Returns None if the
    expression uses something mathtext doesn't support (e.g. an
    `aligned`/`align` environment), so the caller can fall back to showing
    the raw LaTeX instead of failing the whole export.
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import mathtext
    from matplotlib.font_manager import FontProperties

    fontsize = _DISPLAY_MATH_FONT_SIZE if display else _INLINE_MATH_FONT_SIZE
    prop = FontProperties(size=fontsize)
    # mathtext's grammar rejects embedded newlines/indentation — LaTeX math
    # mode treats whitespace as insignificant, so collapsing it is safe. This
    # matters because display math is often written with the delimiter and
    # body on separate lines, e.g. "\[\n   \sqrt{2} = \frac{p}{q}\n   \]".
    normalized = re.sub(r"\s+", " ", latex).strip()
    wrapped = f"${normalized}$"
    try:
        width, height, _depth, _glyphs, _rects = mathtext.MathTextParser("path").parse(wrapped, dpi=72, prop=prop)
        path = os.path.join(tmp_dir, f"math-{math_index}.png")
        mathtext.math_to_image(wrapped, path, prop=prop, dpi=_MATH_RASTER_DPI, format="png")
    except Exception:
        return None

    valign = "middle" if display else "baseline"
    return f'<img src="{xml_escape(path)}" width="{width:.2f}" height="{height:.2f}" valign="{valign}"/>'


def _math_markup(math_items: MathItems, tmp_dir: str, math_index: int) -> str:
    latex, display = math_items[math_index]
    tag = _math_img_tag(latex, display, tmp_dir, math_index)
    if tag is not None:
        return tag
    # mathtext couldn't parse this expression — show the raw LaTeX rather
    # than silently dropping the content.
    return f'<font face="{FONT_MONO}" size="9">{xml_escape(latex)}</font>'


def _escape_with_math(text: str | None, math_items: MathItems, tmp_dir: str) -> str:
    if not text:
        return ""
    if not math_items or "" not in text:
        return xml_escape(text)
    parts: list[str] = []
    last = 0
    for m in _MATH_PLACEHOLDER_RE.finditer(text):
        parts.append(xml_escape(text[last : m.start()]))
        parts.append(_math_markup(math_items, tmp_dir, int(m.group(1))))
        last = m.end()
    parts.append(xml_escape(text[last:]))
    return "".join(parts)


def _sole_display_math_index(el: ET.Element, math_items: MathItems) -> int | None:
    """If `el` (a <p>) contains nothing but a single display-math placeholder,
    returns its index so the caller can render it as its own centered block
    instead of an ordinary body paragraph."""
    if len(el) or not el.text:
        return None
    m = _SOLE_MATH_PLACEHOLDER_RE.match(el.text.strip())
    if not m:
        return None
    idx = int(m.group(1))
    if idx >= len(math_items) or not math_items[idx][1]:
        return None
    return idx


def markdown_flowables(text: str) -> list[Flowable]:
    """Converts Markdown text into a list of flowables for a reportlab story."""
    if not text.strip():
        return []

    text = _THINK_BLOCK_RE.sub("", text)
    text = _STRAY_THINK_TAG_RE.sub("", text)
    if not text.strip():
        return []

    fallback_text = text
    text, math_items = _extract_math(text)
    text = _ensure_blank_line_before_lists(text)
    html = md_lib.markdown(text, extensions=MARKDOWN_EXTENSIONS)
    try:
        root = ET.fromstring(f"<div>{html}</div>")
    except ET.ParseError:
        # Shouldn't normally happen (python-markdown emits well-formed output),
        # but fall back to plain text rather than losing the message.
        return [Paragraph(xml_escape(fallback_text).replace("\n", "<br/>"), STYLES["body"])]

    with tempfile.TemporaryDirectory(prefix="chatpdf-math-") as tmp_dir:
        flowables: list[Flowable] = []
        for el in root:
            flowables.extend(_render_block(el, math_items, tmp_dir))
        return flowables or [Paragraph(xml_escape(fallback_text).replace("\n", "<br/>"), STYLES["body"])]


def _inline_markup(el: ET.Element, math_items: MathItems, tmp_dir: str) -> str:
    """Renders an element's inline content into reportlab's Paragraph mini-markup."""
    parts: list[str] = [_escape_with_math(el.text, math_items, tmp_dir)] if el.text else []
    for child in el:
        tag = child.tag
        inner = _inline_markup(child, math_items, tmp_dir)
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
            parts.append(_escape_with_math(child.tail, math_items, tmp_dir))
    return "".join(parts)


def _render_block(
    el: ET.Element, math_items: MathItems, tmp_dir: str, body_style: ParagraphStyle | None = None
) -> list[Flowable]:
    style = body_style or STYLES["body"]
    tag = el.tag

    if tag == "p":
        display_idx = _sole_display_math_index(el, math_items)
        if display_idx is not None:
            return [Paragraph(_math_markup(math_items, tmp_dir, display_idx), STYLES["math_display"])]
        markup = _inline_markup(el, math_items, tmp_dir)
        return [Paragraph(markup, style)] if markup.strip() else []

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        markup = _inline_markup(el, math_items, tmp_dir)
        return [Paragraph(markup, STYLES[tag])] if markup.strip() else []

    if tag in ("ul", "ol"):
        return [_render_list(el, math_items, tmp_dir)]

    if tag == "pre":
        code_el = el.find("code")
        code_text = "".join((code_el if code_el is not None else el).itertext())
        # python-markdown's fenced_code extension puts the fence's language
        # hint (e.g. ```python) on the <code> element as class="language-python".
        css_class = code_el.get("class", "") if code_el is not None else ""
        lang = css_class.removeprefix("language-") if css_class.startswith("language-") else None
        return [_code_bubble(code_text.rstrip("\n"), lang)]

    if tag == "blockquote":
        flowables: list[Flowable] = []
        for child in el:
            flowables.extend(_render_block(child, math_items, tmp_dir, body_style=STYLES["quote"]))
        return flowables

    if tag == "hr":
        return [HRFlowable(width="100%", color=_BORDER, spaceBefore=4, spaceAfter=10)]

    if tag == "table":
        return [_render_table(el, math_items, tmp_dir)]

    # Unrecognized block element — flatten its inline content into a paragraph.
    markup = _inline_markup(el, math_items, tmp_dir)
    return [Paragraph(markup, style)] if markup.strip() else []


def _highlighted_code_markup(code_text: str, lang: str | None) -> str:
    """Syntax-highlights code into reportlab mini-markup (<font color="...">
    spans), mirroring the highlight.js coloring already used in the browser."""
    lexer = None
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripnl=False)
        except ClassNotFound:
            lexer = None
    if lexer is None:
        try:
            lexer = guess_lexer(code_text)
        except ClassNotFound:
            return xml_escape(code_text)

    try:
        tokens = list(lex(code_text, lexer))
    except Exception:
        return xml_escape(code_text)

    # Pygments' lexers commonly append a trailing newline for correct
    # tokenization even when the input doesn't end with one — drop it again
    # so we don't introduce a blank line the original code block didn't have.
    if tokens and not code_text.endswith("\n"):
        last_type, last_value = tokens[-1]
        if last_value.endswith("\n"):
            trimmed = last_value[:-1]
            if trimmed:
                tokens[-1] = (last_type, trimmed)
            else:
                tokens.pop()

    parts: list[str] = []
    for token_type, value in tokens:
        if not value:
            continue
        escaped = xml_escape(value)
        color = _PYGMENTS_STYLE.style_for_token(token_type)["color"]
        parts.append(f'<font color="#{color}">{escaped}</font>' if color else escaped)
    return "".join(parts)


def _code_bubble(code_text: str, lang: str | None) -> Table:
    """Wraps a fenced code block in a shaded, rounded box (a Table, since
    Preformatted itself can't draw a background) — matching the code block
    "bubble" the browser shows via marked.js."""
    markup = _highlighted_code_markup(code_text, lang)
    pre = XPreformatted(markup, STYLES["code"])
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


def _render_list(el: ET.Element, math_items: MathItems, tmp_dir: str) -> ListFlowable:
    items: list[ListItem] = []
    for li in el:
        if li.tag != "li":
            continue
        items.append(ListItem(_render_li_content(li, math_items, tmp_dir), leftIndent=6))
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


def _render_li_content(li: ET.Element, math_items: MathItems, tmp_dir: str) -> list[Flowable]:
    """A list item may hold plain inline content (tight list) or block children
    (loose list, or a nested list/blockquote/code block inside the item)."""
    block_children = [c for c in li if c.tag in _BLOCK_TAGS]
    if not block_children:
        markup = _inline_markup(li, math_items, tmp_dir)
        return [Paragraph(markup, STYLES["body"])] if markup.strip() else [Paragraph("", STYLES["body"])]

    flowables: list[Flowable] = []
    if li.text and li.text.strip():
        flowables.append(Paragraph(_escape_with_math(li.text.strip(), math_items, tmp_dir), STYLES["body"]))
    for child in block_children:
        flowables.extend(_render_block(child, math_items, tmp_dir))
    return flowables


def _render_table(el: ET.Element, math_items: MathItems, tmp_dir: str) -> Table:
    header_rows: list[list[str]] = []
    thead = el.find("thead")
    if thead is not None:
        header_rows = [[_inline_markup(cell, math_items, tmp_dir) for cell in tr] for tr in thead.findall("tr")]

    tbody = el.find("tbody")
    body_source = tbody if tbody is not None else el
    body_rows = [[_inline_markup(cell, math_items, tmp_dir) for cell in tr] for tr in body_source.findall("tr")]

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
