from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.chat.media import (
    ChatMediaError,
    decode_media_body,
    encode_media_body,
    prepare_object_upload,
    preview_text,
    public_media_payload,
    validate_uploaded_media,
)
from app.analytics.events import EVENT_CHAT_STARTED, track_once
from app.db.models import (
    Block,
    ChatMediaUploadTicket,
    Conversation,
    Match,
    Message,
    Notification,
    PhotoObjectDeletion,
    ProductEvent,
    Profile,
    User,
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


CHAT_MEDIA_UPLOAD_TTL_MINUTES = 15


def _queue_object_deletion(db: Session, object_key: str) -> None:
    key = str(object_key or "").strip()
    if not key:
        return
    existing = db.execute(
        select(PhotoObjectDeletion).where(PhotoObjectDeletion.object_key == key)
    ).scalar_one_or_none()
    if existing is None:
        db.add(PhotoObjectDeletion(object_key=key, status="PENDING"))


def expire_chat_media_uploads(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = now or utcnow()
    rows = list(
        db.execute(
            select(ChatMediaUploadTicket)
            .where(
                ChatMediaUploadTicket.status == "PREPARED",
                ChatMediaUploadTicket.expires_at <= now,
            )
            .order_by(ChatMediaUploadTicket.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    for row in rows:
        row.status = "EXPIRED"
        _queue_object_deletion(db, row.object_key)
    db.flush()
    return {"processed": len(rows), "expired": len(rows)}


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
    media: dict[str, Any] | None = None,
    storage: Any | None = None,
    now: datetime | None = None,
) -> Message:
    now = now or utcnow()
    conversation, match = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=sender_id,
    )
    recipient_id = _other_user(match, sender_id)
    sender = db.get(User, sender_id)
    recipient = db.get(User, recipient_id)
    if sender is None or sender.status != "ACTIVE":
        raise ChatUnavailable("sender_inactive")
    if recipient is None or recipient.status != "ACTIVE":
        raise ChatUnavailable("recipient_inactive")
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

    message_kind = "text"
    if media is None:
        stored_body = _normalize_body(body)
    else:
        if storage is None:
            raise MessageValidationError("chat_media_storage_unavailable")
        object_key = str(media.get("object_key", "") if isinstance(media, dict) else "").strip()
        ticket = db.execute(
            select(ChatMediaUploadTicket).where(
                ChatMediaUploadTicket.object_key == object_key,
                ChatMediaUploadTicket.user_id == sender_id,
                ChatMediaUploadTicket.conversation_id == conversation.id,
            )
        ).scalar_one_or_none()
        if ticket is None or ticket.status != "PREPARED":
            raise MessageValidationError("chat_media_upload_not_prepared")
        if ticket.expires_at <= now:
            ticket.status = "EXPIRED"
            _queue_object_deletion(db, ticket.object_key)
            db.flush()
            raise MessageValidationError("chat_media_upload_expired")
        authoritative_media = {
            "object_key": ticket.object_key,
            "kind": ticket.kind,
            "mime": ticket.mime,
            "name": ticket.original_name,
            "size": ticket.expected_size,
            "duration_seconds": media.get("duration_seconds") if isinstance(media, dict) else None,
        }
        try:
            normalized_media = validate_uploaded_media(
                storage=storage,
                user_id=sender_id,
                conversation_id=conversation.id,
                media=authoritative_media,
            )
            stored_body = encode_media_body(normalized_media, body)
            message_kind = str(normalized_media.get("kind") or "media")
            ticket.status = "CONSUMED"
            ticket.consumed_at = now
        except ChatMediaError as exc:
            ticket.status = "CANCELLED"
            _queue_object_deletion(db, ticket.object_key)
            db.flush()
            raise MessageValidationError(str(exc)) from exc

    message = Message(
        conversation_id=conversation.id,
        sender=sender_id,
        body=stored_body,
        client_message_id=client_message_id,
        created_at=now,
    )
    db.add(message)
    db.flush()

    message_count = int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id)
        )
        or 0
    )
    if message_count == 1:
        track_once(
            db,
            event_type=EVENT_CHAT_STARTED,
            user_id=sender_id,
            metadata={
                "conversation_id": conversation.id,
                "match_id": match.id,
            },
            now=now,
        )

    notification = Notification(
        user_id=recipient_id,
        kind="MESSAGE",
        text="У вас новое сообщение в MatchLab.",
        created_at=now,
    )
    db.add(notification)
    db.add(
        ProductEvent(
            user_id=sender_id,
            event_type="MESSAGE_SENT",
            metadata_json={
                "conversation_id": conversation.id,
                "match_id": match.id,
                "message_kind": message_kind,
            },
            created_at=now,
        )
    )
    db.flush()

    from app.push.service import enqueue_notification

    enqueue_notification(db, notification_id=notification.id, now=now)
    return message


