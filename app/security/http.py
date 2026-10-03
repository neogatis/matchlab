from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Mapping


SESSION_COOKIE_NAME = "ml_session"
CSRF_COOKIE_NAME = "ml_csrf"
MAX_JSON_BYTES = 256 * 1024

SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|authorization|cookie|api[_-]?key|session|credential)",
    re.IGNORECASE,
)


class SecurityError(Exception):
    pass


class InvalidOrigin(SecurityError):
    pass


class InvalidCsrf(SecurityError):
    pass


class RequestTooLarge(SecurityError):
    pass


@dataclass(frozen=True)
class CookiePolicy:
    name: str
    secure: bool = True
    http_only: bool = True
    same_site: str = "Lax"
    path: str = "/"
    max_age: int | None = None

    def header(self, value: str) -> str:
        if not value or any(ch in value for ch in "\r\n;"):
            raise SecurityError("invalid_cookie_value")
        parts = [f"{self.name}={value}", f"Path={self.path}", f"SameSite={self.same_site}"]
        if self.secure:
            parts.append("Secure")
        if self.http_only:
            parts.append("HttpOnly")
        if self.max_age is not None:
            parts.append(f"Max-Age={int(self.max_age)}")
        return "; ".join(parts)


SESSION_COOKIE = CookiePolicy(
    name=SESSION_COOKIE_NAME,
    secure=True,
    http_only=True,
    same_site="Lax",
    path="/",
    max_age=30 * 24 * 60 * 60,
)

CSRF_COOKIE = CookiePolicy(
    name=CSRF_COOKIE_NAME,
    secure=True,
    http_only=False,
    same_site="Strict",
    path="/",
)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf(cookie_token: str, header_token: str) -> None:
    left = (cookie_token or "").encode("utf-8")
    right = (header_token or "").encode("utf-8")
    if not left or not right or not hmac.compare_digest(left, right):
        raise InvalidCsrf("invalid_csrf_token")


def validate_origin(origin: str | None, *, allowed_origins: set[str]) -> None:
    if not origin:
        raise InvalidOrigin("origin_required")
    normalized = origin.rstrip("/")
    allowed = {item.rstrip("/") for item in allowed_origins}
    if normalized not in allowed:
        raise InvalidOrigin("origin_not_allowed")


def parse_json_body(raw: bytes, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    if len(raw) > max_bytes:
        raise RequestTooLarge("request_too_large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecurityError("invalid_json") from exc


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if SENSITIVE_KEY_RE.search(str(key))
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def fingerprint(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()
