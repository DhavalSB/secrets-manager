"""Tests for the permission rules, using the Acme example company.

Run from server/:   ../env/bin/pytest tests/test_permissions.py -v

Org 1 = Acme.  Users: alice (1, admin), bob (2), carol (3), dan (4).
Teams: backend (1) = bob, carol.   frontend (2) = carol, dan.
"""

from datetime import datetime, timezone

from app.models import SecretGrant, Session, User
from app.permissions import READ, WRITE, token_allows, user_can

alice = User(id=1, github_login="alice", org_id=1, is_admin=True)
bob = User(id=2, github_login="bob", org_id=1)
carol = User(id=3, github_login="carol", org_id=1)
dan = User(id=4, github_login="dan", org_id=1)

TEAMS = {bob.id: {1}, carol.id: {1, 2}, dan.id: {2}, alice.id: set()}


def grant(ptype: str, pid: int, perm: str) -> SecretGrant:
    return SecretGrant(secret_id=0, principal_type=ptype, principal_id=pid, permission=perm)


# STRIPE_KEY: bob created it (write), backend team can read.
STRIPE = [grant("user", bob.id, WRITE), grant("team", 1, READ)]
# DB_PASSWORD: carol created it (write), bob personally can read.
DB_PASSWORD = [grant("user", carol.id, WRITE), grant("user", bob.id, READ)]
# SENTRY_DSN: dan created it (write), the whole org can read.
SENTRY = [grant("user", dan.id, WRITE), grant("org", 1, READ)]


def check(user: User, perm: str, grants: list[SecretGrant]) -> bool:
    return user_can(user, perm, grants, TEAMS[user.id])


# --- user_can ---------------------------------------------------------------


def test_creator_can_write_and_read():
    assert check(bob, WRITE, STRIPE)
    assert check(bob, READ, STRIPE)  # write implies read


def test_team_grant():
    assert check(carol, READ, STRIPE)  # carol is in backend
    assert not check(carol, WRITE, STRIPE)  # ...but backend only has read
    assert not check(dan, READ, STRIPE)  # dan is not in backend


def test_user_grant():
    assert check(bob, READ, DB_PASSWORD)
    assert not check(bob, WRITE, DB_PASSWORD)  # question 1 from the walkthrough
    assert not check(dan, READ, DB_PASSWORD)


def test_org_grant():
    for u in (bob, carol, dan):
        assert check(u, READ, SENTRY)
    assert not check(bob, WRITE, SENTRY)


def test_org_grant_for_another_org_does_not_match():
    assert not check(bob, READ, [grant("org", 99, READ)])


def test_admin_can_do_everything():
    for grants in (STRIPE, DB_PASSWORD, SENTRY, []):
        assert check(alice, READ, grants)
        assert check(alice, WRITE, grants)


def test_no_grants_means_no_access():
    assert not check(bob, READ, [])


def test_ids_do_not_collide_across_types():
    # A grant to *team* 2 must not match *user* 2 (bob), and vice versa.
    assert not check(bob, READ, [grant("team", 2, READ)])
    assert not check(dan, READ, [grant("user", 2, READ)])  # dan is in team 2, not user 2


# --- token_allows -------------------------------------------------------------


def agent(read_only: bool = False, keys: str | None = None) -> Session:
    return Session(
        token_hash="x", user_id=bob.id, kind="agent", read_only=read_only,
        allowed_keys=keys, expires_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )


def test_no_session_or_unscoped_session_has_no_limits():
    assert token_allows(None, "STRIPE_KEY", WRITE)
    assert token_allows(agent(), "STRIPE_KEY", WRITE)


def test_read_only_token_cannot_write():
    assert token_allows(agent(read_only=True), "STRIPE_KEY", READ)
    assert not token_allows(agent(read_only=True), "STRIPE_KEY", WRITE)


def test_allowed_keys():
    tok = agent(keys="STRIPE_KEY,STRIPE_WEBHOOK_SECRET")
    assert token_allows(tok, "STRIPE_KEY", READ)
    assert not token_allows(tok, "SENTRY_DSN", READ)  # question 3 from the walkthrough
