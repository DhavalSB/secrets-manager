"""Settings, read from the repo-root .env file (and real env vars, which win)."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./secrets.db")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
SERVER_URL = os.environ.get("SM_SERVER_URL", "http://localhost:8000").rstrip("/")
SESSION_DAYS = int(os.environ.get("SM_SESSION_DAYS", "30"))
# Lets `sm login --dev <login>` skip GitHub. Only for local demos with fake users.
DEV_LOGIN = os.environ.get("SM_DEV_LOGIN", "0") == "1"
