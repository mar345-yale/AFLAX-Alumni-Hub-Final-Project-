"""Accounts: sign up (pending board approval), log in/out, password reset, profile edits,
and signed profile-picture links.

Sign-up and profile edits are multipart forms so a profile picture can ride along.
A member's public shape never includes password_hash, so hashes stay server-side only.
"""

import re
import sqlite3
import uuid

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException,
                     Request, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

import ratelimit
from db import UPLOAD_DIR, connect
from geo import locate
from images import BadImage, sanitize_image
from mailer import new_account_alert, password_reset_email
from reference import AIRCREW_AFSCS, MILITARY_STATUSES, RANK_CODES, STATUSES, canonical_base, grad_years
from security import (consume_reset_token, create_reset_token, create_session, hash_password,
                      resolve_session, revoke_all_sessions, revoke_session, signed_photo_url,
                      verify_password, verify_photo_link)

router = APIRouter(prefix="/api", tags=["auth"])

_email_adapter = TypeAdapter(EmailStr)
PHOTO_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|gif)$")
MIN_PASSWORD, MAX_PASSWORD = 8, 200

# Free-text limits. Besides keeping the UI tidy, they bound how much member-written text
# can ever reach the agent through tool results (a prompt-injection mitigation).
MAX_LEN = {"first_name": 50, "last_name": 50, "job": 100, "city": 100, "phone": 25,
           "rank": 10, "afsc": 10, "aircraft": 20, "base": 80}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class Member(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    grad_year: int
    status: str
    rank: str | None
    afsc: str | None
    aircraft: str | None
    job: str | None
    base: str | None
    city: str | None
    phone: str | None
    photo_url: str | None
    willing_to_mentor: bool
    show_phone: bool = True
    role: str
    location_label: str | None = None
    lat: float | None = None
    lng: float | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: Member


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ForgotRequest(BaseModel):
    email: EmailStr


class ResetRequest(BaseModel):
    token: str
    new_password: str


def member_from_row(row: sqlite3.Row) -> Member:
    return Member(
        id=row["id"], email=row["email"], first_name=row["first_name"],
        last_name=row["last_name"], grad_year=row["grad_year"], status=row["status"],
        rank=row["rank"], afsc=row["afsc"], aircraft=row["aircraft"], job=row["job"],
        base=row["base"], city=row["city"], phone=row["phone"],
        photo_url=signed_photo_url(row["photo_path"]),
        willing_to_mentor=bool(row["willing_to_mentor"]), show_phone=bool(row["show_phone"]),
        role=row["role"], location_label=row["location_label"], lat=row["lat"], lng=row["lng"],
    )


def session_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in.")
    return authorization.split(" ", 1)[1].strip()


def current_user(token: str = Depends(session_token)) -> Member:
    """Resolve the logged-in, board-approved member from a live session, or 401.
    Approval is re-checked on every request, so revoking an account takes effect at once."""
    user_id = resolve_session(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["approval"] != "approved":
        raise HTTPException(status_code=401, detail="Account not active.")
    return member_from_row(row)


def require_admin(user: Member = Depends(current_user)) -> Member:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Alumni board members only.")
    return user


def clean_text(value: str | None, field: str | None = None, max_len: int | None = None) -> str | None:
    """Trim, remove control characters, collapse whitespace, and enforce a length limit."""
    value = " ".join(_CONTROL_CHARS.sub(" ", value or "").split())
    if not value:
        return None
    limit = max_len or (MAX_LEN.get(field, 200) if field else 200)
    if len(value) > limit:
        label = (field or "This field").replace("_", " ").capitalize()
        raise HTTPException(status_code=422, detail=f"{label} must be {limit} characters or fewer.")
    return value


def validate_profile(
    *, first_name: str, last_name: str, grad_year: int, status: str, rank: str | None,
    afsc: str | None, aircraft: str | None, job: str | None, base: str | None,
    city: str | None, phone: str | None,
) -> dict:
    """Shared rules for sign-up and profile edits. Fields that don't apply to the chosen
    military status are dropped, so the database never holds stale conditional values."""
    errors: list[str] = []
    values = {f: clean_text(v, f) for f, v in dict(
        first_name=first_name, last_name=last_name, rank=rank, afsc=afsc, aircraft=aircraft,
        job=job, base=base, city=city, phone=phone).items()}
    first_name, last_name = values["first_name"], values["last_name"]
    rank, afsc, aircraft, job = values["rank"], values["afsc"], values["aircraft"], values["job"]
    base, city, phone = values["base"], values["city"], values["phone"]
    if not first_name or not last_name:
        errors.append("First and last name are required.")
    if grad_year not in grad_years():
        errors.append("Choose a graduation year from the list.")
    if status not in STATUSES:
        errors.append("Choose a military status.")
    if phone and len(re.sub(r"\D", "", phone)) < 10:
        errors.append("Enter a 10-digit phone number.")

    if status in MILITARY_STATUSES:
        if rank not in RANK_CODES:
            errors.append("Choose your current rank.")
        with connect() as conn:
            if not afsc or not conn.execute("SELECT 1 FROM afscs WHERE code = ?", (afsc,)).fetchone():
                errors.append("Choose your current AFSC.")
        if afsc not in AIRCREW_AFSCS:
            aircraft = None
        if not canonical_base(base):
            errors.append("Choose your current base from the list.")
        else:
            base = canonical_base(base)["name"]
        city = None
    elif status == "Civilian":
        if not city:
            errors.append("Enter your current city or ZIP code.")
        rank = afsc = aircraft = base = None
    else:  # Cadet
        rank = afsc = aircraft = base = city = job = None

    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))
    return dict(first_name=first_name, last_name=last_name, grad_year=grad_year, status=status,
                rank=rank, afsc=afsc, aircraft=aircraft, job=job, base=base, city=city, phone=phone)


