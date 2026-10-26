"""AFLAX Alumni Connections: API (accounts, alumni map, schedule, board tools, Explorer,
Cadet Mentorship agent) plus the pre-built React site from frontend/dist.

Run from the backend/ folder (no auto-reload, so one edit never spawns extra servers):
    uvicorn main:app --port 8001          -> open http://localhost:8001
On first start the database is created and seeded automatically.

Production settings (environment / .env):
    FORCE_HTTPS=1          redirect HTTP to HTTPS and send HSTS (set when deployed behind TLS)
    ALLOWED_ORIGINS=...    comma-separated browser origins allowed to call the API
    CHAT_DAILY_LIMIT=40    Falcon Mentor messages per member per day
"""

import logging
import os
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic_ai.exceptions import UsageLimitExceeded
from starlette.concurrency import run_in_threadpool

import agent as agent_module
import ratelimit
from agent import MODEL_NAME, Deps, run_chat
from auth import Member, current_user, router as auth_router
from chat_store import (clear_history, load_history, load_memo, log_usage, messages_today,
                        save_memo, save_message, tool_trace)
from config import REPO_DIR, env_source
from db import connect, init_schema
from explore import router as explore_router
from models import ChatHistoryMessage, ChatRequest, ChatResponse, IntroEmail
from routes import router as portal_router
from tools import mentor_cards, mentor_row

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aflax")

CHAT_DAILY_LIMIT = int(os.getenv("CHAT_DAILY_LIMIT", "40"))
FORCE_HTTPS = os.getenv("FORCE_HTTPS") == "1"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5175,http://127.0.0.1:5175").split(",") if o.strip()]
FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

init_schema()  # creates the database if needed and applies pending migrations
with connect() as _conn:
    _empty = _conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
if _empty:  # first run: load AFSCs, test profiles, schedule, and the admin/grader accounts
    import seed
    log.info("Empty database: seeding it now (first run only)...")
    seed.seed(reset=False)

log.info(".env: %s", env_source())
if agent_module.KEY_SOURCE:
    log.info("Falcon Mentor model: %s via %s", MODEL_NAME, agent_module.KEY_SOURCE)
else:
    log.warning("No PORTKEY_API_KEY or OPENAI_API_KEY found: the site works, but Falcon Mentor "
                "chat will be unavailable until a key is added to .env.")
if not (FRONTEND_DIST / "index.html").is_file():
    log.warning("frontend/dist not found: run `npm run build` in frontend/ or use the Vite dev server.")

app = FastAPI(title="AFLAX Alumni Connections API")
if FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(explore_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Standard hardening headers on every response."""
    response = await call_next(request)
    h = response.headers
    path = request.url.path
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if path.startswith("/api/"):
        # The API only returns JSON and images, so nothing should ever be scripted or framed.
        h.setdefault("Content-Security-Policy", "default-src 'none'; img-src 'self'; frame-ancestors 'none'")
        if not path.startswith("/api/photos/"):
            h.setdefault("Cache-Control", "no-store")
    else:
        # The React site: own scripts only; map tiles from OpenStreetMap; Google Fonts.
        h.setdefault("Content-Security-Policy", (
            "default-src 'self'; script-src 'self'; connect-src 'self'; "
            "img-src 'self' data: blob: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'; base-uri 'self'"))
    if FORCE_HTTPS:
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "falcon_mentor": "ready" if agent_module.MODEL is not None else "no API key"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: Member = Depends(current_user)) -> ChatResponse:
    # Cost controls: a short burst limit plus a persistent daily cap per member.
    ratelimit.check("chat_burst", str(user.id), "You're sending messages quickly.")
    if await run_in_threadpool(messages_today, user.id) >= CHAT_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've reached today's limit of {CHAT_DAILY_LIMIT} Falcon Mentor messages. "
                   f"Try again tomorrow, or browse the Explorer page in the meantime.",
        )
    ratelimit.hit("chat_burst", str(user.id))

    # History and memo come from the server, not the browser, so a client can't rewrite them.
    history = await run_in_threadpool(load_history, user.id)
    memo = await run_in_threadpool(load_memo, user.id)
    deps = Deps(user_id=user.id, first_name=user.first_name, last_name=user.last_name,
                grad_year=user.grad_year, status=user.status, afsc=user.afsc, base=user.base,
                memo=memo)
    started = time.monotonic()
    try:
        result = await run_chat(body.message, history, deps)
    except Exception as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        if agent_module.MODEL is None and "model" in str(exc).lower():
            raise HTTPException(
                status_code=503,
                detail="Falcon Mentor isn't configured: add PORTKEY_API_KEY (or OPENAI_API_KEY) "
                       "to a .env file in the project folder or the folder above it, then restart.",
            )
        await run_in_threadpool(log_usage, user.id, MODEL_NAME, "error", None, elapsed)
        text = str(exc).lower()
        log.exception("chat failed for user %s", user.id)
        if "content_filter" in text or "content management policy" in text:
            reply = ("I can't help with that one. I'm here for AFSC, base, and mentorship "
                     "questions. What career field or base are you thinking about?")
            return ChatResponse(reply=reply, mentors=[])
        if isinstance(exc, UsageLimitExceeded):
            raise HTTPException(
                status_code=422,
                detail="That question needed more steps than Falcon Mentor allows in one answer. "
                       "Try asking about one AFSC or base at a time.",
            )
        raise HTTPException(
            status_code=502,
            detail="Falcon Mentor is having trouble right now. Please try again in a moment.",
        )
    elapsed = int((time.monotonic() - started) * 1000)
    out = result.output
    intro = None
    if out.intro_email and (row := mentor_row(out.intro_email.mentor_id)):
        intro = IntroEmail(mentor_id=row["id"], to=row["email"],
                           subject=out.intro_email.subject, body=out.intro_email.body)
    # Cards are rebuilt from the database so contact details are authoritative.
    cards = await run_in_threadpool(mentor_cards, out.mentor_ids)

    def persist() -> None:
        save_message(user.id, "user", body.message)
        save_message(user.id, "assistant", out.reply, out.mentor_ids, intro)
        save_memo(user.id, out.memo)
        # `usage` is a property in this PydanticAI version (a method in older ones).
        usage = result.usage() if callable(result.usage) else result.usage
        log_usage(user.id, MODEL_NAME, "ok", usage, elapsed, tool_trace(result.new_messages()))

    await run_in_threadpool(persist)
    return ChatResponse(reply=out.reply, mentors=cards, intro_email=intro)


@app.get("/api/chat/history", response_model=list[ChatHistoryMessage])
def chat_history(user: Member = Depends(current_user)) -> list[ChatHistoryMessage]:
    return load_history(user.id)


@app.delete("/api/chat/history", status_code=204)
def reset_chat(user: Member = Depends(current_user)) -> None:
    clear_history(user.id)


# ---------------------------------------------------------------- the React site
# Registered last so it never shadows an API route. Any non-API path that isn't a real file
# returns index.html, so client-side routes like /alumni work on refresh.
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
