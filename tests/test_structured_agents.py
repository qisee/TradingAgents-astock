"""Tests for structured-output agents (Trader and Research Manager).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader and Research Manager so all three
decision-making agents share the same shape.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    AStockMarketType,
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    astock_daily_limit_pct,
    astock_min_lot,
    infer_market_type,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Action**: Hold" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        # The trailing FINAL TRANSACTION PROPOSAL line is preserved for the
        # analyst stop-signal text and any external code that greps for it.
        assert "FINAL TRANSACTION PROPOSAL: **HOLD**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**Action**: Buy" in md
        assert "**Entry Price**: 189.5" in md
        assert "**Stop Loss**: 178.0" in md
        assert "**Position Sizing**: 6% of portfolio" in md
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        assert "Entry Price" not in md
        assert "Stop Loss" not in md
        assert "Position Sizing" not in md
        assert "FINAL TRANSACTION PROPOSAL: **SELL**" in md


@pytest.mark.unit
class TestAStockMarketType:
    """Code-prefix → market segment classification + derived constraint helpers."""

    def test_infer_main_sh(self):
        assert infer_market_type("600519") == AStockMarketType.MAIN_SH
        assert infer_market_type("601318") == AStockMarketType.MAIN_SH

    def test_infer_main_sz(self):
        assert infer_market_type("000001") == AStockMarketType.MAIN_SZ
        assert infer_market_type("002594") == AStockMarketType.MAIN_SZ

    def test_infer_star_board(self):
        assert infer_market_type("688017") == AStockMarketType.STAR
        assert infer_market_type("688981") == AStockMarketType.STAR

    def test_infer_chinext(self):
        assert infer_market_type("300750") == AStockMarketType.CHINEXT
        assert infer_market_type("301038") == AStockMarketType.CHINEXT

    def test_infer_beijing_exchange(self):
        assert infer_market_type("832000") == AStockMarketType.BEIJING
        assert infer_market_type("430047") == AStockMarketType.BEIJING

    def test_st_name_wins_over_code(self):
        # ST flag in the name overrides any code-prefix bucket — ST gets ±5%.
        assert infer_market_type("600519", name="ST 茅台") == AStockMarketType.ST
        assert infer_market_type("688017", name="*ST 新材") == AStockMarketType.ST

    def test_daily_limits(self):
        assert astock_daily_limit_pct(AStockMarketType.MAIN_SH) == 10.0
        assert astock_daily_limit_pct(AStockMarketType.STAR) == 20.0
        assert astock_daily_limit_pct(AStockMarketType.CHINEXT) == 20.0
        assert astock_daily_limit_pct(AStockMarketType.ST) == 5.0
        assert astock_daily_limit_pct(AStockMarketType.BEIJING) == 30.0

    def test_min_lot(self):
        assert astock_min_lot(AStockMarketType.MAIN_SH) == 100
        assert astock_min_lot(AStockMarketType.STAR) == 200
        assert astock_min_lot(AStockMarketType.CHINEXT) == 200
        assert astock_min_lot(AStockMarketType.BEIJING) == 100


@pytest.mark.unit
class TestTraderProposalGuardRails:
    """Schema-level validators must reject invalid A-share proposals."""

    def test_positive_prices_required(self):
        with pytest.raises(ValueError, match="must be positive"):
            TraderProposal(action=TraderAction.BUY, reasoning="r", entry_price=-1.0)
        with pytest.raises(ValueError, match="must be positive"):
            TraderProposal(action=TraderAction.SELL, reasoning="r", stop_loss=0)

    def test_buy_requires_stop_below_entry(self):
        with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
            TraderProposal(
                action=TraderAction.BUY,
                reasoning="r",
                entry_price=100.0,
                stop_loss=110.0,  # wrong side for a long
            )

    def test_sell_requires_stop_above_entry(self):
        with pytest.raises(ValueError, match="stop_loss must be above entry_price"):
            TraderProposal(
                action=TraderAction.SELL,
                reasoning="r",
                entry_price=100.0,
                stop_loss=90.0,  # wrong side for a short
            )

    def test_min_lot_violation_rejected_for_star(self):
        # STAR board minimum lot is 200; "150 shares" must fail.
        with pytest.raises(ValueError, match="multiple of 200"):
            TraderProposal(
                action=TraderAction.BUY,
                reasoning="r",
                astock_market_type=AStockMarketType.STAR,
                position_sizing="买入 150 股建仓",
            )

    def test_min_lot_violation_rejected_for_main_board(self):
        # Main-board minimum lot is 100; "50 shares" must fail.
        with pytest.raises(ValueError, match="multiple of 100"):
            TraderProposal(
                action=TraderAction.BUY,
                reasoning="r",
                astock_market_type=AStockMarketType.MAIN_SH,
                position_sizing="买入 50 股",
            )

    def test_percent_sizing_passes_through(self):
        # Sizing as "5% of portfolio" should pass — concrete share count
        # gets rounded at execution time, not at the schema layer.
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="r",
            astock_market_type=AStockMarketType.STAR,
            position_sizing="5% of portfolio",
        )
        assert p.position_sizing == "5% of portfolio"

    def test_valid_lot_count_accepted(self):
        # Main-board 600 = 6 lots of 100.
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="r",
            entry_price=10.0,
            stop_loss=9.0,
            astock_market_type=AStockMarketType.MAIN_SH,
            position_sizing="买入 600 股",
        )
        assert p.astock_market_type == AStockMarketType.MAIN_SH

    def test_no_market_type_skips_lot_check(self):
        # Without astock_market_type the lot validator should not fire.
        TraderProposal(
            action=TraderAction.BUY,
            reasoning="r",
            position_sizing="买入 50 股",
        )


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**Recommendation**: Overweight" in md
        assert "**Rationale**: Bull case carried" in md
        assert "**Strategic Actions**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**Recommendation**: {rating.value}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Action**: Buy" in plan
        assert "**Entry Price**: 189.5" in plan
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The investment plan is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "FINAL TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Recommendation**: Overweight" in ip
        assert "**Rationale**: Bull case" in ip
        assert "**Strategic Actions**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response
