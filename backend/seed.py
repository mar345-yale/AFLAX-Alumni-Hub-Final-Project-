"""Build data/aflax.db from the source files in ../DATA plus the curated reference JSON.

Run from the backend/ folder (with the project venv active):
    python seed.py          # create the database if it doesn't exist yet
    python seed.py --reset  # wipe all tables and reload everything (removes sign-ups!)

Loads:
  - AFSC codes, titles, categories (USAFA_Test_Profiles.xlsx -> 'AFSC Reference')
  - Official AFSC descriptions (Air Force AFSC data.pdf)
  - 100 fictional test profiles (USAFA_Test_Profiles.xlsx -> 'Profiles'), pre-approved
    and opted in to mentoring; they have no password, so nobody can log in as them
  - The 2026 lacrosse schedule and sample tailgates (reference/schedule_2026.json)
  - The first board admin account (generic; password from ADMIN_PASSWORD or randomly
    generated and printed once) and the temporary grader account
"""

import json
import os
import re
import secrets
import sys
from pathlib import Path

import openpyxl
from pypdf import PdfReader

import config  # noqa: F401  (loads .env, e.g. ADMIN_PASSWORD)
from db import BACKEND_DIR, REFERENCE_DIR, connect, init_schema
from geo import locate
from reference import canonical_base
from security import hash_password

SOURCE_DIR = BACKEND_DIR.parent / "DATA"
PROFILES_XLSX = SOURCE_DIR / "USAFA_Test_Profiles.xlsx"
AFSC_PDF = SOURCE_DIR / "Air Force AFSC data.pdf"

# Generic first board admin. No password is published: set ADMIN_PASSWORD in .env to choose
# one, otherwise a random password is generated and printed once when the database is built.
_ADMIN_PASSWORD_FROM_ENV = bool(os.getenv("ADMIN_PASSWORD", "").strip())
ADMIN = {
    "email": "admin@aflax.example",
    "password": os.getenv("ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12),
    "first_name": "Board",
    "last_name": "Admin",
    "grad_year": 2017,
    "status": "Civilian",
}

# Temporary account for the professor/TA to grade the project. It has board access so every
# page (including the Board tools) can be reviewed. DELETE BEFORE LAUNCHING to real alumni.
GRADER = {
    "email": "grader@aflax.example",
    "password": "GoFalcons2026!",
    "first_name": "Course",
    "last_name": "Grader",
    "grad_year": 2017,
    "status": "Civilian",
    "job": "Project Grader (temporary test account)",
    "city": "Colorado Springs, CO",
}

STATUS_MAP = {"Active Duty": "Active Duty", "Reserve": "Guard/Reserve", "Guard": "Guard/Reserve",
              "Civilian": "Civilian", "Cadet": "Cadet"}


def load_afsc_reference() -> list[tuple[str, str, str]]:
    wb = openpyxl.load_workbook(PROFILES_XLSX, read_only=True, data_only=True)
    rows = list(wb["AFSC Reference"].iter_rows(values_only=True))[1:]
    return [(str(c).strip(), str(t).strip(), str(cat).strip()) for c, t, cat in rows if c]


def load_afsc_descriptions(codes: list[str]) -> dict[str, str]:
    """Split the PDF text into one block per AFSC code (codes start a line)."""
    reader = PdfReader(str(AFSC_PDF))
    lines: list[str] = []
    for page in reader.pages:
        for line in (page.extract_text() or "").splitlines():
            if re.fullmatch(r"\s*\d*\s*", line):  # blank lines and page numbers
                continue
            lines.append(line.rstrip())
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        for code in codes:
            if re.match(rf"^{re.escape(code)}\b", line):
                starts.append((i, code))
                break
    out: dict[str, str] = {}
    for n, (i, code) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        block = " ".join(lines[i:end])
        block = block[len(code):].strip()
        # Drop the job-title words before the first numbered section, if there is one.
        first_section = block.find("1.")
        if 0 <= first_section < 120:
            block = block[first_section:]
        block = re.sub(r"\s+", " ", block)
        block = block.replace("Nonrated AFSCs", "").strip()
        # A bare title with no duties (e.g. "Pilot") means the PDF has no description.
        out[code] = block if len(block) > 40 or "Same as" in block else ""
    if "35P1" in out:
        out["35P1"] = ("(Source note: the provided PDF lists Air Force band-program duties under "
                       "35P1; the career field is Public Affairs.) " + out["35P1"])
    return out


def load_profiles() -> list[dict]:
    wb = openpyxl.load_workbook(PROFILES_XLSX, read_only=True, data_only=True)
    rows = list(wb["Profiles"].iter_rows(values_only=True))
    header = [str(h).strip() for h in rows[0]]
    profiles = []
    for r in rows[1:]:
        if not r[0]:
            continue
        d = dict(zip(header, r))
        status = STATUS_MAP.get(str(d["Military Status"]).strip(), "Civilian")
        where = str(d["Current Base / Working City"]).strip()
        is_military = status in {"Active Duty", "Guard/Reserve"}
        base_entry = canonical_base(where) if is_military else None
        profiles.append({
            "email": str(d["Email"]).strip().lower(),
            "first_name": str(d["First Name"]).strip(),
            "last_name": str(d["Last Name"]).strip(),
            "grad_year": int(d["Class Year"]),
            "status": status,
            "rank": d["Officer Rank"],
            "afsc": d["AFSC"],
            "job": d["Job Title"],
            "base": base_entry["name"] if base_entry else (where if is_military else None),
            "city": None if is_military else where,
            "phone": d["Phone"],
        })
    return profiles


def insert_user(conn, p: dict, *, password: str | None, role: str, source: str) -> None:
    label, lat, lng = locate(p["status"], p.get("base"), p.get("city"), allow_network=False)
    conn.execute(
        """
        INSERT INTO users (email, password_hash, first_name, last_name, grad_year, status, rank,
                           afsc, aircraft, job, base, city, phone, willing_to_mentor, role,
                           approval, location_label, lat, lng, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'approved', ?, ?, ?, ?)
        """,
        (p["email"], hash_password(password) if password else None, p["first_name"],
         p["last_name"], p["grad_year"], p["status"], p.get("rank"), p.get("afsc"),
         p.get("aircraft"), p.get("job"), p.get("base"), p.get("city"), p.get("phone"),
         role, label, lat, lng, source),
    )


def add_grader(conn) -> None:
    """Create the grader test account if it doesn't exist (not offered as a mentor)."""
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (GRADER["email"],)).fetchone():
        return
    insert_user(conn, GRADER, password=GRADER["password"], role="admin", source="signup")
    conn.execute("UPDATE users SET willing_to_mentor = 0 WHERE email = ?", (GRADER["email"],))


