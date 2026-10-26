"""Falcon Mentor tools and guardrails, tested directly (no model calls)."""

import pytest
from pydantic_ai import ModelRetry

import agent
import tools
from models import AgentReply, IntroDraft


def test_search_afscs_matches_interests():
    codes = [a["code"] for a in tools.search_afscs("space satellites")]
    assert "13S1" in codes
    assert len(tools.search_afscs("")) <= 6


def test_afsc_details_are_short_unless_official_requested():
    short = tools.get_afsc_details("92T0")
    assert "official_description" not in short and short["training"]
    full = tools.get_afsc_details("62E1C", include_official=True)
    assert "62E1A description" in full["official_description"]  # engineering shreds include parent


def test_bases_lookup():
    assert any(b["name"] == "Columbus AFB, MS" for b in tools.search_bases("pilot training"))
    hill = tools.get_base_details("hill")
    assert hill["name"] == "Hill AFB, UT" and hill["pros"] and hill["cons"]
    assert "error" in tools.get_base_details("Atlantis")


def test_find_mentors_ranks_exact_afsc_first_and_excludes_self():
    mentors = tools.find_mentors(afsc="92T0", limit=4)
    assert mentors and all(m["afsc"] == "92T0" for m in mentors)
    me = mentors[0]["mentor_id"]
    assert me not in [m["mentor_id"] for m in tools.find_mentors(afsc="92T0", exclude_user_id=me)]


def test_intro_email_uses_rank_abbreviation():
    mentor = tools.find_mentors(afsc="92T0", limit=1)[0]
    draft = tools.draft_intro_message(mentor["mentor_id"], "becoming a pilot", "Riley Jones", 2028)
    assert draft["body"].startswith("Dear ") and "O-" not in draft["body"].splitlines()[0]
    assert "Class of 2028" in draft["body"]


def test_mentor_cards_respect_hidden_phone():
    mentor_id = tools.find_mentors(afsc="13S1", limit=1)[0]["mentor_id"]
    from db import connect
    with connect() as conn:
        conn.execute("UPDATE users SET show_phone = 0 WHERE id = ?", (mentor_id,))
    try:
        assert tools.mentor_cards([mentor_id])[0]["phone"] is None
    finally:
        with connect() as conn:
            conn.execute("UPDATE users SET show_phone = 1 WHERE id = ?", (mentor_id,))


def test_output_validator_rejects_invented_mentors():
    real = tools.find_mentors(afsc="92T0", limit=1)[0]["mentor_id"]
    ok = agent.validate_mentors(AgentReply(reply="hi", mentor_ids=[real, real], memo="  note  "))
    assert ok.mentor_ids == [real] and ok.memo == "note"
    with pytest.raises(ModelRetry):
        agent.validate_mentors(AgentReply(reply="hi", mentor_ids=[999_999]))
    with pytest.raises(ModelRetry):
        agent.validate_mentors(AgentReply(reply="hi", intro_email=IntroDraft(mentor_id=999_999, subject="s", body="b")))


def test_agent_uses_instructions_so_they_survive_history():
    # `instructions` are re-sent every turn; `system_prompt` would be dropped once history exists.
    assert "Falcon Mentor" in agent.INSTRUCTIONS
    assert agent.HISTORY_TURNS <= 6


def test_chat_end_to_end_with_offline_test_model(client, approved_member):
    """Full /api/chat round trip (agent run, cards, memo, usage log, history) using
    PydanticAI's TestModel instead of the real model, so it costs nothing."""
    from pydantic_ai.models.test import TestModel

    headers, _, _ = approved_member
    mentor = tools.find_mentors(base="Wright-Patterson AFB, OH", limit=1)[0]["mentor_id"]
    fake = TestModel(call_tools=["find_mentors"], custom_output_args={
        "reply": "Talk to these alumni at Wright-Patt.", "mentor_ids": [mentor], "memo": "Asked about WPAFB."})
    with agent.agent.override(model=fake):
        r = client.post("/api/chat", headers=headers, json={"message": "Who can I talk to about Wright-Patterson AFB?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("Talk to") and body["mentors"][0]["id"] == mentor

    history = client.get("/api/chat/history", headers=headers).json()
    assert [m["role"] for m in history[-2:]] == ["user", "assistant"]
    from db import connect
    with connect() as conn:
        row = conn.execute("SELECT * FROM chat_usage ORDER BY id DESC LIMIT 1").fetchone()
        memo = conn.execute("SELECT memo FROM chat_memos ORDER BY rowid DESC LIMIT 1").fetchone()
    assert row["status"] == "ok" and row["requests"] >= 1
    assert memo["memo"] == "Asked about WPAFB."
    import json
    trace = json.loads(row["tool_trace"])
    assert trace and trace[0]["tool"] == "find_mentors"  # audit trail records the tool call


def test_runaway_agent_is_stopped_by_usage_limits(client, approved_member, monkeypatch):
    """A run that needs more model calls than allowed is cut off and logged as an error,
    instead of looping and spending tokens."""
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.usage import UsageLimits

    headers, _, _ = approved_member
    monkeypatch.setattr(agent, "USAGE_LIMITS", UsageLimits(request_limit=1))  # tool round + answer = 2
    with agent.agent.override(model=TestModel(call_tools=["search_afscs"])):
        r = client.post("/api/chat", headers=headers, json={"message": "Tell me about space."})
    assert r.status_code == 422 and "more steps" in r.json()["detail"]
    from db import connect
    with connect() as conn:
        assert conn.execute("SELECT status FROM chat_usage ORDER BY id DESC LIMIT 1").fetchone()[0] == "error"


def test_missing_api_key_gives_clear_message(client, approved_member, monkeypatch):
    """Without PORTKEY_API_KEY/OPENAI_API_KEY the site runs and chat explains how to fix it."""
    from pydantic_ai import Agent

    headers, _, _ = approved_member
    no_model = Agent(None, deps_type=agent.Deps, output_type=AgentReply)
    monkeypatch.setattr(agent, "agent", no_model)
    monkeypatch.setattr(agent, "MODEL", None)
    r = client.post("/api/chat", headers=headers, json={"message": "hi"})
    assert r.status_code == 503 and "PORTKEY_API_KEY" in r.json()["detail"]
    assert client.get("/api/health").json()["falcon_mentor"] == "no API key"


def test_chat_daily_cap(client, approved_member, monkeypatch):
    import main
    headers, _, _ = approved_member
    monkeypatch.setattr(main, "CHAT_DAILY_LIMIT", 0)
    r = client.post("/api/chat", headers=headers, json={"message": "hi"})
    assert r.status_code == 429 and "limit" in r.json()["detail"]
