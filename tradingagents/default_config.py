import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")


# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":          "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":        "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":       "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL":       "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":       "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":     "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":       "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":    "checkpoint_enabled",
    "TRADINGAGENTS_GOOGLE_THINKING_LEVEL": "google_thinking_level",
    "TRADINGAGENTS_OPENAI_REASONING":     "openai_reasoning_effort",
    "TRADINGAGENTS_ANTHROPIC_EFFORT":      "anthropic_effort",
    "TRADINGAGENTS_MEMORY_LOG_MAX_ENTRIES": "memory_log_max_entries",
    "TRADINGAGENTS_BENCHMARK_TICKER":       "benchmark_ticker",
    "TRADINGAGENTS_ANALYST_CONCURRENCY":    "analyst_concurrency_limit",
    "TRADINGAGENTS_NEWS_ARTICLE_LIMIT":     "news_article_limit",
    "TRADINGAGENTS_GLOBAL_NEWS_LIMIT":      "global_news_article_limit",
    "TRADINGAGENTS_GLOBAL_NEWS_LOOKBACK":   "global_news_lookback_days",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        existing = config.get(key)
        # Memory-log max entries defaults to None; coerce to int when set.
        if existing is None and key == "memory_log_max_entries":
            existing = 0
        config[key] = _coerce(raw, existing)
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "Chinese",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "a_stock",        # Options: a_stock, alpha_vantage, yfinance
        "technical_indicators": "a_stock",   # Options: a_stock, alpha_vantage, yfinance
        "fundamental_data": "a_stock",       # Options: a_stock, alpha_vantage, yfinance
        "news_data": "a_stock",              # Options: a_stock, alpha_vantage, yfinance
        "signal_data": "a_stock",            # A-stock only: topic attribution, capital flow, consensus
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` overrides ``benchmark_map`` for all tickers when set;
    # leave it None to auto-pick from ``benchmark_map`` by exchange / board.
    # The A-share fork's default benchmark is CSI 300 (沪深 300), but the map
    # keeps board-specific alternatives so a STAR-board strategy can be
    # benchmarked against 科创 50 instead, and Hong Kong tickers (via Stock
    # Connect) fall back to HSI without manual config.
    "benchmark_ticker": None,
    "benchmark_map": {
        # Code-prefix → benchmark index (A-stock vendor format, 6-digit)
        "688": "000688",   # 科创板 → 科创 50
        "300": "399006",   # 创业板 → 创业板指
        "301": "399006",
        "8":   "899050",   # 北交所 → 北证 50
        "4":   "899050",
        # Default for sh main board (6xx) / sz main board (000/001/002/003)
        "*":   "000300",   # 沪深 300
        # Suffix support for cross-market tickers (legacy yfinance interop)
        ".HK": "^HSI",     # Hong Kong (Stock Connect) → 恒生指数
        ".SS": "000300",   # 上交所 → 沪深 300
        ".SZ": "000300",   # 深交所 → 沪深 300
    },
    # News fetching limits — used by a_stock get_news / get_global_news. Bump
    # for longer-lookback strategies or to broaden macro coverage; cut to
    # save tokens in agent prompts.
    "news_article_limit": 20,             # max articles per ticker
    "global_news_article_limit": 10,      # max articles for macro / global wire
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Tuned to
    # A-share macro drivers (policy / FX / Sino-US trade / commodities).
    "global_news_queries": [
        "央行降准降息MLF LPR 货币政策",
        "证监会 IPO 再融资 减持新规",
        "国务院 产业政策 新质生产力",
        "中美贸易 出口管制 关税",
        "外管局 人民币汇率 跨境资本",
        "国资委 央企改革 并购重组",
    ],
    # Analyst concurrency: when >1, independent analysts (market / social /
    # news / fundamentals / policy / hot_money / lockup) run in parallel
    # through LangGraph's `Send` mechanism instead of sequential chaining.
    # Default 1 preserves the legacy single-threaded behaviour.
    "analyst_concurrency_limit": 1,
})