def seed(reset: bool) -> None:
    init_schema()
    with connect() as conn:
        if reset:
            for table in ("chat_messages", "tailgates", "games", "users", "afscs"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM sqlite_sequence")
        elif conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            add_grader(conn)  # existing databases still get the grader account
            print("Database already seeded (grader account ensured). "
                  "Use `python seed.py --reset` to rebuild it.")
            return

        afscs = load_afsc_reference()
        descriptions = load_afsc_descriptions([c for c, _, _ in afscs])
        conn.executemany(
            "INSERT INTO afscs (code, title, category, description) VALUES (?, ?, ?, ?)",
            [(c, t, cat, descriptions.get(c, "")) for c, t, cat in afscs],
        )

        insert_user(conn, ADMIN, password=ADMIN["password"], role="admin", source="signup")
        add_grader(conn)
        profiles = load_profiles()
        unmatched = sorted({p["base"] for p in profiles
                            if p["base"] and not canonical_base(p["base"])})
        for p in profiles:
            insert_user(conn, p, password=None, role="member", source="seed")

        schedule = json.loads((REFERENCE_DIR / "schedule_2026.json").read_text())
        game_ids: dict[str, int] = {}
        for g in schedule["games"]:
            cur = conn.execute(
                """
                INSERT INTO games (game_date, time_label, home_away, opponent, location, venue,
                                   tournament, result, lat, lng)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (g["date"], g["time"], g["home_away"], g["opponent"], g["location"], g["venue"],
                 g["tournament"], g["result"], g["lat"], g["lng"]),
            )
            game_ids[g["date"]] = cur.lastrowid
        for t in schedule["tailgates"]:
            conn.execute(
                """
                INSERT INTO tailgates (game_id, title, location, start_time, details, host, created_by)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (game_ids[t["game_date"]], t["title"], t["location"], t["start_time"],
                 t["details"], t["host"]),
            )

        mapped = conn.execute("SELECT COUNT(*) FROM users WHERE lat IS NOT NULL").fetchone()[0]
        print(f"AFSCs: {len(afscs)} ({sum(1 for v in descriptions.values() if v)} with PDF descriptions)")
        print(f"Members: {len(profiles) + 1} ({mapped} placed on the map)")
        print(f"Games: {len(schedule['games'])}, tailgates: {len(schedule['tailgates'])}")
        if unmatched:
            print(f"WARNING - bases not in reference/bases.json: {unmatched}")
        if _ADMIN_PASSWORD_FROM_ENV:
            print(f"Board admin login: {ADMIN['email']} (password from ADMIN_PASSWORD)")
        else:
            print(f"Board admin login: {ADMIN['email']} / {ADMIN['password']}  "
                  "(randomly generated; shown only now, so save it)")
        print(f"Grader login: {GRADER['email']} / {GRADER['password']}")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
