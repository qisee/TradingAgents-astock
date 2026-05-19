"""TradingAgents A股分析 — Streamlit Web UI."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402

from web.components.progress_panel import render_progress  # noqa: E402
from web.components.report_viewer import render_report  # noqa: E402
from web.components.sidebar import render_sidebar  # noqa: E402
from web.history import extract_signal, load_analysis  # noqa: E402
from web.progress import ProgressTracker  # noqa: E402
from web.runner import run_analysis_in_thread  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TradingAgents-Astock A股分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');

    /* Hide Streamlit chrome (menu / footer / decoration / toolbar) */
    #MainMenu, footer,
    div[data-testid="stDecoration"],
    div[data-testid="stToolbar"] { display: none !important; }

    /* Header transparent but kept in DOM so any toggle inside remains
       clickable on Streamlit versions where it lives there. */
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: auto !important;
    }

    /* FORCE sidebar to always be expanded and visible — across every
       Streamlit version 1.29..1.57+, the collapse-expand toggle keeps
       getting renamed/moved (collapsedControl → stSidebarCollapsedControl
       → stSidebarHeader → …), so instead of chasing the testid we
       short-circuit the collapsed state entirely: override the
       transform/margin/width Streamlit uses to slide it off-screen,
       and hide the close button inside the sidebar so the user can't
       collapse it. The sidebar is the only entry point on this page,
       hiding it accidentally is always a bug, never a feature. */
    section[data-testid="stSidebar"] {
        transform: none !important;
        margin-left: 0 !important;
        visibility: visible !important;
        display: flex !important;
        min-width: 244px !important;
        width: 244px !important;
        max-width: 244px !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        transform: none !important;
        margin-left: 0 !important;
        width: 244px !important;
    }
    /* Hide the close (collapse) button inside the sidebar across versions */
    section[data-testid="stSidebar"] button[kind="header"],
    section[data-testid="stSidebar"] button[kind="headerNoPadding"],
    section[data-testid="stSidebar"] button[data-testid*="ollaps"],
    section[data-testid="stSidebar"] button[data-testid*="lose"],
    section[data-testid="stSidebar"] button[aria-label*="lose" i],
    section[data-testid="stSidebar"] button[aria-label*="ollapse" i] {
        display: none !important;
    }
    /* And the floating "expand" button (when somehow shown collapsed) —
       force it visible in case CSS above didn't catch this version. */
    button[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapsedControl"],
    button[data-testid*="SidebarCollapseButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 9999 !important;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif;
    }
    .stApp {
        background: #0a0a0a;
    }
    section[data-testid="stSidebar"] {
        background: #0f0f0f;
        border-right: 1px solid #1a1a1a;
    }
    .stMetric label { color: #888 !important; font-size: 0.8rem !important; }
    .stMetric [data-testid="stMetricValue"] {
        color: #ff5a1f !important;
        font-weight: 700 !important;
    }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #ff5a1f, #ff8c42) !important;
    }
    button[kind="primary"] {
        background: linear-gradient(135deg, #ff5a1f, #ff8c42) !important;
        border: none !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        box-shadow: 0 4px 15px rgba(255,90,31,0.3) !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #e04d15, #ff5a1f) !important;
        box-shadow: 0 6px 20px rgba(255,90,31,0.4) !important;
        transform: translateY(-1px) !important;
    }
    /* Secondary buttons (history items) */
    button[kind="secondary"] {
        background: #161616 !important;
        border: 1px solid #2a2a2a !important;
        color: #ccc !important;
        transition: all 0.2s ease !important;
    }
    button[kind="secondary"]:hover {
        background: #1e1e1e !important;
        border-color: #ff5a1f !important;
        color: #ff5a1f !important;
    }
    .stExpander {
        border: 1px solid #222 !important;
        border-radius: 8px !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #888 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #ff5a1f !important;
        border-bottom-color: #ff5a1f !important;
    }
    div[data-testid="stDownloadButton"] button {
        background: #1a1a2e !important;
        border: 1px solid #ff5a1f !important;
        color: #ff5a1f !important;
    }
    /* Text input styling */
    input[data-testid="stTextInputRootElement"] input,
    .stTextInput input {
        background: #161616 !important;
        border-color: #2a2a2a !important;
        color: #f5f1eb !important;
    }
    .stTextInput input:focus {
        border-color: #ff5a1f !important;
        box-shadow: 0 0 0 1px #ff5a1f !important;
    }
    /* Date input styling */
    .stDateInput input {
        background: #161616 !important;
        border-color: #2a2a2a !important;
        color: #f5f1eb !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Build config ─────────────────────────────────────────────────────────────

def _detect_llm_settings() -> dict:
    """Pick provider + models based on which key is set in .env.

    Priority (highest first):
      1. TRADINGAGENTS_LLM_PROVIDER explicitly set → trust the env override
         (DEFAULT_CONFIG already absorbed it via _apply_env_overrides)
      2. ANTHROPIC_AUTH_TOKEN → Kimi (Anthropic-compat Bearer protocol)
      3. MINIMAX_API_KEY      → MiniMax
      4. DEEPSEEK_API_KEY     → DeepSeek
      5. ANTHROPIC_API_KEY    → Anthropic (X-Api-Key)
      6. ZHIPU_API_KEY        → 智谱 GLM
      7. DASHSCOPE_API_KEY    → 通义千问 (Qwen)
      8. OPENAI_API_KEY       → OpenAI
      9. fall through to DEFAULT_CONFIG's defaults
    """
    import os

    if os.environ.get("TRADINGAGENTS_LLM_PROVIDER"):
        return {}  # already applied by _apply_env_overrides in default_config.py

    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        # Kimi Coding Plan default. Users on Moonshot Platform should
        # override the two env vars below in .env.
        return {
            "llm_provider": "anthropic",
            "deep_think_llm": os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "claude-sonnet-4-6"),
            "quick_think_llm": os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "claude-sonnet-4-6"),
            "backend_url": os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL", "https://api.kimi.com/coding/"),
        }
    if os.environ.get("MINIMAX_API_KEY"):
        return {
            "llm_provider": "minimax",
            "deep_think_llm": "MiniMax-M2.7",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        }
    if os.environ.get("DEEPSEEK_API_KEY"):
        return {
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-chat",
            "quick_think_llm": "deepseek-chat",
        }
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "llm_provider": "anthropic",
            "deep_think_llm": "claude-sonnet-4-6",
            "quick_think_llm": "claude-sonnet-4-6",
        }
    if os.environ.get("ZHIPU_API_KEY"):
        return {
            "llm_provider": "glm",
            "deep_think_llm": "glm-4-plus",
            "quick_think_llm": "glm-4-air",
        }
    if os.environ.get("DASHSCOPE_API_KEY"):
        return {
            "llm_provider": "qwen",
            "deep_think_llm": "qwen-max",
            "quick_think_llm": "qwen-turbo",
        }
    if os.environ.get("OPENAI_API_KEY"):
        return {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
        }
    return {}


def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    # Auto-detect LLM provider from env vars; only overrides keys that
    # the detection actually filled in, so any explicit TRADINGAGENTS_*
    # env override that already landed in DEFAULT_CONFIG is preserved.
    config.update(_detect_llm_settings())
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["output_language"] = "Chinese"
    return config


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    render_sidebar()


# ── Handle "Start Analysis" trigger ──────────────────────────────────────────

start_req = st.session_state.pop("start_analysis", None)
if start_req:
    tracker = ProgressTracker(
        ticker=start_req["ticker"],
        trade_date=start_req["trade_date"],
    )
    st.session_state["tracker"] = tracker
    run_analysis_in_thread(
        ticker=start_req["ticker"],
        trade_date=start_req["trade_date"],
        config=_build_config(),
        tracker=tracker,
    )


# ── Main area state machine ─────────────────────────────────────────────────

tracker: ProgressTracker | None = st.session_state.get("tracker")
viewing_history: str | None = st.session_state.get("viewing_history")

# State 1: Viewing a historical analysis
if viewing_history:
    try:
        state = load_analysis(viewing_history)
        signal = extract_signal(state)
        ticker = Path(viewing_history).parent.parent.name
        trade_date = Path(viewing_history).stem.replace("full_states_log_", "")
        render_report(state, ticker, trade_date, signal)
    except Exception as exc:
        st.error(f"加载失败: {exc}")

# State 2: Analysis running
elif tracker and tracker.is_running:
    render_progress(tracker)
    time.sleep(2)
    st.rerun()

# State 3: Analysis complete
elif tracker and tracker.is_complete:
    render_report(
        tracker.final_state,
        tracker.ticker,
        tracker.trade_date,
        tracker.signal,
        elapsed=tracker.elapsed,
    )

# State 4: Analysis errored
elif tracker and tracker.error:
    st.error(f"分析失败: {tracker.error}")
    if st.button("重试"):
        st.session_state.pop("tracker", None)
        st.rerun()

# State 0: Idle — welcome screen
else:
    st.markdown(
        """
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 60vh;
            text-align: center;
        ">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📈</div>
            <div style="
                font-size: 2.5rem;
                font-weight: 900;
                margin-bottom: 0.5rem;
            ">
                <span style="color: #ff5a1f;">Trading</span><span style="color: #f5f1eb;">Agents</span><span style="color: #f5f1eb;">-</span><span style="color: #ff5a1f;">Astock</span>
            </div>
            <div style="color: #888; font-size: 1.1rem; max-width: 500px; line-height: 1.6;">
                A股多Agent投研分析系统<br>
                7位AI分析师 → 质量门控 → 多空辩论 → 风控评估 → 最终决策
            </div>
            <div style="
                margin-top: 2rem;
                padding: 1rem 2rem;
                border: 1px solid #222;
                border-radius: 12px;
                color: #666;
                font-size: 0.9rem;
            ">
                ← 在左侧输入股票代码，开始分析
            </div>
            <div style="
                margin-top: 2.5rem;
                padding: 0.8rem 1.5rem;
                color: #555;
                font-size: 0.75rem;
                max-width: 500px;
                line-height: 1.6;
                border-top: 1px solid #1a1a1a;
            ">
                ⚠️ 本项目仅供学习研究与技术演示，不构成任何投资建议。<br>
                投资决策请咨询持牌专业机构。作者不对使用本工具产生的任何损失承担责任。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
