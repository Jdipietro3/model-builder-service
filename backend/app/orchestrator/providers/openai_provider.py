"""OpenAI-compatible adapter: wraps the /v1/chat/completions streaming shape

behind the provider-neutral Conversation protocol (see base.py). Covers real
OpenAI as well as DeepSeek, Ollama, vLLM, LM Studio, Together and Groq, all of
which speak this dialect via a configurable base_url.
"""

import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from ...config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_TOKENS, LLM_MODEL
from ..tools import TOOL_SPECS
from .base import ToolCall, TurnResult, TurnUsage


class OpenAIConversation:
    """One turn's worth of OpenAI-dialect message-loop state."""

    def __init__(self, system_prompt: str, context_block: str, history: list[dict[str, Any]]):
        # A single system message, not a content-block list: unlike Anthropic,
        # this dialect has no separate cache_control markers -- DeepSeek and
        # vLLM do automatic prefix caching, so there's nothing to opt into here.
        system = {"role": "system", "content": system_prompt + "\n\n" + context_block}
        self._messages: list[dict[str, Any]] = [system, *history]
        self._tools = [s.to_openai() for s in TOOL_SPECS]
        self._client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    def add_tool_result(self, call_id: str, content: str) -> None:
        # One message per tool result, appended immediately (not batched like
        # Anthropic's single user turn) -- that's what this dialect expects,
        # and since the assistant echo is appended eagerly in step() too,
        # there's no flush buffer needed; the next step() just sends
        # self._messages as-is.
        self._messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    async def step(self) -> AsyncIterator[str | TurnResult]:
        accumulated_text: list[str] = []
        # index -> {"id", "name", "args"}. Streamed tool calls arrive as
        # fragments keyed by index: id/name typically show up once on the
        # first fragment for that index, arguments arrive as a string split
        # across many chunks and must be concatenated before parsing.
        tool_acc: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        usage = TurnUsage()

        stream = await self._client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            messages=self._messages,
            tools=self._tools,
            stream=True,
            # Some self-hosted servers reject this field outright; we don't
            # retry without it -- keep it simple and let that surface as an
            # error rather than silently degrading usage reporting.
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            # The final chunk (usage-only, when include_usage is set) has an
            # empty choices list -- guard before indexing into it.
            if chunk.choices:
                choice = chunk.choices[0]
                delta = choice.delta
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                if delta.content:
                    accumulated_text.append(delta.content)
                    yield delta.content
                for tc in delta.tool_calls or []:
                    slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
            if chunk.usage is not None:
                # Fields are read defensively -- self-hosted servers routinely
                # omit some of them (e.g. prompt_tokens_details entirely).
                cached = getattr(
                    getattr(chunk.usage, "prompt_tokens_details", None), "cached_tokens", 0
                )
                usage = TurnUsage(
                    input_tokens=chunk.usage.prompt_tokens or 0,
                    output_tokens=chunk.usage.completion_tokens or 0,
                    cache_read=cached or 0,
                    cache_write=0,  # no equivalent concept in this dialect
                )

        text = "".join(accumulated_text)
        tool_calls: list[ToolCall] = []
        raw_tool_calls: list[dict[str, Any]] = []
        for index in sorted(tool_acc):
            slot = tool_acc[index]
            raw_args = slot["args"]
            try:
                parsed = json.loads(raw_args) if raw_args else {}
                error = None
            except json.JSONDecodeError:
                parsed = {}
                error = f"invalid JSON arguments: {raw_args[:200]!r}"
            tool_calls.append(ToolCall(id=slot["id"], name=slot["name"], input=parsed, error=error))
            raw_tool_calls.append(
                {
                    "id": slot["id"],
                    "type": "function",
                    # Echo the raw accumulated string rather than re-serializing
                    # the parsed dict: some providers validate the echo
                    # against the exact bytes they sent.
                    "function": {"name": slot["name"], "arguments": raw_args},
                }
            )

        if raw_tool_calls:
            self._messages.append(
                {"role": "assistant", "content": text or None, "tool_calls": raw_tool_calls}
            )
        else:
            self._messages.append({"role": "assistant", "content": text})

        # finish_reason == "tool_calls" is the documented signal, but some
        # providers report "stop" even when they emitted tool calls -- so we
        # also treat "we accumulated any tool calls" as sufficient on its own.
        stop = "tools" if finish_reason == "tool_calls" or tool_calls else "end"

        yield TurnResult(text=text, tool_calls=tool_calls, stop=stop, usage=usage)
