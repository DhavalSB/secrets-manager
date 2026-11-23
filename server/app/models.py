class SecretGrant(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    secret_id: int = Field(foreign_key="secret.id")
    principal_type: str   # "user" | "team" | "org"
    principal_id: int
    permission: str       # "read" | "write"
