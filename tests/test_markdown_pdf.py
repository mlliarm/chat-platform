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
    assert '<font face="Courier" size="9">code</font>' in para.text


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


def test_fenced_code_block_becomes_preformatted_and_keeps_raw_text() -> None:
    flowables = markdown_flowables("```python\nprint('hi')\n```")
    assert len(flowables) == 1
    assert isinstance(flowables[0], Preformatted)
    # Preformatted must not have markdown/HTML-escaped the code content.
    assert flowables[0].lines == ["print('hi')"]


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
    assert kinds == ["Paragraph", "Paragraph", "ListFlowable", "Preformatted"]


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
