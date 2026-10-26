"""Static reference data: ranks, statuses, aircraft, bases, AFSC insights.

Bases and insights are curated JSON files in reference/. Base names are canonical
("Hill AFB, UT"); `canonical_base()` maps aliases like "Langley AFB, VA" onto them.
"""

import json
from datetime import date
from functools import lru_cache

from db import REFERENCE_DIR

STATUSES = ["Cadet", "Active Duty", "Guard/Reserve", "Civilian"]
MILITARY_STATUSES = {"Active Duty", "Guard/Reserve"}

RANKS = [
    {"code": "O-1", "title": "Second Lieutenant", "abbr": "2d Lt"},
    {"code": "O-2", "title": "First Lieutenant", "abbr": "1st Lt"},
    {"code": "O-3", "title": "Captain", "abbr": "Capt"},
    {"code": "O-4", "title": "Major", "abbr": "Maj"},
    {"code": "O-5", "title": "Lieutenant Colonel", "abbr": "Lt Col"},
    {"code": "O-6", "title": "Colonel", "abbr": "Col"},
    {"code": "O-7", "title": "Brigadier General", "abbr": "Brig Gen"},
    {"code": "O-8", "title": "Major General", "abbr": "Maj Gen"},
    {"code": "O-9", "title": "Lieutenant General", "abbr": "Lt Gen"},
]
RANK_CODES = {r["code"] for r in RANKS}

# Rated (aircrew) AFSCs. Choosing one of these on sign-up reveals the aircraft dropdown.
AIRCREW_AFSCS = {"92T0", "92T1", "92T2", "92T3"}

FIRST_GRAD_YEAR = 1967


def grad_years() -> list[int]:
    """1967 through four years from now, so current cadets can pick their class."""
    return list(range(date.today().year + 4, FIRST_GRAD_YEAR - 1, -1))


def _load(name: str):
    return json.loads((REFERENCE_DIR / name).read_text())


@lru_cache
def bases() -> list[dict]:
    return _load("bases.json")


@lru_cache
def aircraft() -> list[dict]:
    return _load("aircraft.json")


@lru_cache
def afsc_insights() -> dict[str, dict]:
    return _load("afsc_insights.json")["afscs"]


@lru_cache
def city_coords() -> dict[str, list[float]]:
    return _load("cities.json")["cities"]


@lru_cache
def _base_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for b in bases():
        for key in [b["name"], *b.get("aliases", [])]:
            index[key.lower()] = b
    return index


def canonical_base(name: str | None) -> dict | None:
    """Exact (case-insensitive) match on a base name or alias."""
    if not name:
        return None
    return _base_index().get(name.strip().lower())


def find_base(query: str) -> dict | None:
    """Looser lookup for the agent: exact name/alias, then 'hill' -> 'Hill AFB, UT'."""
    hit = canonical_base(query)
    if hit:
        return hit
    q = query.strip().lower()
    for b in bases():
        names = [b["name"], *b.get("aliases", [])]
        if any(q in n.lower() for n in names):
            return b
    return None


def base_names() -> list[str]:
    return sorted(b["name"] for b in bases())
