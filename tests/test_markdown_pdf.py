"""Tests for markdown_pdf.py — converts Markdown text into reportlab flowables
for PDF export, mirroring what marked.js renders in the browser."""

import re

import pytest
from reportlab.platypus import ListFlowable, Paragraph, Table, XPreformatted

from markdown_pdf import markdown_flowables

_FONT_TAG_RE = re.compile(r"</?font[^>]*>")


def strip_font_tags(markup: str) -> str:
    """Reconstructs the plain code text from syntax-highlighted markup."""
    return _FONT_TAG_RE.sub("", markup)


def test_empty_text_returns_no_flowables() -> None:
    assert markdown_flowables("") == []
    assert markdown_flowables("   \n  ") == []


def test_plain_paragraph() -> None:
    flowables = markdown_flowables("Hello there")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert para.text == "Hello there"


def test_bold_and_italic_and_inline_code() -> None:
    flowables = markdown_flowables("Some **bold** and *italic* and `code`.")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "<b>bold</b>" in para.text
    assert "<i>italic</i>" in para.text
    assert '<font face="DejaVuSansMono" size="9">code</font>' in para.text


def test_headings_use_distinct_larger_styles() -> None:
    flowables = markdown_flowables("# Big\n\n## Smaller")
    big, smaller = flowables
    assert isinstance(big, Paragraph) and isinstance(smaller, Paragraph)
    assert (big.text, smaller.text) == ("Big", "Smaller")
    assert big.style.name == "md-h1"
    assert smaller.style.name == "md-h2"
    assert big.style.fontSize > smaller.style.fontSize


def test_link_renders_as_anchor_tag() -> None:
    flowables = markdown_flowables("[docs](https://example.com)")
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert '<a href="https://example.com"' in para.text
    assert ">docs</a>" in para.text


def test_unordered_list_becomes_list_flowable() -> None:
    flowables = markdown_flowables("- one\n- two\n- three")
    assert len(flowables) == 1
    assert isinstance(flowables[0], ListFlowable)


def test_fenced_code_block_becomes_a_shaded_bubble_with_syntax_highlighting() -> None:
    flowables = markdown_flowables("```python\nprint('hi')\n```")
    assert len(flowables) == 1
    bubble = flowables[0]
    # A bare Preformatted flowable silently ignores backColor/border styling
    # (reportlab quirk), so code blocks are wrapped in a shaded Table "bubble"
    # instead — matching the browser's code block appearance. XPreformatted
    # (not Preformatted) is used so the syntax-highlighting color spans below
    # can be applied while still preserving exact monospace line layout.
    assert isinstance(bubble, Table)
    pre = bubble._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, XPreformatted)
    assert "<font color=" in pre.text
    assert strip_font_tags(pre.text) == "print('hi')"


def test_syntax_highlighting_uses_the_fence_language_hint() -> None:
    flowables = markdown_flowables("```python\ndef foo():\n    return 1\n```")
    pre = flowables[0]._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, XPreformatted)
    # "def" is a Python keyword and must be colored; the reconstructed plain
    # text (tags stripped) must still be exactly the original code.
    assert '<font color="#008000">def</font>' in pre.text
    assert strip_font_tags(pre.text) == "def foo():\n    return 1"


def test_syntax_highlighting_does_not_add_a_spurious_trailing_blank_line() -> None:
    # Pygments lexers commonly append a trailing newline internally for
    # correct tokenization even when the input doesn't end with one.
    flowables = markdown_flowables("```python\nx = 1\n```")
    pre = flowables[0]._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, XPreformatted)
    assert strip_font_tags(pre.text) == "x = 1"
    assert not strip_font_tags(pre.text).endswith("\n")


def test_unrecognized_language_falls_back_to_auto_detection_without_erroring() -> None:
    flowables = markdown_flowables("```apl\nfact ← {×/ 1 ∘⍳ ⍵}\n```")
    pre = flowables[0]._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, XPreformatted)
    assert strip_font_tags(pre.text) == "fact ← {×/ 1 ∘⍳ ⍵}"


