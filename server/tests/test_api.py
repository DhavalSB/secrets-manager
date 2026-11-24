"""End-to-end API tests over the example company in conftest.py."""


def keys(resp) -> set[str]:
    return {s["key"] for s in resp.json()}


def test_requires_login(client):
    assert client.get("/secrets").status_code == 401
    assert client.get("/secrets", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_list_is_filtered_per_user(client, login):
    assert keys(client.get("/secrets", headers=login("alice"))) == {"STRIPE_KEY", "DB_PASSWORD", "SENTRY_DSN"}
    assert keys(client.get("/secrets", headers=login("bob"))) == {"STRIPE_KEY", "DB_PASSWORD", "SENTRY_DSN"}
    assert keys(client.get("/secrets", headers=login("carol"))) == {"STRIPE_KEY", "DB_PASSWORD", "SENTRY_DSN"}
    assert keys(client.get("/secrets", headers=login("dan"))) == {"SENTRY_DSN"}


def test_read_value_and_hidden_secret_is_404(client, login):
    r = client.get("/secrets/STRIPE_KEY", headers=login("carol"))
    assert r.status_code == 200 and r.json()["value"] == "sk_test_demo_123"
    assert client.get("/secrets/STRIPE_KEY", headers=login("dan")).status_code == 404


def test_create_share_and_update(client, login):
    carol = login("carol")
    r = client.put("/secrets/NEW_KEY", headers=carol,
                   json={"value": "v1", "grants": [{"principal": "team:frontend", "permission": "read"}]})
    assert r.status_code == 200, r.text
    assert {"principal": "user:carol", "permission": "write", "display": "user:carol"} in r.json()["grants"]

    dan = login("dan")
    assert client.get("/secrets/NEW_KEY", headers=dan).json()["value"] == "v1"
    assert client.put("/secrets/NEW_KEY", headers=dan, json={"value": "x"}).status_code == 403

    # carol gives dan write; dan updates
    client.put("/secrets/NEW_KEY", headers=carol, json={"grants": [
        {"principal": "user:carol", "permission": "write"}, {"principal": "user:dan", "permission": "write"}]})
    assert client.put("/secrets/NEW_KEY", headers=dan, json={"value": "v2"}).status_code == 200
    assert client.get("/secrets/NEW_KEY", headers=carol).json()["value"] == "v2"


def test_team_membership_change_takes_effect(client, login):
    alice, dan = login("alice"), login("dan")
    assert client.get("/secrets/STRIPE_KEY", headers=dan).status_code == 404
    assert client.post("/teams/backend/members/dan", headers=alice).status_code == 200
    assert client.get("/secrets/STRIPE_KEY", headers=dan).status_code == 200
    client.put("/users/dan/teams", headers=alice, json={"teams": ["frontend"]})  # reassign back
    assert client.get("/secrets/STRIPE_KEY", headers=dan).status_code == 404


def test_admin_only_endpoints(client, login):
    bob = login("bob")
    assert client.post("/teams", headers=bob, json={"name": "x"}).status_code == 403
    assert client.post("/users", headers=bob, json={"github_login": "eve"}).status_code == 403
    alice = login("alice")
    assert client.post("/users", headers=alice, json={"github_login": "eve", "teams": ["backend"]}).status_code == 201
    assert client.post("/users/eve/promote", headers=alice).json()["is_admin"] is True
    assert client.delete("/users/eve", headers=alice).status_code == 200
    assert client.delete("/teams/frontend", headers=alice).status_code == 200
    assert "frontend" not in {t["name"] for t in client.get("/teams", headers=bob).json()}


def test_agent_token_scope(client, login):
    bob = login("bob")
    r = client.post("/tokens", headers=bob, json={"name": "claude", "read_only": True, "keys": ["STRIPE_KEY"]})
    agent = {"Authorization": f"Bearer {r.json()['token']}"}

    assert keys(client.get("/secrets", headers=agent)) == {"STRIPE_KEY"}
    assert client.get("/secrets/SENTRY_DSN", headers=agent).status_code == 404
    assert client.put("/secrets/STRIPE_KEY", headers=agent, json={"value": "x"}).status_code == 403
    assert client.get("/env", headers=agent).json() == {"STRIPE_KEY": "sk_test_demo_123"}
    # agents can't manage tokens or do admin things
    assert client.post("/tokens", headers=agent, json={"name": "x"}).status_code == 403

    log = client.get("/audit", headers=login("alice")).json()
    assert any(e["actor"] == "bob via agent:claude" and e["action"] == "secret.read" for e in log)

    tid = r.json()["id"]
    assert client.delete(f"/tokens/{tid}", headers=bob).status_code == 200
    assert client.get("/secrets", headers=agent).status_code == 401


def test_logout_revokes(client, login):
    bob = login("bob")
    assert client.post("/auth/logout", headers=bob).status_code == 200
    assert client.get("/me", headers=bob).status_code == 401


def test_values_are_encrypted_at_rest(client, login):
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Secret

    with Session(engine) as db:
        s = db.exec(select(Secret).where(Secret.key == "DB_PASSWORD")).one()
        assert "hunter2" not in s.encrypted_value
