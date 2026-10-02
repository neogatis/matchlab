from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Block,
    Conversation,
    DataRequest,
    Match,
    Message,
    ModerationAction,
    Photo,
    Report,
    User,
)


REPORT_REASONS = {
    "SPAM",
    "HARASSMENT",
    "HATE",
    "SCAM",
    "FAKE_PROFILE",
    "SEXUAL_CONTENT",
    "VIOLENCE",
    "UNDERAGE",
    "PRIVACY",
    "OTHER",
}
USER_ACTIONS = {"SOFT_BAN", "BAN", "UNBAN"}
REPORT_DECISIONS = {"RESOLVED", "DISMISSED"}


class SafetyError(Exception):
    pass


class InvalidReport(SafetyError):
    pass


class ModerationError(SafetyError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def block_user(db: Session, *, blocker: int, blocked: int, now: datetime | None = None) -> Block:
    now = now or utcnow()
    if blocker == blocked:
        raise SafetyError("cannot_block_self")
    if db.get(User, blocker) is None or db.get(User, blocked) is None:
        raise SafetyError("user_not_found")
    row = db.get(Block, (blocker, blocked))
    if row is None:
        row = Block(blocker=blocker, blocked=blocked, created_at=now)
        db.add(row)
        db.flush()
    return row


def unblock_user(db: Session, *, blocker: int, blocked: int) -> bool:
    row = db.get(Block, (blocker, blocked))
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def _validate_reason(reason: str) -> str:
    value = (reason or "").strip().upper()
    if value not in REPORT_REASONS:
        raise InvalidReport("unsupported_reason")
    return value


def report_user(db: Session, *, reporter: int, target_user: int, reason: str, now: datetime | None = None) -> Report:
    now = now or utcnow()
    if reporter == target_user:
        raise InvalidReport("cannot_report_self")
    if db.get(User, reporter) is None or db.get(User, target_user) is None:
        raise InvalidReport("user_not_found")
    row = Report(reporter=reporter, target_user=target_user, reason=_validate_reason(reason), status="OPEN", created_at=now)
    db.add(row)
    db.flush()
    return row


def report_photo(db: Session, *, reporter: int, photo_id: int, reason: str, now: datetime | None = None) -> Report:
    now = now or utcnow()
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise InvalidReport("photo_not_found")
    if photo.user_id == reporter:
        raise InvalidReport("cannot_report_own_photo")
    row = Report(reporter=reporter, photo_id=photo_id, reason=_validate_reason(reason), status="OPEN", created_at=now)
    db.add(row)
    db.flush()
    return row


def report_message(db: Session, *, reporter: int, message_id: int, reason: str, now: datetime | None = None) -> Report:
    now = now or utcnow()
    message = db.get(Message, message_id)
    if message is None:
        raise InvalidReport("message_not_found")
    if message.sender == reporter:
        raise InvalidReport("cannot_report_own_message")
    conversation = db.get(Conversation, message.conversation_id)
    match = db.get(Match, conversation.match_id) if conversation else None
    if match is None or reporter not in {match.user1, match.user2}:
        raise InvalidReport("not_message_participant")
    row = Report(reporter=reporter, message_id=message_id, reason=_validate_reason(reason), status="OPEN", created_at=now)
    db.add(row)
    db.flush()
    return row


def moderation_queue(db: Session, *, limit: int = 100) -> list[Report]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    return list(
        db.execute(
            select(Report)
            .where(Report.status.in_(("OPEN", "IN_REVIEW")))
            .order_by(Report.created_at, Report.id)
            .limit(limit)
        ).scalars()
    )


def set_report_reviewing(db: Session, *, report_id: int) -> Report:
    row = db.get(Report, report_id)
    if row is None:
        raise ModerationError("report_not_found")
    if row.status not in {"OPEN", "IN_REVIEW"}:
        raise ModerationError("report_closed")
    row.status = "IN_REVIEW"
    db.flush()
    return row


def moderate_user(
    db: Session,
    *,
    actor: str,
    user_id: int,
    action: str,
    reason: str,
    now: datetime | None = None,
) -> User:
    now = now or utcnow()
    action = (action or "").upper()
    if action not in USER_ACTIONS:
        raise ModerationError("unsupported_user_action")
    user = db.get(User, user_id)
    if user is None:
        raise ModerationError("user_not_found")
    status = {"SOFT_BAN": "SOFT_BANNED", "BAN": "BANNED", "UNBAN": "ACTIVE"}[action]
    user.status = status
    db.add(
        ModerationAction(
            actor=actor,
            target_type="USER",
            target_id=str(user_id),
            action=action,
            metadata_json={"reason": reason[:500]},
            created_at=now,
        )
    )
    db.add(
        AuditLog(
            actor_type="ADMIN",
            actor_id=actor,
            action=f"SAFETY_{action}",
            target_type="USER",
            target_id=str(user_id),
            metadata_json={"reason": reason[:500]},
            created_at=now,
        )
    )
    db.flush()
    return user


def moderate_photo(
    db: Session,
    *,
    actor: str,
    photo_id: int,
    approved: bool,
    reason: str = "",
    now: datetime | None = None,
) -> Photo:
    now = now or utcnow()
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise ModerationError("photo_not_found")
    photo.moderation_status = "APPROVED" if approved else "REJECTED"
    db.add(
        ModerationAction(
            actor=actor,
            target_type="PHOTO",
            target_id=str(photo_id),
            action="PHOTO_APPROVE" if approved else "PHOTO_REJECT",
            metadata_json={"reason": reason[:500]},
            created_at=now,
        )
    )
    db.flush()
    return photo


def close_report(
    db: Session,
    *,
    actor: str,
    report_id: int,
    decision: str,
    note: str = "",
    now: datetime | None = None,
) -> Report:
    now = now or utcnow()
    decision = (decision or "").upper()
    if decision not in REPORT_DECISIONS:
        raise ModerationError("unsupported_report_decision")
    row = db.get(Report, report_id)
    if row is None:
        raise ModerationError("report_not_found")
    row.status = decision
    db.add(
        ModerationAction(
            actor=actor,
            target_type="REPORT",
            target_id=str(report_id),
            action=decision,
            metadata_json={"note": note[:500]},
            created_at=now,
        )
    )
    db.flush()
    return row


def request_account_deletion(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> DataRequest:
    now = now or utcnow()
    user = db.get(User, user_id)
    if user is None:
        raise SafetyError("user_not_found")
    existing = db.execute(
        select(DataRequest).where(
            DataRequest.user_id == user_id,
            DataRequest.request_type == "DELETE",
            DataRequest.status == "PENDING",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user.status = "DELETION_REQUESTED"
    row = DataRequest(user_id=user_id, request_type="DELETE", status="PENDING", requested_at=now)
    db.add(row)
    db.flush()
    return row
