"""Secret endpoints: list, read, create/update/share, delete, and bulk env for `sm run`."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session as DB
from sqlmodel import select

from .audit import record
from .auth import Caller, current_caller
from .crypto import decrypt, encrypt
from .db import get_db
from .models import Org, Secret, SecretGrant, Team, User, utcnow
from .permissions import READ, WRITE, can, token_allows

router = APIRouter(tags=["secrets"])

# Keys look like environment variable names so `sm run` can inject them directly.
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class GrantIO(BaseModel):
    principal: str  # "user:<login>", "team:<name>", or "org"
    permission: str  # "read" | "write"


class SecretPut(BaseModel):
    value: str | None = None
    # None = leave sharing unchanged. A list replaces all grants.
    grants: list[GrantIO] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_key(key: str) -> None:
    if not KEY_RE.match(key):
        raise HTTPException(400, "Keys must look like env var names: letters, digits and _, not starting with a digit.")


def _find_secret(db: DB, caller: Caller, key: str) -> Secret | None:
    return db.exec(select(Secret).where(Secret.org_id == caller.user.org_id, Secret.key == key)).first()


def _resolve_grant(db: DB, org_id: int, g: GrantIO) -> SecretGrant:
    if g.permission not in (READ, WRITE):
        raise HTTPException(400, f"Permission must be 'read' or 'write', got '{g.permission}'")
    kind, _, name = g.principal.partition(":")
    if kind == "org":
        return SecretGrant(secret_id=0, principal_type="org", principal_id=org_id, permission=g.permission)
    if kind == "user":
        u = db.exec(select(User).where(User.org_id == org_id, User.github_login == name.lower())).first()
        if u is None:
            raise HTTPException(400, f"No user '{name}' in this org")
        return SecretGrant(secret_id=0, principal_type="user", principal_id=u.id, permission=g.permission)
    if kind == "team":
        t = db.exec(select(Team).where(Team.org_id == org_id, Team.name == name)).first()
        if t is None:
            raise HTTPException(400, f"No team '{name}' in this org")
        return SecretGrant(secret_id=0, principal_type="team", principal_id=t.id, permission=g.permission)
    raise HTTPException(400, f"Principal must be 'user:<login>', 'team:<name>' or 'org', got '{g.principal}'")


def _describe_grants(db: DB, secret: Secret) -> list[dict]:
    out = []
    for g in db.exec(select(SecretGrant).where(SecretGrant.secret_id == secret.id)).all():
        if g.principal_type == "org":
            org = db.get(Org, g.principal_id)
            label = "org"
            name = org.name if org else "?"
        elif g.principal_type == "team":
            t = db.get(Team, g.principal_id)
            label = f"team:{t.name if t else '?'}"
            name = label
        else:
            u = db.get(User, g.principal_id)
            label = f"user:{u.github_login if u else '?'}"
            name = label
        out.append({"principal": label, "permission": g.permission, "display": name})
    return out


def _login(db: DB, user_id: int | None) -> str | None:
    u = db.get(User, user_id) if user_id else None
    return u.github_login if u else None


def _summary(db: DB, caller: Caller, s: Secret) -> dict:
    return {
        "key": s.key,
        "access": WRITE if can(db, caller.user, s, WRITE, caller.session) else READ,
        "grants": _describe_grants(db, s),
        "created_by": _login(db, s.created_by),
        "updated_by": _login(db, s.updated_by),
        "updated_at": s.updated_at.isoformat(),
    }


def _readable(db: DB, caller: Caller) -> list[Secret]:
    secrets = db.exec(select(Secret).where(Secret.org_id == caller.user.org_id).order_by(Secret.key)).all()
    # Fine for a team-sized org. At scale this would become one SQL query over grants.
    return [s for s in secrets if can(db, caller.user, s, READ, caller.session)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/secrets")
def list_secrets(caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    """Keys you can read, with who they're shared with. Values are not included."""
    return [_summary(db, caller, s) for s in _readable(db, caller)]


