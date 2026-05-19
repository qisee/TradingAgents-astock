"""Regression tests for Kimi / Moonshot Bearer-token auth on the Anthropic
client.

Upstream ``ChatAnthropic`` defaults ``anthropic_api_key`` to ``""`` when the
``ANTHROPIC_API_KEY`` env var is unset, and unconditionally forwards that
empty string to the anthropic SDK. The SDK then treats it as an explicit
credential and refuses to fall back to ``ANTHROPIC_AUTH_TOKEN``, producing
``"Could not resolve authentication method"`` against any Kimi / Moonshot
endpoint (which authenticate via ``Authorization: Bearer ...`` headers).

These tests pin down the swap so the next bump of langchain-anthropic does
not silently undo the fix.
"""

from __future__ import annotations

import os

import pytest

from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic


@pytest.mark.unit
class TestNormalizedChatAnthropicAuth:
    def test_empty_api_key_swapped_for_auth_token(self, monkeypatch):
        # Simulate the fork's default state: only ANTHROPIC_AUTH_TOKEN is set
        # (Kimi-style), ANTHROPIC_API_KEY is unset.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-kimi-test-token")

        llm = NormalizedChatAnthropic(
            model="claude-sonnet-4-6",
            base_url="https://api.kimi.com/coding/",
        )
        params = llm._client_params

        # api_key must be dropped (or empty) so anthropic SDK doesn't enter
        # the "explicit credential" branch with a bogus value.
        assert not params.get("api_key")
        assert params.get("auth_token") == "sk-kimi-test-token"

    def test_explicit_api_key_wins_over_auth_token(self, monkeypatch):
        # If the caller explicitly supplies an api_key, the env-derived
        # auth_token must not override it.
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-kimi-test-token")

        llm = NormalizedChatAnthropic(
            model="claude-sonnet-4-6",
            api_key="sk-real-anthropic-key",
        )
        params = llm._client_params
        assert params.get("api_key") == "sk-real-anthropic-key"
        assert "auth_token" not in params

    def test_no_auth_token_no_swap(self, monkeypatch):
        # When neither key nor token is set, the SDK should fall back to
        # its own env-var lookup (we don't try to substitute anything).
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

        llm = NormalizedChatAnthropic(model="claude-sonnet-4-6")
        params = llm._client_params
        assert "auth_token" not in params
        # api_key remains the empty SecretStr that ChatAnthropic emits;
        # validating its truthiness rather than equality keeps the test
        # robust across langchain-anthropic versions.
        assert not params.get("api_key")
