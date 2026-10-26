# AFLAX Alumni Connections

**Mitch Rose · AI Foundations Final Project**

A members-only web portal for Air Force Academy lacrosse (AFLAX) alumni and cadets. It
keeps alumni connected after graduation and gives cadets an AI mentor, **Falcon Mentor**,
that answers AFSC (career field) and base questions from official Air Force data, then
**recommends real alumni to contact and drafts the intro email**.

- **Alumni Connection:** a world map of who's where, filterable by status, base, and AFSC, plus a contact roster
- **Home:** the season schedule on a map, with tailgates, RSVPs, and add-to-calendar
- **Cadet Mentorship:** Falcon Mentor, a PydanticAI agent with 7 tools (gpt-6-luna via Portkey)
- **Explorer:** browse all 36 officer AFSCs and 81 bases, with no AI cost
- **Board tools:** account approvals and a token-usage dashboard

The project report and slide deck are in [`docs/`](docs/) (open `docs/report.html` or `docs/slides.html` in a browser).

---

## Run it (about 3 minutes)

The website is **pre-built** and served by the Python back end, so you only need **Python**.
You do **not** need Node.js.

### 1. Check Python (3.11 or newer)

```bash
python3 --version          # Windows: python --version
```

### 2. Make sure the API key can be found

The app reads `.env` from **two places, in this order**:

1. this repository's folder (next to this README), then
2. **the folder above** this repository.

It needs **one** of these keys, spelled exactly like this: `PORTKEY_API_KEY` (preferred) or `OPENAI_API_KEY`.

- **Teaching staff:** if your `.env` with `PORTKEY_API_KEY` is in the folder above this repo, there is nothing to do.
- **Everyone else:** `cp .env.example .env`, then put your key after `PORTKEY_API_KEY=`.

### 3. Install and start (run from this repository's folder)

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend
uvicorn main:app --port 8001
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd backend
uvicorn main:app --port 8001
```

On the first start the server creates and fills the database by itself (about 2 seconds).
When you see `Uvicorn running on http://127.0.0.1:8001`, it's ready.

### 4. Open the site and log in

Go to **http://localhost:8001** and log in with the grader account:

| Email | Password |
|---|---|
| `grader@aflax.example` | `GoFalcons2026!` |

This account has alumni-board access, so every page works, including **Board** (approvals and
the Falcon Mentor usage dashboard). All other member data is fictional test data.

There is also a generic board admin, `admin@aflax.example`, whose password is never stored in
this repo. It is either set by `ADMIN_PASSWORD` in `.env`, or randomly generated and printed
once in the terminal the first time the server builds the database. Graders don't need it.

**Things to try:**
1. **Cadet Mentorship:** ask *"Who can I talk to about Wright-Patterson AFB? I'm interested in developmental engineering."*, then *"Draft an intro email to the first mentor you suggested."*
2. **Alumni Connection:** filter by AFSC `92T0 · Pilot`, then click a blue map marker.
3. **Explorer:** open any AFSC or base to see the alumni there.
4. **Home:** click a game to fly the map to it. As a board member you can add a game or tailgate.

To stop the server, press `Ctrl+C` in its terminal.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` or version below 3.11 | Install Python 3.11+ from python.org (on Windows, use `python`). |
| `address already in use` | Another app is using port 8001. Run `uvicorn main:app --port 8010` and open http://localhost:8010. |
| Chat says *"Falcon Mentor isn't configured"* | No key was found. Put `PORTKEY_API_KEY=...` in `.env` here or in the folder above, then restart. Everything else on the site works without a key. |
| Windows: *"running scripts is disabled"* when activating | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `.venv\Scripts\activate.bat` in Command Prompt. |
| Maps don't show | The map tiles load from OpenStreetMap, so an internet connection is needed. |
| Start over with fresh data | Stop the server, delete `backend/data/`, and start it again. |

The server prints which `.env` file it found (never the key itself) and whether Falcon Mentor is ready.
You can also check http://localhost:8001/api/health.

---

## Run the tests (optional)

```bash
cd backend
python -m pytest
```

There are 32 tests covering auth, approvals, rate limits, photo cleaning, the map and roster,
RSVPs, the agent's tools and guardrails, and a full offline chat run. They make no model calls.

## Frontend development (optional, needs Node.js 20.19+)

Only needed to change the React code. With the back end running on port 8001:

```bash
cd frontend
npm install
npm run dev            # http://localhost:5175 (proxies /api to port 8001)
npm run build          # rebuilds frontend/dist, which the back end serves
```

---

## Project layout

```
backend/          FastAPI app, PydanticAI agent (agent.py), tools (tools.py), tests/
  reference/      curated data: 81 bases, AFSC guide, aircraft, 2026 schedule
  prompts/        Falcon Mentor's instructions
frontend/         React + Vite + TypeScript source; dist/ is the pre-built site
DATA/             source files the database is built from (AFSC PDF, test profiles)
docs/             project report and slide deck
.env.example      the keys the app reads (no real values)
```

## Settings (all optional except one key)

| Variable | Purpose |
|---|---|
| `PORTKEY_API_KEY` / `OPENAI_API_KEY` | Model access (one is required for Falcon Mentor). |
| `OPENAI_MODEL` | Model name (default `gpt-6-luna`). |
| `ADMIN_PASSWORD` | Password for the generic `admin@aflax.example` board account (otherwise random, printed once). |
| `CHAT_DAILY_LIMIT`, `CHAT_PER_MINUTE_LIMIT` | Falcon Mentor messages per member per day (40) and per minute (6). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | Real email. Without these, password-reset and board emails are saved to `backend/data/outbox/`. |
| `PRICE_INPUT_PER_M`, `PRICE_CACHED_INPUT_PER_M`, `PRICE_OUTPUT_PER_M` | USD per million tokens, used to show estimated cost on the usage dashboard. |
| `FORCE_HTTPS`, `ALLOWED_ORIGINS`, `APP_URL` | Deployment settings. |

## Notes

- Never commit a real `.env`. It is listed in `.gitignore`.
- All member names, emails, and phone numbers are fictional test data.
- The grader account (`seed.py`) is for evaluation only and will be removed before real alumni are invited.
