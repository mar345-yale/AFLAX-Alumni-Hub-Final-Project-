"""Portal endpoints: dropdown options, the alumni map/roster, the schedule, tailgates and
RSVPs, and the board's approval queue and chat-usage panel. Everything except
/api/options requires a logged-in, approved member; schedule writes, approvals, and usage
require a board admin.
"""

import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth import Member, current_user, member_from_row, require_admin
from db import connect
from geo import geocode_city
from reference import AIRCREW_AFSCS, RANKS, STATUSES, aircraft, base_names, grad_years
from security import signed_photo_url

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- options

@router.get("/options")
def options() -> dict:
    """Everything the sign-up form's dropdowns need (public, so sign-up works logged out)."""
    with connect() as conn:
        afscs = [dict(r) for r in conn.execute(
            "SELECT code, title, category FROM afscs ORDER BY category DESC, code")]
    return {
        "statuses": STATUSES,
        "ranks": RANKS,
        "afscs": afscs,
        "aircrew_afscs": sorted(AIRCREW_AFSCS),
        "aircraft": aircraft(),
        "bases": base_names(),
        "grad_years": grad_years(),
    }


# ---------------------------------------------------------------- alumni map + roster

def roster_entry(row, viewer: Member) -> dict:
    # Members can hide their phone; the board and the member themself still see it.
    phone_visible = bool(row["show_phone"]) or viewer.role == "admin" or viewer.id == row["id"]
    return {
        "id": row["id"],
        "last_name": row["last_name"],
        "first_name": row["first_name"],
        "grad_year": row["grad_year"],
        "status": row["status"],
        "rank": row["rank"],
        "afsc": row["afsc"],
        "afsc_title": row["afsc_title"],
        "aircraft": row["aircraft"],
        "job": row["job"],
        "location": row["location_label"] or row["base"] or row["city"],
        "phone": row["phone"] if phone_visible else None,
        "phone_hidden": not row["show_phone"],
        "email": row["email"],
        "photo_url": signed_photo_url(row["photo_path"]),
        "willing_to_mentor": bool(row["willing_to_mentor"]),
    }


@router.get("/alumni")
def alumni(
    status: str | None = None, base: str | None = None, afsc: str | None = None,
    location: str | None = None, viewer: Member = Depends(current_user),
) -> dict:
    """Map pins (one per location, with a head count) for the Status/Base/AFSC filters,
    plus the roster in last-name order. `location` (a clicked pin) narrows only the roster."""
    where, params = ["u.approval = 'approved'"], []
    if status:
        where.append("u.status = ?")
        params.append(status)
    if base:
        where.append("u.base = ?")
        params.append(base)
    if afsc:
        where.append("u.afsc = ?")
        params.append(afsc)
    sql = f"""
        SELECT u.*, a.title AS afsc_title FROM users u LEFT JOIN afscs a ON a.code = u.afsc
        WHERE {' AND '.join(where)}
        ORDER BY u.last_name COLLATE NOCASE, u.first_name COLLATE NOCASE
    """
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        facet_rows = conn.execute(
            """
            SELECT DISTINCT u.base, u.afsc, a.title FROM users u LEFT JOIN afscs a ON a.code = u.afsc
            WHERE u.approval = 'approved'
            """
        ).fetchall()

    pins: dict[str, dict] = {}
    for r in rows:
        if r["lat"] is None:
            continue
        pin = pins.setdefault(r["location_label"], {
            "label": r["location_label"], "lat": r["lat"], "lng": r["lng"], "count": 0})
        pin["count"] += 1
    roster = [roster_entry(r, viewer) for r in rows if not location or r["location_label"] == location]
    return {
        "pins": sorted(pins.values(), key=lambda p: -p["count"]),
        "roster": roster,
        "total": len(rows),
        "unmapped": sum(1 for r in rows if r["lat"] is None),
        "facets": {
            "statuses": STATUSES,
            "bases": sorted({r["base"] for r in facet_rows if r["base"]}),
            "afscs": sorted({(r["afsc"], r["title"]) for r in facet_rows if r["afsc"]}),
        },
    }


# ---------------------------------------------------------------- schedule + tailgates

