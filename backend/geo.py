"""Turn a member's base or city into a map pin.

Bases come from the curated bases.json. Cities use the offline table in cities.json
first, then a cached OpenStreetMap (Nominatim) lookup, so the same place is only ever
geocoded once. If nothing resolves, the member still appears in the roster, just not on
the map.
"""

import httpx

from db import connect
from reference import canonical_base, city_coords

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AFLAX-Alumni-Portal/1.0 (course project)"


def _normalize_city(text: str) -> str:
    return " ".join(text.replace(" ,", ",").split()).lower()


def _nominatim(query: str) -> tuple[str, float, float] | None:
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": USER_AGENT},
            timeout=5.0,
        )
        resp.raise_for_status()
        results = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    hit = results[0]
    return query, float(hit["lat"]), float(hit["lon"])


def geocode_city(text: str, allow_network: bool = True) -> tuple[str, float, float] | None:
    """Return (label, lat, lng) for 'City, ST' or a ZIP code."""
    if not text or not text.strip():
        return None
    label = text.strip()
    key = _normalize_city(label)
    if key in city_coords():
        lat, lng = city_coords()[key]
        return label, lat, lng
    with connect() as conn:
        row = conn.execute("SELECT label, lat, lng FROM geocache WHERE query = ?", (key,)).fetchone()
    if row:
        return (row["label"], row["lat"], row["lng"]) if row["lat"] is not None else None
    if not allow_network:
        return None
    hit = _nominatim(label)
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO geocache (query, label, lat, lng) VALUES (?, ?, ?, ?)",
            (key, hit[0] if hit else label, hit[1] if hit else None, hit[2] if hit else None),
        )
    return hit


def locate(status: str, base: str | None, city: str | None, allow_network: bool = True):
    """Map pin for a member: their base if military, their city if civilian.
    Returns (location_label, lat, lng), with Nones when it can't be placed."""
    if status in {"Active Duty", "Guard/Reserve"} and base:
        b = canonical_base(base)
        if b:
            return b["name"], b["lat"], b["lng"]
        return base, None, None
    if status == "Cadet":
        b = canonical_base("US Air Force Academy, CO")
        return b["name"], b["lat"], b["lng"]
    if city:
        hit = geocode_city(city, allow_network=allow_network)
        if hit:
            return hit
        return city, None, None
    return None, None, None
