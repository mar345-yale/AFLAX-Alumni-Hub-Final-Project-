"""Environment settings, loaded once for the whole back end.

The `.env` file is looked up in TWO places, in this order:
  1. the repository's own folder (next to README.md), then
  2. the folder ABOVE the repository (where course staff keep a shared .env).
A value found in the first place wins; real environment variables beat both.

Model access needs ONE of these keys (exact names):
  PORTKEY_API_KEY  -> routed through the Portkey gateway (preferred)
  OPENAI_API_KEY   -> sent straight to OpenAI's API
"""

import os
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent
ENV_FILES = [REPO_DIR / ".env", REPO_DIR.parent / ".env"]

for env_file in ENV_FILES:
    if env_file.is_file():
        for key, value in dotenv_values(env_file).items():
            # Earlier files (and real env vars) win, but a BLANK value never hides a real one,
            # e.g. an unfilled copy of .env.example won't mask the key in the folder above.
            if value and value.strip() and not os.environ.get(key, "").strip():
                os.environ[key] = value.strip()


def env_source() -> str:
    """Which .env file(s) were found, for the startup log (never prints values)."""
    found = [str(p) for p in ENV_FILES if p.is_file()]
    return ", ".join(found) if found else "none found (looked in: " + ", ".join(map(str, ENV_FILES)) + ")"


PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
