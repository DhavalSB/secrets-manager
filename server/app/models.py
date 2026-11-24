"""Database tables.

Each class is one table; each instance is one row. Columns ending in `_id`
point at a row in another table (a foreign key).
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Org(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_login: str = Field(unique=True, index=True)
    org_id: int = Field(foreign_key="org.id")
    is_admin: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    org_id: int = Field(foreign_key="org.id")


class TeamMember(SQLModel, table=True):
    """Join table: one row per (team, user) membership."""

    team_id: int = Field(foreign_key="team.id", primary_key=True)
    user_id: int = Field(foreign_key="user.id", primary_key=True)


class Secret(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True)
    encrypted_value: str
    org_id: int = Field(foreign_key="org.id")
    created_by: int | None = Field(default=None, foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SecretGrant(SQLModel, table=True):
    """One sharing rule: `principal` may `permission` this secret."""

    id: int | None = Field(default=None, primary_key=True)
    secret_id: int = Field(foreign_key="secret.id", index=True)
    principal_type: str  # "user" | "team" | "org"
    principal_id: int
    permission: str  # "read" | "write"  (write implies read)


class Session(SQLModel, table=True):
    """A logged-in CLI, or an agent token. We only store a hash of the token."""

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    kind: str = "cli"  # "cli" | "agent"
    name: str = ""  # e.g. "laptop" or "claude"
    # Scope limits. They only ever shrink what the owning user can do.
    read_only: bool = False
    allowed_keys: str | None = None  # comma-separated; None = every key the user can read
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    last_used_at: datetime | None = None

    def allowed_key_list(self) -> list[str] | None:
        if self.allowed_keys is None:
            return None
        return [k for k in self.allowed_keys.split(",") if k]


class AuditLog(SQLModel, table=True):
    """Append-only record of who did what."""

    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow, index=True)
    user_id: int | None = Field(default=None, foreign_key="user.id")
    actor: str  # "alice" or "alice via agent:claude"
    action: str  # e.g. "secret.read", "team.create"
    target: str = ""  # secret key, team name, user login...
    detail: str = ""