def test_table_becomes_table_flowable() -> None:
    flowables = markdown_flowables("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert len(flowables) == 1
    assert isinstance(flowables[0], Table)


def test_blockquote_uses_quote_style() -> None:
    flowables = markdown_flowables("> quoted text")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert para.style.name == "md-quote"
    assert para.text == "quoted text"


def test_mixed_document_produces_expected_flowable_sequence() -> None:
    text = "# Title\n\nSome **bold** text.\n\n- one\n- two\n\n```\ncode here\n```\n"
    flowables = markdown_flowables(text)
    kinds = [type(f).__name__ for f in flowables]
    assert kinds == ["Paragraph", "Paragraph", "ListFlowable", "Table"]


def test_matched_think_block_is_stripped() -> None:
    flowables = markdown_flowables("<think>internal reasoning, ignore me</think>\n\nActual **answer** here.")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "internal reasoning" not in para.text
    assert "<b>answer</b>" in para.text


def test_stray_unmatched_think_tag_does_not_break_markdown_rendering() -> None:
    # Some reasoning models leave a bare closing </think> with no opening tag
    # in the stored reply. That literal "<...>" text used to get passed
    # through as raw (unescaped) HTML by python-markdown, producing a
    # mismatched tag that broke the XML parse and silently fell back to a
    # single unformatted paragraph for the whole message.
    text = "Some **bold** reasoning summary.\n</think>\n\nThe real **answer**."
    flowables = markdown_flowables(text)
    assert len(flowables) == 2
    assert all(isinstance(f, Paragraph) for f in flowables)
    combined = "".join(f.text for f in flowables if isinstance(f, Paragraph))
    assert "</think>" not in combined
    assert "<b>bold</b>" in combined
    assert "<b>answer</b>" in combined


def test_only_think_content_returns_no_flowables() -> None:
    assert markdown_flowables("<think>just reasoning, no visible reply</think>") == []


def test_non_latin1_characters_use_unicode_capable_font() -> None:
    # The PDF standard fonts (Helvetica etc.) only cover Latin-1 — Greek and
    # APL symbols would render as blank boxes unless a Unicode font is used.
    flowables = markdown_flowables("Ναι, γνωρίζω APL: `+/ 1 2 3`")
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert para.style.fontName == "DejaVuSans"
    assert "Ναι, γνωρίζω APL:" in para.text


def test_list_immediately_after_paragraph_with_no_blank_line_still_becomes_a_list() -> None:
    # python-markdown's classic parser (unlike marked.js/CommonMark) won't let
    # a list interrupt a paragraph without a blank line between them — this
    # used to render as one paragraph with literal "- " text instead of bullets.
    text = "**Explanation:**\n- first point\n- second point"
    flowables = markdown_flowables(text)
    assert len(flowables) == 2
    intro, bullets = flowables
    assert isinstance(intro, Paragraph)
    assert intro.text == "<b>Explanation:</b>"
    assert isinstance(bullets, ListFlowable)


def test_ordered_list_immediately_after_paragraph_also_becomes_a_list() -> None:
    text = "Steps:\n1. one\n2. two"
    flowables = markdown_flowables(text)
    assert len(flowables) == 2
    assert isinstance(flowables[1], ListFlowable)


def test_list_after_heading_with_no_blank_line_becomes_a_list() -> None:
    text = "### Section\n- a\n- b"
    flowables = markdown_flowables(text)
    assert len(flowables) == 2
    heading, bullets = flowables
    assert isinstance(heading, Paragraph)
    assert heading.style.name == "md-h3"
    assert isinstance(bullets, ListFlowable)


def test_wrapped_continuation_line_inside_a_list_item_is_not_split_into_two_lists() -> None:
    # A continuation line indented under a bullet is part of that list item,
    # not a paragraph the next bullet needs separating from.
    text = "- Item one continues\n  on a second line\n- Item two"
    flowables = markdown_flowables(text)
    assert len(flowables) == 1
    assert isinstance(flowables[0], ListFlowable)


def test_nested_list_right_after_parent_item_is_not_given_a_spurious_gap() -> None:
    text = "- Parent item\n  - Nested item"
    flowables = markdown_flowables(text)
    assert len(flowables) == 1
    assert isinstance(flowables[0], ListFlowable)


def test_dash_line_inside_fenced_code_block_is_left_as_code_not_turned_into_a_list() -> None:
    text = "Some text\n```\n- not a list, just code\nmore code\n```"
    flowables = markdown_flowables(text)
    kinds = [type(f).__name__ for f in flowables]
    assert kinds == ["Paragraph", "Table"]
    pre = flowables[1]._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, XPreformatted)
    assert strip_font_tags(pre.text) == "- not a list, just code\nmore code"


