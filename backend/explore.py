"""AFSC and Base Explorer: browse the same career-field and base guides the agent uses,
with zero model calls. Every question answered here is one Falcon Mentor doesn't have to
spend tokens on.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth import Member, current_user
from db import connect
from reference import afsc_insights, bases, find_base
from security import signed_photo_url
from tools import _alumni_counts_by, official_description

router = APIRouter(prefix="/api/explore", tags=["explore"])


def _alumni(where: str, value: str, viewer: Member) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT u.*, a.title AS afsc_title FROM users u LEFT JOIN afscs a ON a.code = u.afsc
            WHERE u.approval = 'approved' AND u.status != 'Cadet' AND {where} = ?
            ORDER BY u.last_name COLLATE NOCASE
            """,
            (value,),
        ).fetchall()
    return [{
        "id": r["id"], "first_name": r["first_name"], "last_name": r["last_name"],
        "grad_year": r["grad_year"], "status": r["status"], "rank": r["rank"],
        "afsc": r["afsc"], "afsc_title": r["afsc_title"], "job": r["job"],
        "location": r["location_label"], "email": r["email"],
        "phone": r["phone"] if (r["show_phone"] or viewer.role == "admin") else None,
        "photo_url": signed_photo_url(r["photo_path"]),
        "willing_to_mentor": bool(r["willing_to_mentor"]),
    } for r in rows]


@router.get("/afscs")
def list_afscs(_: Member = Depends(current_user)) -> list[dict]:
    counts = _alumni_counts_by("afsc")
    insights = afsc_insights()
    with connect() as conn:
        rows = conn.execute("SELECT code, title, category FROM afscs ORDER BY category DESC, code").fetchall()
    return [{
        "code": r["code"], "title": r["title"], "category": r["category"],
        "overview": insights.get(r["code"], {}).get("overview", ""),
        "keywords": insights.get(r["code"], {}).get("keywords", []),
        "alumni_count": counts.get(r["code"], 0),
    } for r in rows]


@router.get("/afscs/{code}")
def afsc_detail(code: str, viewer: Member = Depends(current_user)) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT code, title, category FROM afscs WHERE code = ?", (code.upper(),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="AFSC not found.")
    info = afsc_insights().get(row["code"], {})
    return {
        **dict(row),
        **{k: info.get(k, "") for k in ("overview", "training", "lifestyle", "good_fit")},
        "typical_bases": info.get("typical_bases", []),
        "official_description": official_description(row["code"], limit=None),
        "alumni": _alumni("u.afsc", row["code"], viewer),
    }


@router.get("/bases")
def list_bases(_: Member = Depends(current_user)) -> list[dict]:
    counts = _alumni_counts_by("base")
    return [{
        "name": b["name"], "region": b["region"], "type": b["type"],
        "nearby_city": b["nearby_city"], "missions": b["missions"], "aircraft": b["aircraft"],
        "cost_of_living": b["cost_of_living"], "alumni_count": counts.get(b["name"], 0),
    } for b in sorted(bases(), key=lambda b: b["name"])]


@router.get("/bases/{name}")
def base_detail(name: str, viewer: Member = Depends(current_user)) -> dict:
    b = find_base(name)
    if b is None:
        raise HTTPException(status_code=404, detail="Base not found.")
    return {**{k: v for k, v in b.items() if k != "aliases"},
            "alumni": _alumni("u.base", b["name"], viewer)}
