from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_SUBSCRIPTION_STARTED, track_once
from app.db.models import Payment, Subscription, User, UserEntitlement


TIERS = ("FREE", "PREMIUM", "PREMIUM_PLUS")
PAID_TIERS = {"PREMIUM", "PREMIUM_PLUS"}
PROVIDERS = {"APPLE", "GOOGLE", "WEB", "MANUAL"}
ENVIRONMENTS = {"PRODUCTION", "SANDBOX"}
ACTIVE_SUBSCRIPTION_STATUSES = {"ACTIVE", "GRACE"}

PLAN_FEATURES = {
    "FREE": {
        "CORE_MATCHING",
        "BASIC_COMPATIBILITY",
        "QUESTIONNAIRE",
        "MESSAGING",
    },
    "PREMIUM": {
        "CORE_MATCHING",
        "BASIC_COMPATIBILITY",
        "QUESTIONNAIRE",
        "MESSAGING",
        "ADDITIONAL_ACTIVE_MATCHES",
        "EXTENDED_PREFERENCES",
        "DEEP_COMPATIBILITY_BREAKDOWN",
    },
    "PREMIUM_PLUS": {
        "CORE_MATCHING",
        "BASIC_COMPATIBILITY",
        "QUESTIONNAIRE",
        "MESSAGING",
        "ADDITIONAL_ACTIVE_MATCHES",
        "EXTENDED_PREFERENCES",
        "DEEP_COMPATIBILITY_BREAKDOWN",
        "PRIORITY_MATCHING",
        "AI_RELATIONSHIP_ANALYSIS",
    },
}

ONE_TIME_DEEP_REPORT = "DEEP_COMPATIBILITY_REPORT"


class BillingError(Exception):
    pass


