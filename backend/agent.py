"""PydanticAI Cadet Mentorship agent: model (gpt-6-luna via Portkey), prompt, tools.

Entry point: `run_chat(message, history, deps)` -> AgentRunResult (use `.output`).

Token-efficiency notes:
- The prompt and tool definitions are identical on every call and come first, so the
  provider's automatic prompt caching can reuse them (cache hits are logged per message).
- Only the last HISTORY_TURNS messages are resent; anything older is carried by a short
  running memo that the agent itself maintains in its structured output (no extra call).
"""

import os
from dataclasses import dataclass

from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

import tools
from config import OPENAI_API_KEY, PORTKEY_API_KEY
from db import BACKEND_DIR
from models import AgentReply, ChatHistoryMessage

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6-luna")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
REQUEST_TIMEOUT = 60.0
# Recent messages resent each turn (3 exchanges); older context lives in the memo.
HISTORY_TURNS = 6
# gpt-6-luna on Azure (behind Portkey) rejects function tools + reasoning on
# /v1/chat/completions, so the agent uses the Responses API (/v1/responses), which allows
# both. Set OPENAI_API_STYLE=chat to fall back to chat completions with reasoning off.
API_STYLE = os.getenv("OPENAI_API_STYLE", "responses")
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")
PROMPT_CACHE_KEY = "aflax-falcon-mentor"  # routes repeat prefixes to the same cache
# The token budget covers reasoning + tool calls + the answer.
if API_STYLE == "chat":
    MODEL_SETTINGS = OpenAIChatModelSettings(max_tokens=3000, openai_reasoning_effort="none")
else:
    MODEL_SETTINGS = OpenAIResponsesModelSettings(
        max_tokens=3000, openai_reasoning_effort=REASONING_EFFORT,
        openai_prompt_cache_key=PROMPT_CACHE_KEY,
    )

INSTRUCTIONS = (BACKEND_DIR / "prompts" / "prompt.md").read_text()

# Hard ceiling on one answer, so a confused or manipulated agent can't loop or burn tokens.
# Measured on real runs: at most 4 model calls, 8 tool calls, ~13.7k tokens per answer.
USAGE_LIMITS = UsageLimits(request_limit=8, tool_calls_limit=16, total_tokens_limit=60_000)


@dataclass
class Deps:
    """Who is chatting. Passed into every run so the agent can tailor advice, exclude the
    member from their own mentor list, and sign intro emails with their name."""

    user_id: int
    first_name: str
    last_name: str
    grad_year: int
    status: str
    afsc: str | None = None
    base: str | None = None
    memo: str | None = None


def get_model() -> OpenAIResponsesModel | OpenAIChatModel | None:
    """gpt-6-luna via Portkey (PORTKEY_API_KEY), or OpenAI directly (OPENAI_API_KEY).
    Returns None when neither key is set, so the server still starts."""
    if PORTKEY_API_KEY:
        client = AsyncOpenAI(
            api_key=PORTKEY_API_KEY,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": PORTKEY_API_KEY},
            timeout=REQUEST_TIMEOUT,
            max_retries=1,
        )
    elif OPENAI_API_KEY:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL,
                             timeout=REQUEST_TIMEOUT, max_retries=1)
    else:
        return None
    provider = OpenAIProvider(openai_client=client)
    if API_STYLE == "chat":
        return OpenAIChatModel(MODEL_NAME, provider=provider)
    return OpenAIResponsesModel(MODEL_NAME, provider=provider)


MODEL = get_model()
KEY_SOURCE = "PORTKEY_API_KEY" if PORTKEY_API_KEY else "OPENAI_API_KEY" if OPENAI_API_KEY else None

# `instructions` (unlike `system_prompt`) are sent on EVERY request, including turns that
# carry message history. With system_prompt, the agent lost its instructions after turn 1.
agent = Agent(
    MODEL,
    deps_type=Deps,
    output_type=AgentReply,
    instructions=INSTRUCTIONS,
    model_settings=MODEL_SETTINGS,
    retries=2,
)

# Knowledge tools read reference data and the database directly; no run context needed.
agent.tool_plain(tools.search_afscs)
agent.tool_plain(tools.get_afsc_details)
agent.tool_plain(tools.search_bases)
agent.tool_plain(tools.get_base_details)
agent.tool_plain(tools.count_alumni)


