from __future__ import annotations

import json
import mimetypes
import os
import smtplib
import threading
import time
from email.message import EmailMessage
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.auth.service import (
    AuthError,
    InvalidCredentials,
    InvalidOrExpiredChallenge,
    RateLimited,
    authenticate_identifier_password,
    authenticate_password,
    consume_oidc_nonce,
    create_challenge,
    create_oidc_nonce,
    create_session,
    lookup_session,
    normalize_email,
    register_email_user,
    request_email_verification_challenge,
    request_phone_link_code,
    request_phone_login_code,
    request_phone_registration_code,
    reset_password_with_challenge,
    revoke_session,
    verify_email_challenge,
    verify_phone_link_code,
    verify_phone_login_code,
    verify_phone_registration_code,
)
from app.auth.oauth import (
    OAuthError,
    configured_audiences,
    link_identity,
    login_or_register_identity,
    verify_identity_token,
)
from app.auth.sms import SmsError, sms_sender_from_env
from app.auth.web import phone_login_html
from app.analytics.events import (
    EVENT_CANDIDATE_VIEWED,
    EVENT_LANDING_VIEW,
    EVENT_ONBOARDING_STARTED,
    EVENT_REGISTRATION_STARTED,
    track_event,
    track_once,
)
from app.db.models import AuthIdentity, Block, Interest, Market, Match, Notification, Photo, Profile, PushDevice, User
from app.db.session import make_engine
from app.console.access import ConsoleAccessDenied, require_console
from app.console.dashboard import prelaunch_dashboard_html
from app.console.metrics import prelaunch_metrics
from app.console.web import photo_moderation_html
from app.photos.service import (
    PhotoError,
    PhotoLimitReached,
    PhotoNotFound,
    UploadTicketError,
    delete_photo,
    finalize_upload,
    process_deletion_outbox,
    list_owner_photos,
    moderate_photo,
    photo_progress,
    prepare_upload,
    reorder_photos,
    set_main_photo,
)
from app.photos.storage import S3PhotoStorage
from app.chat.service import (
    ChatError,
    ChatUnavailable,
    MessageValidationError,
    NotConversationParticipant,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    mark_read,
    send_message,
)
from app.interests.service import (
    InterestActionsDisabled,
    InterestError,
    InterestUnavailable,
    PairAlreadyMatched,
    _create_match,
    get_match,
    record_decision,
)
from app.matching.service import rank_candidates
from app.push.fcm import FcmProviderClient
from app.push.service import (
    PushError,
    disable_device,
    dispatch_pending,
    enqueue_notification,
    register_device,
)
from app.push.storage import S3PushTokenVault
from app.preferences.catalog import PREFERENCE_CATALOG
from app.preferences.service import (
    InvalidPreference,
    PreferenceError,
    get_preferences,
    set_preferences,
)
from app.prelaunch.policy import feature_flags
from app.prelaunch.service import PrelaunchError, own_compatibility_profile, waitlist_status
from app.privacy.legal import account_deletion_html, privacy_policy_html, terms_html
from app.privacy.service import (
    DeletionAlreadyRequested,
    PrivacyError,
    export_user_data,
    process_due_deletions,
    process_retention_cleanup,
    request_account_deletion,
    retention_policy,
)
from app.safety.service import (
    InvalidReport,
    SafetyError,
    block_user,
    report_user,
    unblock_user,
)
from app.profile.service import (
    MarketUnavailable,
    ProfileError,
    UnderageUser,
    profile_completion_state,
    set_match_profile_details,
    set_readiness,
    set_relationship_state,
    upsert_basic_profile,
    user_age,
)
from app.questionnaire.adaptive import (
    AdaptiveQuestionnaireError,
    answer as adaptive_questionnaire_answer,
    state as adaptive_questionnaire_state,
)
from app.questionnaire.service import (
    InvalidAnswer,
    QuestionnaireError,
    answers_for_user as questionnaire_answers,
    progress as questionnaire_progress,
    save_answers,
    sections as questionnaire_sections,
)
from app.security.http import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    InvalidCsrf,
    InvalidOrigin,
    RequestTooLarge,
    SecurityError,
    new_csrf_token,
    parse_json_body,
    validate_csrf,
    validate_origin,
)


API_PREFIX = "/api/v1"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
WEB_HERO = PROJECT_ROOT / "android" / "app" / "src" / "main" / "res" / "drawable-nodpi" / "matchlab_hero_couple.jpg"


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _allowed_origins() -> set[str]:
    values = set()
    public_url = os.environ.get("PUBLIC_URL", "").strip()
    if public_url:
        values.add(public_url.rstrip("/"))
    for item in os.environ.get("ALLOWED_ORIGINS", "").split(","):
        item = item.strip()
        if item:
            values.add(item.rstrip("/"))
    return values


def _cookie_value(header: str | None, name: str) -> str:
    if not header:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(header)
    except Exception:
        return ""
    morsel = jar.get(name)
    return morsel.value if morsel else ""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


class Runtime:
    def __init__(self) -> None:
        engine = make_engine()
        self.engine = engine
        self.Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def db(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


RUNTIME: Runtime | None = None
PHOTO_STORAGE: S3PhotoStorage | None = None
PUSH_TOKEN_VAULT: S3PushTokenVault | None = None
FCM_CLIENT: FcmProviderClient | None = None


def runtime() -> Runtime:
    global RUNTIME
    if RUNTIME is None:
        RUNTIME = Runtime()
    return RUNTIME


def photo_storage() -> S3PhotoStorage:
    global PHOTO_STORAGE
    if PHOTO_STORAGE is None:
        PHOTO_STORAGE = S3PhotoStorage.from_env()
    return PHOTO_STORAGE


def push_token_vault() -> S3PushTokenVault:
    global PUSH_TOKEN_VAULT
    if PUSH_TOKEN_VAULT is None:
        PUSH_TOKEN_VAULT = S3PushTokenVault.from_env()
    return PUSH_TOKEN_VAULT


def fcm_client() -> FcmProviderClient:
    global FCM_CLIENT
    if FCM_CLIENT is None:
        FCM_CLIENT = FcmProviderClient.from_env()
    return FCM_CLIENT


def photo_storage_configured() -> bool:
    required = (
        "MATCH_PHOTO_BUCKET",
        "AWS_ENDPOINT_URL_S3",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    return all(os.environ.get(name, "").strip() for name in required)


def push_token_vault_configured() -> bool:
    required = (
        "MATCH_PUSH_TOKEN_BUCKET",
        "AWS_ENDPOINT_URL_S3",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    return all(os.environ.get(name, "").strip() for name in required)


def fcm_configured() -> bool:
    return bool(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip())


def phone_auth_configured() -> bool:
    provider = os.environ.get("SMS_PROVIDER", "mobizon").strip().lower() or "mobizon"
    if provider == "mobizon":
        return bool(os.environ.get("MOBIZON_API_KEY", "").strip())
    if provider == "twilio":
        has_sender = bool(
            os.environ.get("TWILIO_FROM_NUMBER", "").strip()
            or os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "").strip()
        )
        return all(
            os.environ.get(name, "").strip()
            for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        ) and has_sender
    return False


def password_reset_email_configured() -> bool:
    return bool(
        os.environ.get("SMTP_HOST", "").strip()
        and os.environ.get("SMTP_FROM", "").strip()
    )


def _send_password_reset_email(email: str, token: str) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip()
    if not host or not sender:
        raise RuntimeError("password_reset_email_not_configured")

    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = os.environ.get("SMTP_SSL", "").strip().lower() in {"1", "true", "yes"}
    use_starttls = os.environ.get("SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes"}
    public_url = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
    if not public_url:
        raise RuntimeError("PUBLIC_URL is required for password reset email")

    reset_url = (
        public_url
        + "/#reset-password?email="
        + quote(email, safe="")
        + "&challenge="
        + quote(token, safe="")
    )

    message = EmailMessage()
    message["Subject"] = "Сброс пароля MatchLab"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Вы запросили новый пароль для MatchLab.\n\n"
        f"Откройте ссылку: {reset_url}\n\n"
        "Если вы не запрашивали восстановление, просто проигнорируйте это письмо."
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=10) as client:
        if not use_ssl and use_starttls:
            client.starttls()
        if username:
            client.login(username, password)
        client.send_message(message)


def _attribution_payload(body: dict[str, Any]) -> dict[str, str]:
    raw = body.get("attribution")
    if not isinstance(raw, dict):
        return {}
    allowed = (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "platform",
    )
    return {
        key: str(raw.get(key, "") or "").strip()[:255]
        for key in allowed
        if str(raw.get(key, "") or "").strip()
    }


def email_verification_configured() -> bool:
    return password_reset_email_configured()


def _send_email_verification_email(email: str, token: str) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip()
    if not host or not sender:
        raise RuntimeError("email_verification_not_configured")

    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = os.environ.get("SMTP_SSL", "").strip().lower() in {"1", "true", "yes"}
    use_starttls = os.environ.get("SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes"}
    public_url = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
    if not public_url:
        raise RuntimeError("PUBLIC_URL is required for verification email")

    verify_url = (
        public_url
        + "/#verify-email?email="
        + quote(email, safe="")
        + "&challenge="
        + quote(token, safe="")
    )
    message = EmailMessage()
    message["Subject"] = "Подтвердите email в MatchLab"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Подтвердите email для MatchLab.\n\n"
        f"Откройте ссылку: {verify_url}\n\n"
        "Ссылка действует ограниченное время. Если это были не вы, письмо можно проигнорировать."
    )

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_cls(host, port, timeout=10) as client:
        if not use_ssl and use_starttls:
            client.starttls()
        if username:
            client.login(username, password)
        client.send_message(message)