@router.get("/secrets/{key}")
def read_secret(key: str, caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    s = _find_secret(db, caller, key)
    # Same 404 whether it doesn't exist or you can't see it, so keys don't leak.
    if s is None or not can(db, caller.user, s, READ, caller.session):
        raise HTTPException(404, f"No secret '{key}' that you can read")
    record(db, caller.user.id, caller.actor, "secret.read", key)
    return {**_summary(db, caller, s), "value": decrypt(s.encrypted_value)}


@router.put("/secrets/{key}")
def put_secret(key: str, body: SecretPut, caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    """Create a secret, or update its value and/or sharing."""
    _check_key(key)
    org_id = caller.user.org_id
    new_grants = [_resolve_grant(db, org_id, g) for g in body.grants] if body.grants is not None else None
    s = _find_secret(db, caller, key)

    if s is None:
        # Anyone can create a secret (agent tokens only if their scope allows writing this key).
        if not token_allows(caller.session, key, WRITE):
            raise HTTPException(403, "This token can't create that secret")
        if body.value is None:
            raise HTTPException(400, "A new secret needs a value")
        s = Secret(key=key, encrypted_value=encrypt(body.value), org_id=org_id,
                   created_by=caller.user.id, updated_by=caller.user.id)
        db.add(s)
        db.commit()
        db.refresh(s)
        grants = new_grants or []
        # The creator always starts with write access.
        if not any(g.principal_type == "user" and g.principal_id == caller.user.id and g.permission == WRITE for g in grants):
            grants.append(SecretGrant(secret_id=0, principal_type="user", principal_id=caller.user.id, permission=WRITE))
        for g in grants:
            g.secret_id = s.id
            db.add(g)
        db.commit()
        record(db, caller.user.id, caller.actor, "secret.create", key, _grant_text(db, s))
        return _summary(db, caller, s)

    if not can(db, caller.user, s, WRITE, caller.session):
        if can(db, caller.user, s, READ, caller.session):
            raise HTTPException(403, f"You can read '{key}' but not change it")
        raise HTTPException(404, f"No secret '{key}' that you can read")

    if body.value is not None:
        s.encrypted_value = encrypt(body.value)
        s.updated_at = utcnow()
        s.updated_by = caller.user.id
        db.add(s)
        db.commit()
        record(db, caller.user.id, caller.actor, "secret.update", key)
    if new_grants is not None:
        for old in db.exec(select(SecretGrant).where(SecretGrant.secret_id == s.id)).all():
            db.delete(old)
        for g in new_grants:
            g.secret_id = s.id
            db.add(g)
        db.commit()
        record(db, caller.user.id, caller.actor, "secret.share", key, _grant_text(db, s))
    return _summary(db, caller, s)


def _grant_text(db: DB, s: Secret) -> str:
    return ", ".join(f"{g['principal']}={g['permission']}" for g in _describe_grants(db, s))


@router.delete("/secrets/{key}")
def delete_secret(key: str, caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    s = _find_secret(db, caller, key)
    if s is None or not can(db, caller.user, s, READ, caller.session):
        raise HTTPException(404, f"No secret '{key}' that you can read")
    if not can(db, caller.user, s, WRITE, caller.session):
        raise HTTPException(403, f"You can read '{key}' but not delete it")
    for g in db.exec(select(SecretGrant).where(SecretGrant.secret_id == s.id)).all():
        db.delete(g)
    db.delete(s)
    db.commit()
    record(db, caller.user.id, caller.actor, "secret.delete", key)
    return {"ok": True}


@router.get("/env")
def env(keys: str | None = Query(default=None, description="Comma-separated; default = all you can read"),
        caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    """Values of several secrets at once, for `sm run`. Every key returned is audited."""
    readable = _readable(db, caller)
    if keys:
        wanted = [k for k in keys.split(",") if k]
        by_key = {s.key: s for s in readable}
        missing = [k for k in wanted if k not in by_key]
        if missing:
            raise HTTPException(404, f"No secret(s) you can read: {', '.join(missing)}")
        readable = [by_key[k] for k in wanted]
    out = {s.key: decrypt(s.encrypted_value) for s in readable}
    if out:
        record(db, caller.user.id, caller.actor, "secret.read", ",".join(out), "via sm run / env")
    return out
