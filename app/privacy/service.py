from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.auth.service import login_bucket
from app.db.models import (
    AdminAccount,
    AuditLog,
    AuthChallenge,
    AuthIdentity,
    AuthOutbox,
    AuthRateLimit,
    Block,
    Consent,
    DataRequest,
    Interest,
    MarketingAttribution,
    Match,
    Message,
    ModerationAction,
    Notification,
    PartnerPreference,
    Payment,
    Photo,
    PhotoObjectDeletion,
    PhotoUploadTicket,
    ProductEvent,
    Profile,
    PushDevice,
    QuestionnaireAnswer,
    Referral,
    Report,
    Session as DbSession,
    Subscription,
    User,
    UserEntitlement,
    UserStatusHistory,
)


DELETION_GRACE_DAYS = 30

RETENTION_POLICY = {
    "account_deletion_grace_days": DELETION_GRACE_DAYS,
    "auth_rate_limit_days": 1,
    "auth_challenge_days": 7,
    "sent_auth_outbox_days": 30,
    "completed_data_request_log_days": 180,
    "photo_deletion_log_days": 30,
    "product_analytics_days": 365,
    "security_audit_days": 365,
    "moderation_audit_days": 365,
    "billing_records": (
        "Retained only as needed for payment-provider reconciliation, fraud prevention, "
        "and applicable accounting or legal obligations; direct account identifiers are "
        "pseudonymized when the deletion purge runs."
    ),
}


class PrivacyError(Exception):
    pass


