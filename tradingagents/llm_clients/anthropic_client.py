import os
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)
# NOTE: ``auth_token`` is deliberately NOT in _PASSTHROUGH_KWARGS.
# ``ChatAnthropic`` does not declare ``auth_token`` as a field, so passing
# it via the constructor sends it into ``model_kwargs``, which then leaks
# into every ``messages.create()`` call and explodes with "unexpected
# keyword argument 'auth_token'". The Kimi / Bearer-token path is handled
# entirely inside ``NormalizedChatAnthropic._client_params``, which feeds
# the underlying anthropic SDK client (where ``auth_token`` IS valid).


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output + Kimi Bearer-auth fix.

    Two adjustments to upstream ChatAnthropic:

    1. ``invoke`` normalizes block-list content to plain string so the
       downstream agents see one shape regardless of extended thinking
       or tool-use.

    2. ``_client_params`` swaps an empty ``api_key`` for ``auth_token``
       when ``ANTHROPIC_AUTH_TOKEN`` is set. Upstream ChatAnthropic
       always passes ``api_key=""`` to the anthropic SDK when
       ``ANTHROPIC_API_KEY`` is unset, which the SDK treats as an
       explicit credential and therefore refuses to fall back to
       ``ANTHROPIC_AUTH_TOKEN``. The result is a confusing
       ``"Could not resolve authentication method"`` error against any
       Kimi / Moonshot endpoint, which authenticate via Bearer tokens.

       Implemented as a plain ``property`` (not ``cached_property``)
       because ``cached_property`` in a subclass shares the instance
       ``__dict__`` slot with the parent's ``cached_property`` of the
       same name and corrupts later ``super()`` calls.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    @property
    def _client_params(self) -> dict[str, Any]:
        params = dict(super()._client_params)
        if not params.get("api_key"):
            auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
            if auth_token:
                params.pop("api_key", None)
                params["auth_token"] = auth_token
        return params


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance.

        Kimi / Moonshot Bearer-token auth is handled inside
        ``NormalizedChatAnthropic._client_params`` (not here), since the
        env-var → ``auth_token`` swap has to happen at the level of the
        underlying anthropic SDK client, not at the ChatAnthropic
        constructor (which has no ``auth_token`` field).
        """
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
