from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProductEvent


EVENT_LANDING_VIEW = "LANDING_VIEW"
EVENT_REGISTRATION_STARTED = "REGISTRATION_STARTED"
EVENT_REGISTRATION_COMPLETED = "REGISTRATION_COMPLETED"
EVENT_REGISTRATION = EVENT_REGISTRATION_COMPLETED
EVENT_EMAIL_VERIFIED = "EMAIL_VERIFIED"
EVENT_PHONE_VERIFIED = "PHONE_VERIFIED"
EVENT_ONBOARDING_STARTED = "ONBOARDING_STARTED"
EVENT_BASIC_PROFILE_COMPLETED = "BASIC_PROFILE_COMPLETED"
EVENT_QUESTIONNAIRE_STARTED = "QUESTIONNAIRE_STARTED"
EVENT_QUESTIONNAIRE_COMPLETED = "QUESTIONNAIRE_COMPLETED"
EVENT_PARTNER_PREFERENCES_COMPLETED = "PARTNER_PREFERENCES_COMPLETED"
EVENT_PHOTO_UPLOADED = "PHOTO_UPLOADED"
EVENT_PHOTO_APPROVED = "PHOTO_APPROVED"
EVENT_PROFILE_READY = "PROFILE_READY"
EVENT_PROFILE_COMPLETED = EVENT_PROFILE_READY
EVENT_WAITLIST_JOINED = "WAITLIST_JOINED"
EVENT_CANDIDATE_VIEWED = "CANDIDATE_VIEWED"
EVENT_CANDIDATE_SKIPPED = "CANDIDATE_SKIPPED"
EVENT_INTEREST_SENT = "INTEREST_EXPRESSED"
EVENT_MUTUAL_MATCH = "MUTUAL_MATCH_CREATED"
EVENT_CHAT_STARTED = "CHAT_STARTED"
EVENT_MESSAGE_SENT = "MESSAGE_SENT"
EVENT_REPORT_CREATED = "REPORT_CREATED"
EVENT_USER_BLOCKED = "USER_BLOCKED"
EVENT_SUBSCRIPTION_STARTED = "SUBSCRIPTION_STARTED"
EVENT_REFERRAL_INVITE = "REFERRAL_INVITE"
EVENT_REFERRAL_REGISTRATION = "REFERRAL_REGISTRATION"
EVENT_REFERRAL_COMPLETED_PROFILE = "REFERRAL_COMPLETED_PROFILE"

PRODUCT_EVENT_TYPES = {
    EVENT_LANDING_VIEW,
    EVENT_REGISTRATION_STARTED,
    EVENT_REGISTRATION_COMPLETED,
    EVENT_EMAIL_VERIFIED,
    EVENT_PHONE_VERIFIED,
    EVENT_ONBOARDING_STARTED,
    EVENT_BASIC_PROFILE_COMPLETED,
    EVENT_QUESTIONNAIRE_STARTED,
    EVENT_QUESTIONNAIRE_COMPLETED,
    EVENT_PARTNER_PREFERENCES_COMPLETED,
    EVENT_PHOTO_UPLOADED,
    EVENT_PHOTO_APPROVED,
    EVENT_PROFILE_READY,
    EVENT_WAITLIST_JOINED,
    EVENT_CANDIDATE_VIEWED,
    EVENT_CANDIDATE_SKIPPED,
    EVENT_INTEREST_SENT,
    EVENT_MUTUAL_MATCH,
    EVENT_CHAT_STARTED,
    EVENT_MESSAGE_SENT,
    EVENT_REPORT_CREATED,
    EVENT_USER_BLOCKED,
    EVENT_SUBSCRIPTION_STARTED,
    EVENT_REFERRAL_INVITE,
    EVENT_REFERRAL_REGISTRATION,
    EVENT_REFERRAL_COMPLETED_PROFILE,
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
