"""Provider-neutral types for the orchestrator turn loop.

The loop only needs four things from a provider: stream text, hand back tool
calls, accept tool results, say why it stopped. Everything else -- message wire
format, tool schema dialect, prompt caching, usage field names -- is provider
dialect and stays inside the adapter.

An adapter therefore owns the native message list for the whole turn; run_turn
never sees provider wire format.
"""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol

StopReason = Literal["end", "tools", "pause"]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]
    # Set when the provider streamed arguments that did not parse as JSON. The
    # loop turns this into the tool_result so the model can self-correct,
    # matching how tools.dispatch() reports validation errors.
    error: str | None = None


@dataclass
class TurnUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass
class TurnResult:
    """Terminal event of a step(): everything the loop needs to decide what next."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: StopReason = "end"
    usage: TurnUsage = field(default_factory=TurnUsage)


class Conversation(Protocol):
    """One turn's worth of provider state. Created per turn, not shared."""

    def step(self) -> AsyncIterator[str | TurnResult]:
        """Run one request.

        Yields text deltas as plain strings while they stream, then exactly one
        TurnResult as the final item.
        """
        ...

    def add_tool_result(self, call_id: str, content: str) -> None:
        """Append a tool result, to be sent with the next step()."""
        ...
