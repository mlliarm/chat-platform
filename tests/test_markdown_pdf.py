"""Tests for markdown_pdf.py — converts Markdown text into reportlab flowables
for PDF export, mirroring what marked.js renders in the browser."""

import pytest
from reportlab.platypus import ListFlowable, Paragraph, Preformatted, Table

from markdown_pdf import markdown_flowables


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


def test_fenced_code_block_becomes_a_shaded_bubble_and_keeps_raw_text() -> None:
    flowables = markdown_flowables("```python\nprint('hi')\n```")
    assert len(flowables) == 1
    bubble = flowables[0]
    # A bare Preformatted flowable silently ignores backColor/border styling
    # (reportlab quirk), so code blocks are wrapped in a shaded Table "bubble"
    # instead — matching the browser's code block appearance.
    assert isinstance(bubble, Table)
    pre = bubble._cellvalues[0][0]  # type: ignore[attr-defined]
    assert isinstance(pre, Preformatted)
    # The code content itself must not be markdown/HTML-escaped.
    assert pre.lines == ["print('hi')"]


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
