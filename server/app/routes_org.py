"""People and teams: everyone can list (for sharing); admins can change."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DB
from sqlmodel import select

from .audit import record
from .auth import Caller, admin_caller, current_caller
from .db import get_db
from .models import Org, Secret, SecretGrant, Session, Team, TeamMember, User

router = APIRouter(tags=["org"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(db: DB, org_id: int, login: str) -> User:
    u = db.exec(select(User).where(User.org_id == org_id, User.github_login == login.lower())).first()
    if u is None:
        raise HTTPException(404, f"No user '{login}'")
    return u


def _team(db: DB, org_id: int, name: str) -> Team:
    t = db.exec(select(Team).where(Team.org_id == org_id, Team.name == name)).first()
    if t is None:
        raise HTTPException(404, f"No team '{name}'")
    return t


def _team_names(db: DB, user: User) -> list[str]:
    rows = db.exec(
        select(Team.name).join(TeamMember, TeamMember.team_id == Team.id).where(TeamMember.user_id == user.id)
    ).all()
    return sorted(rows)


def _member_logins(db: DB, team: Team) -> list[str]:
    rows = db.exec(
        select(User.github_login).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == team.id)
    ).all()
    return sorted(rows)


def _user_out(db: DB, u: User) -> dict:
    return {"login": u.github_login, "is_admin": u.is_admin, "teams": _team_names(db, u)}


def _team_out(db: DB, t: Team) -> dict:
    return {"name": t.name, "members": _member_logins(db, t)}


def _set_user_teams(db: DB, user: User, team_names: list[str]) -> None:
    teams = [_team(db, user.org_id, n) for n in team_names]
    for m in db.exec(select(TeamMember).where(TeamMember.user_id == user.id)).all():
        db.delete(m)
    for t in teams:
        db.add(TeamMember(team_id=t.id, user_id=user.id))
    db.commit()


def _set_team_members(db: DB, team: Team, logins: list[str]) -> None:
    users = [_user(db, team.org_id, login) for login in logins]
    for m in db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all():
        db.delete(m)
    for u in {u.id: u for u in users}.values():
        db.add(TeamMember(team_id=team.id, user_id=u.id))
    db.commit()


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------


@router.get("/me")
def me(caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    org = db.get(Org, caller.user.org_id)
    s = caller.session
    return {
        **_user_out(db, caller.user),
        "org": org.name if org else None,
        "session": {
            "kind": s.kind,
            "name": s.name,
            "read_only": s.read_only,
            "allowed_keys": s.allowed_key_list(),
            "expires_at": s.expires_at.isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserIn(BaseModel):
    github_login: str
    is_admin: bool = False
    teams: list[str] = []


class TeamsIn(BaseModel):
    teams: list[str]


@router.get("/users")
def list_users(caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    users = db.exec(select(User).where(User.org_id == caller.user.org_id).order_by(User.github_login)).all()
    return [_user_out(db, u) for u in users]


@router.post("/users", status_code=201)
def add_user(body: UserIn, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    login = body.github_login.strip().lstrip("@").lower()
    if not login:
        raise HTTPException(400, "github_login is required")
    if db.exec(select(User).where(User.github_login == login)).first():
        raise HTTPException(409, f"User '{login}' already exists")
    u = User(github_login=login, org_id=caller.user.org_id, is_admin=body.is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    _set_user_teams(db, u, body.teams)
    record(db, caller.user.id, caller.actor, "user.add", login, f"admin={body.is_admin} teams={','.join(body.teams)}")
    return _user_out(db, u)


@router.put("/users/{login}/teams")
def reassign_user(login: str, body: TeamsIn, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    """Replace the user's team memberships."""
    u = _user(db, caller.user.org_id, login)
    _set_user_teams(db, u, body.teams)
    record(db, caller.user.id, caller.actor, "user.reassign", u.github_login, ",".join(body.teams))
    return _user_out(db, u)


