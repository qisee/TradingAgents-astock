"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# A-stock market constraints
# ---------------------------------------------------------------------------


class AStockMarketType(str, Enum):
    """A-share market segment, drives daily price limit and minimum lot size."""

    MAIN_SH = "Main-SH"       # 沪市主板 6xx / 9xx (B-share)
    MAIN_SZ = "Main-SZ"       # 深市主板 000 / 001 / 002 (中小板归并)
    STAR = "STAR"             # 科创板 688
    CHINEXT = "ChiNext"       # 创业板 300 / 301
    BEIJING = "Beijing"       # 北交所 8xx / 4xx
    ST = "ST"                 # ST / *ST 风险警示


def infer_market_type(code: str, name: Optional[str] = None) -> AStockMarketType:
    """Infer market segment from 6-digit code (and optional Chinese name).

    Name takes precedence so ST/*ST stocks are flagged regardless of code.
    Code prefix rules:
      688 → STAR (科创板)
      300 / 301 → ChiNext (创业板)
      8 / 4 → Beijing (北交所)
      6 / 9 → Main-SH (沪市主板 / B 股)
      0 / 2 / 3 (otherwise) → Main-SZ (深市主板)
    """
    if name and ("ST" in name.upper() or "*ST" in name.upper()):
        return AStockMarketType.ST
    code = (code or "").strip()
    if code.startswith("688"):
        return AStockMarketType.STAR
    if code.startswith(("300", "301")):
        return AStockMarketType.CHINEXT
    if code.startswith(("8", "4")):
        return AStockMarketType.BEIJING
    if code.startswith(("6", "9")):
        return AStockMarketType.MAIN_SH
    return AStockMarketType.MAIN_SZ


_DAILY_LIMIT_PCT = {
    AStockMarketType.MAIN_SH: 10.0,
    AStockMarketType.MAIN_SZ: 10.0,
    AStockMarketType.STAR: 20.0,
    AStockMarketType.CHINEXT: 20.0,
    AStockMarketType.BEIJING: 30.0,
    AStockMarketType.ST: 5.0,
}


_MIN_LOT = {
    AStockMarketType.MAIN_SH: 100,
    AStockMarketType.MAIN_SZ: 100,
    AStockMarketType.STAR: 200,
    AStockMarketType.CHINEXT: 200,
    AStockMarketType.BEIJING: 100,
    AStockMarketType.ST: 100,
}


def astock_daily_limit_pct(market_type: AStockMarketType) -> float:
    """Daily price limit (% from previous close) for the given segment."""
    return _DAILY_LIMIT_PCT[market_type]


def astock_min_lot(market_type: AStockMarketType) -> int:
    """Minimum tradable share count for a single order."""
    return _MIN_LOT[market_type]


def astock_constraint_summary(market_type: AStockMarketType) -> str:
    """One-line summary for embedding in the Trader's prompt."""
    return (
        f"市场类别: {market_type.value} | "
        f"涨跌停: ±{astock_daily_limit_pct(market_type):.0f}% | "
        f"最小手数: {astock_min_lot(market_type)} 股 | "
        "结算: T+1（当日买入次日方可卖出）"
    )


def _parse_shares_from_text(text: str) -> Optional[int]:
    """Best-effort extraction of an absolute share count from free-text sizing.

    Recognises "1000 shares", "买入 500 股", "建仓 300股". Returns None when
    the sizing is expressed only as a percentage / capital amount / qualitative
    description — in that case lot-size enforcement happens later at execution.

    Note: ``\b`` is not a word boundary after the Chinese character ``股``,
    so we use a non-word-character lookahead / end-of-string instead.
    """
    if not text:
        return None
    m = re.search(
        r"(\d[\d,]*)\s*(?:shares?\b|股)",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.

    A-share constraint guard rails (when ``astock_constraints`` is supplied
    by the orchestration layer):
      - Entry/stop prices must be positive
      - Stop-loss must sit on the correct side of entry given the action
        (BUY: stop < entry; SELL: stop > entry)
      - If ``position_sizing`` mentions an absolute share count, it must be
        a multiple of the segment's minimum lot (100 main board / 200 STAR &
        ChiNext); the validator rejects non-conforming proposals so the
        trader is forced to re-issue a compliant order.
      - T+1 settlement is enforced at the prompt level — the LLM is told
        same-day buy + sell is impossible.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )
    astock_market_type: Optional[AStockMarketType] = Field(
        default=None,
        description=(
            "A-share market segment that drives daily price limit and minimum "
            "lot size. Populated by the trader node from the ticker; the LLM "
            "should pass this through unchanged."
        ),
    )

    @field_validator("entry_price", "stop_loss")
    @classmethod
    def _prices_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("price levels must be positive when supplied")
        return v

    @model_validator(mode="after")
    def _validate_astock_constraints(self) -> "TraderProposal":
        # Stop loss direction must be consistent with the action.
        if self.entry_price is not None and self.stop_loss is not None:
            if self.action == TraderAction.BUY and self.stop_loss >= self.entry_price:
                raise ValueError(
                    "Buy proposal: stop_loss must be below entry_price"
                )
            if self.action == TraderAction.SELL and self.stop_loss <= self.entry_price:
                raise ValueError(
                    "Sell proposal: stop_loss must be above entry_price"
                )

        # Minimum lot size: only enforced when the LLM expressed sizing as a
        # concrete share count *and* a market segment was supplied. Sizing
        # given as "5% of portfolio" or "moderate exposure" passes through;
        # final lot rounding happens at execution.
        if self.astock_market_type and self.position_sizing:
            shares = _parse_shares_from_text(self.position_sizing)
            if shares is not None:
                min_lot = astock_min_lot(self.astock_market_type)
                if shares <= 0 or shares % min_lot != 0:
                    raise ValueError(
                        f"position_sizing share count must be a positive "
                        f"multiple of {min_lot} for {self.astock_market_type.value} "
                        f"(got {shares})"
                    )
        return self


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.astock_market_type is not None:
        parts.extend(["", f"**A股市场类别**: {astock_constraint_summary(proposal.astock_market_type)}"])
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)