def _send_verification_async(email: str, token: str) -> None:
    def worker() -> None:
        try:
            _send_email_verification_email(email, token)
        except (OSError, RuntimeError, smtplib.SMTPException):
            pass

    threading.Thread(
        target=worker,
        name="matchlab-email-verification",
        daemon=True,
    ).start()


def _candidate_photo_urls(db, user_id: int, *, limit: int = 5) -> list[str]:
    photos = list(
        db.execute(
            select(Photo)
            .where(
                Photo.user_id == user_id,
                Photo.moderation_status == "APPROVED",
                Photo.storage_key.is_not(None),
            )
            .order_by(Photo.is_main.desc(), Photo.sort_order, Photo.id)
            .limit(limit)
        ).scalars()
    )
    if not photos or not photo_storage_configured():
        return []
    storage = photo_storage()
    return [
        storage.presign_download(photo.storage_key)
        for photo in photos
        if photo.storage_key
    ]



TEST_PROFILE_EMAILS = {
    "matchlab.virtual.anna@test.invalid": {
        "photo": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=1200&q=86",
        "score": 92,
        "categories": {
            "values": 95,
            "relationship": 91,
            "communication": 94,
            "family": 88,
            "lifestyle": 78,
        },
    },
    "matchlab.virtual.alina@test.invalid": {
        "photo": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=1200&q=86",
        "score": 86,
        "categories": {
            "values": 89,
            "relationship": 84,
            "communication": 90,
            "family": 82,
            "lifestyle": 76,
        },
    },
}


def _test_viewer_enabled(user_id: int) -> bool:
    raw = os.environ.get("MATCHLAB_TEST_VIEWER_USER_IDS", "")
    allowed = {
        int(item.strip())
        for item in raw.split(",")
        if item.strip().isdigit()
    }
    return user_id in allowed


def _test_profile_meta(db, user_id: int) -> dict[str, Any] | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    return TEST_PROFILE_EMAILS.get(user.email)


def _test_candidate_payloads(db, *, viewer_id: int) -> list[dict[str, Any]]:
    if not _test_viewer_enabled(viewer_id):
        return []

    rows = list(
        db.execute(
            select(User).where(User.email.in_(tuple(TEST_PROFILE_EMAILS)))
        ).scalars()
    )
    payloads: list[dict[str, Any]] = []
    for user in rows:
        decision = db.get(Interest, (viewer_id, user.id))
        if decision is not None:
            if decision.state == "INTERESTED":
                continue
            if (
                decision.state == "SKIPPED"
                and (
                    decision.snooze_until is None
                    or decision.snooze_until > datetime.now(timezone.utc)
                )
            ):
                continue

        meta = TEST_PROFILE_EMAILS[user.email]
        payload = _candidate_profile_payload(
            db,
            user_id=user.id,
            scoring={
                "compatibility_score": meta["score"],
                "final_mutual_fit_score": meta["score"],
                "category_scores": meta["categories"],
                "mutual_preference_score": 88,
                "readiness_score": 95,
                "distance_km": 0.0,
            },
        )
        payload["photos"] = [meta["photo"]]
        payload["is_test_profile"] = True
        payloads.append(payload)
    return payloads


