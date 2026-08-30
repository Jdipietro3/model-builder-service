"""The orchestrator agent: a streaming, provider-agnostic tool-use loop.

run_turn() is an async generator yielding UI events:
  {"type": "text_delta", "text": ...}     incremental assistant text
  {"type": "card", "card": {...}}         structured card (plan, ...)
  {"type": "done", "message_id": ...}     turn finished, message persisted
  {"type": "error", "message": ...}       turn failed

The LLM dialect lives entirely in app.orchestrator.providers: this loop only
streams text, dispatches tool calls, and feeds results back.
"""

import json
import logging
from typing import Any, AsyncGenerator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import LLM_MODEL, LLM_PROVIDER
from ..models import Dataset, Message, Run
from .prompts import SYSTEM_PROMPT, build_context_block
from .providers import config_error, start_conversation
from .tools import dispatch

logger = logging.getLogger("orchestrator")

MAX_TOOL_ITERATIONS = 12


def _history_messages(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Rebuild LLM conversation history from persisted messages."""
    rows = db.scalars(
        select(Message).where(Message.project_id == project_id).order_by(Message.created_at)
    ).all()
    history: list[dict[str, Any]] = []
    for m in rows:
        content = m.content
        if not content and m.cards:
            # Card-only messages (e.g. the profile card created on upload)
            kinds = ", ".join(c.get("type", "card") for c in m.cards)
            content = f"[Displayed {kinds} card(s) to the user]"
        if not content:
            continue
        history.append({"role": m.role, "content": content})
    return history


async def run_turn(
    db: Session, project_id: str, user_content: str, hidden: bool = False
) -> AsyncGenerator[dict[str, Any], None]:
    setup_error = config_error()
    if setup_error:
        yield {"type": "error", "message": setup_error}
        return

    # Persist the incoming message first so history is consistent even if the turn fails.
    user_msg = Message(project_id=project_id, role="user", content=user_content, hidden=hidden)
    db.add(user_msg)
    db.commit()

    datasets = db.scalars(select(Dataset).where(Dataset.project_id == project_id)).all()
    runs = db.scalars(select(Run).where(Run.project_id == project_id)).all()

    conv = start_conversation(
        SYSTEM_PROMPT,
        build_context_block(datasets, runs),
        _history_messages(db, project_id),
    )
    accumulated_text: list[str] = []
    accumulated_cards: list[dict] = []

    try:
        for iteration in range(MAX_TOOL_ITERATIONS):
            result = None
            async for event in conv.step():
                if isinstance(event, str):
                    accumulated_text.append(event)
                    yield {"type": "text_delta", "text": event}
                else:
                    result = event  # terminal TurnResult

            usage = result.usage
            logger.info(
                "project=%s provider=%s model=%s iter=%d input=%d cache_read=%d cache_write=%d output=%d stop=%s",
                project_id,
                LLM_PROVIDER,
                LLM_MODEL,
                iteration,
                usage.input_tokens,
                usage.cache_read,
                usage.cache_write,
                usage.output_tokens,
                result.stop,
            )

            if result.stop == "tools":
                for call in result.tool_calls:
                    if call.error:
                        # Malformed arguments off the wire: report them the way
                        # dispatch() reports validation errors so the model can retry.
                        conv.add_tool_result(call.id, json.dumps({"error": call.error}))
                        continue
                    tool_result, card = dispatch(db, project_id, call.name, call.input)
                    if card:
                        accumulated_cards.append(card)
                        yield {"type": "card", "card": card}
                    conv.add_tool_result(call.id, tool_result)
                continue

            if result.stop == "pause":
                continue

            break  # end of turn
        else:
            yield {"type": "error", "message": "Orchestrator exceeded maximum tool iterations."}

        assistant_msg = Message(
            project_id=project_id,
            role="assistant",
            content="".join(accumulated_text),
            cards=accumulated_cards or None,
        )
        db.add(assistant_msg)
        db.commit()
        yield {"type": "done", "message_id": assistant_msg.id}

    except Exception as e:
        db.rollback()
        yield {"type": "error", "message": f"Orchestrator error: {e}"}
