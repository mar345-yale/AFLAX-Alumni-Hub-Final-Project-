"""Cadet Mentorship agent tools.

Career-field knowledge: search_afscs, get_afsc_details   (AFSC PDF + afsc_insights.json)
Base knowledge:         search_bases, get_base_details    (bases.json)
Alumni connection:      find_mentors, count_alumni        (members database)
Outreach:               draft_intro_message               (members database)

Each function's docstring is the description the model sees. Tools return only what the
model needs to reason; mentor contact details are attached to the response afterward
from the database (see mentor_cards), so the model never has to copy emails or phones.
"""

import re

from db import connect
from reference import RANKS, afsc_insights, bases, find_base
from security import signed_photo_url

OFFICIAL_TEXT_LIMIT = 2500  # keep tool output (and token cost) bounded
RANK_ABBR = {r["code"]: r["abbr"] for r in RANKS}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9\-]+", text.lower()) if len(w) > 2]


def _afsc_rows() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM afscs ORDER BY code")]


def _alumni_counts_by(column: str) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {column} AS k, COUNT(*) AS n FROM users
            WHERE approval = 'approved' AND status != 'Cadet' AND {column} IS NOT NULL
            GROUP BY {column}
            """
        ).fetchall()
    return {r["k"]: r["n"] for r in rows}


# ------------------------------------------------------------ career fields

def search_afscs(query: str = "", category: str | None = None) -> list[dict]:
    """Find officer career fields (AFSCs) that match a cadet's interests.

    Args:
        query: Interests or keywords, e.g. "flying", "computers and coding", "space",
            "leading people", "engineering". Leave empty to list every AFSC.
        category: Optional "Rated" (aircrew: pilot, CSO, ABM, RPA) or "Nonrated".

    Returns up to 6 matches with code, title, category, a one-line overview, and how many
    AFLAX alumni hold that AFSC.
    """
    insights = afsc_insights()
    counts = _alumni_counts_by("afsc")
    terms = _words(query)
    scored = []
    for row in _afsc_rows():
        if category and row["category"].lower() != category.lower():
            continue
        info = insights.get(row["code"], {})
        haystack = " ".join([row["title"], info.get("overview", ""), info.get("good_fit", ""),
                             " ".join(info.get("keywords", []))]).lower()
        keyword_text = " ".join(info.get("keywords", [])).lower()
        score = sum(2 if t in keyword_text else 1 for t in terms if t in haystack)
        if row["code"].lower() == query.strip().lower():
            score += 10
        if terms and score == 0:
            continue
        scored.append((score, row, info))
    scored.sort(key=lambda s: (-s[0], s[1]["code"]))
    return [
        {"code": row["code"], "title": row["title"], "category": row["category"],
         "overview": info.get("overview", ""), "alumni_count": counts.get(row["code"], 0)}
        for _, row, info in scored[:6]
    ]


def get_afsc_details(afsc_code: str, include_official: bool = False) -> dict:
    """One AFSC: plain-language overview, training pipeline, typical bases, lifestyle, who
    it suits, and how many AFLAX alumni hold it.

    Args:
        afsc_code: The AFSC code, e.g. "92T0", "13S1", "62E1C". A job title like
            "Space Operations" also works.
        include_official: Also return the long official Air Force duty description. Only
            set this when the cadet asks for official duties/responsibilities.
    """
    rows = _afsc_rows()
    q = afsc_code.strip().lower()
    row = next((r for r in rows if r["code"].lower() == q), None) or next(
        (r for r in rows if q and q in r["title"].lower()), None)
    if row is None:
        return {"error": f"No AFSC matches '{afsc_code}'. Use search_afscs to find valid codes."}
    info = afsc_insights().get(row["code"], {})
    details = {
        "code": row["code"], "title": row["title"], "category": row["category"],
        "overview": info.get("overview", ""), "training": info.get("training", ""),
        "typical_bases": info.get("typical_bases", []), "lifestyle": info.get("lifestyle", ""),
        "good_fit": info.get("good_fit", ""),
        "alumni_count": _alumni_counts_by("afsc").get(row["code"], 0),
    }
    if include_official:
        details["official_description"] = official_description(row["code"])
    return details


def official_description(code: str, limit: int | None = OFFICIAL_TEXT_LIMIT) -> str:
    """Official PDF text for an AFSC (engineering shreds include their 62E1A parent)."""
    rows = {r["code"]: r for r in _afsc_rows()}
    row = rows.get(code)
    if row is None:
        return ""
    official = row["description"] or "(The source PDF has no description for this code.)"
    # Engineering shreds read "Same as 62E1A. Except for ..." - include the parent text.
    parent = re.search(r"Same as (\w+)", official)
    if parent and parent.group(1) in rows:
        official = f"{official} | {parent.group(1)} description: {rows[parent.group(1)]['description']}"
    if limit and len(official) > limit:
        official = official[:limit].rsplit(" ", 1)[0] + " ..."
    return official


# ------------------------------------------------------------ bases

def search_bases(query: str = "", region: str | None = None, aircraft: str | None = None) -> list[dict]:
    """Find Air Force / Space Force installations.

    Args:
        query: Free text matched against base name, state, nearby city, missions, and type,
            e.g. "Colorado", "pilot training", "space launch", "beach", "Europe".
        region: Optional region, one of: Pacific Northwest, California, Southwest,
            Mountain West, Great Plains, Texas, South, Southeast, Florida, Midwest,
            Mid-Atlantic, Northeast, Alaska, Hawaii & Pacific, Europe, Asia-Pacific,
            Middle East, Arctic.
        aircraft: Optional aircraft designation flown there, e.g. "F-35A", "C-17A", "T-38C".

    Returns up to 8 bases with name, region, type, nearby city, main missions, aircraft, and
    AFLAX alumni count. Use get_base_details for pros, cons, and cost of living.
    """
    counts = _alumni_counts_by("base")
    terms = _words(query)
    out = []
    for b in bases():
        if region and b["region"].lower() != region.lower():
            continue
        if aircraft and not any(aircraft.lower().replace(" ", "") in a.lower().replace(" ", "")
                                for a in b["aircraft"]):
            continue
        haystack = " ".join([b["name"], *b.get("aliases", []), b["region"], b["type"],
                             b["nearby_city"], " ".join(b["missions"]),
                             " ".join(b["aircraft"]), " ".join(b["pros"])]).lower()
        score = sum(1 for t in terms if t in haystack)
        if terms and score == 0:
            continue
        out.append((score, b))
    out.sort(key=lambda s: (-s[0], s[1]["name"]))
    return [
        {"name": b["name"], "region": b["region"], "type": b["type"],
         "nearby_city": b["nearby_city"], "missions": b["missions"][:2],
         "aircraft": b["aircraft"][:5], "alumni_count": counts.get(b["name"], 0)}
        for _, b in out[:8]
    ]


def get_base_details(base: str) -> dict:
    """Full profile of one installation: location, missions, aircraft, cost of living,
    honest pros and cons, plus how many AFLAX alumni are there and which AFSCs they hold.

    Args:
        base: Base name, e.g. "Hill AFB, UT", "Hill", "Ramstein", "JBSA-Lackland".
    """
    b = find_base(base)
    if b is None:
        return {"error": f"No base matches '{base}'. Use search_bases to find valid names."}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT u.afsc, a.title, COUNT(*) AS n FROM users u LEFT JOIN afscs a ON a.code = u.afsc
            WHERE u.approval = 'approved' AND u.base = ? GROUP BY u.afsc ORDER BY n DESC
            """,
            (b["name"],),
        ).fetchall()
    return {
        **{k: b[k] for k in ("name", "region", "type", "nearby_city", "missions", "aircraft",
                             "cost_of_living", "pros", "cons")},
        "alumni_count": sum(r["n"] for r in rows),
        "alumni_afscs": [{"afsc": r["afsc"], "title": r["title"], "count": r["n"]} for r in rows],
    }


