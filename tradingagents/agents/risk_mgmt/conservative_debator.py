

def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        policy_report = state.get("policy_report", "")
        hot_money_report = state.get("hot_money_report", "")
        lockup_report = state.get("lockup_report", "")

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst evaluating an A-share (China mainland) stock, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. Critically examine high-risk elements in the trader's plan, pointing out where it may expose the firm to undue risk.

A-Share Conservative Framework — emphasize these China-specific downside risks:
- T+1 Settlement Lock: Any position taken today CANNOT be exited until tomorrow. If the stock gaps down at open (e.g. after overnight policy news or global sell-off), losses are locked in with no recourse. This is the single most important structural risk in A-shares.
- Daily Price Limit Trap (涨跌停板): If a stock hits limit-down (main board -10%, STAR/ChiNext -20%), sell orders cannot execute — you are trapped. Multiple consecutive limit-downs can cause catastrophic losses with no ability to exit.
- Lockup Expiry Overhang: Large lockup expiries (限售解禁) create massive potential sell pressure. Even if insiders haven't started selling, the OPTION to sell depresses sentiment and caps upside.
- Policy Reversal Risk: A-shares are a policy market (政策市). What the government gives, it can take away overnight — sector support can turn to sector crackdown with a single State Council directive.
- Hot Money Exit Risk (游资撤退): Hot money moves fast in both directions. Today's limit-up star is tomorrow's limit-down casualty. Retail investors are the last to know when hot money exits.
- Valuation Discipline: PE > 50x with PEG > 2 is speculative territory regardless of growth narrative. The 30x PE digestion framework should be the anchor — if it takes 5+ years to digest, the position is overvalued.
- ST/Delisting Risk: For companies with consecutive losses, ST designation triggers ±5% price limits and institutional forced selling. The post-2020 退市新规 widened delisting criteria (financial fraud, market-cap floor 3 亿, 20-day-below-1元) — what looks like a "cheap value play" can flip to *ST and into delisting within one disclosure cycle.
- 股权质押爆仓 (Pledged-Share Forced Liquidation): If the controlling shareholder has pledged >50% of holdings, a price decline that breaches the warning line (typically 140%) or close-out line (120%) triggers broker-initiated forced selling — a cascade independent of company fundamentals. Always check most recent 质押公告 before assuming downside is bounded by valuation.
- 一字板 Limit-Down 无法成交: A first-day limit-down can open with seller-imbalance so extreme that no trades print all day. Stop-loss orders are not executable in this regime — the only exit is when the limit-down chain breaks, often after a 30-40% cumulative loss.
- 黑天鹅 / 财务造假停牌: A-share suspensions for financial-irregularity investigations (例: 康美/康得新/瑞幸) can lock positions for months with no NAV update. Concentration risk in a single name is structurally worse here than in markets with continuous trading and short-selling.

Here is the trader's decision:

{trader_decision}

Counter the aggressive and neutral analysts. Highlight where their optimism overlooks A-share structural risks. Use these data sources:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest News Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Policy Analysis Report: {policy_report}
Hot Money / Capital Flow Report: {hot_money_report}
Lockup Expiry / Insider Reduction Report: {lockup_report}
Conversation history: {history} Last aggressive argument: {current_aggressive_response} Last neutral argument: {current_neutral_response}. If no responses yet, present your own argument.

Demonstrate why a conservative stance is the safest path, especially given A-share market structure where downside protection mechanisms (stop-loss, same-day exit) are severely limited. Output conversationally without special formatting."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