def _required(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("This field is required.")
    return v


class GameIn(BaseModel):
    game_date: date
    time_label: str = Field("", max_length=30)
    home_away: str
    opponent: str = Field(max_length=80)
    location: str = Field(max_length=80)
    venue: str = Field("", max_length=100)
    tournament: str = Field("", max_length=80)
    result: str = Field("", max_length=30)

    @field_validator("home_away")
    @classmethod
    def valid_site(cls, v: str) -> str:
        if v not in {"Home", "Away", "Neutral"}:
            raise ValueError("Choose Home, Away, or Neutral.")
        return v

    @field_validator("opponent", "location")
    @classmethod
    def required(cls, v: str) -> str:
        return _required(v)


class TailgateIn(BaseModel):
    game_id: int
    title: str = Field(max_length=80)
    location: str = Field(max_length=120)
    start_time: str = Field("", max_length=30)
    details: str = Field("", max_length=500)
    host: str = Field("", max_length=80)

    @field_validator("title", "location")
    @classmethod
    def required(cls, v: str) -> str:
        return _required(v)


@router.get("/schedule")
def schedule(viewer: Member = Depends(current_user)) -> dict:
    with connect() as conn:
        games = [dict(r) for r in conn.execute("SELECT * FROM games ORDER BY game_date")]
        tailgates = [dict(r) for r in conn.execute("SELECT * FROM tailgates ORDER BY id")]
        rsvps = conn.execute(
            """
            SELECT r.tailgate_id, u.id, u.first_name, u.last_name, u.grad_year
            FROM tailgate_rsvps r JOIN users u ON u.id = r.user_id
            ORDER BY r.created_at
            """
        ).fetchall()
    going: dict[int, list[dict]] = {}
    for r in rsvps:
        going.setdefault(r["tailgate_id"], []).append(
            {"id": r["id"], "name": f"{r['first_name']} {r['last_name']}", "grad_year": r["grad_year"]})
    by_game: dict[int, list[dict]] = {}
    for t in tailgates:
        attendees = going.get(t["id"], [])
        t["attendees"] = attendees
        t["rsvp_count"] = len(attendees)
        t["going"] = any(a["id"] == viewer.id for a in attendees)
        by_game.setdefault(t["game_id"], []).append(t)
    for g in games:
        g["tailgates"] = by_game.get(g["id"], [])
    today = date.today().isoformat()
    upcoming = [g for g in games if g["game_date"] >= today]
    seasons = sorted({int(g["game_date"][:4]) for g in games})
    return {"games": games, "next_game_id": upcoming[0]["id"] if upcoming else None,
            "seasons": seasons}


@router.post("/tailgates/{tailgate_id}/rsvp", status_code=204)
def rsvp(tailgate_id: int, viewer: Member = Depends(current_user)) -> None:
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM tailgates WHERE id = ?", (tailgate_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Tailgate not found.")
        conn.execute("INSERT OR IGNORE INTO tailgate_rsvps (tailgate_id, user_id) VALUES (?, ?)",
                     (tailgate_id, viewer.id))


@router.delete("/tailgates/{tailgate_id}/rsvp", status_code=204)
def cancel_rsvp(tailgate_id: int, viewer: Member = Depends(current_user)) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM tailgate_rsvps WHERE tailgate_id = ? AND user_id = ?",
                     (tailgate_id, viewer.id))


def _game_coords(location: str) -> tuple[float | None, float | None]:
    if location.strip().lower() in {"usafa, co", "air force academy, co", "colorado springs, co"}:
        return 38.997, -104.844
    hit = geocode_city(location)
    return (hit[1], hit[2]) if hit else (None, None)


@router.post("/games", status_code=201)
def add_game(body: GameIn, _: Member = Depends(require_admin)) -> dict:
    lat, lng = _game_coords(body.location)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO games (game_date, time_label, home_away, opponent, location, venue,
                               tournament, result, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (body.game_date.isoformat(), body.time_label.strip(), body.home_away, body.opponent,
             body.location, body.venue.strip(), body.tournament.strip(), body.result.strip(), lat, lng),
        )
    return {"id": cur.lastrowid, "mapped": lat is not None}


@router.put("/games/{game_id}")
def update_game(game_id: int, body: GameIn, _: Member = Depends(require_admin)) -> dict:
    lat, lng = _game_coords(body.location)
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE games SET game_date=?, time_label=?, home_away=?, opponent=?, location=?,
                   venue=?, tournament=?, result=?, lat=?, lng=? WHERE id = ?
            """,
            (body.game_date.isoformat(), body.time_label.strip(), body.home_away, body.opponent,
             body.location, body.venue.strip(), body.tournament.strip(), body.result.strip(),
             lat, lng, game_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Game not found.")
    return {"id": game_id, "mapped": lat is not None}


@router.delete("/games/{game_id}", status_code=204)
def delete_game(game_id: int, _: Member = Depends(require_admin)) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM games WHERE id = ?", (game_id,))


@router.post("/tailgates", status_code=201)
def add_tailgate(body: TailgateIn, admin: Member = Depends(require_admin)) -> dict:
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM games WHERE id = ?", (body.game_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Game not found.")
        cur = conn.execute(
            """
            INSERT INTO tailgates (game_id, title, location, start_time, details, host, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (body.game_id, body.title, body.location, body.start_time.strip(),
             body.details.strip(), body.host.strip() or f"{admin.first_name} {admin.last_name}",
             admin.id),
        )
    return {"id": cur.lastrowid}


