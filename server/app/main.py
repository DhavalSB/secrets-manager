"""FastAPI app. Run from server/:  ../.venv/bin/uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import auth, routes_org, routes_secrets, routes_tokens
from .db import create_tables
from .pages import docs_page


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


DESCRIPTION = """
A shared place for a team's secrets (API keys, credentials) that both people and
coding agents can use. Most people use it through the `sm` CLI; this page documents
the HTTP API underneath.

**Authentication.** Every endpoint except login needs `Authorization: Bearer <token>`.
Get a token with `sm login` (it's saved in `~/.config/sm/credentials.json`), or a scoped
agent token with `sm token create`. Click **Authorize** to paste one and try requests here.

**Permissions.** Admins can do everything. Everyone else needs a grant on the secret, to
them, one of their teams, or the whole org. Write implies read. Agent tokens can only
narrow their owner's access (read-only, specific keys, expiry).
"""

TAGS = [
    {"name": "secrets", "description": "List, read, create, share and delete secrets. `/env` serves `sm run`."},
    {"name": "org", "description": "People and teams. Everyone can list them (to share with them); admins can change them."},
    {"name": "tokens", "description": "Scoped, expiring agent tokens, and the admin audit log."},
    {"name": "auth", "description": "GitHub login used by `sm login`, and logout."},
]

app = FastAPI(
    title="SecretsManager",
    version="1.0",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    docs_url=None,  # replaced by the styled /docs below
    redoc_url=None,
)
app.include_router(routes_secrets.router)
app.include_router(routes_org.router)
app.include_router(routes_tokens.router)
app.include_router(auth.router)


@app.get("/docs", include_in_schema=False)
def docs() -> HTMLResponse:
    return HTMLResponse(docs_page(app.openapi_url or "/openapi.json"))


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}
