from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProductEvent


EVENT_REGISTRATION = "REGISTRATION"
EVENT_QUESTIONNAIRE_STARTED = "QUESTIONNAIRE_STARTED"
EVENT_QUESTIONNAIRE_COMPLETED = "QUESTIONNAIRE_COMPLETED"
EVENT_PHOTO_UPLOADED = "PHOTO_UPLOADED"
EVENT_PROFILE_COMPLETED = "PROFILE_COMPLETED"
EVENT_INTEREST_SENT = "INTEREST_EXPRESSED"
EVENT_MUTUAL_MATCH = "MUTUAL_MATCH_CREATED"
EVENT_CHAT_STARTED = "CHAT_STARTED"
EVENT_SUBSCRIPTION_STARTED = "SUBSCRIPTION_STARTED"
EVENT_REFERRAL_INVITE = "REFERRAL_INVITE"
EVENT_REFERRAL_REGISTRATION = "REFERRAL_REGISTRATION"
EVENT_REFERRAL_COMPLETED_PROFILE = "REFERRAL_COMPLETED_PROFILE"

PRODUCT_EVENT_TYPES = {
    EVENT_REGISTRATION,
    EVENT_QUESTIONNAIRE_STARTED,
    EVENT_QUESTIONNAIRE_COMPLETED,
    EVENT_PHOTO_UPLOADED,
    EVENT_PROFILE_COMPLETED,
    EVENT_INTEREST_SENT,
    EVENT_MUTUAL_MATCH,
    EVENT_CHAT_STARTED,
    EVENT_SUBSCRIPTION_STARTED,
    EVENT_REFERRAL_INVITE,
    EVENT_REFERRAL_REGISTRATION,
    EVENT_REFERRAL_COMPLETED_PROFILE,
    "CANDIDATE_SKIPPED",
    "MESSAGE_SENT",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def track_event(
    db: Session,
    *,
    event_type: str,
    user_id: int | None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ProductEvent:
    event_type = (event_type or "").strip().upper()
    if not event_type or len(event_type) > 100:
        raise ValueError("invalid_event_type")
    row = ProductEvent(
        user_id=user_id,
        event_type=event_type,
        metadata_json=metadata or {},
        created_at=now or utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def track_once(
    db: Session,
    *,
    event_type: str,
    user_id: int,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ProductEvent:
    event_type = (event_type or "").strip().upper()
    existing = db.execute(
        select(ProductEvent)
        .where(
            ProductEvent.user_id == user_id,
            ProductEvent.event_type == event_type,
        )
        .order_by(ProductEvent.id)
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return track_event(
        db,
        event_type=event_type,
        user_id=user_id,
        metadata=metadata,
        now=now,
    )
