"""Create the org and first admin from .env.

    ../.venv/bin/python -m app.seed            # org + admin only
    ../.venv/bin/python -m app.seed --demo     # also dayvidwang/carol/dan, two teams, three secrets
"""

import os
import sys

from sqlmodel import Session as DB
from sqlmodel import select

from . import config  # noqa: F401  (loads .env)
from .crypto import encrypt
from .db import create_tables, engine
from .models import Org, Secret, SecretGrant, Team, TeamMember, User


def get_or_create_user(db: DB, login: str, org: Org, is_admin: bool = False) -> User:
    u = db.exec(select(User).where(User.github_login == login.lower())).first()
    if u is None:
        u = User(github_login=login.lower(), org_id=org.id, is_admin=is_admin)
        db.add(u)
        db.commit()
        db.refresh(u)
        print(f"  user {u.github_login}{' (admin)' if is_admin else ''}")
    return u


def seed(demo: bool = False) -> None:
    create_tables()
    org_name = os.environ.get("SEED_ORG_NAME", "Acme")
    admin_login = os.environ.get("SEED_ADMIN_GITHUB_LOGIN", "").strip()
    if not admin_login:
        sys.exit("Set SEED_ADMIN_GITHUB_LOGIN in .env")

    with DB(engine) as db:
        org = db.exec(select(Org).where(Org.name == org_name)).first()
        if org is None:
            # The app has a single org. Changing SEED_ORG_NAME after seeding must not
            # create a second, empty org next to the one everyone is in.
            existing = db.exec(select(Org)).first()
            if existing is not None:
                sys.exit(
                    f"The database already has org '{existing.name}', but .env says SEED_ORG_NAME={org_name}.\n"
                    f"Either set SEED_ORG_NAME={existing.name}, rename the org in the database, "
                    "or delete server/secrets.db to start over."
                )
            org = Org(name=org_name)
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"  org {org.name}")
        get_or_create_user(db, admin_login, org, is_admin=True)

        if not demo:
            return
        dayvidwang, carol, dan = (get_or_create_user(db, n, org) for n in ("dayvidwang", "carol", "dan"))
        teams = {}
        for name, members in {"backend": [dayvidwang, carol], "frontend": [carol, dan]}.items():
            t = db.exec(select(Team).where(Team.name == name, Team.org_id == org.id)).first()
            if t is None:
                t = Team(name=name, org_id=org.id)
                db.add(t)
                db.commit()
                db.refresh(t)
                for m in members:
                    db.add(TeamMember(team_id=t.id, user_id=m.id))
                db.commit()
                print(f"  team {name}: {', '.join(m.github_login for m in members)}")
            teams[name] = t
        demo_secrets = [
            ("OPENAI_API_KEY", "supersecretpassword", dayvidwang, [("team", teams["backend"].id, "read")]),
            ("DB_PASSWORD", "hunter2", carol, [("user", dayvidwang.id, "read")]),
            ("SENTRY_DSN", "https://abc@sentry.example/1", dan, [("org", org.id, "read")]),
        ]
        for key, value, owner, grants in demo_secrets:
            if db.exec(select(Secret).where(Secret.key == key, Secret.org_id == org.id)).first():
                continue
            s = Secret(key=key, encrypted_value=encrypt(value), org_id=org.id, created_by=owner.id, updated_by=owner.id)
            db.add(s)
            db.commit()
            db.refresh(s)
            db.add(SecretGrant(secret_id=s.id, principal_type="user", principal_id=owner.id, permission="write"))
            for ptype, pid, perm in grants:
                db.add(SecretGrant(secret_id=s.id, principal_type=ptype, principal_id=pid, permission=perm))
            db.commit()
            print(f"  secret {key} (owner {owner.github_login})")


if __name__ == "__main__":
    seed(demo="--demo" in sys.argv)
    print("Seeded.")