def check_new_password(password: str, confirm: str | None = None) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be {MAX_PASSWORD} characters or fewer.")
    if confirm is not None and password != confirm:
        raise HTTPException(status_code=422, detail="Passwords don't match.")


async def save_photo(photo: UploadFile | None) -> str | None:
    """Sanitize (re-encode, strip metadata, resize) and store an uploaded picture."""
    if photo is None or not photo.filename:
        return None
    data = await photo.read()
    try:
        clean, ext = await run_in_threadpool(sanitize_image, data)
    except BadImage as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    name = f"{uuid.uuid4().hex}{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / name).write_bytes(clean)
    return name


@router.post("/auth/signup", status_code=201)
async def signup(
    request: Request, background: BackgroundTasks,
    email: str = Form(...), confirm_email: str = Form(...),
    password: str = Form(...), confirm_password: str = Form(...),
    first_name: str = Form(...), last_name: str = Form(...),
    grad_year: int = Form(...), status: str = Form(...),
    rank: str | None = Form(None), afsc: str | None = Form(None),
    aircraft: str | None = Form(None), job: str | None = Form(None),
    base: str | None = Form(None), city: str | None = Form(None),
    phone: str | None = Form(None), willing_to_mentor: bool = Form(False),
    show_phone: bool = Form(True),
    photo: UploadFile | None = File(None),
) -> dict:
    ratelimit.check_and_hit("signup_ip", ratelimit.client_ip(request), "Too many sign-up attempts.")
    email = email.strip().lower()
    try:
        _email_adapter.validate_python(email)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if email != confirm_email.strip().lower():
        raise HTTPException(status_code=422, detail="Email addresses don't match.")
    check_new_password(password, confirm_password)
    profile = validate_profile(
        first_name=first_name, last_name=last_name, grad_year=grad_year, status=status,
        rank=rank, afsc=afsc, aircraft=aircraft, job=job, base=base, city=city, phone=phone)

    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
    # Geocoding may hit the network; run it off the event loop so other requests keep flowing.
    label, lat, lng = await run_in_threadpool(locate, profile["status"], profile["base"], profile["city"])
    photo_path = await save_photo(photo)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users (email, password_hash, first_name, last_name, grad_year, status, rank,
                               afsc, aircraft, job, base, city, phone, photo_path, willing_to_mentor,
                               show_phone, location_label, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email, hash_password(password), profile["first_name"], profile["last_name"],
             profile["grad_year"], profile["status"], profile["rank"], profile["afsc"],
             profile["aircraft"], profile["job"], profile["base"], profile["city"],
             profile["phone"], photo_path, int(willing_to_mentor), int(show_phone), label, lat, lng),
        )
        admins = [r["email"] for r in conn.execute(
            "SELECT email FROM users WHERE role = 'admin' AND approval = 'approved'")]
    background.add_task(new_account_alert, admins, {**profile, "email": email})
    return {"message": "Account created. The AFLAX alumni board will review it shortly."}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request) -> AuthResponse:
    email, ip = body.email.lower(), ratelimit.client_ip(request)
    ratelimit.check("login_email", email, "Too many failed login attempts for this account.")
    ratelimit.check("login_ip", ip, "Too many failed login attempts.")
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    # Same error whether the email is unknown or the password is wrong, so the response
    # never reveals which emails have accounts.
    if row is None or not verify_password(body.password, row["password_hash"]):
        ratelimit.hit("login_email", email)
        ratelimit.hit("login_ip", ip)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    ratelimit.clear("login_email", email)
    if row["approval"] == "pending":
        raise HTTPException(status_code=403, detail="Your account is waiting for alumni board approval. You'll be able to log in once it's approved.")
    if row["approval"] == "rejected":
        raise HTTPException(status_code=403, detail="This account was not approved. Contact the AFLAX alumni board for help.")
    user = member_from_row(row)
    return AuthResponse(token=create_session(user.id), user=user)


