"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import (
    TraderProposal,
    astock_constraint_summary,
    astock_daily_limit_pct,
    astock_min_lot,
    infer_market_type,
    render_trader_proposal,
)
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.a_stock import _normalize_ticker


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]

        # Derive A-stock market segment from the ticker so the schema-level
        # guard rails (lot size, ST flag) and the prompt-level constraints
        # (price limit %) use concrete values for this specific instrument
        # rather than the generic 5%/10%/20% laundry list.
        try:
            code = _normalize_ticker(company_name)
            market_type = infer_market_type(code, name=company_name)
        except Exception:
            market_type = None

        # Collect A-stock specific analyst reports
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        # Build optional A-stock context block
        astock_context_parts = []
        if policy_report:
            astock_context_parts.append(f"Policy Analysis Report:\n{policy_report}")
        if hot_money_report:
            astock_context_parts.append(f"Hot Money / Capital Flow Report:\n{hot_money_report}")
        if lockup_report:
            astock_context_parts.append(f"Lockup Expiry / Insider Reduction Report:\n{lockup_report}")
        astock_context = "\n\n".join(astock_context_parts)

        if market_type is not None:
            limit_pct = astock_daily_limit_pct(market_type)
            min_lot = astock_min_lot(market_type)
            constraint_line = astock_constraint_summary(market_type)
            system_constraints = (
                f"This instrument's A-share segment is **{market_type.value}**. "
                f"Apply these constraints — they are hard rules, not suggestions:\n"
                f"- Daily price limit: ±{limit_pct:.0f}% from previous close. Entry "
                f"price and stop-loss MUST sit inside this band.\n"
                f"- Minimum lot: {min_lot} shares. If you express sizing as an "
                f"absolute share count, it must be a multiple of {min_lot}; "
                f"otherwise the schema validator will reject your proposal "
                f"and you will be re-prompted.\n"
                f"- T+1 settlement: shares bought today cannot be sold until "
                f"the next trading day. Same-day round trips are impossible.\n"
                f"- Trading hours: 09:30-11:30, 13:00-15:00 Beijing time.\n"
                f"- Populate the `astock_market_type` field with "
                f"\"{market_type.value}\" — pass it through unchanged.\n"
            )
        else:
            constraint_line = "市场类别: 未识别（按沪市主板默认: ±10% 涨跌停, 100 股最小手）"
            system_constraints = (
                "A-share constraints (use as a baseline since the market "
                "segment could not be auto-detected):\n"
                "- T+1 settlement: shares bought today cannot be sold until the next trading day\n"
                "- Daily price limits: main board ±10%, STAR/ChiNext ±20%, ST stocks ±5%\n"
                "- Minimum lot: 100 shares (main board) or 200 shares (STAR/ChiNext)\n"
                "- Trading hours: 09:30-11:30, 13:00-15:00 Beijing time\n"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent specialising in A-share (China mainland) stocks. "
                    "Translate the Research Manager's investment plan into a concrete, executable "
                    "transaction proposal.\n\n"
                    + system_constraints
                    + "\nAnchor your reasoning in the analysts' reports and the research plan. "
                    "Be specific about entry price, stop loss, and position sizing."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts (including market, "
                    f"sentiment, news, fundamentals, policy, capital flow, and lockup/reduction "
                    f"specialists), here is an investment plan for {company_name}.\n\n"
                    f"{instrument_context}\n\n"
                    f"{constraint_line}\n\n"
                    f"Proposed Investment Plan:\n{investment_plan}\n\n"
                    + (f"Additional A-Stock Analyst Context:\n{astock_context}\n\n" if astock_context else "")
                    + "Leverage these insights to craft a precise transaction proposal."
                    + get_language_instruction()
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