@agent.tool
def find_mentors(
    ctx: RunContext[Deps], afsc: str | None = None, base: str | None = None,
    career_field: str | None = None, limit: int = 4,
) -> list[dict]:
    """AFLAX alumni who opted in to mentoring and match an interest, best first (exact AFSC,
    then same career-field family, then same base, then job keywords).

    Args:
        afsc: AFSC code of interest, e.g. "92T0".
        base: Base of interest, e.g. "Hill AFB, UT" or "Hill".
        career_field: Free-text interest, e.g. "space", "acquisition", "airline pilot".
        limit: How many mentors to return (1-8).

    Returns mentor_id, name, class, status, rank, AFSC, job, location, and match reason.
    Put the mentor_id values you recommend in mentor_ids.
    """
    return tools.find_mentors(afsc=afsc, base=base, career_field=career_field, limit=limit,
                              exclude_user_id=ctx.deps.user_id)


@agent.tool
def draft_intro_message(ctx: RunContext[Deps], mentor_id: int, topic: str) -> dict:
    """Draft a short, respectful first email from the member to one mentor, signed with
    their name and class year. Use only when they ask for help reaching out.

    Args:
        mentor_id: A mentor_id returned by find_mentors.
        topic: What they want to ask about, e.g. "becoming a pilot".

    Returns subject and body. Put them in intro_email (you may lightly personalize the body).
    """
    d = ctx.deps
    return tools.draft_intro_message(mentor_id, topic, f"{d.first_name} {d.last_name}", d.grad_year)


@agent.output_validator
def validate_mentors(output: AgentReply) -> AgentReply:
    """Keep the agent honest against the database: every mentor it recommends must be a
    real, approved, opted-in alumnus. If it invents an id, make it try again."""
    seen: set[int] = set()
    deduped = [m for m in output.mentor_ids if not (m in seen or seen.add(m))]
    bad = [m for m in deduped if tools.mentor_row(m) is None]
    if output.intro_email and tools.mentor_row(output.intro_email.mentor_id) is None:
        bad.append(output.intro_email.mentor_id)
    if bad:
        raise ModelRetry(
            f"These mentor_ids are not available mentors: {bad}. Only use mentor_id values "
            f"returned by find_mentors in this conversation. Fix them and respond again."
        )
    output.mentor_ids = deduped[:8]
    output.memo = output.memo.strip()[:600]
    return output


@agent.instructions
def member_context(ctx: RunContext[Deps]) -> str:
    """Per-run context: who is chatting, plus the running memo. Kept short and placed after
    the static instructions so the cached prefix stays identical across members."""
    d = ctx.deps
    lines = [f"Member: {d.first_name} {d.last_name}, Class of {d.grad_year}, status: {d.status}."]
    if d.status == "Cadet":
        lines.append("They are a current cadet: focus on helping them choose an AFSC and base.")
    else:
        details = ", ".join(filter(None, [d.afsc and f"AFSC {d.afsc}", d.base and f"at {d.base}"]))
        lines.append("They are an alumnus" + (f" ({details})" if details else "") + ": help them "
                     "explore career fields and bases, find fellow alumni, or prepare to mentor cadets.")
    if d.memo:
        lines.append(f"Your running memo from earlier in this conversation: {d.memo}")
    return "\n".join(lines)


def _to_message_history(history: list[ChatHistoryMessage]) -> list[ModelMessage]:
    """Convert the most recent prior turns into PydanticAI message history. Mentor ids
    shown earlier are noted so follow-ups like 'email the second one' resolve correctly."""
    messages: list[ModelMessage] = []
    for m in history[-HISTORY_TURNS:]:
        if m.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        elif m.role == "assistant":
            text = m.content
            if m.mentors:
                shown = "; ".join(f"mentor_id {c['id']} = {c['first_name']} {c['last_name']}"
                                  for c in m.mentors)
                text += f"\n\n[Mentor cards shown: {shown}]"
            messages.append(ModelResponse(parts=[TextPart(content=text)]))
    return messages


async def run_chat(message: str, history: list[ChatHistoryMessage], deps: Deps):
    return await agent.run(message, message_history=_to_message_history(history), deps=deps,
                           usage_limits=USAGE_LIMITS)
