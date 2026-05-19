# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述
基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（65K Stars）的 A 股深度特化 fork。多 Agent 投研框架，7 个 Analyst 角色通过 Bull/Bear 辩论 + 三方风险辩论生成投资报告。

- **仓库**: https://github.com/simonlin1212/TradingAgents-astock
- **协议**: Apache 2.0
- **Python**: >=3.10
- **当前版本**: 0.2.5

## 常用命令

```bash
# 安装（开发模式）— 整个 pip 解析可能爬树太深 (resolution-too-deep)，
# 因为 langchain-google-genai 要 httpx>=0.28 而 mootdx 锁死 httpx==0.25。
# 推荐两步：
pip install mootdx --no-deps
pip install -e .

# mootdx --no-deps 会漏掉它的运行时依赖。如果跑分析时看到大量
# "mootdx K-line failed: No module named 'tdxpy'" 警告并 fallback 到
# Sina HTTP（功能不挂但慢 2-3 倍），补装：
pip install tdxpy prettytable py-mini-racer

# 跑全部测试
python -m pytest tests/ -v

# 跑单个测试文件 / 单个用例
python -m pytest tests/test_safe_ticker_component.py -v
python -m pytest tests/test_safe_ticker_component.py::test_resolve_chinese_name -v

# 按 marker 过滤（pyproject 已注册 unit/integration/smoke）
python -m pytest -m unit
python -m pytest -m "not integration"

# CLI 入口（交互式）
tradingagents

# Web UI（Streamlit）
tradingagents-web
# 或：streamlit run web/app.py

# 一次性脚本式跑分析（示例）
python main.py
# 或编辑 test_astock.py 后：python test_astock.py
```

无 lint/format 工具配置在 pyproject.toml 中；改代码后只跑 pytest 即可。

## 配置链路

- `tradingagents/default_config.py` 是默认值，**默认 `llm_provider="openai"` + `deep_think_llm="gpt-5.4"` 几乎不可用**，用户实际靠 `.env` + 调用方传入的 `config` 字典覆盖（见 `main.py` / README）。
- `.env` 里放 provider API key（`MINIMAX_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` 等），`TradingAgentsGraph(config=...)` 里指定 `llm_provider` + 模型名。
- **`TRADINGAGENTS_*` 环境变量覆盖表**（`default_config.py::_ENV_OVERRIDES`）：`TRADINGAGENTS_LLM_PROVIDER` / `..._DEEP_THINK_LLM` / `..._QUICK_THINK_LLM` / `..._LLM_BACKEND_URL` / `..._OUTPUT_LANGUAGE` / `..._MAX_DEBATE_ROUNDS` / `..._MAX_RISK_ROUNDS` / `..._CHECKPOINT_ENABLED` / `..._BENCHMARK_TICKER` / `..._ANALYST_CONCURRENCY` / `..._NEWS_ARTICLE_LIMIT` / `..._GLOBAL_NEWS_LIMIT` / `..._GLOBAL_NEWS_LOOKBACK`。加新覆盖只需在表里加一行，类型按现有默认值自动 coerce。
- LLM 客户端工厂：`tradingagents/llm_clients/factory.py`。OpenAI 兼容协议白名单：`openai/xai/deepseek/qwen/glm/ollama/openrouter/minimax`，其余 anthropic/google/azure 各有独立 client。
- 数据 vendor 路由：`default_config["data_vendors"]`（category 级）+ `tool_vendors`（tool 级覆盖），在 `dataflows/interface.py` 里分发到 `a_stock` / `yfinance` / `alpha_vantage` 各自的实现。**A 股场景下应全部走 `a_stock`**（默认值已正确）。
- 新闻参数：`news_article_limit` / `global_news_article_limit` / `global_news_lookback_days` / `global_news_queries`。tool wrapper 默认 `limit=0`，底层 vendor 看到 0 时读取 config 默认。
- Alpha 基准：`benchmark_ticker`（显式覆盖）或 `benchmark_map`（按代码前缀自动分发 → 688 走科创 50、300 走创业板指、8/4 走北证 50、其它走沪深 300）。reflection 层据此动态选择基准，不再硬编码 CSI 300。

## 架构

### 12 阶段 Pipeline（LangGraph 拓扑）
入口：`tradingagents/graph/trading_graph.py::TradingAgentsGraph`
拓扑：`tradingagents/graph/setup.py::GraphSetup.setup_graph()`

