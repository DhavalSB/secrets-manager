"""Agent tokens (scoped, expiring copies of your own access) and the audit log."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DB
from sqlmodel import select

from .audit import record
from .auth import Caller, admin_caller, create_session, human_caller
from .db import get_db
from .models import AuditLog, Session, User

router = APIRouter(tags=["tokens"])


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    read_only: bool = True
    keys: list[str] | None = None  # None = every key you can read
    expires_days: float = Field(default=7, gt=0, le=90)


def _token_out(s: Session, current: Session | None = None) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "name": s.name,
        "read_only": s.read_only,
        "allowed_keys": s.allowed_key_list(),
        "created_at": s.created_at.isoformat(),
        "expires_at": s.expires_at.isoformat(),
        "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
        "current": current is not None and s.id == current.id,
    }


@router.post("/tokens", status_code=201)
def create_token(body: TokenIn, caller: Caller = Depends(human_caller), db: DB = Depends(get_db)):
    """Create an agent token. The raw token is returned once and never stored."""
    token, row = create_session(
        db, caller.user, kind="agent", name=body.name, read_only=body.read_only,
        allowed_keys=body.keys, days=body.expires_days,
    )
    scope = f"read_only={body.read_only} keys={','.join(body.keys) if body.keys else '*'} days={body.expires_days}"
    record(db, caller.user.id, caller.actor, "token.create", body.name, scope)
    return {**_token_out(row), "token": token}


@router.get("/tokens")
def list_tokens(caller: Caller = Depends(human_caller), db: DB = Depends(get_db)):
    """Your sessions: CLI logins and agent tokens."""
    rows = db.exec(select(Session).where(Session.user_id == caller.user.id).order_by(Session.created_at)).all()
    return [_token_out(s, caller.session) for s in rows]


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, caller: Caller = Depends(human_caller), db: DB = Depends(get_db)):
    s = db.get(Session, token_id)
    if s is None or s.user_id != caller.user.id:
        raise HTTPException(404, "No such token")
    db.delete(s)
    db.commit()
    record(db, caller.user.id, caller.actor, "token.revoke", s.name)
    return {"ok": True}


@router.get("/audit")
def audit(limit: int = 100, secret: str | None = None, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    q = (
        select(AuditLog)
        .join(User, AuditLog.user_id == User.id, isouter=True)
        .where((User.org_id == caller.user.org_id) | (AuditLog.user_id == None))  # noqa: E711
        .order_by(AuditLog.id.desc())
        .limit(min(limit, 1000))
    )
    if secret:
        q = q.where(AuditLog.action.startswith("secret."), AuditLog.target.contains(secret))
    return [
        {"at": a.at.isoformat(), "actor": a.actor, "action": a.action, "target": a.target, "detail": a.detail}
        for a in db.exec(q).all()
    ]
