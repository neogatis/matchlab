from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.events import (
    EVENT_REFERRAL_COMPLETED_PROFILE,
    EVENT_REFERRAL_INVITE,
    EVENT_REFERRAL_REGISTRATION,
    track_event,
)
from app.db.models import Referral, User


class ReferralError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_referral_code(db: Session, *, code: str) -> User | None:
    code = (code or "").strip()
    if not code:
        return None
    return db.execute(
        select(User).where(
            User.referral_code == code,
            User.status.in_(("ACTIVE", "SOFT_BANNED")),
        )
    ).scalar_one_or_none()


def referral_link(
    db: Session,
    *,
    user_id: int,
    base_url: str,
) -> str:
    user = db.get(User, user_id)
    if user is None:
        raise ReferralError("user_not_found")
    parts = urlsplit((base_url or "").strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ReferralError("invalid_base_url")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = user.referral_code
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment)
    )


def record_invite(
    db: Session,
    *,
    user_id: int,
    channel: str | None = None,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    user = db.get(User, user_id)
    if user is None:
        raise ReferralError("user_not_found")
    user.invites_sent += 1
    track_event(
        db,
        event_type=EVENT_REFERRAL_INVITE,
        user_id=user_id,
        metadata={"channel": (channel or "share").strip()[:40] or "share"},
        now=now,
    )
    db.flush()
    return user.invites_sent


def register_referral(
    db: Session,
    *,
    referrer_user_id: int,
    referred_user_id: int,
    referral_code_used: str | None = None,
    now: datetime | None = None,
) -> Referral:
    now = now or utcnow()
    if referrer_user_id == referred_user_id:
        raise ReferralError("self_referral")
    referrer = db.get(User, referrer_user_id)
    referred = db.get(User, referred_user_id)
    if referrer is None or referred is None:
        raise ReferralError("user_not_found")

    existing = db.execute(
        select(Referral).where(Referral.referred_user_id == referred_user_id)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.referrer_user_id != referrer_user_id:
            raise ReferralError("referral_already_attributed")
        return existing

    code = (referral_code_used or referrer.referral_code or "").strip()
    if not code:
        raise ReferralError("referral_code_missing")

    row = Referral(
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        referral_code_used=code,
        registered_at=now,
    )
    db.add(row)
    referred.referred_by = referrer_user_id
    db.flush()
    track_event(
        db,
        event_type=EVENT_REFERRAL_REGISTRATION,
        user_id=referrer_user_id,
        metadata={"referred_user_id": referred_user_id},
        now=now,
    )
    return row


def mark_referred_profile_completed(
    db: Session,
    *,
    referred_user_id: int,
    now: datetime | None = None,
) -> Referral | None:
    now = now or utcnow()
    row = db.execute(
        select(Referral).where(Referral.referred_user_id == referred_user_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.profile_completed_at is not None:
        return row

    row.profile_completed_at = now
    if row.referrer_user_id is not None:
        track_event(
            db,
            event_type=EVENT_REFERRAL_COMPLETED_PROFILE,
            user_id=row.referrer_user_id,
            metadata={"referred_user_id": referred_user_id},
            now=now,
        )
    db.flush()
    return row


def referral_stats(db: Session, *, user_id: int) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise ReferralError("user_not_found")

    registrations = int(
        db.scalar(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_user_id == user_id
            )
        )
        or 0
    )
    completed = int(
        db.scalar(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_user_id == user_id,
                Referral.profile_completed_at.is_not(None),
            )
        )
        or 0
    )
    return {
        "referral_code": user.referral_code,
        "invites_sent": int(user.invites_sent),
        "registrations": registrations,
        "completed_profiles": completed,
        "registration_rate": (
            round(registrations * 100 / user.invites_sent, 1)
            if user.invites_sent > 0
            else None
        ),
        "completion_rate": (
            round(completed * 100 / registrations, 1)
            if registrations > 0
            else None
        ),
    }