def _ensure_test_mutual_chats(db, *, viewer_id: int) -> None:
    if not _test_viewer_enabled(viewer_id):
        return

    test_users = list(
        db.execute(
            select(User).where(User.email.in_(tuple(TEST_PROFILE_EMAILS)))
        ).scalars()
    )
    now = datetime.now(timezone.utc)
    welcome_copy = {
        "matchlab.virtual.anna@test.invalid":
            "Привет 🙂 Увидела, что у нас высокая совместимость. Что для тебя самое важное в хорошем знакомстве?",
        "matchlab.virtual.alina@test.invalid":
            "Привет! Похоже, у нас много общего по анкете. Чем ты любишь заниматься, когда есть свободный вечер?",
    }

    for test_user in test_users:
        if test_user.id == viewer_id:
            continue
        meta = TEST_PROFILE_EMAILS[test_user.email]

        for from_user, to_user in (
            (viewer_id, test_user.id),
            (test_user.id, viewer_id),
        ):
            row = db.get(Interest, (from_user, to_user))
            if row is None:
                row = Interest(
                    from_user=from_user,
                    to_user=to_user,
                    state="INTERESTED",
                    source_algorithm_version="test-profile-v1",
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.state = "INTERESTED"
                row.source_algorithm_version = "test-profile-v1"
                row.snooze_until = None
                row.updated_at = now

        db.flush()

        match = get_match(db, viewer_id, test_user.id)
        if match is None:
            match = _create_match(
                db,
                user_a=viewer_id,
                user_b=test_user.id,
                evaluated={
                    "compatibility_score": meta["score"],
                    "final_mutual_fit_score": meta["score"],
                    "algorithm_version": "test-profile-v1",
                    "category_scores": meta["categories"],
                    "mutual_preference_score": 88,
                    "activity_score": 90,
                    "readiness_score": 95,
                },
                now=now,
            )

        conversation = get_or_create_conversation(
            db,
            match_id=match.id,
            user_id=viewer_id,
            now=now,
        )
        existing_messages = list_messages(
            db,
            conversation_id=conversation.id,
            user_id=viewer_id,
            limit=1,
        )
        if not existing_messages:
            send_message(
                db,
                conversation_id=conversation.id,
                sender_id=test_user.id,
                body=welcome_copy[test_user.email],
                client_message_id=f"test-welcome-{test_user.id}",
                now=now,
            )


def _record_test_decision(
    db,
    *,
    viewer_id: int,
    candidate_user_id: int,
    state: str,
) -> dict[str, Any] | None:
    if not _test_viewer_enabled(viewer_id):
        return None
    if _test_profile_meta(db, candidate_user_id) is None:
        return None

    now = datetime.now(timezone.utc)
    row = db.get(Interest, (viewer_id, candidate_user_id))
    changed = row is None or row.state != state
    if row is None:
        row = Interest(
            from_user=viewer_id,
            to_user=candidate_user_id,
            state=state,
            source_algorithm_version="test-profile-v1",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.state = state
        row.source_algorithm_version = "test-profile-v1"
        row.updated_at = now

    row.snooze_until = now + timedelta(days=30) if state == "SKIPPED" else None
    db.flush()
    return {
        "state": state,
        "changed": changed,
        "mutual_match": False,
        "match_id": None,
        "candidate_user_id": candidate_user_id,
        "test_profile": True,
        "snooze_until": row.snooze_until,
    }


def _candidate_profile_payload(
    db,
    *,
    user_id: int,
    scoring: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "profile_not_found")
    market = db.get(Market, profile.market_id) if profile.market_id is not None else None
    age = user_age(profile.dob) if profile.dob is not None else None
    result: dict[str, Any] = {
        "user_id": user_id,
        "display_name": profile.display_name,
        "age": age,
        "city": profile.city or (market.name if market else ""),
        "dating_goal": profile.dating_goal,
        "bio": profile.bio,
        "height": profile.height,
        "children_status": profile.children_status,
        "children_plans": profile.children_plans,
        "smoking": profile.smoking,
        "alcohol": profile.alcohol,
        "lifestyle": profile.lifestyle,
        "religion": profile.religion,
        "photos": _candidate_photo_urls(db, user_id),
    }
    if scoring:
        result.update(
            {
                "compatibility_score": scoring.get("compatibility_score"),
                "mutual_fit_score": scoring.get("final_mutual_fit_score"),
                "distance_km": scoring.get("distance_km"),
                "category_scores": scoring.get("category_scores") or {},
                "mutual_preference_score": scoring.get("mutual_preference_score"),
                "readiness_score": scoring.get("readiness_score"),
            }
        )
    return result


def _match_payload(db, *, match: Match, viewer_id: int) -> dict[str, Any]:
    other_id = match.user2 if match.user1 == viewer_id else match.user1
    return {
        "match_id": match.id,
        "compatibility_score": match.compatibility_score,
        "mutual_fit_score": match.mutual_fit_score,
        "created_at": match.created_at,
        "profile": _candidate_profile_payload(db, user_id=other_id),
    }


def social_auth_configured() -> dict[str, bool]:
    def configured(provider: str) -> bool:
        try:
            return bool(configured_audiences(provider))
        except OAuthError:
            return False

    return {
        "google": configured("GOOGLE"),
        "apple": configured("APPLE"),
    }


def run_maintenance_once() -> dict[str, Any]:
    result: dict[str, Any] = {}
    with runtime().db() as db:
        result["privacy_deletions"] = process_due_deletions(db, limit=100)
        result["retention"] = process_retention_cleanup(db)
        if photo_storage_configured():
            result["photo_deletions"] = process_deletion_outbox(
                db,
                storage=photo_storage(),
                limit=100,
            )
        else:
            result["photo_deletions"] = {"skipped": "photo_storage_not_configured"}

        if push_token_vault_configured() and fcm_configured():
            deliveries = dispatch_pending(
                db,
                clients={"FCM": fcm_client()},
                vault=push_token_vault(),
                limit=100,
            )
            result["push_deliveries"] = {
                "processed": len(deliveries),
                "sent": sum(1 for item in deliveries if item.status == "SENT"),
                "failed": sum(1 for item in deliveries if item.status == "FAILED"),
                "disabled": sum(1 for item in deliveries if item.status == "DISABLED"),
            }
        else:
            result["push_deliveries"] = {
                "skipped": "push_provider_not_configured"
            }
    return result


def _maintenance_loop() -> None:
    try:
        interval = int(os.environ.get("MAINTENANCE_INTERVAL_SECONDS", "3600"))
    except ValueError:
        interval = 3600
    interval = max(300, interval)

    # Give the HTTP listener time to become healthy before maintenance work.
    time.sleep(15)
    while True:
        try:
            result = run_maintenance_once()
            print(
                "maintenance completed:",
                json.dumps(result, ensure_ascii=False, default=_json_default),
                flush=True,
            )
        except Exception as exc:
            print(
                f"maintenance failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
        time.sleep(interval)


def start_maintenance_thread() -> threading.Thread:
    thread = threading.Thread(
        target=_maintenance_loop,
        name="matchlab-maintenance",
        daemon=True,
    )
    thread.start()
    return thread


class MatchLabHandler(BaseHTTPRequestHandler):
    server_version = "MatchLab/35"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep stdlib request logs concise; sensitive body/header data is never logged.
        super().log_message(format, *args)

    def _send_text(
        self,
        status: int,
        body: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _send_json(self, status: int, payload: Any, *, cookies: list[str] | None = None) -> None:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _send_file(
        self,
        status: int,
        file_path: Path,
        *,
        content_type: str | None = None,
        cache_control: str = "public, max-age=3600",
    ) -> None:
        if not file_path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found")
        raw = file_path.read_bytes()
        resolved_type = (
            content_type
            or mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream"
        )
        if resolved_type.startswith("text/") or resolved_type in {
            "application/javascript",
            "application/json",
            "application/manifest+json",
            "image/svg+xml",
        }:
            resolved_type += "; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", resolved_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _serve_web(self, path: str) -> bool:
        if self.command not in {"GET", "HEAD"}:
            return False
        if path in {"/", "/app"}:
            self._send_file(
                HTTPStatus.OK,
                WEB_ROOT / "index.html",
                content_type="text/html",
                cache_control="no-cache",
            )
            return True
        if path == "/web/hero.jpg":
            self._send_file(
                HTTPStatus.OK,
                WEB_HERO,
                content_type="image/jpeg",
                cache_control="public, max-age=86400",
            )
            return True
        if not path.startswith("/web/"):
            return False
        relative = path[len("/web/"):]
        if not relative or ".." in relative.split("/"):
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found")
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in target.parents:
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found")
        cache = "no-cache" if target.name in {"index.html", "sw.js"} or target.suffix in {".css", ".js"} else "public, max-age=3600"
        content_type = (
            "application/manifest+json"
            if target.suffix == ".webmanifest"
            else None
        )
        self._send_file(
            HTTPStatus.OK,
            target,
            content_type=content_type,
            cache_control=cache,
        )
        return True

    def _origin_guard(self) -> None:
        allowed = _allowed_origins()
        if not allowed:
            raise InvalidOrigin("allowed_origins_not_configured")
        validate_origin(self.headers.get("Origin"), allowed_origins=allowed)

    def _body(self) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise SecurityError("invalid_content_length") from exc
        if size < 0:
            raise SecurityError("invalid_content_length")
        raw = self.rfile.read(size)
        value = parse_json_body(raw)
        if not isinstance(value, dict):
            raise SecurityError("json_object_required")
        return value

    def _principal(self, db):
        token = _cookie_value(self.headers.get("Cookie"), SESSION_COOKIE.name)
        principal = lookup_session(db, token)
        if principal is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "authentication_required")
        user = db.get(User, principal.user_id)
        if user is None or user.status in {"BANNED", "DELETION_REQUESTED"}:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "account_unavailable")
        return principal

    def _csrf_guard(self) -> None:
        cookie = _cookie_value(self.headers.get("Cookie"), CSRF_COOKIE.name)
        header = self.headers.get("X-CSRF-Token", "")
        validate_csrf(cookie, header)

    def _dispatch(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        method = self.command

        if method == "OPTIONS":
            self._send_json(HTTPStatus.NO_CONTENT, {})
            return

        if self._serve_web(path):
            return


        if method == "GET" and path == "/health":
            with runtime().db() as db:
                db.execute(text("SELECT 1"))
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "matchlab",
                        "runtime": "postgres-http",
                        "phase": 35,
                        "adaptive_questionnaire": True,
                        "openai_adaptive_configured": bool(
                            os.environ.get("OPENAI_API_KEY", "").strip()
                            and os.environ.get("OPENAI_ADAPTIVE_MODEL", "").strip()
                        ),
                        "phone_auth_configured": phone_auth_configured(),
                        "password_reset_email_configured": password_reset_email_configured(),
                        "email_verification_configured": email_verification_configured(),
                        "social_auth": social_auth_configured(),
                        "photo_storage_configured": photo_storage_configured(),
                        "push": {
                            "token_vault": push_token_vault_configured(),
                            "fcm": fcm_configured(),
                        },
                        "features": feature_flags(db),
                    },
                )
            return

        if method == "GET" and path == "/privacy":
            self._send_text(
                HTTPStatus.OK,
                privacy_policy_html(),
                content_type="text/html; charset=utf-8",
            )
            return

        if method == "GET" and path == "/terms":
            self._send_text(
                HTTPStatus.OK,
                terms_html(),
                content_type="text/html; charset=utf-8",
            )
            return

        if method == "GET" and path == "/account-deletion":
            self._send_text(
                HTTPStatus.OK,
                account_deletion_html(),
                content_type="text/html; charset=utf-8",
            )
            return

        if method == "GET" and path == "/phone-login":
            self._send_text(
                HTTPStatus.OK,
                phone_login_html(),
                content_type="text/html; charset=utf-8",
            )
            return

        if method == "GET" and path == f"{API_PREFIX}/privacy/retention":
            self._send_json(HTTPStatus.OK, retention_policy())
            return

        if method == "POST" and path == f"{API_PREFIX}/analytics/anonymous":
            self._origin_guard()
            body = self._body()
            event_type = str(body.get("event_type", "")).upper()
            if event_type not in {EVENT_LANDING_VIEW, EVENT_REGISTRATION_STARTED}:
                raise ApiError(HTTPStatus.BAD_REQUEST, "unsupported_anonymous_event")
            visitor_id = str(body.get("visitor_id", "")).strip()[:128]
            if not visitor_id:
                raise ApiError(HTTPStatus.BAD_REQUEST, "visitor_id_required")
            metadata = _attribution_payload(body)
            metadata.update(
                {
                    "visitor_id": visitor_id,
                    "platform": str(body.get("platform", "web"))[:32],
                }
            )
            with runtime().db() as db:
                track_event(
                    db,
                    event_type=event_type,
                    user_id=None,
                    metadata=metadata,
                )
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True})
            return

        if method == "POST" and path in {
            f"{API_PREFIX}/auth/register",
            f"{API_PREFIX}/auth/login",
        }:
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                if path.endswith("/register"):
                    user = register_email_user(
                        db,
                        body.get("email", ""),
                        body.get("password", ""),
                        referral_code=body.get("referral_code"),
                        attribution=_attribution_payload(body),
                    )
                    _, verification_token = request_email_verification_challenge(
                        db,
                        user_id=user.id,
                    )
                    if verification_token and email_verification_configured():
                        _send_verification_async(user.email, verification_token)
                else:
                    identifier = body.get("identifier")
                    if identifier is None:
                        user = authenticate_password(
                            db,
                            body.get("email", ""),
                            body.get("password", ""),
                        )
                    else:
                        user = authenticate_identifier_password(
                            db,
                            str(identifier),
                            str(body.get("password", "")),
                        )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.CREATED if path.endswith("/register") else HTTPStatus.OK,
                    {
                        "ok": True,
                        "user_id": user.id,
                        "email_verified": bool(user.email_verified_at),
                        "email_verification_delivery": (
                            "email"
                            if path.endswith("/register") and email_verification_configured()
                            else None
                        ),
                    },
                    cookies=[
                        SESSION_COOKIE.header(bearer),
                        CSRF_COOKIE.header(csrf),
                    ],
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/phone/register/request":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                request_phone_registration_code(
                    db,
                    phone_e164=str(body.get("phone", "")),
                    sender=sms_sender_from_env(),
                )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {"ok": True, "delivery": "sms"},
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/phone/register/verify":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                user = verify_phone_registration_code(
                    db,
                    phone_e164=str(body.get("phone", "")),
                    code=str(body.get("code", "")),
                    password=str(body.get("password", "")),
                    referral_code=body.get("referral_code"),
                    attribution=_attribution_payload(body),
                )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.CREATED,
                    {"ok": True, "user_id": user.id, "auth_method": "phone"},
                    cookies=[
                        SESSION_COOKIE.header(bearer),
                        CSRF_COOKIE.header(csrf),
                    ],
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/phone/request":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                request_phone_login_code(
                    db,
                    phone_e164=str(body.get("phone", "")),
                    sender=sms_sender_from_env(),
                )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {"ok": True, "delivery": "sms"},
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/phone/verify":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                password_value = body.get("password")
                user = verify_phone_login_code(
                    db,
                    phone_e164=str(body.get("phone", "")),
                    code=str(body.get("code", "")),
                    referral_code=body.get("referral_code"),
                    attribution=_attribution_payload(body),
                    new_password=(
                        str(password_value)
                        if password_value is not None and str(password_value) != ""
                        else None
                    ),
                )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "user_id": user.id, "auth_method": "phone"},
                    cookies=[
                        SESSION_COOKIE.header(bearer),
                        CSRF_COOKIE.header(csrf),
                    ],
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/password/reset/request":
            self._origin_guard()
            body = self._body()
            normalized = normalize_email(str(body.get("email", "")))
            configured = password_reset_email_configured()
            with runtime().db() as db:
                user = db.execute(
                    select(User).where(User.email == normalized)
                ).scalar_one_or_none()
                if (
                    configured
                    and user is not None
                    and not user.email.endswith(
                        ("@phone.matchlab.invalid", "@identity.matchlab.invalid")
                    )
                ):
                    token = create_challenge(
                        db,
                        user_id=user.id,
                        purpose="PASSWORD_RESET",
                        channel="email",
                        target=normalized,
                    )
                    try:
                        _send_password_reset_email(normalized, token)
                    except (OSError, RuntimeError, smtplib.SMTPException):
                        pass
            self._send_json(
                HTTPStatus.ACCEPTED,
                {
                    "ok": True,
                    "delivery": "email" if configured else "email_not_configured",
                    "message": "Если такой email зарегистрирован, инструкция отправлена.",
                },
            )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/password/reset/confirm":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                user = reset_password_with_challenge(
                    db,
                    email=str(body.get("email", "")),
                    secret=str(body.get("token", "")),
                    new_password=str(body.get("password", "")),
                )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "user_id": user.id},
                    cookies=[
                        SESSION_COOKIE.header(bearer),
                        CSRF_COOKIE.header(csrf),
                    ],
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/email/verify":
            self._origin_guard()
            body = self._body()
            with runtime().db() as db:
                user = verify_email_challenge(
                    db,
                    email=str(body.get("email", "")),
                    secret=str(body.get("token", "")),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "email_verified": True, "user_id": user.id},
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/oidc/nonce":
            self._origin_guard()
            body = self._body()
            provider = str(body.get("provider", "")).upper()
            with runtime().db() as db:
                nonce = create_oidc_nonce(
                    db,
                    provider=provider,
                    purpose="OIDC_LOGIN",
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {"provider": provider, "nonce": nonce},
                )
            return

        if method == "POST" and path == f"{API_PREFIX}/auth/oauth":
            self._origin_guard()
            body = self._body()
            provider = str(body.get("provider", "")).upper()
            nonce = str(body.get("nonce", ""))
            identity = verify_identity_token(
                provider=provider,
                id_token=str(body.get("id_token", "")),
                expected_nonce=nonce,
            )
            with runtime().db() as db:
                consume_oidc_nonce(
                    db,
                    provider=provider,
                    purpose="OIDC_LOGIN",
                    nonce=nonce,
                )
                user = login_or_register_identity(
                    db,
                    identity=identity,
                    referral_code=body.get("referral_code"),
                    attribution=_attribution_payload(body),
                )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "user_id": user.id, "auth_method": provider.lower()},
                    cookies=[
                        SESSION_COOKIE.header(bearer),
                        CSRF_COOKIE.header(csrf),
                    ],
                )
            return

        with runtime().db() as db:
            principal = self._principal(db)

            if method not in SAFE_METHODS:
                self._origin_guard()
                self._csrf_guard()

            if method == "GET" and path == "/moderation/photos":
                require_console(
                    db,
                    user_id=principal.user_id,
                    minimum_role="MODERATOR",
                )
                self._send_text(
                    HTTPStatus.OK,
                    photo_moderation_html(),
                    content_type="text/html; charset=utf-8",
                )
                return

            if method == "GET" and path == "/ops":
                require_console(
                    db,
                    user_id=principal.user_id,
                    minimum_role="VIEWER",
                )
                self._send_text(
                    HTTPStatus.OK,
                    prelaunch_dashboard_html(),
                    content_type="text/html; charset=utf-8",
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/admin/prelaunch/metrics":
                require_console(
                    db,
                    user_id=principal.user_id,
                    minimum_role="VIEWER",
                )
                self._send_json(
                    HTTPStatus.OK,
                    prelaunch_metrics(db),
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/logout":
                token = _cookie_value(self.headers.get("Cookie"), SESSION_COOKIE.name)
                revoke_session(db, token)
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True},
                    cookies=[
                        SESSION_COOKIE.header("deleted") + "; Max-Age=0",
                        CSRF_COOKIE.header("deleted") + "; Max-Age=0",
                    ],
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/auth/methods":
                identities = list(
                    db.execute(
                        select(AuthIdentity)
                        .where(AuthIdentity.user_id == principal.user_id)
                        .order_by(AuthIdentity.provider)
                    ).scalars()
                )
                user = db.get(User, principal.user_id)
                methods = {row.provider.lower() for row in identities}
                if user and not user.email.endswith(
                    ("@phone.matchlab.invalid", "@identity.matchlab.invalid")
                ):
                    methods.add("email")
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "methods": sorted(methods),
                        "email": (
                            user.email
                            if user
                            and not user.email.endswith(
                                ("@phone.matchlab.invalid", "@identity.matchlab.invalid")
                            )
                            else None
                        ),
                        "email_verified": bool(user and user.email_verified_at),
                        "phone": user.phone_e164 if user else None,
                        "phone_verified": bool(user and user.phone_verified_at),
                        "contact_verified": bool(
                            user and (user.email_verified_at or user.phone_verified_at)
                        ),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/email/verification/request":
                user, token = request_email_verification_challenge(
                    db,
                    user_id=principal.user_id,
                )
                if token is None:
                    self._send_json(
                        HTTPStatus.OK,
                        {"ok": True, "email_verified": True, "delivery": None},
                    )
                    return
                configured = email_verification_configured()
                if configured:
                    _send_verification_async(user.email, token)
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "ok": True,
                        "email_verified": False,
                        "delivery": "email" if configured else "email_not_configured",
                        "message": (
                            "Письмо отправлено."
                            if configured
                            else "Отправка email пока не настроена."
                        ),
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/markets":
                rows = list(
                    db.execute(
                        select(Market)
                        .where(Market.registration_open.is_(True))
                        .order_by(Market.id)
                    ).scalars()
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "markets": [
                            {
                                "code": row.code,
                                "name": row.display_name,
                                "matching_open": bool(row.matching_open),
                            }
                            for row in rows
                        ]
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/analytics/event":
                body = self._body()
                event_type = str(body.get("event_type", "")).upper()
                if event_type not in {
                    EVENT_ONBOARDING_STARTED,
                    EVENT_CANDIDATE_VIEWED,
                }:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "unsupported_client_event")
                metadata = body.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["platform"] = str(metadata.get("platform", "web"))[:32]
                if event_type == EVENT_ONBOARDING_STARTED:
                    row = track_once(
                        db,
                        event_type=event_type,
                        user_id=principal.user_id,
                        metadata=metadata,
                    )
                else:
                    row = track_event(
                        db,
                        event_type=event_type,
                        user_id=principal.user_id,
                        metadata=metadata,
                    )
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "event_id": row.id})
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/link/phone/request":
                body = self._body()
                request_phone_link_code(
                    db,
                    user_id=principal.user_id,
                    phone_e164=str(body.get("phone", "")),
                    sender=sms_sender_from_env(),
                )
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "delivery": "sms"})
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/link/phone/verify":
                body = self._body()
                user = verify_phone_link_code(
                    db,
                    user_id=principal.user_id,
                    phone_e164=str(body.get("phone", "")),
                    code=str(body.get("code", "")),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "phone": user.phone_e164,
                        "phone_verified": bool(user.phone_verified_at),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/link/oidc/nonce":
                body = self._body()
                provider = str(body.get("provider", "")).upper()
                nonce = create_oidc_nonce(
                    db,
                    provider=provider,
                    purpose="OIDC_LINK",
                    user_id=principal.user_id,
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {"provider": provider, "nonce": nonce},
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/auth/link/oauth":
                body = self._body()
                provider = str(body.get("provider", "")).upper()
                nonce = str(body.get("nonce", ""))
                identity = verify_identity_token(
                    provider=provider,
                    id_token=str(body.get("id_token", "")),
                    expected_nonce=nonce,
                )
                consume_oidc_nonce(
                    db,
                    provider=provider,
                    purpose="OIDC_LINK",
                    nonce=nonce,
                    expected_user_id=principal.user_id,
                )
                linked = link_identity(
                    db,
                    user_id=principal.user_id,
                    identity=identity,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "provider": linked.provider.lower(),
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/push/devices":
                devices = list(
                    db.execute(
                        select(PushDevice)
                        .where(PushDevice.user_id == principal.user_id)
                        .order_by(PushDevice.id)
                    ).scalars()
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "devices": [
                            {
                                "id": item.id,
                                "provider": item.provider,
                                "platform": item.platform,
                                "locale": item.locale,
                                "enabled": item.enabled,
                                "last_seen_at": item.last_seen_at,
                            }
                            for item in devices
                        ]
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/push/devices":
                body = self._body()
                item = register_device(
                    db,
                    user_id=principal.user_id,
                    provider="FCM",
                    platform="ANDROID",
                    token=str(body.get("token", "")),
                    vault=push_token_vault(),
                    locale=str(body.get("locale", "ru-KZ")),
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {
                        "id": item.id,
                        "provider": item.provider,
                        "platform": item.platform,
                        "enabled": item.enabled,
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/push/devices/disable":
                body = self._body()
                device_id = int(body.get("device_id", 0))
                device = db.get(PushDevice, device_id)
                if device is None or device.user_id != principal.user_id:
                    raise ApiError(HTTPStatus.NOT_FOUND, "push_device_not_found")
                disable_device(
                    db,
                    device_id=device_id,
                    vault=push_token_vault(),
                )
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            if method == "GET" and path == f"{API_PREFIX}/profile/me":
                profile = db.get(Profile, principal.user_id)
                if profile is None:
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "profile": None,
                            "completion": profile_completion_state(None),
                        },
                    )
                    return

                market = (
                    db.get(Market, profile.market_id)
                    if profile.market_id is not None
                    else None
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "profile": {
                            "user_id": profile.user_id,
                            "display_name": profile.display_name,
                            "dob": profile.dob,
                            "gender": profile.gender,
                            "seek_gender": profile.seek_gender,
                            "market_code": market.code if market else None,
                            "city": profile.city,
                            "country_code": profile.country_code,
                            "preferred_locale": profile.preferred_locale,
                            "relationship_status": profile.relationship_status,
                            "eligibility_status": profile.eligibility_status,
                            "dating_goal": profile.dating_goal,
                            "readiness_chat": profile.readiness_chat,
                            "readiness_offline": profile.readiness_offline,
                            "readiness_score": profile.readiness_score,
                            "bio": profile.bio,
                            "height": profile.height,
                            "smoking": profile.smoking,
                            "alcohol": profile.alcohol,
                            "lifestyle": profile.lifestyle,
                            "religion": profile.religion,
                            "nationality": profile.nationality,
                            "children_status": profile.children_status,
                            "children_plans": profile.children_plans,
                        },
                        "completion": profile_completion_state(profile),
                        "account": {
                            "email": (
                                user.email
                                if (user := db.get(User, principal.user_id))
                                and not user.email.endswith(
                                    ("@phone.matchlab.invalid", "@identity.matchlab.invalid")
                                )
                                else None
                            ),
                            "email_verified": bool(user and user.email_verified_at),
                            "phone_verified": bool(user and user.phone_verified_at),
                            "contact_verified": bool(
                                user and (user.email_verified_at or user.phone_verified_at)
                            ),
                        },
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/onboarding":
                profile = db.get(Profile, principal.user_id)
                completion = profile_completion_state(profile)
                account_user = db.get(User, principal.user_id)
                response: dict[str, Any] = {
                    "completion": completion,
                    "account": {
                        "email": (
                            account_user.email
                            if account_user
                            and not account_user.email.endswith(
                                ("@phone.matchlab.invalid", "@identity.matchlab.invalid")
                            )
                            else None
                        ),
                        "email_verified": bool(account_user and account_user.email_verified_at),
                        "phone_verified": bool(account_user and account_user.phone_verified_at),
                        "contact_verified": bool(
                            account_user
                            and (account_user.email_verified_at or account_user.phone_verified_at)
                        ),
                    },
                    "questionnaire": {
                        "progress": questionnaire_progress(
                            db,
                            user_id=principal.user_id,
                        ),
                        "answers": (
                            questionnaire_answers(
                                db,
                                user_id=principal.user_id,
                            )
                            if profile is not None
                            else {}
                        ),
                    },
                    "preferences": get_preferences(
                        db,
                        user_id=principal.user_id,
                    ),
                    "photos": (
                        photo_progress(db, user_id=principal.user_id)
                        if profile is not None
                        else {
                            "approved": 0,
                            "approved_main": False,
                            "complete": False,
                        }
                    ),
                }
                if profile is not None:
                    market = (
                        db.get(Market, profile.market_id)
                        if profile.market_id is not None
                        else None
                    )
                    response["profile"] = {
                        "display_name": profile.display_name,
                        "dob": profile.dob,
                        "gender": profile.gender,
                        "seek_gender": profile.seek_gender,
                        "market_code": market.code if market else None,
                        "city": profile.city,
                        "relationship_status": profile.relationship_status,
                        "eligibility_status": profile.eligibility_status,
                        "dating_goal": profile.dating_goal,
                        "readiness_chat": profile.readiness_chat,
                        "readiness_offline": profile.readiness_offline,
                        "readiness_score": profile.readiness_score,
                        "height": profile.height,
                        "children_status": profile.children_status,
                        "children_plans": profile.children_plans,
                        "smoking": profile.smoking,
                        "alcohol": profile.alcohol,
                        "lifestyle": profile.lifestyle,
                        "bio": profile.bio,
                        "religion": profile.religion,
                        "nationality": profile.nationality,
                    }
                    response["waitlist"] = waitlist_status(
                        db,
                        user_id=principal.user_id,
                    )
                else:
                    response["profile"] = None
                    response["waitlist"] = {
                        "state": "NEEDS_BASIC_PROFILE",
                        "ready": False,
                        "completion": completion,
                        "message": "Заполните базовый профиль.",
                    }
                self._send_json(HTTPStatus.OK, response)
                return

            if method == "POST" and path == f"{API_PREFIX}/profile/basic":
                body = self._body()
                dob = date.fromisoformat(str(body.get("dob", "")))
                row = upsert_basic_profile(
                    db,
                    user_id=principal.user_id,
                    display_name=str(body.get("display_name", "")),
                    dob=dob,
                    gender=str(body.get("gender", "")),
                    seek_gender=str(body.get("seek_gender", "")),
                    market_code=str(body.get("market_code", "")),
                    preferred_locale=body.get("preferred_locale"),
                    city_text=body.get("city_text"),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "user_id": row.user_id})
                return

            if method == "POST" and path == f"{API_PREFIX}/profile/details":
                body = self._body()
                try:
                    height = int(body.get("height"))
                except (TypeError, ValueError) as exc:
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_height",
                    ) from exc
                row = set_match_profile_details(
                    db,
                    user_id=principal.user_id,
                    height=height,
                    dating_goal=str(body.get("dating_goal", "")),
                    children_status=str(body.get("children_status", "")),
                    children_plans=str(body.get("children_plans", "")),
                    smoking=str(body.get("smoking", "")),
                    alcohol=str(body.get("alcohol", "")),
                    lifestyle=str(body.get("lifestyle", "")),
                    bio=str(body.get("bio", "")),
                    religion=str(body.get("religion", "")),
                    nationality=str(body.get("nationality", "")),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "completion": profile_completion_state(row),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/profile/relationship":
                body = self._body()
                row = set_relationship_state(
                    db,
                    user_id=principal.user_id,
                    in_relationship=bool(body.get("in_relationship")),
                    openness=str(body.get("openness", "")),
                    source="http",
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "relationship_status": row.relationship_status,
                        "eligibility_status": row.eligibility_status,
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/profile/readiness":
                body = self._body()
                row = set_readiness(
                    db,
                    user_id=principal.user_id,
                    chat=str(body.get("chat", "")),
                    offline=str(body.get("offline", "")),
                )
                self._send_json(HTTPStatus.OK, {"readiness_score": row.readiness_score})
                return

            if method == "GET" and path == f"{API_PREFIX}/questionnaire/adaptive":
                self._send_json(
                    HTTPStatus.OK,
                    adaptive_questionnaire_state(
                        db,
                        user_id=principal.user_id,
                    ),
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/questionnaire/adaptive/answer":
                body = self._body()
                token = str(body.get("question_token", ""))
                try:
                    value = int(body.get("value"))
                except (TypeError, ValueError) as exc:
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_adaptive_answer",
                    ) from exc
                self._send_json(
                    HTTPStatus.OK,
                    adaptive_questionnaire_answer(
                        db,
                        user_id=principal.user_id,
                        question_token=token,
                        value=value,
                    ),
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/questionnaire":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "sections": questionnaire_sections(db),
                        "progress": questionnaire_progress(db, user_id=principal.user_id),
                        "answers": questionnaire_answers(db, user_id=principal.user_id),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/questionnaire/answers":
                body = self._body()
                raw_answers = body.get("answers", {})
                if not isinstance(raw_answers, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "answers_object_required")
                answers = {int(key): value for key, value in raw_answers.items()}
                self._send_json(
                    HTTPStatus.OK,
                    save_answers(db, user_id=principal.user_id, answers=answers),
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/preferences":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "catalog": PREFERENCE_CATALOG,
                        "values": get_preferences(db, user_id=principal.user_id),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/preferences":
                body = self._body()
                self._send_json(
                    HTTPStatus.OK,
                    set_preferences(
                        db,
                        user_id=principal.user_id,
                        preferences=body.get("preferences", {}),
                    ),
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/photos":
                storage = photo_storage()
                items = []
                for photo in list_owner_photos(db, user_id=principal.user_id):
                    items.append(
                        {
                            "id": photo.id,
                            "mime": photo.mime,
                            "byte_size": photo.byte_size,
                            "is_main": photo.is_main,
                            "sort_order": photo.sort_order,
                            "moderation_status": photo.moderation_status,
                            "moderation_reason": photo.moderation_reason,
                            "created_at": photo.created_at,
                            "url": (
                                storage.presign_download(photo.storage_key)
                                if photo.storage_key
                                else None
                            ),
                        }
                    )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "photos": items,
                        "progress": photo_progress(db, user_id=principal.user_id),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/photos/prepare":
                body = self._body()
                self._send_json(
                    HTTPStatus.CREATED,
                    prepare_upload(
                        db,
                        user_id=principal.user_id,
                        mime=str(body.get("mime", "")),
                        storage=photo_storage(),
                    ),
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/photos/finalize":
                body = self._body()
                photo = finalize_upload(
                    db,
                    user_id=principal.user_id,
                    ticket_token=str(body.get("ticket", "")),
                    storage=photo_storage(),
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {
                        "id": photo.id,
                        "moderation_status": photo.moderation_status,
                        "progress": photo_progress(db, user_id=principal.user_id),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/photos/main":
                body = self._body()
                photo = set_main_photo(
                    db,
                    user_id=principal.user_id,
                    photo_id=int(body.get("photo_id", 0)),
                )
                self._send_json(HTTPStatus.OK, {"id": photo.id, "is_main": photo.is_main})
                return

            if method == "POST" and path == f"{API_PREFIX}/photos/reorder":
                body = self._body()
                raw_ids = body.get("photo_ids", [])
                if not isinstance(raw_ids, list):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "photo_ids_list_required")
                ordered = reorder_photos(
                    db,
                    user_id=principal.user_id,
                    ordered_photo_ids=[int(value) for value in raw_ids],
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"photo_ids": [photo.id for photo in ordered]},
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/photos/delete":
                body = self._body()
                delete_photo(
                    db,
                    user_id=principal.user_id,
                    photo_id=int(body.get("photo_id", 0)),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "progress": photo_progress(db, user_id=principal.user_id)},
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/admin/photos/pending":
                require_console(db, user_id=principal.user_id, minimum_role="MODERATOR")
                storage = photo_storage()
                rows = db.execute(
                    select(Photo)
                    .where(Photo.moderation_status == "PENDING")
                    .order_by(Photo.created_at, Photo.id)
                    .limit(100)
                ).scalars()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "photos": [
                            {
                                "id": photo.id,
                                "user_id": photo.user_id,
                                "mime": photo.mime,
                                "byte_size": photo.byte_size,
                                "is_main": photo.is_main,
                                "created_at": photo.created_at,
                                "url": storage.presign_download(photo.storage_key)
                                if photo.storage_key
                                else None,
                            }
                            for photo in rows
                        ]
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/admin/photos/moderate":
                require_console(db, user_id=principal.user_id, minimum_role="MODERATOR")
                body = self._body()
                photo = moderate_photo(
                    db,
                    photo_id=int(body.get("photo_id", 0)),
                    status=str(body.get("status", "")),
                    actor=f"user:{principal.user_id}",
                    reason=str(body.get("reason", "")),
                )
                kind = (
                    "PHOTO_APPROVED"
                    if photo.moderation_status == "APPROVED"
                    else "PHOTO_REJECTED"
                )
                notification = Notification(
                    user_id=photo.user_id,
                    kind=kind,
                    text=(
                        "Фото одобрено."
                        if kind == "PHOTO_APPROVED"
                        else "Фото отклонено. Проверьте статус фото в профиле."
                    ),
                )
                db.add(notification)
                db.flush()
                enqueue_notification(
                    db,
                    notification_id=notification.id,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "id": photo.id,
                        "user_id": photo.user_id,
                        "moderation_status": photo.moderation_status,
                        "notification_id": notification.id,
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/safety/blocked":
                rows = list(
                    db.execute(
                        select(Block)
                        .where(Block.blocker == principal.user_id)
                        .order_by(Block.created_at.desc())
                    ).scalars()
                )
                items = []
                for row in rows:
                    profile = db.get(Profile, row.blocked)
                    items.append(
                        {
                            "user_id": row.blocked,
                            "display_name": profile.display_name if profile else "Пользователь",
                            "age": (
                                user_age(profile.dob)
                                if profile is not None and profile.dob is not None
                                else None
                            ),
                            "city": profile.city if profile else None,
                            "blocked_at": row.created_at,
                        }
                    )
                self._send_json(HTTPStatus.OK, {"blocked": items})
                return

            if method == "POST" and path == f"{API_PREFIX}/safety/block":
                body = self._body()
                row = block_user(
                    db,
                    blocker=principal.user_id,
                    blocked=int(body.get("user_id", 0)),
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "user_id": row.blocked,
                        "blocked_at": row.created_at,
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/safety/unblock":
                body = self._body()
                user_id = int(body.get("user_id", 0))
                changed = unblock_user(
                    db,
                    blocker=principal.user_id,
                    blocked=user_id,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "user_id": user_id, "changed": changed},
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/safety/report":
                body = self._body()
                report = report_user(
                    db,
                    reporter=principal.user_id,
                    target_user=int(body.get("user_id", 0)),
                    reason=str(body.get("reason", "")),
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {
                        "ok": True,
                        "report_id": report.id,
                        "status": report.status,
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/privacy/export":
                self._send_json(
                    HTTPStatus.OK,
                    export_user_data(db, user_id=principal.user_id),
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/privacy/delete":
                body = self._body()
                if str(body.get("confirmation", "")) != "DELETE":
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "deletion_confirmation_required",
                        "confirmation must equal DELETE",
                    )
                result = request_account_deletion(
                    db,
                    user_id=principal.user_id,
                )
                self._send_json(
                    HTTPStatus.ACCEPTED,
                    result,
                    cookies=[
                        SESSION_COOKIE.header("deleted") + "; Max-Age=0",
                        CSRF_COOKIE.header("deleted") + "; Max-Age=0",
                    ],
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/discovery/candidates":
                query = parse_qs(urlparse(self.path).query)
                try:
                    limit = int((query.get("limit") or ["5"])[0])
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_limit") from exc
                ranked = rank_candidates(
                    db,
                    user_id=principal.user_id,
                    limit=limit,
                )
                candidates = [
                    _candidate_profile_payload(
                        db,
                        user_id=int(item["user_id"]),
                        scoring=item,
                    )
                    for item in ranked
                ]
                existing_ids = {int(item["user_id"]) for item in candidates}
                for item in _test_candidate_payloads(
                    db,
                    viewer_id=principal.user_id,
                ):
                    if int(item["user_id"]) not in existing_ids:
                        candidates.append(item)
                    if len(candidates) >= limit:
                        break
                for item in candidates:
                    track_event(
                        db,
                        event_type=EVENT_CANDIDATE_VIEWED,
                        user_id=principal.user_id,
                        metadata={
                            "candidate_user_id": int(item["user_id"]),
                            "surface": "discovery",
                        },
                    )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "candidates": candidates,
                        "enabled": feature_flags(db).get("candidate_output_enabled", False)
                        or bool(_test_candidate_payloads(db, viewer_id=principal.user_id)),
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/discovery/decision":
                body = self._body()
                action = str(body.get("action", "")).upper()
                if action not in {"INTERESTED", "SKIPPED"}:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_candidate_action")
                candidate_user_id = int(body.get("candidate_user_id", 0))
                result = _record_test_decision(
                    db,
                    viewer_id=principal.user_id,
                    candidate_user_id=candidate_user_id,
                    state=action,
                )
                if result is None:
                    result = record_decision(
                        db,
                        from_user=principal.user_id,
                        to_user=candidate_user_id,
                        state=action,
                    )
                self._send_json(HTTPStatus.OK, result)
                return

            if method == "GET" and path == f"{API_PREFIX}/matches":
                matches = list(
                    db.execute(
                        select(Match)
                        .where(
                            (Match.user1 == principal.user_id)
                            | (Match.user2 == principal.user_id)
                        )
                        .order_by(Match.created_at.desc(), Match.id.desc())
                        .limit(100)
                    ).scalars()
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "matches": [
                            _match_payload(db, match=item, viewer_id=principal.user_id)
                            for item in matches
                        ]
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/matches/conversation":
                body = self._body()
                conversation = get_or_create_conversation(
                    db,
                    match_id=int(body.get("match_id", 0)),
                    user_id=principal.user_id,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "conversation_id": conversation.id,
                        "match_id": conversation.match_id,
                    },
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/chat/conversations":
                _ensure_test_mutual_chats(
                    db,
                    viewer_id=principal.user_id,
                )
                conversations = list_conversations(
                    db,
                    user_id=principal.user_id,
                    limit=50,
                )
                for item in conversations:
                    other_id = int(item["other_user_id"])
                    item["profile"] = _candidate_profile_payload(
                        db,
                        user_id=other_id,
                    )
                    match = db.get(Match, int(item["match_id"]))
                    if match is not None:
                        item["compatibility_score"] = match.compatibility_score
                        item["mutual_fit_score"] = match.mutual_fit_score
                self._send_json(
                    HTTPStatus.OK,
                    {"conversations": conversations},
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/chat/messages":
                query = parse_qs(urlparse(self.path).query)
                try:
                    conversation_id = int((query.get("conversation_id") or ["0"])[0])
                    limit = int((query.get("limit") or ["50"])[0])
                    before_raw = (query.get("before_id") or [None])[0]
                    before_id = int(before_raw) if before_raw not in (None, "") else None
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_chat_query") from exc
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "messages": list_messages(
                            db,
                            conversation_id=conversation_id,
                            user_id=principal.user_id,
                            limit=limit,
                            before_id=before_id,
                        )
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/chat/messages":
                body = self._body()
                message = send_message(
                    db,
                    conversation_id=int(body.get("conversation_id", 0)),
                    sender_id=principal.user_id,
                    body=str(body.get("body", "")),
                    client_message_id=body.get("client_message_id"),
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {
                        "message": {
                            "id": message.id,
                            "sender_id": message.sender,
                            "body": message.body,
                            "created_at": message.created_at,
                            "read_at": message.read_at,
                            "is_mine": True,
                        }
                    },
                )
                return

            if method == "POST" and path == f"{API_PREFIX}/chat/read":
                body = self._body()
                raw_through = body.get("through_message_id")
                changed = mark_read(
                    db,
                    conversation_id=int(body.get("conversation_id", 0)),
                    user_id=principal.user_id,
                    through_message_id=(
                        int(raw_through)
                        if raw_through not in (None, "")
                        else None
                    ),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "marked_read": changed})
                return

            if method == "GET" and path == f"{API_PREFIX}/waitlist/status":
                self._send_json(
                    HTTPStatus.OK,
                    waitlist_status(db, user_id=principal.user_id),
                )
                return

            if method == "GET" and path == f"{API_PREFIX}/compatibility/me":
                self._send_json(
                    HTTPStatus.OK,
                    own_compatibility_profile(db, user_id=principal.user_id),
                )
                return

        raise ApiError(HTTPStatus.NOT_FOUND, "not_found")

    def _handle(self) -> None:
        try:
            self._dispatch()
        except RateLimited as exc:
            self._send_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                {"error": "rate_limited", "retry_after_seconds": exc.retry_after_seconds},
            )
        except InvalidCredentials:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"})
        except (InvalidOrigin, InvalidCsrf) as exc:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except RequestTooLarge as exc:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": str(exc)})
        except UnderageUser as exc:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "age_gate", "message": str(exc)})
        except ConsoleAccessDenied as exc:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except DeletionAlreadyRequested as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (OAuthError, SmsError, InvalidOrExpiredChallenge, PushError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except InterestActionsDisabled as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (InterestUnavailable, PairAlreadyMatched, ChatUnavailable) as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (InterestError, ChatError, MessageValidationError, NotConversationParticipant) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except PhotoNotFound as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except (
            PhotoError,
            PhotoLimitReached,
            UploadTicketError,
            AuthError,
            MarketUnavailable,
            ProfileError,
            InvalidAnswer,
            QuestionnaireError,
            AdaptiveQuestionnaireError,
            InvalidPreference,
            PreferenceError,
            PrelaunchError,
            PrivacyError,
            SafetyError,
            InvalidReport,
            SecurityError,
            ValueError,
        ) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.code, "message": exc.message})
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})

    do_GET = _handle
    do_POST = _handle
    do_OPTIONS = _handle
    do_HEAD = _handle


def main() -> None:
    # Fail fast: production runtime must have both database and same-origin config.
    if not os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required")
    if not _allowed_origins():
        raise RuntimeError("PUBLIC_URL or ALLOWED_ORIGINS is required")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), MatchLabHandler)
    start_maintenance_thread()
    print(f"MatchLab PostgreSQL HTTP runtime listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
