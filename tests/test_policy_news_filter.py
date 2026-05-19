"""Regression tests for get_policy_news / _parse_pub_dt / date-window filter.

Three bugs fixed in this round, all pinned here so the next refactor doesn't
silently reintroduce them:

1. NoneType crash: CLS / Eastmoney sometimes return ``{"data": null}``;
   the old ``d.get("data", {}).get("roll_data", [])`` chain blew up because
   ``None.get`` is undefined. Use ``d.get("data") or {}`` instead.

2. Date-window filter: the policy stream never compared publication
   timestamps against ``[curr_date - look_back_days, curr_date]``, so
   querying "2026-04-30, last 30 days" returned same-day 2026-05-19
   news. ``_in_window`` now drops out-of-window items.

3. Unknown-timestamp behaviour: items whose timestamp could not be parsed
   (rare, but happens with bad upstream payloads) are KEPT, not dropped.
   Keyword-relevant news should not be silently lost over a parsing nit.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.dataflows.a_stock import (
    _is_policy_news,
    _parse_pub_dt,
    get_policy_news,
)


@pytest.mark.unit
class TestParsePubDt:
    def test_unix_seconds_int(self):
        # 2026-04-30 12:00:00 UTC -> a specific local datetime; we only
        # care that parsing yields a non-None datetime.
        ts = int(datetime(2026, 4, 30, 12, 0, 0).timestamp())
        result = _parse_pub_dt(ts)
        assert isinstance(result, datetime)
        assert result.year == 2026 and result.month == 4 and result.day == 30

    def test_unix_seconds_string(self):
        ts = str(int(datetime(2026, 4, 30, 12, 0, 0).timestamp()))
        result = _parse_pub_dt(ts)
        assert isinstance(result, datetime)
        assert result.year == 2026

    def test_iso_datetime_string(self):
        result = _parse_pub_dt("2026-04-30 09:30:00")
        assert result == datetime(2026, 4, 30, 9, 30, 0)

    def test_date_only_string(self):
        result = _parse_pub_dt("2026-04-30")
        assert result == datetime(2026, 4, 30)

    def test_unparseable_returns_none(self):
        assert _parse_pub_dt("not a date") is None
        assert _parse_pub_dt("") is None
        assert _parse_pub_dt(None) is None


@pytest.mark.unit
class TestPolicyKeywordFilter:
    def test_government_body_in_title_matches(self):
        assert _is_policy_news("证监会发布新规", "")
        assert _is_policy_news("", "国务院常务会议召开")
        assert _is_policy_news("央行宣布降准", "")

    def test_no_government_body_does_not_match(self):
        assert not _is_policy_news("某公司发布新产品", "市场反响积极")
        assert not _is_policy_news("A 股大涨", "成交额放大")

    def test_substring_match_on_compound_body(self):
        # "国家金融监督管理总局" is in the whitelist; "国家发改委" is too
        assert _is_policy_news("某事件", "国家金融监督管理总局表态")
        assert _is_policy_news("产业政策", "国家发改委发文")


@pytest.mark.unit
class TestGetPolicyNewsResilience:
    def _make_response(self, json_payload):
        r = MagicMock()
        r.json.return_value = json_payload
        return r

    def test_null_data_field_does_not_crash(self):
        """Regression: ``{"data": null}`` used to NoneType-crash the chain."""
        with patch("tradingagents.dataflows.a_stock._requests.get") as mock_get:
            # Both CLS and Eastmoney return null data.
            mock_get.return_value = self._make_response({"data": None})
            result = get_policy_news("2026-04-30", look_back_days=7, limit=10)
        assert "No policy news found" in result

    def test_missing_inner_list_does_not_crash(self):
        """Regression: ``{"data": {"roll_data": null}}`` also handled."""
        with patch("tradingagents.dataflows.a_stock._requests.get") as mock_get:
            mock_get.return_value = self._make_response(
                {"data": {"roll_data": None, "fastNewsList": None}}
            )
            result = get_policy_news("2026-04-30", look_back_days=7, limit=10)
        assert "No policy news found" in result

    def test_out_of_window_items_dropped(self):
        """News from outside [curr_date - look_back, curr_date] must NOT appear."""
        in_window_ts = int(datetime(2026, 4, 25).timestamp())  # inside lookback
        out_of_window_ts = int(datetime(2026, 5, 19).timestamp())  # 19 days AFTER curr_date

        def fake_get(url, **kwargs):
            if "cls.cn" in url:
                return self._make_response({
                    "data": {
                        "roll_data": [
                            {
                                "title": "国务院常务会议召开",
                                "content": "讨论新质生产力",
                                "ctime": in_window_ts,
                            },
                            {
                                "title": "证监会 5 月新规",
                                "content": "应在窗口外",
                                "ctime": out_of_window_ts,
                            },
                        ]
                    }
                })
            # Eastmoney empty
            return self._make_response({"data": {"fastNewsList": []}})

        with patch("tradingagents.dataflows.a_stock._requests.get", side_effect=fake_get):
            result = get_policy_news("2026-04-30", look_back_days=30, limit=10)

        assert "国务院常务会议召开" in result
        assert "证监会 5 月新规" not in result

    def test_unknown_timestamp_kept(self):
        """News with an unparseable ``ctime`` is kept (we don't have evidence
        to drop it). Important to avoid silent data loss."""
        def fake_get(url, **kwargs):
            if "cls.cn" in url:
                return self._make_response({
                    "data": {
                        "roll_data": [
                            {
                                "title": "央行政策新闻",
                                "content": "重要政策信号",
                                "ctime": "garbage-timestamp",
                            },
                        ]
                    }
                })
            return self._make_response({"data": {"fastNewsList": []}})

        with patch("tradingagents.dataflows.a_stock._requests.get", side_effect=fake_get):
            result = get_policy_news("2026-04-30", look_back_days=7, limit=10)
        assert "央行政策新闻" in result
