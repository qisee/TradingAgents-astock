from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name or Chinese text"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    limit: Annotated[int, "Max articles; 0 = use config default (news_article_limit, TRADINGAGENTS_NEWS_ARTICLE_LIMIT)"] = 0,
) -> str:
    """
    Retrieve news data for a given stock code.
    Uses the configured news_data vendor.
    Args:
        ticker (str): 6-digit A-stock code, e.g. 600379, 300750. Must be the numeric code, not the company name.
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
        limit (int): Maximum number of articles to return. 0 (default) falls back to ``news_article_limit``.
    Returns:
        str: A formatted string containing news data
    """
    return route_to_vendor("get_news", ticker, start_date, end_date, limit)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Lookback days; 0 = use config default (global_news_lookback_days)"] = 0,
    limit: Annotated[int, "Max articles; 0 = use config default (global_news_article_limit)"] = 0,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Days to look back. 0 (default) falls back to ``global_news_lookback_days``.
        limit (int): Maximum articles. 0 (default) falls back to ``global_news_article_limit``.
    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_policy_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Lookback days; 0 = use config default"] = 0,
    limit: Annotated[int, "Max articles; 0 = use config default"] = 0,
) -> str:
    """
    Retrieve first-hand A-share policy news, filtered from the CLS / Eastmoney
    wires by government-body keywords (国务院 / 证监会 / 央行 / 发改委 /
    工信部 / 国资委 / 商务部 / 财政部 / 外管局 / 网信办 ...). Use this when
    you want policy-only context; for broader macro news use `get_global_news`.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Days to look back. 0 (default) falls back to ``global_news_lookback_days``.
        limit (int): Maximum articles. 0 (default) falls back to ``global_news_article_limit``.
    Returns:
        str: Markdown-formatted policy news stream
    """
    return route_to_vendor("get_policy_news", curr_date, look_back_days, limit)


@tool
def get_insider_transactions(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): 6-digit A-stock code, e.g. 600379
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker)
