"""Regression test for the ``moonshot`` provider wiring.

Kimi has two distinct API products: ``api.kimi.com/coding`` (Kimi For
Coding, Anthropic protocol, whitelist-only) and ``api.moonshot.cn``
(Moonshot Platform, OpenAI-compatible, open to any client). The fork
adds ``moonshot`` as a first-class OpenAI-compatible provider so users
who can't pass the Coding-Agent whitelist (third-party UIs, generic
integrations) have a clean way out. These tests pin the wiring.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE, create_llm_client
from tradingagents.llm_clients.openai_client import _PROVIDER_CONFIG, OpenAIClient


@pytest.mark.unit
class TestMoonshotProviderRegistration:
    def test_moonshot_in_openai_compatible_allowlist(self):
        assert "moonshot" in _OPENAI_COMPATIBLE

    def test_moonshot_in_provider_config(self):
        assert "moonshot" in _PROVIDER_CONFIG

    def test_moonshot_default_base_url(self):
        base_url, key_env = _PROVIDER_CONFIG["moonshot"]
        assert base_url == "https://api.moonshot.cn/v1"
        assert key_env == "MOONSHOT_API_KEY"

    def test_factory_returns_openai_client_for_moonshot(self):
        # Avoid triggering ChatOpenAI's pydantic-settings env load
        # (which fails fast in CI with no key). The client object
        # itself is enough — we don't need to call get_llm here.
        client = create_llm_client("moonshot", "kimi-k2.6")
        assert isinstance(client, OpenAIClient)
        assert client.provider == "moonshot"
        assert client.model == "kimi-k2.6"


@pytest.mark.unit
class TestMoonshotClientResolution:
    def test_get_llm_picks_moonshot_base_url_and_key(self, monkeypatch):
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test-moonshot-key")

        client = OpenAIClient("kimi-k2.6", provider="moonshot")

        # Patch the constructor to capture kwargs without actually
        # initialising ChatOpenAI (avoids needing langchain_openai env
        # validation in this fast unit test).
        captured: dict = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI", FakeChat):
            client.get_llm()

        assert captured["base_url"] == "https://api.moonshot.cn/v1"
        assert captured["api_key"] == "sk-test-moonshot-key"
        # Moonshot is a third-party OpenAI-compatible provider → Chat
        # Completions, NOT the Responses API.
        assert "use_responses_api" not in captured

    def test_explicit_base_url_overrides_default(self, monkeypatch):
        """Corporate proxy / local LiteLLM gateway override path."""
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test-key")

        client = OpenAIClient(
            "kimi-k2.6",
            base_url="https://my-gateway.local/moonshot/v1",
            provider="moonshot",
        )

        captured: dict = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI", FakeChat):
            client.get_llm()

        assert captured["base_url"] == "https://my-gateway.local/moonshot/v1"

    def test_no_key_env_does_not_inject_api_key(self, monkeypatch):
        """When MOONSHOT_API_KEY is unset, api_key is omitted (so any
        explicit kwarg or env-fallback inside ChatOpenAI can take over).
        Mirrors the existing behaviour for deepseek / minimax."""
        monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        client = OpenAIClient("kimi-k2.6", provider="moonshot")

        captured: dict = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI", FakeChat):
            client.get_llm()

        assert "api_key" not in captured
