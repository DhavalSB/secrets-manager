"""Who may read or write a secret.

`can()` is what the API calls. It gathers facts from the database and passes
them to two small pure functions, `user_can` and `token_allows`, which hold
all of the rules. Being pure (no database) makes them easy to test:
see server/tests/test_permissions.py.
"""

from sqlmodel import Session as DB
from sqlmodel import select

from .models import Secret, SecretGrant, Session, TeamMember, User

READ = "read"
WRITE = "write"


def user_can(user: User, perm: str, grants: list[SecretGrant], team_ids: set[int]) -> bool:
    """May `user` do `perm` ("read" or "write") on a secret with these `grants`?

    `team_ids` is the set of team ids the user belongs to.
    Rules:
      - admins can do everything
      - a grant matches the user if it is for (user, user.id),
        (team, one of team_ids) or (org, user.org_id)
      - write implies read
    """

    if user.is_admin:
        return True
    for g in grants:
        if perm == WRITE and g.permission == READ:
            continue
        if g.principal_type == "user" and g.principal_id == user.id:
            return True
        if g.principal_type == "org" and g.principal_id == user.org_id:
            return True
        if g.principal_type == "team" and g.principal_id in team_ids:
            return True
    return False


def token_allows(session: Session | None, secret_key: str, perm: str) -> bool:
    """Does this session's scope permit `perm` on `secret_key`?

    A scope can only narrow what the user can do, never widen it.
      - no session, or a normal CLI session: no extra limits
      - read_only sessions may not write
      - if the session lists allowed keys, only those keys are allowed
    """
    if session is None:
        return True
    if session.read_only and perm == WRITE:
        return False
    allowed_keys = session.allowed_key_list()
    if allowed_keys is None or secret_key in allowed_keys:
        return True
    return False


# ---------------------------------------------------------------------------
# Database glue (already done; you shouldn't need to change this)
# ---------------------------------------------------------------------------


def team_ids_for(db: DB, user: User) -> set[int]:
    rows = db.exec(select(TeamMember.team_id).where(TeamMember.user_id == user.id)).all()
    return set(rows)


def grants_for(db: DB, secret: Secret) -> list[SecretGrant]:
    return list(db.exec(select(SecretGrant).where(SecretGrant.secret_id == secret.id)).all())


def can(db: DB, user: User, secret: Secret, perm: str, session: Session | None = None) -> bool:
    if secret.org_id != user.org_id:
        return False
    return user_can(user, perm, grants_for(db, secret), team_ids_for(db, user)) and token_allows(
        session, secret.key, perm
    )
