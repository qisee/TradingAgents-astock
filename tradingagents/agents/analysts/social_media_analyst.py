"""Sentiment analyst — A-share retail sentiment via pre-fetched data blocks.

Adapted from the upstream sentiment_analyst pattern (issue TauricResearch
/TradingAgents#557): previously the agent had only `get_news` and was
prompt-pressured into fabricating Reddit/StockTwits content for A-share
tickers — there is no Reddit/StockTwits coverage for 600519 / 688017 / etc.

This version pre-fetches three A-share-native data blocks before the LLM
is invoked and injects them directly into the prompt:

  1. Stock-specific news        — 东方财富 (个股新闻流)
  2. Hot-stock / 题材 board     — 同花顺热股榜（连板 / 题材归因 / 板块归属）
  3. Capital flow snapshot      — 东方财富 push2 (主力 / 散户分单资金流)

The agent produces the sentiment report in a single LLM invocation; no
tool-calling loop, no chance for the model to hallucinate sources that
don't exist for A-shares.

A backwards-compatible alias ``create_social_media_analyst`` is preserved
so anything that still imports the old name keeps working.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


_UNAVAILABLE = "<unavailable: source returned no data>"


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def _safe_fetch(label: str, fn, *args, **kwargs) -> str:
    """Run a fetch fn, degrade gracefully to a placeholder string on any error.

    Sentiment analysis must always see *something* — either real data or an
    explicit placeholder — so the LLM can correctly flag data quality.
    """
    try:
        out = fn(*args, **kwargs)
        if not out or (isinstance(out, str) and not out.strip()):
            return f"{_UNAVAILABLE} ({label})"
        return out if isinstance(out, str) else str(out)
    except Exception as e:
        return f"{_UNAVAILABLE} ({label}: {type(e).__name__}: {e})"


def create_sentiment_analyst(llm):
    """Pre-fetch A-share sentiment sources, then make a single LLM call.

    Drops tool-calling: the data is in the prompt from turn 0. This makes
    the agent deterministic w.r.t. data sources and prevents the well-known
    failure mode where an LLM, asked about social-media sentiment for a
    Chinese A-share, invents Reddit threads that never existed.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)

        # Import here so test collection / import of this module does not
        # eagerly pull in mootdx / requests / the whole a_stock chain.
        from tradingagents.dataflows.a_stock import (
            get_news as a_get_news,
            get_hot_stocks as a_get_hot_stocks,
            get_fund_flow as a_get_fund_flow,
        )

        news_block = _safe_fetch(
            "stock news", a_get_news, ticker, start_date, end_date
        )
        hot_block = _safe_fetch(
            "hot-stock board", a_get_hot_stocks, end_date
        )
        flow_block = _safe_fetch(
            "fund flow", a_get_fund_flow, ticker, end_date, include_history=True
        )

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            hot_block=hot_block,
            flow_block=flow_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # No bind_tools — single-call architecture. The data is already in
        # the prompt; the LLM's only job is synthesis.
        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    hot_block: str,
    flow_block: str,
) -> str:
    """Assemble the system message with the three pre-fetched A-share blocks."""
    return f"""你是一位专注于 A 股市场的散户情绪分析师。任务：基于以下三块已经为你抓好的数据，为 {ticker} 输出 {start_date} 至 {end_date} 的情绪研报。**不要调用任何工具**，所有数据已在 prompt 中。

## 数据块（已预取，A 股原生数据源）

### 个股新闻流 — 东方财富 (过去 7 天)
机构与媒体框架，事件型信号，相对慢速。

<start_of_news>
{news_block}
<end_of_news>

### 热股榜 / 题材归因 — 同花顺
当日强势股清单 + 人工题材归因。判断目标公司是否：
- 在热股榜上（暗示散户关注度爆发）
- 与某些主流题材绑定（共振板块情绪）
- 被同花顺标记为「连板龙头」/「补涨」/「跟风」（情绪定位决定后续路径）

<start_of_hot_stocks>
{hot_block}
<end_of_hot_stocks>

### 主力 / 散户资金分单流向 — 东方财富 push2
A 股 push2 的资金流细分（主力 / 大单 / 中单 / 小单）是观测散户与机构博弈的最直接指标：
- 主力净流入 + 小单净流出 → 机构吸筹，散户割肉（看涨信号）
- 主力净流出 + 小单净流入 → 机构出货，散户接盘（顶部信号）
- 全部同向 → 一致性预期，警惕反转

<start_of_fund_flow>
{flow_block}
<end_of_fund_flow>

## 分析框架

1. **散户情绪权重**：A 股散户占成交超过 60%，情绪驱动远大于成熟市场。新闻情绪 + 热股榜定位 + 资金流向，三者一致 = 高置信度信号，三者背离 = 警惕拐点。

2. **反向指标**：当散户情绪一致性极高（题材榜 + 新闻 + 小单流入全向同方向），往往是阶段顶部或底部。情绪和价格背离时，资金流给出真实方向。

3. **题材归属**：如果热股榜把目标股归到「连板龙头」，短期情绪强但脆弱；归到「跟风」表明情绪正在扩散；不在榜单上则散户关注度不足。

4. **资金流时间序列**：分析 20 日资金流，识别主力是否长期累积建仓 / 出货，比单日数据可靠得多。

5. **数据缺失要诚实**：若某个数据块返回 `<unavailable: ...>`，明确在报告里标注数据缺失，情绪判断的置信度相应下调。

## 输出格式

按顺序产出：

1. **总体情绪方向** — 极度悲观 / 悲观 / 中性 / 乐观 / 极度乐观 — 含数据完整性说明
2. **三个数据块的分项解读** — 新闻 / 热股榜 / 资金流分别给出什么信号
3. **关键背离与共振** — 三块数据之间是一致还是冲突？冲突更有价值
4. **触发因素与潜在拐点** — 哪些事件 / 资金流变化可能改变当前情绪
5. **Markdown 表格** — 关键情绪信号、方向、来源、佐证数据

📋 必采清单 — 以下数据点必须出现在报告中，无法获取时显式标注 [数据缺失: xxx]：
1. 新闻数量和正面 / 负面 / 中性比例
2. 是否登榜同花顺热股 + 题材定位
3. 5 日主力净流入金额
4. 5 日小单净流入金额
5. 情绪评分（极度悲观 / 悲观 / 中性 / 乐观 / 极度乐观）
6. 情绪趋势（升温 / 降温 / 平稳）

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work. Will be removed in a future minor version.
    """
    warnings.warn(
        "create_social_media_analyst is deprecated; use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
