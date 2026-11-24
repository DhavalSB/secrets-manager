"""The seed script must never create a second org."""

import pytest
from sqlmodel import Session, SQLModel, select

from app.db import engine
from app.models import Org
from app.seed import seed


def test_reseeding_is_safe_and_a_renamed_org_is_refused(monkeypatch):
    SQLModel.metadata.drop_all(engine)
    seed(demo=True)
    seed(demo=True)  # running it again changes nothing

    monkeypatch.setenv("SEED_ORG_NAME", "SomethingElse")
    with pytest.raises(SystemExit, match="already has org 'Acme'"):
        seed(demo=True)

    with Session(engine) as db:
        assert [o.name for o in db.exec(select(Org)).all()] == ["Acme"]