class DeletionAlreadyRequested(PrivacyError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def retention_policy() -> dict[str, Any]:
    return dict(RETENTION_POLICY)


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _record(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _value(getattr(row, field)) for field in fields}


def _rows(db: Session, model, predicate, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        _record(row, fields)
        for row in db.execute(select(model).where(predicate)).scalars()
    ]


def export_user_data(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    user = db.get(User, user_id)
    if user is None:
        raise PrivacyError("user_not_found")

    profile = db.get(Profile, user_id)

    request = DataRequest(
        user_id=user_id,
        request_type="EXPORT",
        status="COMPLETED",
        requested_at=now,
        completed_at=now,
    )
    db.add(request)
    db.flush()

    match_rows = db.execute(
        select(Match).where(or_(Match.user1 == user_id, Match.user2 == user_id))
    ).scalars().all()

    payload = {
        "schema_version": "matchlab-export-v1",
        "generated_at": now,
        "account": {
            "id": user.id,
            "email": user.email,
            "phone_e164": user.phone_e164,
            "status": user.status,
            "email_verified_at": user.email_verified_at,
            "phone_verified_at": user.phone_verified_at,
            "created_at": user.created_at,
        },
        "profile": (
            _record(
                profile,
                (
                    "display_name",
                    "dob",
                    "gender",
                    "seek_gender",
                    "city",
                    "country_code",
                    "preferred_locale",
                    "relationship_status",
                    "eligibility_status",
                    "dating_goal",
                    "readiness_chat",
                    "readiness_offline",
                    "readiness_score",
                    "bio",
                    "height",
                    "smoking",
                    "alcohol",
                    "lifestyle",
                    "religion",
                    "nationality",
                    "children_status",
                    "children_attitude",
                    "children_plans",
                    "questionnaire_completed",
                    "partner_preferences_completed",
                    "photos_completed",
                    "profile_completed",
                    "status_confirmed_at",
                    "updated_at",
                ),
            )
            if profile is not None
            else None
        ),
        "status_history": _rows(
            db,
            UserStatusHistory,
            UserStatusHistory.user_id == user_id,
            ("relationship_status", "eligibility_status", "source", "created_at"),
        ),
        "questionnaire_answers": _rows(
            db,
            QuestionnaireAnswer,
            QuestionnaireAnswer.user_id == user_id,
            ("question_id", "value_int", "value_text", "value_json", "answered_at"),
        ),
        "partner_preferences": _rows(
            db,
            PartnerPreference,
            PartnerPreference.user_id == user_id,
            (
                "criterion_key",
                "importance",
                "value_text",
                "value_bool",
                "min_value",
                "max_value",
                "values_json",
                "updated_at",
            ),
        ),
        "photos": _rows(
            db,
            Photo,
            Photo.user_id == user_id,
            (
                "id",
                "mime",
                "byte_size",
                "is_main",
                "sort_order",
                "moderation_status",
                "moderation_reason",
                "moderated_at",
                "created_at",
            ),
        ),
        # Related users' internal identifiers are deliberately omitted.
        "interest_actions": _rows(
            db,
            Interest,
            Interest.from_user == user_id,
            ("state", "source_algorithm_version", "snooze_until", "created_at", "updated_at"),
        ),
        "matches": [
            {
                "compatibility_score": row.compatibility_score,
                "mutual_fit_score": row.mutual_fit_score,
                "algorithm_version": row.algorithm_version,
                "created_at": row.created_at,
            }
            for row in match_rows
        ],
        "sent_messages": _rows(
            db,
            Message,
            Message.sender == user_id,
            ("body", "created_at", "read_at"),
        ),
        "blocks_created": _rows(
            db,
            Block,
            Block.blocker == user_id,
            ("created_at",),
        ),
        "reports_created": _rows(
            db,
            Report,
            Report.reporter == user_id,
            ("reason", "status", "created_at"),
        ),
        "marketing_attribution": _rows(
            db,
            MarketingAttribution,
            MarketingAttribution.user_id == user_id,
            ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "referral_input"),
        ),
        "subscriptions": _rows(
            db,
            Subscription,
            Subscription.user_id == user_id,
            (
                "provider",
                "product_code",
                "tier",
                "status",
                "environment",
                "auto_renew",
                "current_period_start",
                "current_period_end",
                "verified_at",
                "created_at",
                "updated_at",
            ),
        ),
        "payments": _rows(
            db,
            Payment,
            Payment.user_id == user_id,
            (
                "provider",
                "product_code",
                "purchase_kind",
                "amount_minor",
                "currency",
                "status",
                "environment",
                "purchased_at",
                "created_at",
            ),
        ),
        "notifications": _rows(
            db,
            Notification,
            Notification.user_id == user_id,
            ("kind", "text", "created_at", "read_at"),
        ),
        "consents": _rows(
            db,
            Consent,
            Consent.user_id == user_id,
            ("consent_type", "version", "granted", "created_at"),
        ),
        "analytics_events": _rows(
            db,
            ProductEvent,
            ProductEvent.user_id == user_id,
            ("event_type", "metadata_json", "created_at"),
        ),
        "retention_policy": retention_policy(),
        "export_request_id": request.id,
    }

    db.add(
        AuditLog(
            actor_type="USER",
            actor_id=str(user_id),
            action="PRIVACY_EXPORT",
            target_type="data_request",
            target_id=str(request.id),
            metadata_json={"schema_version": payload["schema_version"]},
            created_at=now,
        )
    )
    db.flush()
    return payload


def request_account_deletion(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    user = db.get(User, user_id)
    if user is None:
        raise PrivacyError("user_not_found")

    active = db.execute(
        select(DataRequest).where(
            DataRequest.user_id == user_id,
            DataRequest.request_type == "DELETE",
            DataRequest.status == "PENDING",
        )
    ).scalar_one_or_none()
    if active is not None:
        raise DeletionAlreadyRequested("deletion_already_requested")

    request = DataRequest(
        user_id=user_id,
        request_type="DELETE",
        status="PENDING",
        requested_at=now,
    )
    db.add(request)

    user.status = "DELETION_REQUESTED"

    profile = db.get(Profile, user_id)
    if profile is not None:
        profile.relationship_status = "NOT_ACTIVE"
        profile.eligibility_status = "NOT_ACTIVE_FOR_MATCHING"
        profile.updated_at = now

    for row in db.execute(
        select(DbSession).where(
            DbSession.user_id == user_id,
            DbSession.revoked_at.is_(None),
        )
    ).scalars():
        row.revoked_at = now

    for device in db.execute(
        select(PushDevice).where(PushDevice.user_id == user_id)
    ).scalars():
        device.enabled = False
        device.updated_at = now

    db.flush()
    purge_after = now + timedelta(days=DELETION_GRACE_DAYS)
    db.add(
        AuditLog(
            actor_type="USER",
            actor_id=str(user_id),
            action="ACCOUNT_DELETION_REQUESTED",
            target_type="data_request",
            target_id=str(request.id),
            metadata_json={"purge_after": purge_after.isoformat()},
            created_at=now,
        )
    )
    db.flush()
    return {
        "request_id": request.id,
        "status": request.status,
        "requested_at": request.requested_at,
        "purge_after": purge_after,
        "grace_days": DELETION_GRACE_DAYS,
    }


def _purge_one(
    db: Session,
    *,
    request: DataRequest,
    now: datetime,
) -> bool:
    user_id = request.user_id
    user = db.get(User, user_id)
    if user is None:
        request.status = "COMPLETED"
        request.completed_at = now
        return False

    original_email = user.email

    photo_rows = list(
        db.execute(select(Photo).where(Photo.user_id == user_id)).scalars()
    )
    photo_ids = [row.id for row in photo_rows]
    photo_keys = [row.storage_key for row in photo_rows if row.storage_key]

    match_ids = [
        row.id
        for row in db.execute(
            select(Match).where(or_(Match.user1 == user_id, Match.user2 == user_id))
        ).scalars()
    ]
    message_ids: list[int] = []
    if match_ids:
        from app.db.models import Conversation

        conversation_ids = list(
            db.execute(
                select(Conversation.id).where(Conversation.match_id.in_(match_ids))
            ).scalars()
        )
        if conversation_ids:
            message_ids = list(
                db.execute(
                    select(Message.id).where(Message.conversation_id.in_(conversation_ids))
                ).scalars()
            )

    report_conditions = [
        Report.reporter == user_id,
        Report.target_user == user_id,
    ]
    if photo_ids:
        report_conditions.append(Report.photo_id.in_(photo_ids))
    if message_ids:
        report_conditions.append(Report.message_id.in_(message_ids))
    db.execute(delete(Report).where(or_(*report_conditions)))

    if photo_ids:
        db.execute(
            delete(ModerationAction).where(
                ModerationAction.target_type == "photo",
                ModerationAction.target_id.in_([str(value) for value in photo_ids]),
            )
        )

    for object_key in photo_keys:
        existing = db.execute(
            select(PhotoObjectDeletion).where(
                PhotoObjectDeletion.object_key == object_key
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(PhotoObjectDeletion(object_key=object_key, status="PENDING"))

    # Remove product/account data that has no separate statutory retention need.
    for model, predicate in (
        (AdminAccount, AdminAccount.user_id == user_id),
        (AuthIdentity, AuthIdentity.user_id == user_id),
        (AuthChallenge, AuthChallenge.user_id == user_id),
        (DbSession, DbSession.user_id == user_id),
        (UserStatusHistory, UserStatusHistory.user_id == user_id),
        (QuestionnaireAnswer, QuestionnaireAnswer.user_id == user_id),
        (PartnerPreference, PartnerPreference.user_id == user_id),
        (PhotoUploadTicket, PhotoUploadTicket.user_id == user_id),
        (Photo, Photo.user_id == user_id),
        (Interest, or_(Interest.from_user == user_id, Interest.to_user == user_id)),
        (Match, or_(Match.user1 == user_id, Match.user2 == user_id)),
        (Block, or_(Block.blocker == user_id, Block.blocked == user_id)),
        (MarketingAttribution, MarketingAttribution.user_id == user_id),
        (UserEntitlement, UserEntitlement.user_id == user_id),
        (Notification, Notification.user_id == user_id),
        (PushDevice, PushDevice.user_id == user_id),
        (Consent, Consent.user_id == user_id),
    ):
        db.execute(delete(model).where(predicate))

    db.execute(
        delete(AuthOutbox).where(AuthOutbox.recipient == original_email)
    )
    try:
        bucket = login_bucket(original_email)
        db.execute(delete(AuthRateLimit).where(AuthRateLimit.bucket_key == bucket))
    except Exception:
        pass

    db.execute(
        delete(Referral).where(Referral.referred_user_id == user_id)
    )
    db.execute(
        update(Referral)
        .where(Referral.referrer_user_id == user_id)
        .values(referrer_user_id=None)
    )
    db.execute(
        update(User)
        .where(User.referred_by == user_id, User.id != user_id)
        .values(referred_by=None)
    )

    # Analytics is retained only in de-identified form.
    db.execute(
        update(ProductEvent)
        .where(ProductEvent.user_id == user_id)
        .values(user_id=None)
    )

    # Billing records stay attached only to a pseudonymous internal tombstone.
    # They are not available to the deleted account and contain no restored profile.
    user.email = (
        f"deleted-{user_id}-{secrets.token_hex(10)}@deleted.invalid"
    )
    user.password_hash = secrets.token_urlsafe(64)
    user.referral_code = "deleted-" + secrets.token_urlsafe(18)
    user.referred_by = None
    user.invites_sent = 0
    user.phone_e164 = None
    user.email_verified_at = None
    user.phone_verified_at = None
    user.password_updated_at = now
    user.status = "DELETION_REQUESTED"

    request.status = "COMPLETED"
    request.completed_at = now

    db.add(
        AuditLog(
            actor_type="SYSTEM",
            actor_id=None,
            action="ACCOUNT_PRIVACY_PURGE_COMPLETED",
            target_type="data_request",
            target_id=str(request.id),
            metadata_json={
                "photo_objects_queued": len(photo_keys),
                "billing_rows_retained_pseudonymously": True,
            },
            created_at=now,
        )
    )
    db.flush()
    return True


def process_due_deletions(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = now or utcnow()
    cutoff = now - timedelta(days=DELETION_GRACE_DAYS)
    requests = list(
        db.execute(
            select(DataRequest)
            .where(
                DataRequest.request_type == "DELETE",
                DataRequest.status == "PENDING",
                DataRequest.requested_at <= cutoff,
            )
            .order_by(DataRequest.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    purged = 0
    for request in requests:
        if _purge_one(db, request=request, now=now):
            purged += 1
    db.flush()
    return {"processed": len(requests), "purged": purged}


def process_retention_cleanup(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or utcnow()
    counts: dict[str, int] = {}

    def run(name: str, statement) -> None:
        result = db.execute(statement)
        counts[name] = int(result.rowcount or 0)

    run(
        "auth_rate_limits",
        delete(AuthRateLimit).where(
            AuthRateLimit.updated_at < now - timedelta(days=RETENTION_POLICY["auth_rate_limit_days"])
        ),
    )
    run(
        "auth_challenges",
        delete(AuthChallenge).where(
            AuthChallenge.created_at < now - timedelta(days=RETENTION_POLICY["auth_challenge_days"])
        ),
    )
    run(
        "sent_auth_outbox",
        delete(AuthOutbox).where(
            AuthOutbox.status == "SENT",
            AuthOutbox.sent_at.is_not(None),
            AuthOutbox.sent_at < now - timedelta(days=RETENTION_POLICY["sent_auth_outbox_days"]),
        ),
    )
    run(
        "completed_data_requests",
        delete(DataRequest).where(
            DataRequest.status.in_(("COMPLETED", "CANCELLED", "FAILED")),
            DataRequest.completed_at.is_not(None),
            DataRequest.completed_at
            < now - timedelta(days=RETENTION_POLICY["completed_data_request_log_days"]),
        ),
    )
    run(
        "photo_deletion_logs",
        delete(PhotoObjectDeletion).where(
            PhotoObjectDeletion.status == "DONE",
            PhotoObjectDeletion.deleted_at.is_not(None),
            PhotoObjectDeletion.deleted_at
            < now - timedelta(days=RETENTION_POLICY["photo_deletion_log_days"]),
        ),
    )
    run(
        "product_analytics",
        delete(ProductEvent).where(
            ProductEvent.created_at < now - timedelta(days=RETENTION_POLICY["product_analytics_days"])
        ),
    )
    run(
        "security_audit",
        delete(AuditLog).where(
            AuditLog.created_at < now - timedelta(days=RETENTION_POLICY["security_audit_days"])
        ),
    )
    run(
        "moderation_audit",
        delete(ModerationAction).where(
            ModerationAction.created_at
            < now - timedelta(days=RETENTION_POLICY["moderation_audit_days"])
        ),
    )
    db.flush()
    return counts
