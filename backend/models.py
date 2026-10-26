"""Shapes shared by the chat endpoint and the agent."""

from pydantic import BaseModel, Field


class IntroDraft(BaseModel):
    """An introduction email the cadet can send to one mentor."""

    mentor_id: int = Field(description="mentor_id of the alumnus this email is addressed to")
    subject: str
    body: str


class AgentReply(BaseModel):
    """What the mentorship agent returns each turn."""

    reply: str = Field(description="Your answer to the cadet, in friendly plain text (short paragraphs or bullets).")
    mentor_ids: list[int] = Field(
        default_factory=list,
        description="mentor_id values (from find_mentors in this conversation) to show as contact cards. Empty if none.",
    )
    intro_email: IntroDraft | None = Field(
        default=None,
        description="Only when the cadet asked for help writing to a mentor: the draft from draft_intro_message, optionally polished.",
    )
    memo: str = Field(
        default="",
        description=(
            "Private running memo for your future turns (never shown to the member), max 60 words: "
            "update the previous memo with their goals, interests, AFSCs/bases discussed, and "
            "mentor_ids already suggested."
        ),
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class IntroEmail(BaseModel):
    mentor_id: int
    to: str
    subject: str
    body: str


class ChatResponse(BaseModel):
    reply: str
    mentors: list[dict]
    intro_email: IntroEmail | None = None


class ChatHistoryMessage(BaseModel):
    role: str
    content: str
    mentors: list[dict] = []
    intro_email: IntroEmail | None = None
