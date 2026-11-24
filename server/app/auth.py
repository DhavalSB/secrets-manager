"""Login, sessions, and "who is calling?" dependencies.

Login flow (no copy/paste):
  1. `sm login` starts a tiny server on 127.0.0.1:<port> and opens the browser at
     /auth/login?port=<port>&state=<random>.
  2. We remember (port, state) under a fresh nonce and redirect to GitHub.
  3. GitHub sends the browser back to /auth/callback?code=...&state=<nonce>.
  4. We trade the code for a GitHub access token, ask GitHub who this is, look the
     login up in our User table, create a Session, and redirect the browser to
     http://127.0.0.1:<port>/callback?token=...&state=<the CLI's state>.
  5. The CLI checks the state matches, saves the token, and closes its server.
"""

import secrets as pysecrets
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlmodel import Session as DB
from sqlmodel import select

from . import config
from .audit import record
from .crypto import hash_token, new_token
from .db import get_db
from .models import Session, User, utcnow
from .pages import login_result

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(
    db: DB,
    user: User,
    *,
    kind: str = "cli",
    name: str = "",
    read_only: bool = False,
    allowed_keys: list[str] | None = None,
    days: float = config.SESSION_DAYS,
) -> tuple[str, Session]:
    """Create a session row and return (raw token, row). The raw token is never stored."""
    token = new_token("sma" if kind == "agent" else "sm")
    row = Session(
        token_hash=hash_token(token),
        user_id=user.id,
        kind=kind,
        name=name,
        read_only=read_only,
        allowed_keys=",".join(allowed_keys) if allowed_keys is not None else None,
        expires_at=utcnow() + timedelta(days=days),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return token, row


@dataclass
class Caller:
    """Who is making this request, and through which session."""

    user: User
    session: Session

    @property
    def is_agent(self) -> bool:
        return self.session.kind == "agent"

    @property
    def actor(self) -> str:
        if self.is_agent:
            return f"{self.user.github_login} via agent:{self.session.name}"
        return self.user.github_login


# Reads "Authorization: Bearer <token>" and adds the Authorize button to /docs.
_bearer = HTTPBearer(auto_error=False, description="A token from `sm login` (~/.config/sm/credentials.json) or `sm token create`.")


def current_caller(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: DB = Depends(get_db)
) -> Caller:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not logged in. Run `sm login`.")
    token = creds.credentials.strip()
    session = db.exec(select(Session).where(Session.token_hash == hash_token(token))).first()
    if session is None:
        raise HTTPException(401, "Invalid or revoked token. Run `sm login`.")
    if session.expires_at < utcnow():
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Session expired. Run `sm login`.")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "User no longer exists.")
    session.last_used_at = utcnow()
    db.add(session)
    db.commit()
    return Caller(user=user, session=session)


def human_caller(caller: Caller = Depends(current_caller)) -> Caller:
    """Agent tokens may only touch secrets; account management needs a human."""
    if caller.is_agent:
        raise HTTPException(403, "Agent tokens can't do this. Ask the human who owns the token.")
    return caller


def admin_caller(caller: Caller = Depends(human_caller)) -> Caller:
    if not caller.user.is_admin:
        raise HTTPException(403, "Admins only.")
    return caller


# ---------------------------------------------------------------------------
# GitHub OAuth (authorization code flow with a loopback redirect to the CLI)
# ---------------------------------------------------------------------------

# nonce -> (cli_port, cli_state, created_at). In memory is fine for one local server.
_pending: dict[str, tuple[int, str, float]] = {}
_PENDING_TTL = 600


def _cli_redirect(port: int, **params: str) -> RedirectResponse:
    return RedirectResponse(f"http://127.0.0.1:{port}/callback?{urlencode(params)}")


@router.get("/login")
def login(port: int = Query(ge=1024, le=65535), state: str = Query(min_length=8, max_length=128)):
    if not config.GITHUB_CLIENT_ID or not config.GITHUB_CLIENT_SECRET:
        raise HTTPException(500, "Server is missing GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET in .env")
    now = time.time()
    for k, (_, _, t) in list(_pending.items()):
        if now - t > _PENDING_TTL:
            del _pending[k]
    nonce = pysecrets.token_urlsafe(24)
    _pending[nonce] = (port, state, now)
    query = urlencode(
        {
            "client_id": config.GITHUB_CLIENT_ID,
            "redirect_uri": f"{config.SERVER_URL}/auth/callback",
            "state": nonce,
            "allow_signup": "false",
        }
    )
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{query}")


@router.get("/callback")
def callback(code: str = "", state: str = "", error: str = "", db: DB = Depends(get_db)):
    pending = _pending.pop(state, None)
    if pending is None:
        return HTMLResponse(login_result(error="this login link has expired or was already used."), status_code=400)
    port, cli_state, _ = pending
    if error or not code:
        return _cli_redirect(port, state=cli_state, error=error or "GitHub did not return a code")

    try:
        with httpx.Client(timeout=10) as http:
            r = http.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": config.GITHUB_CLIENT_ID,
                    "client_secret": config.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": f"{config.SERVER_URL}/auth/callback",
                },
            )
            gh_token = r.json().get("access_token")
            if not gh_token:
                return _cli_redirect(port, state=cli_state, error=r.json().get("error_description", "token exchange failed"))
            me = http.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"},
            ).json()
    except httpx.HTTPError as e:
        return _cli_redirect(port, state=cli_state, error=f"Could not reach GitHub: {e}")

    login_name = str(me.get("login", "")).lower()
    user = db.exec(select(User).where(User.github_login == login_name)).first()
    if user is None:
        record(db, None, login_name or "unknown", "auth.denied", login_name, "not a member of this org")
        return _cli_redirect(
            port, state=cli_state, error=f"GitHub user '{login_name}' is not a member. Ask an admin to add you."
        )

    token, _ = create_session(db, user, kind="cli", name="cli")
    record(db, user.id, user.github_login, "auth.login")
    return _cli_redirect(port, state=cli_state, token=token, login=user.github_login)


@router.get("/done", response_class=HTMLResponse, include_in_schema=False)
def done(login: str = "", error: str = ""):
    """Where `sm login` sends the browser at the end: a styled "you're logged in" page.

    Only shows text; the token never comes here (it went straight to the CLI).
    """
    return HTMLResponse(login_result(login=login[:100], error=error[:300]), status_code=400 if error else 200)


class DevLoginIn(BaseModel):
    login: str


@router.post("/dev-login")
def dev_login(body: DevLoginIn, db: DB = Depends(get_db)):
    """Log in as any existing user without GitHub. Only when SM_DEV_LOGIN=1 (demos with fake users)."""
    if not config.DEV_LOGIN:
        raise HTTPException(404, "Not found")
    user = db.exec(select(User).where(User.github_login == body.login.lower())).first()
    if user is None:
        raise HTTPException(404, f"No user '{body.login}'")
    token, _ = create_session(db, user, kind="cli", name="dev")
    record(db, user.id, user.github_login, "auth.login", detail="dev login")
    return {"token": token, "login": user.github_login}


@router.post("/logout")
def logout(caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    record(db, caller.user.id, caller.actor, "auth.logout")
    db.delete(caller.session)
    db.commit()
    return {"ok": True}
