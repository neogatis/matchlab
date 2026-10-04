from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import jwt
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_REGISTRATION, EVENT_REGISTRATION_COMPLETED, track_once
from app.db.models import AuthIdentity, MarketingAttribution, User
from .service import AuthError, hash_password, normalize_email


GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
APPLE_ISSUER = "https://appleid.apple.com"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_JWKS = "https://appleid.apple.com/auth/keys"


class OAuthError(AuthError):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    claims: dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _csv_env(*names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        for item in raw.split(","):
            item = item.strip()
            if item and item not in values:
                values.append(item)
    return values


def configured_audiences(provider: str) -> list[str]:
    provider = (provider or "").strip().upper()
    if provider == "GOOGLE":
        values = _csv_env(
            "GOOGLE_SERVER_CLIENT_ID",
            "GOOGLE_CLIENT_IDS",
            "GOOGLE_CLIENT_ID",  # backwards-compatible alias
        )
        missing = "google_server_client_id_missing"
    elif provider == "APPLE":
        values = _csv_env(
            "APPLE_CLIENT_IDS",
            "APPLE_CLIENT_ID",  # backwards-compatible alias
        )
        missing = "apple_client_id_missing"
    else:
        raise OAuthError("unsupported_oauth_provider")
    if not values:
        raise OAuthError(missing)
    return values


def _jwks_url(provider: str) -> str:
    return GOOGLE_JWKS if provider == "GOOGLE" else APPLE_JWKS


def verify_identity_token(
    *,
    provider: str,
    id_token: str,
    expected_nonce: str,
) -> VerifiedIdentity:
    provider = (provider or "").strip().upper()
    if provider not in {"GOOGLE", "APPLE"}:
        raise OAuthError("unsupported_oauth_provider")
    if not id_token or not expected_nonce:
        raise OAuthError("id_token_and_nonce_required")

    try:
        jwk_client = PyJWKClient(_jwks_url(provider), cache_keys=True, lifespan=3600)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=configured_audiences(provider),
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except Exception as exc:
        raise OAuthError("invalid_identity_token") from exc

    issuer = claims.get("iss")
    if provider == "GOOGLE":
        if issuer not in GOOGLE_ISSUERS:
            raise OAuthError("invalid_identity_issuer")
    elif issuer != APPLE_ISSUER:
        raise OAuthError("invalid_identity_issuer")

    claim_nonce = str(claims.get("nonce") or "")
    nonce_hash = hashlib.sha256(expected_nonce.encode("utf-8")).hexdigest()
    if claim_nonce not in {expected_nonce, nonce_hash}:
        raise OAuthError("invalid_identity_nonce")

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise OAuthError("identity_subject_missing")

    raw_email = str(claims.get("email") or "").strip()
    email = normalize_email(raw_email) if raw_email else None
    verified_raw = claims.get("email_verified")
    email_verified = verified_raw is True or str(verified_raw).lower() == "true"

    # Apple relay addresses are verified by Apple when present.
    if provider == "APPLE" and email:
        email_verified = True

    return VerifiedIdentity(
        provider=provider,
        subject=subject,
        email=email,
        email_verified=email_verified,
        claims=claims,
    )


def _synthetic_email(provider: str, subject: str) -> str:
    digest = hashlib.sha256(f"{provider}:{subject}".encode("utf-8")).hexdigest()[:40]
    return f"{provider.lower()}-{digest}@identity.matchlab.invalid"


def _new_identity_user(
    db: Session,
    *,
    identity: VerifiedIdentity,
    referral_code: str | None = None,
    attribution: dict | None = None,
) -> User:
    email = identity.email if identity.email_verified and identity.email else _synthetic_email(
        identity.provider, identity.subject
    )
    user = User(
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        referral_code=secrets.token_urlsafe(9),
        email_verified_at=_utcnow() if identity.email_verified and identity.email else None,
        password_updated_at=_utcnow(),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise OAuthError("identity_account_conflict") from exc

    attribution = attribution or {}
    db.add(
        MarketingAttribution(
            user_id=user.id,
            utm_source=str(attribution.get("utm_source", ""))[:255],
            utm_medium=str(attribution.get("utm_medium", ""))[:255],
            utm_campaign=str(attribution.get("utm_campaign", ""))[:255],
            utm_content=str(attribution.get("utm_content", ""))[:255],
            utm_term=str(attribution.get("utm_term", ""))[:255],
            referral_input=(referral_code or "").strip()[:255],
        )
    )
    metadata = {
        "channel": identity.provider.lower(),
        "platform": str((attribution or {}).get("platform", "web")),
    }
    track_once(db, event_type=EVENT_REGISTRATION, user_id=user.id, metadata=metadata)
    track_once(db, event_type=EVENT_REGISTRATION_COMPLETED, user_id=user.id, metadata=metadata)
    return user


def login_or_register_identity(
    db: Session,
    *,
    identity: VerifiedIdentity,
    referral_code: str | None = None,
    attribution: dict | None = None,
) -> User:
    existing_identity = db.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == identity.provider,
            AuthIdentity.provider_subject == identity.subject,
        )
    ).scalar_one_or_none()
    if existing_identity is not None:
        user = db.get(User, existing_identity.user_id)
        if user is None or user.status not in {"ACTIVE", "SOFT_BANNED"}:
            raise OAuthError("account_unavailable")
        return user

    user = None
    if identity.email_verified and identity.email:
        user = db.execute(
            select(User).where(func.lower(User.email) == identity.email.lower())
        ).scalar_one_or_none()
        if user is not None and user.email_verified_at is None:
            raise OAuthError("existing_email_requires_verification")

    if user is None:
        user = _new_identity_user(
            db,
            identity=identity,
            referral_code=referral_code,
            attribution=attribution,
        )

    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=identity.provider,
            provider_subject=identity.subject,
            provider_email=identity.email,
            verified_at=_utcnow(),
        )
    )
    db.flush()
    return user


def link_identity(
    db: Session,
    *,
    user_id: int,
    identity: VerifiedIdentity,
) -> AuthIdentity:
    existing = db.execute(
        select(AuthIdentity).where(
            AuthIdentity.provider == identity.provider,
            AuthIdentity.provider_subject == identity.subject,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id != user_id:
            raise OAuthError("identity_already_linked")
        return existing

    row = AuthIdentity(
        user_id=user_id,
        provider=identity.provider,
        provider_subject=identity.subject,
        provider_email=identity.email,
        verified_at=_utcnow(),
    )
    db.add(row)
    db.flush()
    return row