```
7 Analyst（市场/情绪/新闻/基本面/政策/游资/解禁）
  ↓ 每个 Analyst 带 ToolNode 循环抓数据
Quality Gate（agents/quality_gate.py 兜底质检）
  ↓
Bull Researcher ↔ Bear Researcher（max_debate_rounds 轮）
  ↓
Research Manager（deep_think_llm 综合研判 → 投资计划）
  ↓
Trader（套 A 股约束：T+1/涨跌停/手数/ST）
  ↓
Aggressive ↔ Conservative ↔ Neutral 三方风险辩论（max_risk_discuss_rounds 轮）
  ↓
Portfolio Manager（deep_think_llm 终判 → Buy/Hold/Sell + 仓位）
```

### 双 LLM 设计
- `quick_think_llm`：所有 Analyst / Researcher / Trader / Risk Debater
- `deep_think_llm`：Research Manager + Portfolio Manager（综合全局决策）
- 输出语言由 `output_language` 控制（默认中文），**内部辩论始终走英文**以保推理质量。

### 数据层（v0.2.5 全部直连 HTTP，零第三方数据库依赖）
| 来源 | 协议 | 数据 |
|------|------|------|
| mootdx | TCP 7709 | OHLCV K线、财务快照、F10 文本 |
| 腾讯财经 | HTTP (qt.gtimg.cn) | PE/PB/市值/换手率 |
| 东方财富 datacenter | HTTP (datacenter-web) | 龙虎榜、限售解禁、板块行情 |
| 东方财富 push2 | HTTP (push2.eastmoney) | 实时行情、个股信息、板块列表 |
| 东方财富 np-weblist | HTTP | 滚动新闻 |
| 新浪财经 | HTTP (money.finance.sina) | K线历史、财报三表 |
| 同花顺 10jqka | HTTP | EPS 一致预期、热股题材 |
| 财联社 cls.cn | HTTP | 全球财经快讯 |
| 百度股市通 | HTTP (gushitong.baidu) | 备用行情 |

### 关键路径
- `tradingagents/graph/analyst_execution.py` — 声明式 ANALYST_NODE_SPECS（7 个分析师）+ `build_analyst_execution_plan` + `AnalystWallTimeTracker`。**新增分析师只改这里和 setup.py 的 factories 字典**，不要再在 setup.py 里加 if-else 分支。
- `tradingagents/graph/` — LangGraph 编排、状态传播（`propagation.py`）、信号处理（`signal_processing.py`）、SQLite checkpoint（`checkpointer.py`）、反思（`reflection.py`，按 `benchmark_map` 动态选基准）
- `tradingagents/agents/analysts/` — 7 个 Analyst（原版 4 + 政策/游资/解禁 3）。`social_media_analyst.py` 已 rename 为 sentiment_analyst 模式（pre-fetch 数据块 + 单次 LLM 调用，无 tool-call 循环），数据源：东财个股新闻 + 同花顺热股 + 主散资金分单流向。
- `tradingagents/agents/quality_gate.py` — Analyst 输出质检兜底
- `tradingagents/agents/schemas.py` — Pydantic 结构化输出 schema。**TraderProposal 含 A 股代码级护栏**：`infer_market_type()` 从 6 位代码派生 market_type（主板/科创/创业/北交所/ST）+ daily_limit / min_lot；validator 拒绝 stop_loss 方向错误 + 拒绝 min_lot 非整倍数的股数。
- `tradingagents/dataflows/a_stock.py` — A 股数据 vendor，所有 A 股数据获取入口。新增 `get_index_history`（CSI 300 等指数 K 线，Sina HTTP）+ `get_policy_news`（一手政策流，按政府机构关键词过滤 CLS / 东财快讯）
- `tradingagents/dataflows/interface.py` — 数据 vendor 路由层（按 `data_vendors` / `tool_vendors` 分发）
- `tradingagents/dataflows/utils.py` — `safe_ticker_component` 路径安全校验 + 中文 ticker 自动解析
- `tradingagents/llm_clients/factory.py` — LLM 客户端工厂
- `web/app.py` / `web/runner.py` — Streamlit UI 主入口 + 后台线程 runner
- `cli/main.py` — CLI Typer 入口

### 中文股票名解析链路
用户/LLM 输入 → `safe_ticker_component` 检测中文 → `resolve_ticker()` → `_build_name_code_map()`（mootdx 全市场映射，缓存）→ 返回 6 位代码

## 已知问题与注意事项

