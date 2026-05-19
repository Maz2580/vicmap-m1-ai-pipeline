"""Shared implementation for OpenAI-API-compatible providers.

Many modern LLM providers expose the OpenAI Chat Completions API at a
different `base_url` (OpenRouter, Groq, Ollama, Together.ai, Anyscale, …).
We use one `openai.OpenAI` client across all of them.
"""
import os
from openai import OpenAI

from .base import LLMProvider, ChatResponse


# (default_base_url, default_model, env_var_for_api_key)
# None for default_base_url means "use the openai SDK's built-in default".
# None for env_var means the provider doesn't need a real key (Ollama).
PRESETS: dict[str, tuple[str | None, str, str | None]] = {
    "openai":     (None,                                "gpt-4o-mini",                          "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",      "openai/gpt-4o-mini",                   "OPENROUTER_API_KEY"),
    "groq":       ("https://api.groq.com/openai/v1",    "llama-3.1-70b-versatile",              "GROQ_API_KEY"),
    "ollama":     ("http://localhost:11434/v1",         "llama3.1",                             None),
    "together":   ("https://api.together.xyz/v1",       "meta-llama/Llama-3.1-70B-Instruct-Turbo", "TOGETHER_API_KEY"),
}


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        preset: str = "openai",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        if preset not in PRESETS:
            raise ValueError(
                f"Unknown OpenAI-compatible preset '{preset}'. "
                f"Choose from: {sorted(PRESETS)}"
            )
        default_base_url, default_model, key_env = PRESETS[preset]
        self.name = preset
        self.model = model or os.getenv("LLM_MODEL") or default_model

        # For Ollama (and any keyless local server), pass a dummy key — the
        # openai SDK requires a non-empty string but the server ignores it.
        if key_env is None:
            resolved_key = api_key or "ollama-no-key"
        else:
            resolved_key = api_key or os.getenv(key_env, "")
            if not resolved_key:
                raise ValueError(
                    f"Provider '{preset}' needs an API key. Set {key_env} in "
                    f".env or pass api_key= to the constructor."
                )

        self._client = OpenAI(
            api_key=resolved_key,
            base_url=base_url or default_base_url,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = self._client.chat.completions.create(**kwargs)
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = None
        if resp.usage:
            usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
            }
        return ChatResponse(content=content, model=resp.model, usage=usage, raw=resp)
