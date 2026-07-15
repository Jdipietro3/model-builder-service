"""The orchestrator agent: a streaming Claude tool-use loop.

run_turn() is an async generator yielding UI events:
  {"type": "text_delta", "text": ...}     incremental assistant text
  {"type": "card", "card": {...}}         structured card (plan, ...)
  {"type": "done", "message_id": ...}     turn finished, message persisted
  {"type": "error", "message": ...}       turn failed
"""

from typing import Any, AsyncGenerator

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from ..models import Dataset, Message, Run
from .prompts import SYSTEM_PROMPT, build_context_block
from .tools import TOOLS, dispatch

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
    if not ANTHROPIC_API_KEY:
        yield {
            "type": "error",
            "message": "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to backend/.env and add your key.",
        }
        return

    # Persist the incoming message first so history is consistent even if the turn fails.
    user_msg = Message(project_id=project_id, role="user", content=user_content, hidden=hidden)
    db.add(user_msg)
    db.commit()

    datasets = db.scalars(select(Dataset).where(Dataset.project_id == project_id)).all()
    runs = db.scalars(select(Run).where(Run.project_id == project_id)).all()
    system = SYSTEM_PROMPT + build_context_block(datasets, runs)
    messages = _history_messages(db, project_id)

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    accumulated_text: list[str] = []
    accumulated_cards: list[dict] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            async with client.messages.stream(
                model=ANTHROPIC_MODEL,
                max_tokens=16000,
                system=system,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        accumulated_text.append(event.delta.text)
                        yield {"type": "text_delta", "text": event.delta.text}
                response = await stream.get_final_message()

            if response.stop_reason == "tool_use":
                # Echo the full assistant content (incl. thinking blocks) back, then
                # answer every tool_use block in a single user message.
                messages.append(
                    {"role": "assistant", "content": [b.model_dump() for b in response.content]}
                )
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result, card = dispatch(db, project_id, block.name, block.input)
                    if card:
                        accumulated_cards.append(card)
                        yield {"type": "card", "card": card}
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result}
                    )
                messages.append({"role": "user", "content": tool_results})
                continue

            if response.stop_reason == "pause_turn":
                messages.append(
                    {"role": "assistant", "content": [b.model_dump() for b in response.content]}
                )
                continue

            break  # end_turn / max_tokens / refusal — stop looping
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
