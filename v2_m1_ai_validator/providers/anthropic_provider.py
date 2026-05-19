"""Anthropic Claude provider.

Anthropic's API is similar in spirit to OpenAI's chat completions but differs
on three points we have to bridge:

1. System prompt is a top-level `system=` parameter, not a `{"role":"system"}`
   message.
2. There's no native `response_format={"type":"json_object"}` — we emulate it
   by appending a JSON-only directive to the system prompt.
3. The response is a list of content blocks (`TextBlock`, etc.) rather than a
   single string.
"""
import os

from .base import LLMProvider, ChatResponse


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ):
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package not installed. Run `pip install anthropic` "
                "to enable LLM_PROVIDER=anthropic."
            ) from e

        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY env var required for the Anthropic provider."
            )
        self._client = Anthropic(api_key=resolved_key)
        # Default to a recent Claude — adopters can override via LLM_MODEL or
        # by passing `model=` to the constructor.
        self.model = model or os.getenv("LLM_MODEL") or "claude-sonnet-4-6"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        # Pull the (optional) system message out of the messages list.
        system_msg: str | None = None
        conv: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                # Last system message wins, matching OpenAI behavior.
                system_msg = m["content"]
            else:
                conv.append({"role": m["role"], "content": m["content"]})

        # Anthropic doesn't have OpenAI's response_format. Emulate JSON mode
        # by appending a strong instruction to the system prompt.
        if response_format is not None and response_format.get("type") in (
            "json_object",
            "json_schema",
        ):
            json_directive = (
                "\n\nIMPORTANT: Respond with valid JSON only. No prose, no "
                "markdown code fences (no ```json), just the raw JSON object."
            )
            system_msg = (system_msg or "") + json_directive

        kwargs: dict = {
            "model": self.model,
            "messages": conv,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg is not None:
            kwargs["system"] = system_msg

        resp = self._client.messages.create(**kwargs)
        # Concatenate text blocks; ignore tool-use / image blocks for now.
        content = "".join(
            getattr(b, "text", "") for b in (resp.content or [])
        )
        usage = None
        if getattr(resp, "usage", None):
            usage = {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
        return ChatResponse(content=content, model=resp.model, usage=usage, raw=resp)
