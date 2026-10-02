from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.db.models import AuthChallenge, AuthRateLimit, Session as DbSession, User


PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class AuthError(Exception):
    pass


class InvalidCredentials(AuthError):
    pass


class InvalidOrExpiredChallenge(AuthError):
    pass


class RateLimited(AuthError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("Too many attempts")
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: int
    selector: str
    legacy: bool = False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(value: str) -> str:
    raw = (value or "").strip()
    try:
        return validate_email(raw, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise AuthError("Invalid email") from exc


def validate_password(password: str) -> None:
    if len(password or "") < 10:
        raise AuthError("Password must contain at least 10 characters")
    if len(password) > 1024:
        raise AuthError("Password is too long")


def hash_password(password: str) -> str:
    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    try:
        raw = base64.b64decode(stored, validate=True)
        if len(raw) != 48:
            return False
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    if not stored:
        return False, False
    if stored.startswith("$argon2"):
        try:
            ok = PASSWORD_HASHER.verify(stored, password)
            return bool(ok), bool(ok and PASSWORD_HASHER.check_needs_rehash(stored))
        except (VerifyMismatchError, InvalidHashError):
            return False, False
    return _verify_legacy_pbkdf2(password, stored), True


def register_email_user(db: OrmSession, email: str, password: str, referred_by: int | None = None) -> User:
    normalized = normalize_email(email)
    password_hash = hash_password(password)
    user = User(
        email=normalized,
        password_hash=password_hash,
        referral_code=secrets.token_urlsafe(9),
        referred_by=referred_by,
        password_updated_at=utcnow(),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AuthError("Email already registered") from exc
    return user


def _rate_limit(
    db: OrmSession,
    bucket_key: str,
    *,
    limit: int,
    window_seconds: int,
    block_seconds: int,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    row = db.execute(
        select(AuthRateLimit).where(AuthRateLimit.bucket_key == bucket_key).with_for_update()
    ).scalar_one_or_none()

    if row and row.blocked_until and row.blocked_until > now:
        raise RateLimited(int((row.blocked_until - now).total_seconds()) + 1)

    if row is None:
        row = AuthRateLimit(bucket_key=bucket_key, window_started_at=now, hits=0, updated_at=now)
        db.add(row)
        db.flush()

    if now - row.window_started_at >= timedelta(seconds=window_seconds):
        row.window_started_at = now
        row.hits = 0
        row.blocked_until = None

    row.hits += 1
    row.updated_at = now
    if row.hits > limit:
        row.blocked_until = now + timedelta(seconds=block_seconds)
        db.flush()
        raise RateLimited(block_seconds)

    db.flush()
    return max(0, limit - row.hits)


def login_bucket(email: str) -> str:
    return "login:" + sha256_text(normalize_email(email))


def authenticate_password(
    db: OrmSession,
    email: str,
    password: str,
    *,
    apply_rate_limit: bool = True,
    now: datetime | None = None,
) -> User:
    normalized = normalize_email(email)
    if apply_rate_limit:
        _rate_limit(
            db,
            login_bucket(normalized),
            limit=8,
            window_seconds=15 * 60,
            block_seconds=15 * 60,
            now=now,
        )

    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if not user or user.status != "ACTIVE":
        raise InvalidCredentials("Invalid email or password")

    ok, needs_upgrade = verify_password(password, user.password_hash)
    if not ok:
        raise InvalidCredentials("Invalid email or password")

    if needs_upgrade:
        validate_password(password)
        user.password_hash = PASSWORD_HASHER.hash(password)
        user.password_updated_at = now or utcnow()
        db.flush()

    return user


def create_session(
    db: OrmSession,
    user_id: int,
    *,
    user_agent: str = "",
    ttl: timedelta = timedelta(days=30),
    now: datetime | None = None,
) -> str:
    now = now or utcnow()
    selector = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    secret_hash = sha256_text(secret)
    row = DbSession(
        token=selector,
        user_id=user_id,
        secret_hash=secret_hash,
        created_at=now,
        expires_at=now + ttl,
        last_seen_at=now,
        user_agent_hash=sha256_text(user_agent) if user_agent else None,
    )
    db.add(row)
    db.flush()
    return selector + "." + secret


def lookup_session(
    db: OrmSession,
    cookie_value: str,
    *,
    now: datetime | None = None,
    touch: bool = True,
) -> SessionPrincipal | None:
    now = now or utcnow()
    raw = cookie_value or ""

    legacy = "." not in raw
    if legacy:
        secret_hash = sha256_text(raw)
        row = db.execute(
            select(DbSession).where(DbSession.secret_hash == secret_hash)
        ).scalar_one_or_none()
        selector = row.token if row else ""
    else:
        selector, secret = raw.split(".", 1)
        if not selector or not secret:
            return None
        row = db.get(DbSession, selector)
        secret_hash = sha256_text(secret)

    if row is None or not row.secret_hash:
        return None
    if not hmac.compare_digest(row.secret_hash, secret_hash):
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at is not None and row.expires_at <= now:
        return None
    if touch:
        row.last_seen_at = now
        db.flush()
    return SessionPrincipal(user_id=row.user_id, selector=selector, legacy=legacy)


def revoke_session(db: OrmSession, cookie_value: str, *, now: datetime | None = None) -> bool:
    principal = lookup_session(db, cookie_value, now=now, touch=False)
    if not principal:
        return False
    row = db.get(DbSession, principal.selector)
    row.revoked_at = now or utcnow()
    db.flush()
    return True


def revoke_all_sessions(db: OrmSession, user_id: int, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    rows = db.execute(
        select(DbSession).where(DbSession.user_id == user_id, DbSession.revoked_at.is_(None))
    ).scalars().all()
    for row in rows:
        row.revoked_at = now
    db.flush()
    return len(rows)


def challenge_target_hash(channel: str, target: str) -> str:
    normalized = normalize_email(target) if channel == "email" else (target or "").strip()
    return sha256_text(channel + ":" + normalized)


def create_challenge(
    db: OrmSession,
    *,
    user_id: int | None,
    purpose: str,
    channel: str,
    target: str,
    ttl: timedelta = timedelta(minutes=20),
    max_attempts: int = 5,
    now: datetime | None = None,
) -> str:
    now = now or utcnow()
    if channel not in {"email", "phone"}:
        raise AuthError("Unsupported challenge channel")
    secret = f"{secrets.randbelow(1_000_000):06d}" if channel == "phone" else secrets.token_urlsafe(32)
    row = AuthChallenge(
        user_id=user_id,
        purpose=purpose,
        channel=channel,
        target_hash=challenge_target_hash(channel, target),
        secret_hash=sha256_text(secret),
        max_attempts=max_attempts,
        expires_at=now + ttl,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return secret


def consume_challenge(
    db: OrmSession,
    *,
    purpose: str,
    channel: str,
    target: str,
    secret: str,
    now: datetime | None = None,
) -> AuthChallenge:
    now = now or utcnow()
    target_hash = challenge_target_hash(channel, target)
    row = db.execute(
        select(AuthChallenge)
        .where(
            AuthChallenge.purpose == purpose,
            AuthChallenge.channel == channel,
            AuthChallenge.target_hash == target_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .order_by(AuthChallenge.id.desc())
        .with_for_update()
    ).scalars().first()

    if row is None or row.expires_at <= now or row.attempts >= row.max_attempts:
        raise InvalidOrExpiredChallenge("Invalid or expired challenge")

    if not hmac.compare_digest(row.secret_hash, sha256_text(secret or "")):
        row.attempts += 1
        db.flush()
        raise InvalidOrExpiredChallenge("Invalid or expired challenge")

    row.consumed_at = now
    db.flush()
    return row


def verify_email_challenge(
    db: OrmSession,
    *,
    email: str,
    secret: str,
    now: datetime | None = None,
) -> User:
    now = now or utcnow()
    normalized = normalize_email(email)
    challenge = consume_challenge(
        db,
        purpose="EMAIL_VERIFY",
        channel="email",
        target=normalized,
        secret=secret,
        now=now,
    )
    user = db.get(User, challenge.user_id) if challenge.user_id else None
    if user is None or user.email != normalized:
        raise InvalidOrExpiredChallenge("Invalid or expired challenge")
    user.email_verified_at = now
    db.flush()
    return user


def verify_phone_challenge(
    db: OrmSession,
    *,
    phone_e164: str,
    secret: str,
    now: datetime | None = None,
) -> User:
    now = now or utcnow()
    challenge = consume_challenge(
        db,
        purpose="PHONE_VERIFY",
        channel="phone",
        target=phone_e164,
        secret=secret,
        now=now,
    )
    user = db.get(User, challenge.user_id) if challenge.user_id else None
    if user is None:
        raise InvalidOrExpiredChallenge("Invalid or expired challenge")
    user.phone_e164 = phone_e164.strip()
    user.phone_verified_at = now
    db.flush()
    return user


def reset_password_with_challenge(
    db: OrmSession,
    *,
    email: str,
    secret: str,
    new_password: str,
    now: datetime | None = None,
) -> User:
    now = now or utcnow()
    normalized = normalize_email(email)
    challenge = consume_challenge(
        db,
        purpose="PASSWORD_RESET",
        channel="email",
        target=normalized,
        secret=secret,
        now=now,
    )
    user = db.get(User, challenge.user_id) if challenge.user_id else None
    if user is None or user.email != normalized:
        raise InvalidOrExpiredChallenge("Invalid or expired challenge")
    user.password_hash = hash_password(new_password)
    user.password_updated_at = now
    revoke_all_sessions(db, user.id, now=now)
    db.flush()
    return user
