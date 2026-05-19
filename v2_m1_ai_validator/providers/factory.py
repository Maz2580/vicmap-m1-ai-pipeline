"""Factory: instantiate an LLM provider by name.

Lookup order:
1. Explicit `name` argument passed to `get_provider()`.
2. `LLM_PROVIDER` environment variable.
3. Default `"openai"`.
"""
import os

from .base import LLMProvider
from .openai_compat import OpenAICompatibleProvider, PRESETS as _OPENAI_COMPAT


# Names users put in LLM_PROVIDER.
SUPPORTED_PROVIDERS: tuple[str, ...] = tuple(_OPENAI_COMPAT.keys()) + ("anthropic",)


def get_provider(name: str | None = None, **kwargs) -> LLMProvider:
    """Return an LLMProvider configured for the requested backend.

    `**kwargs` are forwarded to the provider's constructor (api_key, model,
    base_url, etc.) — letting callers override env-driven defaults.
    """
    resolved = (name or os.getenv("LLM_PROVIDER") or "openai").strip().lower()

    if resolved in _OPENAI_COMPAT:
        return OpenAICompatibleProvider(preset=resolved, **kwargs)

    if resolved == "anthropic":
        # Import lazily so adopters who don't use Anthropic don't need the SDK.
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(**kwargs)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{resolved}'. Supported: {SUPPORTED_PROVIDERS}"
    )
