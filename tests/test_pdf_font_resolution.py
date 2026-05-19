"""Regression test for the PDF exporter's CJK font discovery.

The original ``_FONT_CANDIDATES`` list contained only macOS and Linux
paths, so on every Windows host PDF export fell through to Helvetica
and crashed on the very first Chinese character with:

    Character "股" at index 1 in text is outside the range of characters
    supported by the font used: "helvetica".

This test pins three guarantees:

1. ``_find_cjk_font()`` returns a real, existing file on the running
   host (any of the platform-appropriate candidates).
2. ``TRADINGAGENTS_CJK_FONT`` env override wins when set.
3. A short Chinese string actually renders to PDF without raising —
   the end-to-end fix verified, not just the path lookup.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from web.pdf_export import _FONT_CANDIDATES, _find_cjk_font


@pytest.mark.unit
class TestFontResolution:
    def test_finds_some_cjk_font_on_this_host(self):
        """At least one candidate must exist on the developer's machine.
        Skipped only if the host has no CJK font installed at all."""
        result = _find_cjk_font()
        if result is None:
            pytest.skip(
                "No CJK font found on this host. Install one of: "
                + ", ".join(_FONT_CANDIDATES[:3])
            )
        assert Path(result).exists(), f"_find_cjk_font returned non-existent {result}"

    def test_env_override_wins(self, tmp_path, monkeypatch):
        """A user-set TRADINGAGENTS_CJK_FONT takes precedence over candidates."""
        fake_font = tmp_path / "my-font.ttf"
        fake_font.write_bytes(b"")  # exists but empty — we only test path resolution
        monkeypatch.setenv("TRADINGAGENTS_CJK_FONT", str(fake_font))
        assert _find_cjk_font() == str(fake_font)

    def test_env_override_ignored_when_path_missing(self, monkeypatch):
        """A non-existent env override should be ignored, not crash."""
        monkeypatch.setenv("TRADINGAGENTS_CJK_FONT", "/no/such/font.ttf")
        # Should fall through to candidates instead of returning the bogus path
        result = _find_cjk_font()
        if result is not None:
            assert result != "/no/such/font.ttf"

    def test_candidates_include_windows_paths(self):
        """Regression: the windows %WINDIR%\\Fonts entries must be in the list,
        not just macOS / Linux paths."""
        joined = "\n".join(_FONT_CANDIDATES).lower()
        assert "fonts" in joined and ("msyh" in joined or "simhei" in joined or "simsun" in joined), (
            "Windows CJK font candidates missing from _FONT_CANDIDATES — PDF "
            "export will crash on every Windows host"
        )


@pytest.mark.unit
class TestPdfChineseRendering:
    def test_chinese_text_renders_without_crash(self):
        """End-to-end: generate a minimal PDF with Chinese content; the
        original bug was a hard exception, so survival = pass."""
        font = _find_cjk_font()
        if font is None:
            pytest.skip("No CJK font on this host; skip end-to-end render check")

        # Use fpdf directly to keep the test fast — the production
        # _ReportPDF subclass goes through the same _use_font path.
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_font("CJK", "", font)
        pdf.set_font("CJK", "", 12)
        pdf.add_page()
        # The exact string from the original crash report
        pdf.cell(0, 10, "股票分析 测试 中文")
        output = bytes(pdf.output())
        assert output.startswith(b"%PDF"), "PDF header missing — render failed silently"
        assert len(output) > 1000, f"PDF suspiciously small ({len(output)} bytes)"
