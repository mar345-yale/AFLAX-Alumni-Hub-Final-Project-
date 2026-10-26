"""Saved mentorship conversations (one thread per member), the agent's running memo,
and the per-message token-usage log."""

import json

from db import connect
from models import ChatHistoryMessage, IntroEmail
from tools import mentor_cards


def save_message(user_id: int, role: str, content: str, mentor_ids: list[int] | None = None,
                 intro: IntroEmail | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, mentor_ids, intro) VALUES (?, ?, ?, ?, ?)",
            (user_id, role, content, json.dumps(mentor_ids or []),
             intro.model_dump_json() if intro else None),
        )


def load_history(user_id: int, limit: int = 60) -> list[ChatHistoryMessage]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM (SELECT * FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?)
            ORDER BY id
            """,
            (user_id, limit),
        ).fetchall()
    return [
        ChatHistoryMessage(
            role=r["role"], content=r["content"],
            mentors=mentor_cards(json.loads(r["mentor_ids"])),
            intro_email=IntroEmail.model_validate_json(r["intro"]) if r["intro"] else None,
        )
        for r in rows
    ]


def clear_history(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM chat_memos WHERE user_id = ?", (user_id,))


def load_memo(user_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT memo FROM chat_memos WHERE user_id = ?", (user_id,)).fetchone()
    return row["memo"] if row else None


def save_memo(user_id: int, memo: str) -> None:
    if not memo:
        return
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_memos (user_id, memo) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET memo = excluded.memo, updated_at = datetime('now')
            """,
            (user_id, memo),
        )


def tool_trace(messages) -> list[dict]:
    """Audit trail for one run: each tool the agent called, its arguments, and a short
    preview of what the tool returned. (The final structured answer is not a tool.)"""
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

    steps: list[dict] = []
    by_id: dict[str, dict] = {}
    for msg in messages:
        for part in msg.parts:
            if isinstance(msg, ModelResponse) and isinstance(part, ToolCallPart):
                if part.tool_name == "final_result":
                    continue
                step = {"tool": part.tool_name, "args": part.args_as_dict(), "result": ""}
                steps.append(step)
                by_id[part.tool_call_id] = step
            elif isinstance(msg, ModelRequest) and isinstance(part, ToolReturnPart):
                if part.tool_call_id in by_id:
                    by_id[part.tool_call_id]["result"] = part.model_response_str()[:300]
    return steps


def log_usage(user_id: int, model: str, status: str, usage=None, duration_ms: int = 0,
              trace: list[dict] | None = None) -> None:
    """Record one chat message's model usage (usage is a PydanticAI RunUsage, or None)."""
    details = getattr(usage, "details", None) or {}
    reasoning = getattr(usage, "output_reasoning_tokens", 0) or details.get("reasoning_tokens", 0)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_usage (user_id, model, status, requests, tool_calls, input_tokens,
                                    cache_read_tokens, output_tokens, reasoning_tokens, duration_ms,
                                    tool_trace)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, model, status,
             getattr(usage, "requests", 0) or 0, getattr(usage, "tool_calls", 0) or 0,
             getattr(usage, "input_tokens", 0) or 0, getattr(usage, "cache_read_tokens", 0) or 0,
             getattr(usage, "output_tokens", 0) or 0, reasoning or 0, duration_ms,
             json.dumps(trace or [], default=str)),
        )


def messages_today(user_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM chat_usage WHERE user_id = ? AND date(created_at) = date('now')",
            (user_id,),
        ).fetchone()[0]
