"""Append-only audit log."""

from sqlmodel import Session as DB

from .models import AuditLog


def record(db: DB, user_id: int | None, actor: str, action: str, target: str = "", detail: str = "") -> None:
    db.add(AuditLog(user_id=user_id, actor=actor, action=action, target=target, detail=detail))
    db.commit()