@router.post("/users/{login}/promote")
def promote(login: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    u = _user(db, caller.user.org_id, login)
    u.is_admin = True
    db.add(u)
    db.commit()
    record(db, caller.user.id, caller.actor, "user.promote", u.github_login)
    return _user_out(db, u)


@router.post("/users/{login}/demote")
def demote(login: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    u = _user(db, caller.user.org_id, login)
    admins = db.exec(select(User).where(User.org_id == u.org_id, User.is_admin == True)).all()  # noqa: E712
    if u.is_admin and len(admins) <= 1:
        raise HTTPException(400, "Can't demote the last admin")
    u.is_admin = False
    db.add(u)
    db.commit()
    record(db, caller.user.id, caller.actor, "user.demote", u.github_login)
    return _user_out(db, u)


@router.delete("/users/{login}")
def delete_user(login: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    u = _user(db, caller.user.org_id, login)
    if u.id == caller.user.id:
        raise HTTPException(400, "You can't delete yourself")
    for row in db.exec(select(TeamMember).where(TeamMember.user_id == u.id)).all():
        db.delete(row)
    for row in db.exec(select(Session).where(Session.user_id == u.id)).all():
        db.delete(row)  # logs them out everywhere and revokes their agent tokens
    for row in db.exec(
        select(SecretGrant).where(SecretGrant.principal_type == "user", SecretGrant.principal_id == u.id)
    ).all():
        db.delete(row)
    for s in db.exec(select(Secret).where((Secret.created_by == u.id) | (Secret.updated_by == u.id))).all():
        s.created_by = None if s.created_by == u.id else s.created_by
        s.updated_by = None if s.updated_by == u.id else s.updated_by
        db.add(s)
    db.delete(u)
    db.commit()
    record(db, caller.user.id, caller.actor, "user.delete", login.lower())
    return {"ok": True}


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class TeamIn(BaseModel):
    name: str
    members: list[str] = []


class MembersIn(BaseModel):
    members: list[str]


@router.get("/teams")
def list_teams(caller: Caller = Depends(current_caller), db: DB = Depends(get_db)):
    teams = db.exec(select(Team).where(Team.org_id == caller.user.org_id).order_by(Team.name)).all()
    return [_team_out(db, t) for t in teams]


@router.post("/teams", status_code=201)
def create_team(body: TeamIn, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    name = body.name.strip()
    if not name or ":" in name or "," in name:
        raise HTTPException(400, "Team names can't be empty or contain ':' or ','")
    if db.exec(select(Team).where(Team.org_id == caller.user.org_id, Team.name == name)).first():
        raise HTTPException(409, f"Team '{name}' already exists")
    t = Team(name=name, org_id=caller.user.org_id)
    db.add(t)
    db.commit()
    db.refresh(t)
    _set_team_members(db, t, body.members)
    record(db, caller.user.id, caller.actor, "team.create", name, ",".join(body.members))
    return _team_out(db, t)


@router.put("/teams/{name}/members")
def set_members(name: str, body: MembersIn, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    t = _team(db, caller.user.org_id, name)
    _set_team_members(db, t, body.members)
    record(db, caller.user.id, caller.actor, "team.members", name, ",".join(body.members))
    return _team_out(db, t)


@router.post("/teams/{name}/members/{login}")
def add_member(name: str, login: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    t = _team(db, caller.user.org_id, name)
    u = _user(db, caller.user.org_id, login)
    if not db.get(TeamMember, (t.id, u.id)):
        db.add(TeamMember(team_id=t.id, user_id=u.id))
        db.commit()
    record(db, caller.user.id, caller.actor, "team.add_member", name, u.github_login)
    return _team_out(db, t)


@router.delete("/teams/{name}/members/{login}")
def remove_member(name: str, login: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    t = _team(db, caller.user.org_id, name)
    u = _user(db, caller.user.org_id, login)
    m = db.get(TeamMember, (t.id, u.id))
    if m:
        db.delete(m)
        db.commit()
    record(db, caller.user.id, caller.actor, "team.remove_member", name, u.github_login)
    return _team_out(db, t)


@router.delete("/teams/{name}")
def delete_team(name: str, caller: Caller = Depends(admin_caller), db: DB = Depends(get_db)):
    t = _team(db, caller.user.org_id, name)
    for m in db.exec(select(TeamMember).where(TeamMember.team_id == t.id)).all():
        db.delete(m)
    for g in db.exec(
        select(SecretGrant).where(SecretGrant.principal_type == "team", SecretGrant.principal_id == t.id)
    ).all():
        db.delete(g)
    db.delete(t)
    db.commit()
    record(db, caller.user.id, caller.actor, "team.delete", name)
    return {"ok": True}