# ------------------------------------------------------------ alumni connection

def find_mentors(
    afsc: str | None = None, base: str | None = None, career_field: str | None = None,
    limit: int = 5, exclude_user_id: int | None = None,
) -> list[dict]:
    """AFLAX alumni who opted in to mentoring and match a cadet's interest, best first.
    Ranking: exact AFSC match, then same career-field family (e.g. any 62E engineer),
    then same base, then keyword match on job and career field; currently serving
    officers rank slightly above civilians for the same match.

    Args:
        afsc: AFSC code of interest, e.g. "92T0".
        base: Base of interest, e.g. "Hill AFB, UT" or "Hill".
        career_field: Free-text interest, e.g. "space", "acquisition", "airline pilot".
        limit: How many mentors to return (1-8).

    Returns mentor_id, name, class year, status, rank, AFSC and title, job, location, and
    why they matched. Put the mentor_id values you recommend in mentor_ids.
    """
    limit = max(1, min(limit, 8))
    base_name = (find_base(base) or {}).get("name") if base else None
    afsc = afsc.strip().upper() if afsc else None
    terms = _words(career_field or "")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT u.*, a.title AS afsc_title FROM users u LEFT JOIN afscs a ON a.code = u.afsc
            WHERE u.approval = 'approved' AND u.willing_to_mentor = 1 AND u.status != 'Cadet'
            """
        ).fetchall()
    scored = []
    for r in rows:
        if exclude_user_id and r["id"] == exclude_user_id:
            continue
        score, reasons = 0.0, []
        if afsc and r["afsc"] == afsc:
            score += 6
            reasons.append(f"holds {afsc}")
        elif afsc and r["afsc"] and r["afsc"][:3] == afsc[:3]:
            score += 3
            reasons.append(f"same career-field family ({r['afsc']})")
        if base_name and r["base"] == base_name:
            score += 4
            reasons.append(f"stationed at {base_name}")
        if terms:
            text = " ".join(filter(None, [r["job"], r["afsc_title"], r["aircraft"]])).lower()
            hits = [t for t in terms if t in text]
            if hits:
                score += 1.5 * len(hits)
                reasons.append("works in " + ", ".join(hits))
        if score == 0:
            continue
        if r["status"] in {"Active Duty", "Guard/Reserve"}:
            score += 0.5
        scored.append((score, r, reasons))
    scored.sort(key=lambda s: (-s[0], -s[1]["grad_year"]))
    return [
        {"mentor_id": r["id"], "name": f"{r['first_name']} {r['last_name']}",
         "class_year": r["grad_year"], "status": r["status"], "rank": r["rank"],
         "afsc": r["afsc"], "afsc_title": r["afsc_title"], "job": r["job"],
         "location": r["location_label"], "match_reason": "; ".join(reasons)}
        for _, r, reasons in scored[:limit]
    ]


def count_alumni(afsc: str | None = None, base: str | None = None, status: str | None = None) -> dict:
    """Count AFLAX alumni (not cadets) matching optional filters, with a breakdown.

    Args:
        afsc: AFSC code, e.g. "92T0".
        base: Base name, e.g. "Nellis AFB, NV" or "Nellis".
        status: "Active Duty", "Guard/Reserve", or "Civilian".

    Returns the total plus the top locations (or top AFSCs, when filtering by base).
    """
    where, params = ["u.approval = 'approved'", "u.status != 'Cadet'"], []
    base_name = None
    if afsc:
        where.append("u.afsc = ?")
        params.append(afsc.strip().upper())
    if base:
        base_name = (find_base(base) or {}).get("name", base)
        where.append("u.base = ?")
        params.append(base_name)
    if status:
        where.append("u.status = ?")
        params.append(status)
    group = "u.afsc" if base else "u.location_label"
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM users u WHERE {' AND '.join(where)}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT {group} AS k, COUNT(*) AS n FROM users u WHERE {' AND '.join(where)}
            GROUP BY {group} ORDER BY n DESC LIMIT 8
            """,
            params,
        ).fetchall()
    return {"total": total, "filters": {"afsc": afsc, "base": base_name, "status": status},
            "breakdown_by": "afsc" if base else "location",
            "breakdown": [{"value": r["k"], "count": r["n"]} for r in rows if r["k"]]}


