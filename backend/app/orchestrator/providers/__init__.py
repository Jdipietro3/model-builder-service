"""Provider selection for the orchestrator.

LLM_PROVIDER picks the adapter:
  anthropic -- native SDK, keeps explicit prompt-cache breakpoints
  openai    -- OpenAI-compatible /v1/chat/completions; with LLM_BASE_URL this
               covers DeepSeek, Ollama, vLLM, LM Studio, Together, Groq
"""

from typing import Any

from ...config import LLM_API_KEY, LLM_PROVIDER
from .base import Conversation, StopReason, ToolCall, TurnResult, TurnUsage

__all__ = [
    "Conversation",
    "StopReason",
    "ToolCall",
    "TurnResult",
    "TurnUsage",
    "config_error",
    "start_conversation",
]

_PROVIDERS = ("anthropic", "openai")


def config_error() -> str | None:
    """Return a user-facing setup message, or None if the provider is usable."""
    if LLM_PROVIDER not in _PROVIDERS:
        return (
            f"LLM_PROVIDER is '{LLM_PROVIDER}'; expected one of {', '.join(_PROVIDERS)}. "
            "Check backend/.env."
        )
    if not LLM_API_KEY:
        if LLM_PROVIDER == "anthropic":
            return (
                "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and add your key."
            )
        return (
            "LLM_API_KEY is not set. Set it in backend/.env — local model servers "
            "usually ignore the value, but one must be supplied."
        )
    return None


def start_conversation(
    system_prompt: str, context_block: str, history: list[dict[str, Any]]
) -> Conversation:
    """Build a per-turn Conversation for the configured provider.

    history is neutral: a list of {"role", "content"} dicts with string content.
    """
    if LLM_PROVIDER == "openai":
        from .openai_provider import OpenAIConversation

        return OpenAIConversation(system_prompt, context_block, history)

    from .anthropic_provider import AnthropicConversation

    return AnthropicConversation(system_prompt, context_block, history)
