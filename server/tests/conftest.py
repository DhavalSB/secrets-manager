"""Test setup: a throwaway database and encryption key, and dev login enabled."""

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
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture
def client():
    SQLModel.metadata.drop_all(engine)
    seed(demo=True)
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