class InvalidVerifiedTransaction(BillingError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _provider(value: str) -> str:
    provider = (value or "").strip().upper()
    if provider not in PROVIDERS:
        raise InvalidVerifiedTransaction("unsupported_provider")
    return provider


def _environment(value: str) -> str:
    env = (value or "PRODUCTION").strip().upper()
    if env not in ENVIRONMENTS:
        raise InvalidVerifiedTransaction("unsupported_environment")
    return env


def _tier(value: str) -> str:
    tier = (value or "").strip().upper()
    if tier not in PAID_TIERS:
        raise InvalidVerifiedTransaction("unsupported_paid_tier")
    return tier


def _status(value: str) -> str:
    status = (value or "").strip().upper()
    allowed = {"ACTIVE", "GRACE", "BILLING_RETRY", "EXPIRED", "REVOKED"}
    if status not in allowed:
        raise InvalidVerifiedTransaction("unsupported_subscription_status")
    return status


def apply_verified_subscription(
    db: Session,
    *,
    user_id: int,
    provider: str,
    provider_subscription_id: str,
    product_code: str,
    tier: str,
    status: str,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    auto_renew: bool,
    environment: str = "PRODUCTION",
    verified_at: datetime | None = None,
) -> Subscription:
    user = db.get(User, user_id)
    if user is None:
        raise BillingError("user_not_found")

    provider = _provider(provider)
    environment = _environment(environment)
    tier = _tier(tier)
    status = _status(status)
    external_id = (provider_subscription_id or "").strip()
    product_code = (product_code or "").strip()
    if not external_id:
        raise InvalidVerifiedTransaction("subscription_id_required")
    if not product_code:
        raise InvalidVerifiedTransaction("product_code_required")
    if current_period_start and current_period_end and current_period_start > current_period_end:
        raise InvalidVerifiedTransaction("invalid_subscription_period")

    row = db.execute(
        select(Subscription).where(
            Subscription.provider == provider,
            Subscription.provider_subscription_id == external_id,
        )
    ).scalar_one_or_none()

    now = verified_at or utcnow()
    if row is None:
        row = Subscription(
            user_id=user_id,
            provider=provider,
            provider_subscription_id=external_id,
            product_code=product_code,
            tier=tier,
            status=status,
            environment=environment,
            auto_renew=bool(auto_renew),
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            verified_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        if row.user_id != user_id:
            raise InvalidVerifiedTransaction("subscription_belongs_to_another_user")
        row.product_code = product_code
        row.tier = tier
        row.status = status
        row.environment = environment
        row.auto_renew = bool(auto_renew)
        row.current_period_start = current_period_start
        row.current_period_end = current_period_end
        row.verified_at = now
        row.updated_at = now

    db.flush()
    if status in ACTIVE_SUBSCRIPTION_STATUSES:
        track_once(
            db,
            event_type=EVENT_SUBSCRIPTION_STARTED,
            user_id=user_id,
            metadata={"provider": provider, "tier": tier},
            now=now,
        )
    return row


def active_plan(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> str:
    now = now or utcnow()
    rows = db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(tuple(ACTIVE_SUBSCRIPTION_STATUSES)),
            or_(
                Subscription.current_period_end.is_(None),
                Subscription.current_period_end > now,
            ),
        )
    ).scalars().all()
    if not rows:
        return "FREE"
    tiers = {row.tier for row in rows}
    if "PREMIUM_PLUS" in tiers:
        return "PREMIUM_PLUS"
    if "PREMIUM" in tiers:
        return "PREMIUM"
    return "FREE"


def plan_features(plan: str) -> set[str]:
    plan = (plan or "").strip().upper()
    if plan not in PLAN_FEATURES:
        raise BillingError("unknown_plan")
    return set(PLAN_FEATURES[plan])


def plan_has_feature(plan: str, feature: str) -> bool:
    return (feature or "").strip().upper() in plan_features(plan)


def record_verified_payment(
    db: Session,
    *,
    user_id: int,
    provider: str,
    provider_transaction_id: str,
    product_code: str,
    purchase_kind: str,
    status: str,
    purchased_at: datetime,
    amount_minor: int | None = None,
    currency: str | None = None,
    environment: str = "PRODUCTION",
) -> Payment:
    if db.get(User, user_id) is None:
        raise BillingError("user_not_found")
    provider = _provider(provider)
    environment = _environment(environment)
    tx = (provider_transaction_id or "").strip()
    product = (product_code or "").strip()
    kind = (purchase_kind or "").strip().upper()
    payment_status = (status or "").strip().upper()
    if not tx:
        raise InvalidVerifiedTransaction("transaction_id_required")
    if not product:
        raise InvalidVerifiedTransaction("product_code_required")
    if kind not in {"SUBSCRIPTION", "ONE_TIME"}:
        raise InvalidVerifiedTransaction("unsupported_purchase_kind")
    if payment_status not in {"PURCHASED", "PENDING", "REFUNDED", "REVOKED"}:
        raise InvalidVerifiedTransaction("unsupported_payment_status")
    if amount_minor is not None and amount_minor < 0:
        raise InvalidVerifiedTransaction("negative_amount")
    normalized_currency = currency.upper() if currency else None
    if normalized_currency is not None and len(normalized_currency) != 3:
        raise InvalidVerifiedTransaction("invalid_currency")

    existing = db.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_transaction_id == tx,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != user_id or existing.product_code != product:
            raise InvalidVerifiedTransaction("transaction_conflict")
        existing.status = payment_status
        return existing

    row = Payment(
        user_id=user_id,
        provider=provider,
        provider_transaction_id=tx,
        product_code=product,
        purchase_kind=kind,
        amount_minor=amount_minor,
        currency=normalized_currency,
        status=payment_status,
        environment=environment,
        purchased_at=purchased_at,
    )
    db.add(row)
    db.flush()
    return row


def grant_one_time_entitlement(
    db: Session,
    *,
    user_id: int,
    entitlement_key: str,
    scope_key: str,
    payment_id: int,
    expires_at: datetime | None = None,
) -> UserEntitlement:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.user_id != user_id:
        raise BillingError("payment_not_found")
    if payment.purchase_kind != "ONE_TIME" or payment.status != "PURCHASED":
        raise BillingError("payment_not_eligible")
    key = (entitlement_key or "").strip().upper()
    scope = (scope_key or "").strip()
    if not key or not scope:
        raise BillingError("entitlement_key_and_scope_required")

    row = db.get(UserEntitlement, (user_id, key, scope))
    if row is None:
        row = UserEntitlement(
            user_id=user_id,
            entitlement_key=key,
            scope_key=scope,
            source_payment_id=payment.id,
            expires_at=expires_at,
        )
        db.add(row)
    else:
        row.source_payment_id = payment.id
        row.expires_at = expires_at
        row.revoked_at = None
    db.flush()
    return row


def grant_deep_report(
    db: Session,
    *,
    user_id: int,
    match_id: int,
    payment_id: int,
) -> UserEntitlement:
    if match_id <= 0:
        raise BillingError("invalid_match_id")
    return grant_one_time_entitlement(
        db,
        user_id=user_id,
        entitlement_key=ONE_TIME_DEEP_REPORT,
        scope_key=f"match:{match_id}",
        payment_id=payment_id,
    )


def has_entitlement(
    db: Session,
    *,
    user_id: int,
    entitlement_key: str,
    scope_key: str,
    now: datetime | None = None,
) -> bool:
    now = now or utcnow()
    row = db.get(
        UserEntitlement,
        (user_id, entitlement_key.strip().upper(), scope_key.strip()),
    )
    if row is None or row.revoked_at is not None:
        return False
    return row.expires_at is None or row.expires_at > now


def billing_state(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan = active_plan(db, user_id=user_id, now=now)
    return {
        "plan": plan,
        "features": sorted(plan_features(plan)),
    }