@router.put("/tailgates/{tailgate_id}")
def update_tailgate(tailgate_id: int, body: TailgateIn, _: Member = Depends(require_admin)) -> dict:
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE tailgates SET game_id=?, title=?, location=?, start_time=?, details=?, host=?
            WHERE id = ?
            """,
            (body.game_id, body.title, body.location, body.start_time.strip(),
             body.details.strip(), body.host.strip(), tailgate_id),
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Tailgate not found.")
    return {"id": tailgate_id}


@router.delete("/tailgates/{tailgate_id}", status_code=204)
def delete_tailgate(tailgate_id: int, _: Member = Depends(require_admin)) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM tailgates WHERE id = ?", (tailgate_id,))


# ---------------------------------------------------------------- board approvals

class RoleChange(BaseModel):
    role: str


def _admin_view(row) -> dict:
    m = member_from_row(row).model_dump()
    m["approval"] = row["approval"]
    m["created_at"] = row["created_at"]
    m["source"] = row["source"]
    return m


@router.get("/admin/accounts")
def accounts(_: Member = Depends(require_admin)) -> dict:
    """Real sign-ups (not the seeded test profiles), pending first."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users WHERE source = 'signup'
            ORDER BY CASE approval WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                     created_at DESC
            """
        ).fetchall()
    return {"accounts": [_admin_view(r) for r in rows]}


def _set_approval(user_id: int, approval: str) -> dict:
    with connect() as conn:
        cur = conn.execute("UPDATE users SET approval = ? WHERE id = ?", (approval, user_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {"id": user_id, "approval": approval}


@router.post("/admin/accounts/{user_id}/approve")
def approve(user_id: int, _: Member = Depends(require_admin)) -> dict:
    return _set_approval(user_id, "approved")


@router.post("/admin/accounts/{user_id}/reject")
def reject(user_id: int, admin: Member = Depends(require_admin)) -> dict:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't reject your own account.")
    return _set_approval(user_id, "rejected")


@router.post("/admin/accounts/{user_id}/role")
def set_role(user_id: int, body: RoleChange, admin: Member = Depends(require_admin)) -> dict:
    if body.role not in {"member", "admin"}:
        raise HTTPException(status_code=422, detail="Role must be member or admin.")
    if user_id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="You can't remove your own board access.")
    with connect() as conn:
        cur = conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {"id": user_id, "role": body.role}


# ---------------------------------------------------------------- chat usage (tokenomics)

def _price(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


@router.get("/admin/usage")
def usage(_: Member = Depends(require_admin)) -> dict:
    """Falcon Mentor token usage. Set PRICE_INPUT_PER_M / PRICE_CACHED_INPUT_PER_M /
    PRICE_OUTPUT_PER_M (USD per million tokens) in .env to see estimated cost."""
    windows = {"today": "date(created_at) = date('now')",
               "7d": "created_at >= datetime('now', '-7 days')",
               "30d": "created_at >= datetime('now', '-30 days')"}
    totals = {}
    with connect() as conn:
        for key, cond in windows.items():
            r = conn.execute(
                f"""
                SELECT COUNT(*) AS messages, COALESCE(SUM(requests), 0) AS requests,
                       COALESCE(SUM(tool_calls), 0) AS tool_calls,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                       COALESCE(AVG(duration_ms), 0) AS avg_ms,
                       COALESCE(SUM(status = 'error'), 0) AS errors
                FROM chat_usage WHERE {cond}
                """
            ).fetchone()
            totals[key] = dict(r)
        top = conn.execute(
            """
            SELECT u.first_name || ' ' || u.last_name AS name, COUNT(*) AS messages,
                   SUM(c.input_tokens + c.output_tokens) AS tokens
            FROM chat_usage c JOIN users u ON u.id = c.user_id
            WHERE c.created_at >= datetime('now', '-30 days')
            GROUP BY c.user_id ORDER BY tokens DESC LIMIT 5
            """
        ).fetchall()
        recent = conn.execute(
            """
            SELECT c.created_at, u.first_name || ' ' || u.last_name AS name, c.requests,
                   c.tool_calls, c.input_tokens, c.cache_read_tokens, c.output_tokens,
                   c.duration_ms, c.status
            FROM chat_usage c JOIN users u ON u.id = c.user_id
            ORDER BY c.id DESC LIMIT 10
            """
        ).fetchall()
    prices = {"input": _price("PRICE_INPUT_PER_M"), "cached_input": _price("PRICE_CACHED_INPUT_PER_M"),
              "output": _price("PRICE_OUTPUT_PER_M")}
    for t in totals.values():
        if prices["input"] is not None and prices["output"] is not None:
            cached_price = prices["cached_input"] if prices["cached_input"] is not None else prices["input"]
            fresh = t["input_tokens"] - t["cache_read_tokens"]
            t["est_cost_usd"] = round((fresh * prices["input"] + t["cache_read_tokens"] * cached_price
                                       + t["output_tokens"] * prices["output"]) / 1_000_000, 4)
        else:
            t["est_cost_usd"] = None
    return {"totals": totals, "top_users": [dict(r) for r in top],
            "recent": [dict(r) for r in recent],
            "daily_limit": int(os.getenv("CHAT_DAILY_LIMIT", "40"))}
