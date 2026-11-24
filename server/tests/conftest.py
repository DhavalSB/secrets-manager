"""Test setup: a throwaway database and encryption key, dev login enabled, and a
fixed example company. The tests never use the demo seed, so editing
app/seed.py can't break them.

The example company (same as test_permissions.py):
  org Acme.  alice (admin), bob, carol, dan.
  teams: backend = bob, carol.   frontend = carol, dan.
  STRIPE_KEY  (bob, write)    shared with team backend (read)
  DB_PASSWORD (carol, write)  shared with user bob (read)
  SENTRY_DSN  (dan, write)    shared with the whole org (read)
"""

import os
import tempfile

from cryptography.fernet import Fernet

# Must be set before `app` is imported (config reads them at import time).
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SM_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["SM_DEV_LOGIN"] = "1"
os.environ["SEED_ADMIN_GITHUB_LOGIN"] = "alice"
os.environ["SEED_ORG_NAME"] = "Acme"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.crypto import encrypt  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Org, Secret, SecretGrant, Team, TeamMember, User  # noqa: E402


def create_example_company() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        org = Org(name="Acme")
        db.add(org)
        db.flush()

        users = {}
        for login in ("alice", "bob", "carol", "dan"):
            users[login] = User(github_login=login, org_id=org.id, is_admin=login == "alice")
            db.add(users[login])
        db.flush()

        teams = {}
        for name, members in {"backend": ["bob", "carol"], "frontend": ["carol", "dan"]}.items():
            teams[name] = Team(name=name, org_id=org.id)
            db.add(teams[name])
            db.flush()
            for m in members:
                db.add(TeamMember(team_id=teams[name].id, user_id=users[m].id))

        secrets = [
            ("STRIPE_KEY", "sk_test_demo_123", "bob", ("team", teams["backend"].id)),
            ("DB_PASSWORD", "hunter2", "carol", ("user", users["bob"].id)),
            ("SENTRY_DSN", "https://abc@sentry.example/1", "dan", ("org", org.id)),
        ]
        for key, value, owner, (ptype, pid) in secrets:
            s = Secret(key=key, encrypted_value=encrypt(value), org_id=org.id,
                       created_by=users[owner].id, updated_by=users[owner].id)
            db.add(s)
            db.flush()
            db.add(SecretGrant(secret_id=s.id, principal_type="user", principal_id=users[owner].id, permission="write"))
            db.add(SecretGrant(secret_id=s.id, principal_type=ptype, principal_id=pid, permission="read"))
        db.commit()


@pytest.fixture
def client():
    create_example_company()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    """login("bob") -> headers for bob."""

    def _login(name: str) -> dict:
        r = client.post("/auth/dev-login", json={"login": name})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return _login
