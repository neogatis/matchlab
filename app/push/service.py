from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Notification, PushDelivery, PushDevice, User


MAX_ATTEMPTS = 5
RETRY_MINUTES = (1, 5, 30, 120, 360)


class PushError(Exception):
    pass


class PushProviderError(PushError):
    pass


class PushTokenVault(Protocol):
    def store(self, token: str) -> str:
        ...

    def resolve(self, token_ref: str) -> str:
        ...

    def delete(self, token_ref: str) -> None:
        ...


@dataclass(frozen=True)
class PushSendResult:
    ok: bool
    provider_message_id: str | None = None
    invalid_token: bool = False
    error: str | None = None


class PushProviderClient(Protocol):
    def send(
        self,
        *,
        token: str,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> PushSendResult:
        ...


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_device(
    db: Session,
    *,
    user_id: int,
    provider: str,
    platform: str,
    token: str,
    vault: PushTokenVault,
    locale: str = "ru-KZ",
    now: datetime | None = None,
) -> PushDevice:
    now = now or utcnow()
    if db.get(User, user_id) is None:
        raise PushError("user_not_found")

    provider = (provider or "").strip().upper()
    platform = (platform or "").strip().upper()
    token = (token or "").strip()

    if provider not in {"APNS", "FCM"}:
        raise PushError("unsupported_provider")
    if platform not in {"IOS", "ANDROID"}:
        raise PushError("unsupported_platform")
    if provider == "APNS" and platform != "IOS":
        raise PushError("provider_platform_mismatch")
    if provider == "FCM" and platform != "ANDROID":
        raise PushError("provider_platform_mismatch")
    if len(token) < 16 or len(token) > 4096:
        raise PushError("invalid_token_length")

    token_hash = _hash_token(token)
    row = db.execute(
        select(PushDevice).where(
            PushDevice.provider == provider,
            PushDevice.token_hash == token_hash,
        )
    ).scalar_one_or_none()

    token_ref = vault.store(token)
    if not token_ref:
        raise PushError("token_vault_failed")

    if row is None:
        row = PushDevice(
            user_id=user_id,
            provider=provider,
            platform=platform,
            token_hash=token_hash,
            token_ref=token_ref,
            locale=(locale or "ru-KZ")[:16],
            enabled=True,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        if row.token_ref != token_ref:
            try:
                vault.delete(row.token_ref)
            except Exception:
                pass
        row.user_id = user_id
        row.platform = platform
        row.token_ref = token_ref
        row.locale = (locale or "ru-KZ")[:16]
        row.enabled = True
        row.last_seen_at = now
        row.updated_at = now

    db.flush()
    return row


def disable_device(
    db: Session,
    *,
    device_id: int,
    vault: PushTokenVault | None = None,
    now: datetime | None = None,
) -> bool:
    row = db.get(PushDevice, device_id)
    if row is None:
        return False

    row.enabled = False
    row.updated_at = now or utcnow()

    if vault is not None:
        try:
            vault.delete(row.token_ref)
        except Exception:
            pass

    db.flush()
    return True


def safe_payload(notification: Notification) -> tuple[str, str, dict[str, str]]:
    kind = (notification.kind or "").upper()

    if kind == "MATCH":
        return "MatchLab", "У вас взаимный интерес", {"kind": "MATCH"}

    if kind == "MESSAGE":
        return "MatchLab", "У вас новое сообщение", {"kind": "MESSAGE"}

    if kind == "DATE":
        return "MatchLab", "Вам предложили встречу", {"kind": "DATE"}

    if kind == "DATE_RESULT":
        return (
            "MatchLab",
            "Обновление по предложению встречи",
            {"kind": "DATE_RESULT"},
        )

    if kind == "PHOTO_APPROVED":
        return "MatchLab", "Ваше фото одобрено", {"kind": "PHOTO_APPROVED"}

    if kind == "PHOTO_REJECTED":
        return (
            "MatchLab",
            "Одно из фото не прошло модерацию",
            {"kind": "PHOTO_REJECTED"},
        )

    return (
        "MatchLab",
        "У вас новое уведомление",
        {"kind": kind[:40] or "GENERAL"},
    )


def enqueue_notification(
    db: Session,
    *,
    notification_id: int,
    now: datetime | None = None,
) -> list[PushDelivery]:
    now = now or utcnow()
    notification = db.get(Notification, notification_id)

    if notification is None:
        raise PushError("notification_not_found")

    devices = list(
        db.execute(
            select(PushDevice).where(
                PushDevice.user_id == notification.user_id,
                PushDevice.enabled.is_(True),
            )
        ).scalars()
    )

    deliveries: list[PushDelivery] = []

    for device in devices:
        row = db.execute(
            select(PushDelivery).where(
                PushDelivery.notification_id == notification.id,
                PushDelivery.device_id == device.id,
            )
        ).scalar_one_or_none()

        if row is None:
            row = PushDelivery(
                notification_id=notification.id,
                device_id=device.id,
                status="PENDING",
                attempts=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()

        deliveries.append(row)

    return deliveries


def pending_deliveries(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> list[PushDelivery]:
    now = now or utcnow()

    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")

    return list(
        db.execute(
            select(PushDelivery)
            .where(
                PushDelivery.status.in_(("PENDING", "FAILED")),
                PushDelivery.attempts < MAX_ATTEMPTS,
                or_(
                    PushDelivery.next_attempt_at.is_(None),
                    PushDelivery.next_attempt_at <= now,
                ),
            )
            .order_by(PushDelivery.created_at, PushDelivery.id)
            .limit(limit)
        ).scalars()
    )


def dispatch_delivery(
    db: Session,
    *,
    delivery_id: int,
    clients: dict[str, PushProviderClient],
    vault: PushTokenVault,
    now: datetime | None = None,
) -> PushDelivery:
    now = now or utcnow()

    delivery = db.get(PushDelivery, delivery_id)
    if delivery is None:
        raise PushError("delivery_not_found")

    if delivery.status in {"SENT", "DISABLED"}:
        return delivery

    if delivery.attempts >= MAX_ATTEMPTS:
        return delivery

    notification = db.get(Notification, delivery.notification_id)
    device = db.get(PushDevice, delivery.device_id)

    if notification is None or device is None or not device.enabled:
        delivery.status = "DISABLED"
        delivery.updated_at = now
        db.flush()
        return delivery

    client = clients.get(device.provider)
    if client is None:
        raise PushProviderError(f"provider_client_missing:{device.provider}")

    try:
        token = vault.resolve(device.token_ref)
    except Exception as exc:
        raise PushError("token_vault_resolve_failed") from exc

    title, body, data = safe_payload(notification)

    delivery.status = "SENDING"
    delivery.attempts += 1
    delivery.updated_at = now
    db.flush()

    try:
        result = client.send(
            token=token,
            title=title,
            body=body,
            data=data,
        )
    except Exception as exc:
        result = PushSendResult(
            ok=False,
            error=type(exc).__name__,
        )

    if result.ok:
        delivery.status = "SENT"
        delivery.provider_message_id = (
            (result.provider_message_id or "")[:255] or None
        )
        delivery.last_error = None
        delivery.next_attempt_at = None
        delivery.sent_at = now

    elif result.invalid_token:
        delivery.status = "DISABLED"
        delivery.last_error = (result.error or "invalid_token")[:1000]
        delivery.next_attempt_at = None
        device.enabled = False
        device.updated_at = now

        try:
            vault.delete(device.token_ref)
        except Exception:
            pass

    else:
        delivery.status = "FAILED"
        delivery.last_error = (result.error or "provider_error")[:1000]

        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.next_attempt_at = None
        else:
            minutes = RETRY_MINUTES[
                min(delivery.attempts - 1, len(RETRY_MINUTES) - 1)
            ]
            delivery.next_attempt_at = now + timedelta(minutes=minutes)

    delivery.updated_at = now
    db.flush()
    return delivery


def dispatch_pending(
    db: Session,
    *,
    clients: dict[str, PushProviderClient],
    vault: PushTokenVault,
    limit: int = 100,
    now: datetime | None = None,
) -> list[PushDelivery]:
    now = now or utcnow()

    rows = pending_deliveries(
        db,
        limit=limit,
        now=now,
    )

    return [
        dispatch_delivery(
            db,
            delivery_id=row.id,
            clients=clients,
            vault=vault,
            now=now,
        )
        for row in rows
    ]