### 依赖冲突
mootdx 锁死 `httpx==0.25.2`，与 langchain-google-genai 的 `httpx>=0.28.1` 冲突；同时 langchain 全家桶 + mootdx 的依赖图深到 pip 解析爆栈 (resolution-too-deep)。绕过：先 `pip install mootdx --no-deps`，再 `pip install -e .`。

mootdx --no-deps 会漏掉它的运行时依赖 `tdxpy / prettytable / py-mini-racer`，跑分析时会持续打 `mootdx K-line failed: No module named 'tdxpy'`，自动 fallback 到 Sina HTTP（功能 OK，但每次请求多走一次失败重试）。补 `pip install tdxpy prettytable py-mini-racer` 即可。

### akshare 已移除（v0.2.5）
v0.2.5 起完全移除 akshare 依赖，所有数据通过直连 HTTP API 获取。彻底消除了 akshare + pandas 3.0 + pyarrow 的 `ArrowInvalid` 崩溃问题，也消除了 akshare 与 mootdx 的 httpx 版本冲突。

### 模型兼容性
deepseek-v4-flash 等模型在 tool call 时可能返回中文股票名而非 6 位代码。`safe_ticker_component` 已加兜底自动转码，但不同模型表现仍有差异。

### 默认 vendor 是 a_stock，main.py 是上游遗留
`default_config.py` 的 `data_vendors` 全部默认 `a_stock`，但根目录 `main.py` 是上游遗留的 NVDA + yfinance 示例，**不要把它当成 A 股使用模板**，参考 README 的 `ta.propagate("688017", "2026-05-12")` 写法。

## Issue 归档
所有 GitHub Issue 的详细记录在 `issues/` 文件夹中，包含问题描述、根因分析、修复方案和当前状态。

## 开发规范
- 改动前先跑 `python -m pytest tests/ -v` 确保不破坏现有测试
- `safe_ticker_component` 是安全边界（防路径遍历），任何绕过路径校验的改动必须慎重评估
- 数据层新增接口遵循 `tradingagents/dataflows/interface.py` 的 vendor 路由模式：先在对应 vendor 模块实现，再在 interface 里加路由分支；其他 vendor（yfinance/alpha_vantage）不实现新方法时 wrapper 用 `**_unused` 吞额外参数即可，不要在 wrapper 层做 vendor 分支
- Agent 新增：在 `analyst_execution.py::ANALYST_NODE_SPECS` 注册 spec、在 `setup.py::analyst_factories` 加 factory、在 `conditional_logic.py` 加 `should_continue_<key>` 方法、在 `trading_graph._create_tool_nodes` 加 ToolNode
- Trader 改动要同步考虑 `TraderProposal` 的 A 股 validator 是否需要更新
- Web UI 改动在 `web/` 目录，用 `streamlit run web/app.py` 本地测试

## 最近一轮 A 股短板补齐（v0.2.6 进行中）
- **Alpha 基准取数走 a_stock vendor**：`trading_graph._fetch_returns_astock` 用 Sina HTTP 拉股价 + 指数；yfinance 仅作兜底。彻底脱离 yfinance 对 A 股的依赖。
- **Trader 代码级护栏**：`TraderProposal` 加 `astock_market_type` + pydantic validator（涨跌停范围 / 最小手数 / 多空止损方向）。
- **三方风险辩论补漏**：aggressive 加一字板 / 连板效应；conservative 加质押爆仓 / 退市新规 / 财务造假停牌；neutral 加市场温度 + 质押风险敞口。
- **政策一手数据源**：`get_policy_news` 从 CLS + 东财抓快讯，按 30+ 个政府机构关键词过滤；接入 policy_analyst 的 ToolNode。
- **声明式 graph**：`analyst_execution.py` 替换 setup.py 的 7 个 if-else 分支。
- **sentiment_analyst pre-fetch 模式**：上游设计移植，A 股化数据源（东财新闻 + 同花顺热股 + 主散资金流），消除 LLM 编造 Reddit/StockTwits 的失败模式。
- **env override 表**：`TRADINGAGENTS_*` 全套，加新覆盖 1 行配置。
- **benchmark_map**：按代码前缀自动选基准，reflection 层 prompt 也跟着动态生成 label。

## 相关项目
- [a-stock-data](https://github.com/simonlin1212/a-stock-data) — A 股 MCP 数据服务（Claude Code 用的 skill）
- 上游 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — 原版框架
