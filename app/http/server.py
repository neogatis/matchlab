from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.auth.service import (
    AuthError,
    InvalidCredentials,
    RateLimited,
    authenticate_password,
    create_session,
    lookup_session,
    register_email_user,
    revoke_session,
)
from app.db.models import Photo, User
from app.db.session import make_engine
from app.console.access import ConsoleAccessDenied, require_console
from app.photos.service import (
    PhotoError,
    PhotoLimitReached,
    PhotoNotFound,
    UploadTicketError,
    delete_photo,
    finalize_upload,
    list_owner_photos,
    moderate_photo,
    photo_progress,
    prepare_upload,
    reorder_photos,
    set_main_photo,
)
from app.photos.storage import S3PhotoStorage
from app.preferences.catalog import PREFERENCE_CATALOG
from app.preferences.service import (
    InvalidPreference,
    PreferenceError,
    get_preferences,
    set_preferences,
)
from app.prelaunch.policy import feature_flags
from app.prelaunch.service import PrelaunchError, own_compatibility_profile, waitlist_status
from app.profile.service import (
    MarketUnavailable,
    ProfileError,
    UnderageUser,
    set_readiness,
    set_relationship_state,
    upsert_basic_profile,
)
from app.questionnaire.service import (
    InvalidAnswer,
    QuestionnaireError,
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


def photo_storage_configured() -> bool:
    required = (
        "MATCH_PHOTO_BUCKET",
        "AWS_ENDPOINT_URL_S3",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    return all(os.environ.get(name, "").strip() for name in required)


class MatchLabHandler(BaseHTTPRequestHandler):
    server_version = "MatchLab/25"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep stdlib request logs concise; sensitive body/header data is never logged.
        super().log_message(format, *args)

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

        if method == "GET" and path == "/health":
            with runtime().db() as db:
                db.execute(text("SELECT 1"))
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "matchlab",
                        "runtime": "postgres-http",
                        "phase": 25,
                        "photo_storage_configured": photo_storage_configured(),
                        "features": feature_flags(db),
                    },
                )
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
                    )
                else:
                    user = authenticate_password(
                        db,
                        body.get("email", ""),
                        body.get("password", ""),
                    )
                bearer = create_session(
                    db,
                    user.id,
                    user_agent=self.headers.get("User-Agent", ""),
                )
                csrf = new_csrf_token()
                self._send_json(
                    HTTPStatus.CREATED if path.endswith("/register") else HTTPStatus.OK,
                    {"ok": True, "user_id": user.id},
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
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "user_id": row.user_id})
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

            if method == "GET" and path == f"{API_PREFIX}/questionnaire":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "sections": questionnaire_sections(db),
                        "progress": questionnaire_progress(db, user_id=principal.user_id),
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
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "id": photo.id,
                        "user_id": photo.user_id,
                        "moderation_status": photo.moderation_status,
                    },
                )
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
            InvalidPreference,
            PreferenceError,
            PrelaunchError,
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
    print(f"MatchLab PostgreSQL HTTP runtime listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
