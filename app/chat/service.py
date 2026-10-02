from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Block,
    Conversation,
    Match,
    Message,
    Notification,
    ProductEvent,
    Profile,
)


MAX_MESSAGE_LENGTH = 4000
MAX_PAGE_SIZE = 100


class ChatError(Exception):
    pass


class ChatUnavailable(ChatError):
    pass


class NotConversationParticipant(ChatError):
    pass


class MessageValidationError(ChatError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _match_for_user(db: Session, match_id: int, user_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise ChatUnavailable("match_not_found")
    if user_id not in {match.user1, match.user2}:
        raise NotConversationParticipant("not_match_participant")
    return match


def _other_user(match: Match, user_id: int) -> int:
    if user_id == match.user1:
        return match.user2
    if user_id == match.user2:
        return match.user1
    raise NotConversationParticipant("not_match_participant")


def _blocked(db: Session, a: int, b: int) -> bool:
    return db.execute(
        select(Block.blocker).where(
            or_(
                and_(Block.blocker == a, Block.blocked == b),
                and_(Block.blocker == b, Block.blocked == a),
            )
        )
    ).first() is not None


def get_or_create_conversation(
    db: Session,
    *,
    match_id: int,
    user_id: int,
    now: datetime | None = None,
) -> Conversation:
    now = now or utcnow()
    match = _match_for_user(db, match_id, user_id)
    other = _other_user(match, user_id)
    if _blocked(db, user_id, other):
        raise ChatUnavailable("blocked")

    row = db.execute(
        select(Conversation).where(Conversation.match_id == match_id)
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = Conversation(match_id=match_id, created_at=now)
    db.add(row)
    db.flush()
    return row


def get_conversation(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
) -> tuple[Conversation, Match]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ChatUnavailable("conversation_not_found")
    match = _match_for_user(db, conversation.match_id, user_id)
    return conversation, match


def _normalize_body(body: str) -> str:
    if not isinstance(body, str):
        raise MessageValidationError("message_must_be_text")
    value = body.strip()
    if not value:
        raise MessageValidationError("message_is_empty")
    if len(value) > MAX_MESSAGE_LENGTH:
        raise MessageValidationError("message_too_long")
    return value


def send_message(
    db: Session,
    *,
    conversation_id: int,
    sender_id: int,
    body: str,
    client_message_id: str | None = None,
    now: datetime | None = None,
) -> Message:
    now = now or utcnow()
    body = _normalize_body(body)
    conversation, match = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=sender_id,
    )
    recipient_id = _other_user(match, sender_id)

    if _blocked(db, sender_id, recipient_id):
        raise ChatUnavailable("blocked")

    if client_message_id is not None:
        client_message_id = str(client_message_id).strip()
        if not client_message_id or len(client_message_id) > 120:
            raise MessageValidationError("invalid_client_message_id")
        existing = db.execute(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.sender == sender_id,
                Message.client_message_id == client_message_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    message = Message(
        conversation_id=conversation.id,
        sender=sender_id,
        body=body,
        client_message_id=client_message_id,
        created_at=now,
    )
    db.add(message)
    db.flush()

    db.add(
        Notification(
            user_id=recipient_id,
            kind="MESSAGE",
            text="У вас новое сообщение в MatchLab.",
            created_at=now,
        )
    )
    db.add(
        ProductEvent(
            user_id=sender_id,
            event_type="MESSAGE_SENT",
            metadata_json={
                "conversation_id": conversation.id,
                "match_id": match.id,
            },
            created_at=now,
        )
    )
    db.flush()
    return message


def list_messages(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    limit: int = 50,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    conversation, match = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    query = select(Message).where(Message.conversation_id == conversation.id)
    if before_id is not None:
        query = query.where(Message.id < before_id)
    rows = list(
        db.execute(
            query.order_by(Message.id.desc()).limit(limit)
        ).scalars()
    )
    rows.reverse()
    return [
        {
            "id": row.id,
            "sender_id": row.sender,
            "body": row.body,
            "created_at": row.created_at,
            "read_at": row.read_at,
            "is_mine": row.sender == user_id,
        }
        for row in rows
    ]


def mark_read(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    through_message_id: int | None = None,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    conversation, _ = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    conditions = [
        Message.conversation_id == conversation.id,
        Message.sender != user_id,
        Message.read_at.is_(None),
    ]
    if through_message_id is not None:
        conditions.append(Message.id <= through_message_id)

    result = db.execute(
        update(Message)
        .where(*conditions)
        .values(read_at=now)
    )
    db.flush()
    return int(result.rowcount or 0)


def unread_count(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
) -> int:
    conversation, _ = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.sender != user_id,
            Message.read_at.is_(None),
        )
    )
    return int(count or 0)


def list_conversations(
    db: Session,
    *,
    user_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")

    rows = db.execute(
        select(Conversation, Match)
        .join(Match, Match.id == Conversation.match_id)
        .where(or_(Match.user1 == user_id, Match.user2 == user_id))
        .order_by(Conversation.id.desc())
        .limit(limit)
    ).all()

    result: list[dict[str, Any]] = []
    for conversation, match in rows:
        other_id = _other_user(match, user_id)
        profile = db.get(Profile, other_id)
        last = db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        result.append(
            {
                "conversation_id": conversation.id,
                "match_id": match.id,
                "other_user_id": other_id,
                "other_display_name": profile.display_name if profile else "",
                "last_message": None
                if last is None
                else {
                    "id": last.id,
                    "sender_id": last.sender,
                    "body": last.body,
                    "created_at": last.created_at,
                    "read_at": last.read_at,
                },
                "unread_count": unread_count(
                    db,
                    conversation_id=conversation.id,
                    user_id=user_id,
                ),
                "can_send": not _blocked(db, user_id, other_id),
            }
        )
    return result
