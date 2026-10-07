from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.photos.storage import InvalidImageObject, S3PhotoStorage


MEDIA_PREFIX = "__MATCHLAB_MEDIA_V1__:"
VOICE_MAX_SECONDS = 300

MEDIA_SPECS: dict[str, tuple[str, str, int]] = {
    "image/jpeg": ("image", ".jpg", 12 * 1024 * 1024),
    "image/png": ("image", ".png", 12 * 1024 * 1024),
    "image/webp": ("image", ".webp", 12 * 1024 * 1024),
    "video/mp4": ("video", ".mp4", 60 * 1024 * 1024),
    "video/webm": ("video", ".webm", 60 * 1024 * 1024),
    "video/quicktime": ("video", ".mov", 60 * 1024 * 1024),
    "audio/webm": ("voice", ".webm", 25 * 1024 * 1024),
    "audio/ogg": ("voice", ".ogg", 25 * 1024 * 1024),
    "audio/mp4": ("voice", ".m4a", 25 * 1024 * 1024),
    "audio/mpeg": ("voice", ".mp3", 25 * 1024 * 1024),
}


class ChatMediaError(ValueError):
    pass


def normalize_mime(value: str) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _clean_name(value: str, *, fallback: str) -> str:
    name = str(value or "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return (name[:120] or fallback)


def _spec(mime: str, requested_kind: str | None = None) -> tuple[str, str, int]:
    normalized = normalize_mime(mime)
    spec = MEDIA_SPECS.get(normalized)
    if spec is None:
        raise ChatMediaError("unsupported_chat_media_type")
    kind, extension, max_bytes = spec
    if requested_kind:
        requested = str(requested_kind).strip().lower()
        if requested == "audio":
            requested = "voice"
        if requested != kind:
            raise ChatMediaError("chat_media_kind_mismatch")
    return kind, extension, max_bytes


def _looks_like_mp4_family(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[4:8] == b"ftyp"


def validate_media_signature(*, storage: S3PhotoStorage, object_key: str, mime: str) -> None:
    normalized = normalize_mime(mime)
    if normalized.startswith("image/"):
        return
    try:
        raw = storage.get_prefix(object_key, max_bytes=4096)
    except Exception as exc:
        raise ChatMediaError("chat_media_signature_unavailable") from exc
    if not raw:
        raise ChatMediaError("invalid_chat_media_content")

    ok = False
    if normalized in {"video/mp4", "video/quicktime", "audio/mp4"}:
        ok = _looks_like_mp4_family(raw)
    elif normalized == "video/webm":
        ok = raw.startswith(b"\x1a\x45\xdf\xa3")
    elif normalized == "audio/ogg":
        ok = raw.startswith(b"OggS")
    elif normalized == "audio/webm":
        ok = raw.startswith(b"\x1a\x45\xdf\xa3")
    elif normalized == "audio/mpeg":
        ok = raw.startswith(b"ID3") or (
            len(raw) >= 2
            and raw[0] == 0xFF
            and (raw[1] & 0xE0) == 0xE0
        )
    if not ok:
        raise ChatMediaError("invalid_chat_media_content")


def prepare_object_upload(
    *,
    storage: S3PhotoStorage,
    user_id: int,
    conversation_id: int,
    mime: str,
    kind: str,
    size: int,
    name: str = "",
) -> dict[str, Any]:
    normalized_mime = normalize_mime(mime)
    normalized_kind, extension, max_bytes = _spec(normalized_mime, kind)
    try:
        requested_size = int(size)
    except (TypeError, ValueError) as exc:
        raise ChatMediaError("invalid_chat_media_size") from exc
    if requested_size <= 0 or requested_size > max_bytes:
        raise ChatMediaError("chat_media_too_large")

    object_key = (
        f"users/{int(user_id)}/chat/{int(conversation_id)}/"
        f"{uuid.uuid4().hex}{extension}"
    )
    signed = storage.presign_upload(
        object_key,
        normalized_mime,
        expires_seconds=600,
    )
    fallback = (
        "Голосовое сообщение"
        if normalized_kind == "voice"
        else "Видео"
        if normalized_kind == "video"
        else "Фото"
    )
    return {
        "object_key": object_key,
        "kind": normalized_kind,
        "mime": normalized_mime,
        "name": _clean_name(name, fallback=fallback),
        "max_bytes": max_bytes,
        "upload": signed,
    }


def validate_uploaded_media(
    *,
    storage: S3PhotoStorage,
    user_id: int,
    conversation_id: int,
    media: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(media, dict):
        raise ChatMediaError("invalid_chat_media")

    object_key = str(media.get("object_key", "")).strip()
    expected_prefix = f"users/{int(user_id)}/chat/{int(conversation_id)}/"
    if not object_key.startswith(expected_prefix):
        raise ChatMediaError("invalid_chat_media_key")

    mime = normalize_mime(str(media.get("mime", "")))
    kind, _, max_bytes = _spec(mime, str(media.get("kind", "")))

    try:
        metadata = storage.head(object_key)
    except Exception as exc:
        raise ChatMediaError("chat_media_not_uploaded") from exc

    if metadata.content_length <= 0 or metadata.content_length > max_bytes:
        try:
            storage.delete(object_key)
        finally:
            raise ChatMediaError("chat_media_too_large")
    if normalize_mime(metadata.content_type) != mime:
        try:
            storage.delete(object_key)
        finally:
            raise ChatMediaError("chat_media_content_type_mismatch")

    if kind == "image":
        try:
            metadata = storage.sanitize_image(
                object_key,
                expected_mime=mime,
                max_bytes=max_bytes,
            )
        except InvalidImageObject as exc:
            try:
                storage.delete(object_key)
            finally:
                raise ChatMediaError(str(exc)) from exc
        except Exception as exc:
            raise ChatMediaError("chat_image_sanitize_failed") from exc
    else:
        try:
            validate_media_signature(
                storage=storage,
                object_key=object_key,
                mime=mime,
            )
        except ChatMediaError:
            try:
                storage.delete(object_key)
            finally:
                raise

    fallback = (
        "Голосовое сообщение"
        if kind == "voice"
        else "Видео"
        if kind == "video"
        else "Фото"
    )
    result: dict[str, Any] = {
        "kind": kind,
        "mime": mime,
        "object_key": object_key,
        "name": _clean_name(str(media.get("name", "")), fallback=fallback),
        "size": int(metadata.content_length),
    }

    duration_raw = media.get("duration_seconds")
    if duration_raw not in (None, ""):
        try:
            duration = max(0.0, float(duration_raw))
        except (TypeError, ValueError) as exc:
            raise ChatMediaError("invalid_chat_media_duration") from exc
        if kind == "voice" and duration > VOICE_MAX_SECONDS + 3:
            raise ChatMediaError("voice_message_too_long")
        result["duration_seconds"] = round(duration, 1)

    return result


def encode_media_body(media: dict[str, Any], caption: str = "") -> str:
    text = str(caption or "").strip()
    if len(text) > 1000:
        raise ChatMediaError("chat_media_caption_too_long")
    payload = {
        "v": 1,
        "caption": text,
        "kind": media["kind"],
        "mime": media["mime"],
        "object_key": media["object_key"],
        "name": media.get("name") or "",
        "size": int(media.get("size") or 0),
    }
    if media.get("duration_seconds") is not None:
        payload["duration_seconds"] = float(media["duration_seconds"])
    packed = MEDIA_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(packed) > 4000:
        raise ChatMediaError("chat_media_message_too_large")
    return packed


def decode_media_body(body: str) -> dict[str, Any] | None:
    raw = str(body or "")
    if not raw.startswith(MEDIA_PREFIX):
        return None
    try:
        payload = json.loads(raw[len(MEDIA_PREFIX):])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("v") != 1:
        return None
    try:
        kind, _, _ = _spec(
            str(payload.get("mime", "")),
            str(payload.get("kind", "")),
        )
    except ChatMediaError:
        return None
    object_key = str(payload.get("object_key", "")).strip()
    if not object_key:
        return None
    result: dict[str, Any] = {
        "kind": kind,
        "mime": normalize_mime(str(payload.get("mime", ""))),
        "object_key": object_key,
        "name": _clean_name(
            str(payload.get("name", "")),
            fallback=(
                "Голосовое сообщение"
                if kind == "voice"
                else "Видео"
                if kind == "video"
                else "Фото"
            ),
        ),
        "size": max(0, int(payload.get("size") or 0)),
        "caption": str(payload.get("caption", "") or "").strip()[:1000],
    }
    if payload.get("duration_seconds") is not None:
        try:
            result["duration_seconds"] = max(
                0.0, float(payload.get("duration_seconds") or 0)
            )
        except (TypeError, ValueError):
            pass
    return result


def preview_text(media: dict[str, Any], caption: str = "") -> str:
    text = str(caption or "").strip()
    if text:
        return text
    return {
        "voice": "🎙 Голосовое сообщение",
        "video": "🎥 Видео",
        "image": "📷 Фото",
    }.get(str(media.get("kind", "")), "Вложение")


def public_media_payload(media: dict[str, Any], *, message_id: int) -> dict[str, Any]:
    payload = {
        "kind": media["kind"],
        "mime": media["mime"],
        "name": media.get("name") or "",
        "size": int(media.get("size") or 0),
        "url": f"/api/v1/chat/media/{int(message_id)}",
    }
    if media.get("duration_seconds") is not None:
        payload["duration_seconds"] = media["duration_seconds"]
    return payload