def _message_payload(row: Message, *, user_id: int) -> dict[str, Any]:
    decoded = decode_media_body(row.body)
    payload: dict[str, Any] = {
        "id": row.id,
        "sender_id": row.sender,
        "body": row.body,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "is_mine": row.sender == user_id,
    }
    if decoded is not None:
        payload["body"] = decoded.get("caption", "")
        payload["media"] = public_media_payload(decoded, message_id=row.id)
    return payload


def message_payload(row: Message, *, user_id: int) -> dict[str, Any]:
    return _message_payload(row, user_id=user_id)


def get_message_media(
    db: Session,
    *,
    message_id: int,
    user_id: int,
) -> dict[str, Any]:
    message = db.get(Message, message_id)
    if message is None:
        raise ChatUnavailable("message_not_found")
    get_conversation(
        db,
        conversation_id=message.conversation_id,
        user_id=user_id,
    )
    media = decode_media_body(message.body)
    if media is None:
        raise ChatUnavailable("message_has_no_media")
    expected_prefix = (
        f"users/{int(message.sender)}/chat/{int(message.conversation_id)}/"
    )
    if not str(media.get("object_key", "")).startswith(expected_prefix):
        raise ChatUnavailable("invalid_message_media")
    return media


def prepare_media_upload(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    mime: str,
    kind: str,
    size: int,
    name: str,
    storage: Any,
) -> dict[str, Any]:
    conversation, match = get_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    other_id = _other_user(match, user_id)
    if _blocked(db, user_id, other_id):
        raise ChatUnavailable("blocked")
    sender = db.get(User, user_id)
    recipient = db.get(User, other_id)
    if sender is None or sender.status != "ACTIVE":
        raise ChatUnavailable("sender_inactive")
    if recipient is None or recipient.status != "ACTIVE":
        raise ChatUnavailable("recipient_inactive")
    try:
        prepared = prepare_object_upload(
            storage=storage,
            user_id=user_id,
            conversation_id=conversation.id,
            mime=mime,
            kind=kind,
            size=size,
            name=name,
        )
        now = utcnow()
        ticket = ChatMediaUploadTicket(
            user_id=user_id,
            conversation_id=conversation.id,
            object_key=prepared["object_key"],
            mime=prepared["mime"],
            kind=prepared["kind"],
            original_name=prepared["name"],
            expected_size=int(size),
            status="PREPARED",
            expires_at=now + timedelta(minutes=CHAT_MEDIA_UPLOAD_TTL_MINUTES),
            created_at=now,
        )
        db.add(ticket)
        db.flush()
        prepared["expires_at"] = ticket.expires_at
        return prepared
    except ChatMediaError as exc:
        raise MessageValidationError(str(exc)) from exc


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
    return [_message_payload(row, user_id=user_id) for row in rows]


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
        last_payload = None
        if last is not None:
            last_payload = _message_payload(last, user_id=user_id)
            decoded = decode_media_body(last.body)
            if decoded is not None:
                last_payload["body"] = preview_text(
                    decoded,
                    str(last_payload.get("body") or ""),
                )
                last_payload.pop("media", None)

        result.append(
            {
                "conversation_id": conversation.id,
                "match_id": match.id,
                "other_user_id": other_id,
                "other_display_name": profile.display_name if profile else "",
                "last_message": last_payload,
                "unread_count": unread_count(
                    db,
                    conversation_id=conversation.id,
                    user_id=user_id,
                ),
                "can_send": not _blocked(db, user_id, other_id),
            }
        )
    return result
