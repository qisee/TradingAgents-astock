"""End-to-end test: run TradingAgents pipeline on A-stock 688017 via Moonshot Platform (kimi-k2.6).

Why Moonshot Platform and not Kimi For Coding:
- ``api.kimi.com/coding/`` only accepts whitelisted Coding-Agent clients
  (Kimi CLI / Claude Code / Roo Code / Kilo Code …). Generic third-party
  integrations get HTTP 403 ``access_terminated_error``.
- ``api.moonshot.cn/v1`` is the OpenAI-compatible Chat Completions
  endpoint; works with any OpenAI SDK, token-metered (sk-xxx key).
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

load_dotenv()

config = DEFAULT_CONFIG.copy()

# --- LLM: kimi-k2.6 via Moonshot Platform (OpenAI-compatible) ---
config["llm_provider"] = "moonshot"
config["deep_think_llm"] = "kimi-k2.6"
config["quick_think_llm"] = "kimi-k2.6"
# backend_url not set → openai_client picks Moonshot default
# (https://api.moonshot.cn/v1). API key from MOONSHOT_API_KEY in .env.

# --- Data: A-stock vendor (mootdx + tencent + eastmoney + sina) ---
config["data_vendors"] = {
    "core_stock_apis": "a_stock",
    "technical_indicators": "a_stock",
    "fundamental_data": "a_stock",
    "news_data": "a_stock",
}

# --- Debate settings: minimal for first test ---
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["output_language"] = "Chinese"

print("=" * 60)
print("TradingAgents-Astock E2E Test")
print("Ticker: 688017")
print("Trade date: 2026-04-30")
print("LLM: kimi-k2.6 via Moonshot Platform (OpenAI-compatible)")
print("Data: a_stock (mootdx + tencent + eastmoney + sina)")
print("=" * 60)

ta = TradingAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("688017", "2026-04-30")
print("\n" + "=" * 60)
print("FINAL DECISION:")
print("=" * 60)
print(decision)