# ------------------------------------------------------------ outreach

def mentor_row(mentor_id: int):
    with connect() as conn:
        return conn.execute(
            """
            SELECT u.*, a.title AS afsc_title FROM users u LEFT JOIN afscs a ON a.code = u.afsc
            WHERE u.id = ? AND u.approval = 'approved' AND u.willing_to_mentor = 1
                  AND u.status != 'Cadet'
            """,
            (mentor_id,),
        ).fetchone()


def draft_intro_message(mentor_id: int, topic: str, sender_name: str, sender_class: int | None) -> dict:
    """Template behind the agent's draft_intro_message tool (see agent.py)."""
    r = mentor_row(mentor_id)
    if r is None:
        return {"error": f"mentor_id {mentor_id} is not an available mentor. Use find_mentors first."}
    abbr = RANK_ABBR.get(r["rank"] or "")
    serving = r["status"] in {"Active Duty", "Guard/Reserve"}
    salutation = f"{abbr} {r['last_name']}" if serving and abbr else f"{r['first_name']} {r['last_name']}"
    class_line = f"Class of {sender_class}" if sender_class else "a current cadet"
    what = f"the {r['afsc_title']} career field" if r["afsc_title"] else "your career field"
    where = r["location_label"] or "your current assignment"
    body = (
        f"Dear {salutation},\n\n"
        f"My name is {sender_name}, {class_line} and a member of the Air Force Lacrosse family. "
        f"I found you through the AFLAX Alumni Connections portal.\n\n"
        f"I'm weighing my options and am especially interested in {topic}. Given your experience "
        f"in {what} ({where}), I'd be grateful for 15-20 minutes of your time to hear what the "
        f"job is really like and any advice you'd give a cadet making this decision.\n\n"
        f"I'm happy to work around your schedule by phone or video. Thank you for considering it, "
        f"and Go Falcons!\n\n"
        f"Respectfully,\n{sender_name}"
    )
    return {"mentor_id": mentor_id, "mentor_name": f"{r['first_name']} {r['last_name']}",
            "subject": f"AFLAX cadet seeking advice on {topic}", "body": body}


def mentor_cards(mentor_ids: list[int]) -> list[dict]:
    """Contact cards for the UI, read fresh from the database (never model-authored)."""
    cards = []
    for mid in mentor_ids:
        r = mentor_row(mid)
        if r is None:
            continue
        cards.append({
            "id": r["id"], "first_name": r["first_name"], "last_name": r["last_name"],
            "grad_year": r["grad_year"], "status": r["status"], "rank": r["rank"],
            "afsc": r["afsc"], "afsc_title": r["afsc_title"], "aircraft": r["aircraft"],
            "job": r["job"], "location": r["location_label"], "email": r["email"],
            "phone": r["phone"] if r["show_phone"] else None,
            "photo_url": signed_photo_url(r["photo_path"]),
        })
    return cards
