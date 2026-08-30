"""Anthropic adapter: wraps the native Claude message loop behind the
provider-neutral Conversation protocol (see base.py).

This is a straight port of the streaming tool-use loop that used to live in
agent.py — same caching strategy, same echo-block handling — just reshaped so
run_turn no longer touches Anthropic wire format directly.
"""

from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from ...config import LLM_API_KEY, LLM_MAX_TOKENS, LLM_MODEL
from ..tools import TOOL_SPECS
from .base import ToolCall, TurnResult, TurnUsage

# Response-only fields the API attaches to content blocks (e.g. structured-output
# parsing) that it rejects as "extra inputs" when a block is echoed back in history.
_RESPONSE_ONLY_FIELDS = {"parsed_output"}


def _echo_blocks(content: list[Any]) -> list[dict[str, Any]]:
    """Serialize response content blocks so they can be re-sent as input."""
    return [
        {k: v for k, v in b.model_dump().items() if k not in _RESPONSE_ONLY_FIELDS}
        for b in content
    ]


def _apply_cache_breakpoint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return messages with a cache_control marker on the final content block.

    Copies rather than mutates: the caller keeps appending to `messages`, and a
    stale marker left on an earlier block would burn one of the 4 allowed
    cache breakpoints per request.
    """
    out = list(messages)
    last = dict(out[-1])
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    else:
        content = [dict(b) for b in content]
    content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
    last["content"] = content
    out[-1] = last
    return out


class AnthropicConversation:
    """One turn's worth of Anthropic message-loop state."""

    def __init__(self, system_prompt: str, context_block: str, history: list[dict[str, Any]]):
        # The breakpoint on the system prompt caches the tools + system prefix
        # (tools render before system). The volatile per-request context block
        # sits after it so project-state changes don't invalidate the cached
        # prefix. Note the prefix may be under the model's minimum cacheable
        # length — harmless; the message-level breakpoint below still covers
        # it via lookback.
        self._system = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": context_block},
        ]
        self._tools = [s.to_anthropic() for s in TOOL_SPECS]
        self._messages: list[dict[str, Any]] = list(history)
        self._pending_tool_results: list[dict[str, Any]] = []
        self._client = AsyncAnthropic(api_key=LLM_API_KEY)

    def add_tool_result(self, call_id: str, content: str) -> None:
        self._pending_tool_results.append(
            {"type": "tool_result", "tool_use_id": call_id, "content": content}
        )

    async def step(self) -> AsyncIterator[str | TurnResult]:
        if self._pending_tool_results:
            self._messages.append({"role": "user", "content": self._pending_tool_results})
            self._pending_tool_results = []

        # Applied at request time only, never persisted onto self._messages:
        # marking the last block means iteration N+1's request (whose last
        # block is the newest tool_result) looks back to the cache entry
        # written by iteration N, so each iteration only pays uncached tokens
        # for its own new blocks.
        request_messages = (
            _apply_cache_breakpoint(self._messages) if self._messages else self._messages
        )

        accumulated_text: list[str] = []
        async with self._client.messages.stream(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=self._system,
            tools=self._tools,
            messages=request_messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    accumulated_text.append(event.delta.text)
                    yield event.delta.text
            response = await stream.get_final_message()

        usage = response.usage

        if response.stop_reason == "tool_use":
            self._messages.append({"role": "assistant", "content": _echo_blocks(response.content)})
            tool_calls = [
                ToolCall(id=block.id, name=block.name, input=block.input)
                for block in response.content
                if block.type == "tool_use"
            ]
            stop = "tools"
        elif response.stop_reason == "pause_turn":
            self._messages.append({"role": "assistant", "content": _echo_blocks(response.content)})
            tool_calls = []
            stop = "pause"
        else:
            tool_calls = []
            stop = "end"

        yield TurnResult(
            text="".join(accumulated_text),
            tool_calls=tool_calls,
            stop=stop,
            usage=TurnUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read=usage.cache_read_input_tokens or 0,
                cache_write=usage.cache_creation_input_tokens or 0,
            ),
        )
