"""Provider-agnostic chat-completion ABC."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatResponse:
    """Normalized response returned by every provider.

    Always carries the assistant message content as a string; the caller is
    responsible for parsing JSON when that's the expected format.
    """
    content: str
    model: str
    usage: dict[str, int] | None = None  # {"input_tokens": ..., "output_tokens": ...}
    raw: Any = None  # provider-specific response object, for debugging


class LLMProvider(ABC):
    """Abstract base for chat-completion providers.

    Concrete subclasses live in this package (openai_compat, anthropic).
    """

    name: str = "base"

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        """Send a chat-style conversation and return the assistant reply.

        Args:
            messages: List of {"role": "system" | "user" | "assistant", "content": str}.
            response_format: OpenAI-style hint, e.g. {"type": "json_object"} or
                {"type": "json_schema", "json_schema": {...}}. Providers that don't
                support this natively (Anthropic) emulate it via a system-prompt
                instruction. None means free-form text.
            temperature: 0.0 for deterministic (default for validation).
            max_tokens: Cap on response length.
        """
        ...