@router.post("/auth/logout", status_code=204)
def logout(token: str = Depends(session_token)) -> None:
    revoke_session(token)


@router.post("/auth/forgot")
def forgot_password(body: ForgotRequest, request: Request, background: BackgroundTasks) -> dict:
    email = body.email.lower()
    ratelimit.check_and_hit("forgot_ip", ratelimit.client_ip(request), "Too many reset requests.")
    ratelimit.check_and_hit("forgot_email", email, "Too many reset requests for this email.")
    with connect() as conn:
        row = conn.execute(
            "SELECT id, first_name FROM users WHERE email = ? AND password_hash IS NOT NULL "
            "AND approval != 'rejected'",
            (email,),
        ).fetchone()
    if row:
        token = create_reset_token(row["id"])
        background.add_task(password_reset_email, email, row["first_name"], token)
    # Identical response either way, so this can't be used to discover member emails.
    return {"message": "If that email has an account, a reset link is on its way. It expires in one hour."}


@router.post("/auth/reset")
def reset_password(body: ResetRequest) -> dict:
    check_new_password(body.new_password)
    user_id = consume_reset_token(body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    with connect() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(body.new_password), user_id))
    revoke_all_sessions(user_id)  # sign out everywhere after a reset
    return {"message": "Password updated. You can log in with your new password."}


@router.get("/me", response_model=Member)
def me(user: Member = Depends(current_user)) -> Member:
    return user


@router.put("/me", response_model=Member)
async def update_me(
    first_name: str = Form(...), last_name: str = Form(...),
    grad_year: int = Form(...), status: str = Form(...),
    rank: str | None = Form(None), afsc: str | None = Form(None),
    aircraft: str | None = Form(None), job: str | None = Form(None),
    base: str | None = Form(None), city: str | None = Form(None),
    phone: str | None = Form(None), willing_to_mentor: bool = Form(False),
    show_phone: bool = Form(True),
    photo: UploadFile | None = File(None),
    user: Member = Depends(current_user),
) -> Member:
    profile = validate_profile(
        first_name=first_name, last_name=last_name, grad_year=grad_year, status=status,
        rank=rank, afsc=afsc, aircraft=aircraft, job=job, base=base, city=city, phone=phone)
    label, lat, lng = await run_in_threadpool(locate, profile["status"], profile["base"], profile["city"])
    photo_path = await save_photo(photo)
    with connect() as conn:
        conn.execute(
            """
            UPDATE users SET first_name=?, last_name=?, grad_year=?, status=?, rank=?, afsc=?,
                   aircraft=?, job=?, base=?, city=?, phone=?, willing_to_mentor=?, show_phone=?,
                   location_label=?, lat=?, lng=?, photo_path=COALESCE(?, photo_path)
            WHERE id = ?
            """,
            (profile["first_name"], profile["last_name"], profile["grad_year"], profile["status"],
             profile["rank"], profile["afsc"], profile["aircraft"], profile["job"],
             profile["base"], profile["city"], profile["phone"], int(willing_to_mentor),
             int(show_phone), label, lat, lng, photo_path, user.id),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
    return member_from_row(row)


@router.post("/me/password")
def change_password(body: PasswordChange, user: Member = Depends(current_user),
                    token: str = Depends(session_token)) -> dict:
    check_new_password(body.new_password)
    with connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
        if not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(body.new_password), user.id))
    revoke_all_sessions(user.id, keep_token=token)  # other devices must log in again
    return {"message": "Password updated. You've been signed out on other devices."}


@router.get("/photos/{name}")
def photo(name: str, exp: int, sig: str) -> FileResponse:
    """Serve a profile picture only for a valid, unexpired signed link."""
    if not PHOTO_NAME.match(name) or not verify_photo_link(name, exp, sig):
        raise HTTPException(status_code=404, detail="Not found.")
    path = UPLOAD_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
