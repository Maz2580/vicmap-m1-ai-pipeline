"""LLM provider abstraction layer.

The validator code talks to one of several LLM providers (OpenAI, OpenRouter,
Groq, Ollama, Together.ai, Anthropic). All providers expose the same `chat()`
interface from `LLMProvider`. Use `get_provider()` to obtain an instance
configured via env vars.
"""
from .base import LLMProvider, ChatResponse
from .factory import get_provider, SUPPORTED_PROVIDERS

__all__ = ["LLMProvider", "ChatResponse", "get_provider", "SUPPORTED_PROVIDERS"]
