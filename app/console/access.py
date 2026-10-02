from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AdminAccount, User


ROLE_RANK = {
    "VIEWER": 10,
    "MODERATOR": 20,
    "ADMIN": 30,
    "SUPERADMIN": 40,
}


class ConsoleError(Exception):
    pass


class ConsoleAccessDenied(ConsoleError):
    pass


class InvalidConsoleAction(ConsoleError):
    pass


def require_console(
    db: Session,
    *,
    user_id: int,
    minimum_role: str = "VIEWER",
) -> AdminAccount:
    minimum_role = (minimum_role or "").upper()
    if minimum_role not in ROLE_RANK:
        raise InvalidConsoleAction("unknown_required_role")
    user = db.get(User, user_id)
    account = db.get(AdminAccount, user_id)
    if (
        user is None
        or user.status != "ACTIVE"
        or account is None
        or not account.is_active
        or ROLE_RANK.get(account.role, 0) < ROLE_RANK[minimum_role]
    ):
        raise ConsoleAccessDenied("console_access_denied")
    return account
