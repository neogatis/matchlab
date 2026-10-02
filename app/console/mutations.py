from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AdminAccount, AuditLog, Setting, User
from .access import InvalidConsoleAction, ROLE_RANK, require_console


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def set_setting(
    db: Session,
    *,
    console_user_id: int,
    key: str,
    value: str,
    now: datetime | None = None,
) -> Setting:
    now = now or utcnow()
    require_console(db, user_id=console_user_id, minimum_role="ADMIN")
    key = (key or "").strip()
    if not key or len(key) > 120:
        raise InvalidConsoleAction("invalid_setting_key")
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=str(value))
        db.add(row)
    else:
        row.value = str(value)
    db.add(
        AuditLog(
            actor_type="ADMIN",
            actor_id=str(console_user_id),
            action="SETTING_UPDATE",
            target_type="SETTING",
            target_id=key,
            metadata_json={"value_changed": True},
            created_at=now,
        )
    )
    db.flush()
    return row


def set_console_role(
    db: Session,
    *,
    console_user_id: int,
    target_user_id: int,
    role: str,
    active: bool = True,
    now: datetime | None = None,
) -> AdminAccount:
    now = now or utcnow()
    require_console(db, user_id=console_user_id, minimum_role="SUPERADMIN")
    role = (role or "").upper()
    if role not in ROLE_RANK:
        raise InvalidConsoleAction("invalid_console_role")
    if db.get(User, target_user_id) is None:
        raise InvalidConsoleAction("target_user_not_found")

    row = db.get(AdminAccount, target_user_id)
    if row is None:
        row = AdminAccount(
            user_id=target_user_id,
            role=role,
            is_active=bool(active),
            created_by_user_id=console_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.role = role
        row.is_active = bool(active)
        row.updated_at = now

    db.add(
        AuditLog(
            actor_type="ADMIN",
            actor_id=str(console_user_id),
            action="CONSOLE_ROLE_UPDATE",
            target_type="ADMIN_ACCOUNT",
            target_id=str(target_user_id),
            metadata_json={"role": role, "active": bool(active)},
            created_at=now,
        )
    )
    db.flush()
    return row
