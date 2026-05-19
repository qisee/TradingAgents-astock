"""Regression test for the 同花顺 consensus EPS scraper.

In pandas >=2.0 ``pd.read_html`` no longer accepts a bare HTML string
positional arg — it tries to ``open()`` it as a filesystem path and
raises ``[Errno 2] No such file or directory: <!DOCTYPE HTML>...``.
The fork's ``_ths_eps_forecast`` was hitting exactly this error on
every analyst run, silently dropping the consensus-EPS data even
though the upstream HTML was returned correctly.

The fix wraps the response text in ``StringIO`` before handing it to
pandas. This test pins that behaviour so the next pandas bump or
refactor doesn't silently regress it.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.a_stock import _ths_eps_forecast


_FAKE_THS_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="gbk"><title>盈利预测</title></head>
<body>
  <table>
    <caption>汇总--预测年报每股收益</caption>
    <thead>
      <tr><th>年度</th><th>预测机构数</th><th>最小值</th><th>均值</th><th>最大值</th></tr>
    </thead>
    <tbody>
      <tr><td>2026</td><td>12</td><td>0.94</td><td>1.05</td><td>1.15</td></tr>
      <tr><td>2027</td><td>11</td><td>1.38</td><td>1.55</td><td>1.76</td></tr>
    </tbody>
  </table>
  <table>
    <thead><tr><th>无关表格</th></tr></thead>
    <tbody><tr><td>x</td></tr></tbody>
  </table>
</body>
</html>
"""


@pytest.mark.unit
class TestThsEpsForecast:
    def test_does_not_crash_on_html_string(self):
        """Regression: pandas 2.x must NOT try to open() the HTML body as a file."""
        with patch("tradingagents.dataflows.a_stock._requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = _FAKE_THS_HTML
            mock_get.return_value = mock_resp

            df = _ths_eps_forecast("688017")

        # Must return a non-empty DataFrame (the EPS forecast table)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_picks_eps_summary_table(self):
        """The selector prefers the table that mentions 每股收益 / 均值."""
        with patch("tradingagents.dataflows.a_stock._requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = _FAKE_THS_HTML
            mock_get.return_value = mock_resp
            df = _ths_eps_forecast("688017")

        cols = [str(c) for c in df.columns]
        assert any("均值" in c for c in cols), f"expected 均值 column, got {cols}"
        # Should contain the 2026 row from the EPS summary table
        first_col = df.iloc[:, 0].astype(str).tolist()
        assert "2026" in first_col

    def test_empty_html_returns_empty_dataframe(self):
        """When the page has no parseable tables, return an empty DataFrame
        instead of letting the ValueError leak (so downstream gets a clean
        ``df.empty`` signal)."""
        with patch("tradingagents.dataflows.a_stock._requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = "<html><body>no tables here</body></html>"
            mock_get.return_value = mock_resp
            df = _ths_eps_forecast("688017")

        assert isinstance(df, pd.DataFrame)
        assert df.empty