def test_malformed_html_fallback_still_returns_readable_text(monkeypatch: pytest.MonkeyPatch) -> None:
    import xml.etree.ElementTree as ET

    import markdown_pdf

    def broken_fromstring(_: str) -> None:
        raise ET.ParseError("boom")

    monkeypatch.setattr(markdown_pdf.ET, "fromstring", broken_fromstring)
    flowables = markdown_pdf.markdown_flowables("plain fallback text")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "plain fallback text" in para.text


def test_inline_latex_renders_as_an_image_not_raw_source() -> None:
    flowables = markdown_flowables(r"The area is \(\pi r^2\).")
    assert len(flowables) == 1
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "<img" in para.text
    assert r"\(\pi r^2\)" not in para.text
    assert "The area is" in para.text


def test_dollar_delimited_inline_latex_also_renders_as_an_image() -> None:
    flowables = markdown_flowables(r"Let $x^2$ be a square.")
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "<img" in para.text
    assert "$x^2$" not in para.text


def test_display_latex_becomes_its_own_centered_paragraph() -> None:
    flowables = markdown_flowables("Given:\n\n$$a^2 + b^2 = c^2$$\n\nQ.E.D.")
    kinds = [type(f).__name__ for f in flowables]
    assert kinds == ["Paragraph", "Paragraph", "Paragraph"]
    given, equation, qed = flowables
    assert "<img" in equation.text
    assert equation.style.name == "md-math-display"
    assert given.style.name != "md-math-display"
    assert qed.style.name != "md-math-display"


def test_bracket_delimited_display_latex_also_renders() -> None:
    flowables = markdown_flowables("\\[E = mc^2\\]")
    assert len(flowables) == 1
    para = flowables[0]
    assert para.style.name == "md-math-display"
    assert "<img" in para.text


def test_currency_dollar_amount_is_not_mistaken_for_math() -> None:
    flowables = markdown_flowables("This costs $5, not math.")
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "<img" not in para.text
    assert "This costs $5, not math." in para.text


def test_math_delimiters_inside_code_are_left_untouched() -> None:
    flowables = markdown_flowables("Inline `\\(not math\\)` and:\n\n```\n$also not math$\n```")
    kinds = [type(f).__name__ for f in flowables]
    assert kinds == ["Paragraph", "Table"]
    para = flowables[0]
    assert "<img" not in para.text
    assert r"\(not math\)" in para.text
    pre = flowables[1]._cellvalues[0][0]  # type: ignore[attr-defined]
    assert strip_font_tags(pre.text) == "$also not math$"


def test_display_latex_with_delimiter_and_body_on_separate_lines_still_renders() -> None:
    # LLM output commonly puts the `\[`/`\]` delimiter on its own line, with
    # the equation body (and its surrounding indentation) on the next, e.g.:
    #   \[
    #      \sqrt{2} = \frac{p}{q}
    #   \]
    # matplotlib's mathtext rejects embedded newlines, so this must be
    # normalized to a single line before being handed to it.
    flowables = markdown_flowables("Given:\n\n\\[\n   \\sqrt{2} = \\frac{p}{q}\n   \\]\n\nQ.E.D.")
    equation = flowables[1]
    assert isinstance(equation, Paragraph)
    assert equation.style.name == "md-math-display"
    assert "<img" in equation.text
    assert "sqrt" not in equation.text


def test_latex_unsupported_by_the_renderer_falls_back_to_raw_source() -> None:
    # matplotlib's mathtext (used to rasterize LaTeX with no system LaTeX
    # install required) doesn't understand `aligned`/`align` environments —
    # this should degrade to showing the LaTeX source, not blow up the export.
    flowables = markdown_flowables(r"\(\begin{aligned}a &= b\end{aligned}\)")
    para = flowables[0]
    assert isinstance(para, Paragraph)
    assert "<img" not in para.text
    assert "begin" in para.text
    assert "aligned" in para.text
