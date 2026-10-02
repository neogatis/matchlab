from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.events import EVENT_PHOTO_UPLOADED, track_event
from app.db.models import (
    ModerationAction,
    Photo,
    PhotoObjectDeletion,
    PhotoUploadTicket,
    Profile,
)
from .storage import ObjectMetadata, S3PhotoStorage


MIN_PHOTOS = 2
RECOMMENDED_PHOTOS = (3, 5)
MAX_PHOTOS = 5
MAX_FILE_BYTES = 12 * 1024 * 1024
UPLOAD_TTL = timedelta(minutes=10)

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class PhotoError(Exception):
    pass


class PhotoLimitReached(PhotoError):
    pass


class UploadTicketError(PhotoError):
    pass


class PhotoNotFound(PhotoError):
    pass


class ModerationError(PhotoError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_ticket(token: str) -> tuple[int, str]:
    try:
        raw_id, secret = (token or "").split(".", 1)
        ticket_id = int(raw_id)
    except Exception as exc:
        raise UploadTicketError("Invalid upload ticket") from exc
    if ticket_id <= 0 or not secret:
        raise UploadTicketError("Invalid upload ticket")
    return ticket_id, secret


def _photo_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(select(func.count()).select_from(Photo).where(Photo.user_id == user_id))
        or 0
    )


def _active_ticket_count(db: Session, user_id: int, now: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(PhotoUploadTicket)
            .where(
                PhotoUploadTicket.user_id == user_id,
                PhotoUploadTicket.status == "PREPARED",
                PhotoUploadTicket.expires_at > now,
            )
        )
        or 0
    )


def prepare_upload(
    db: Session,
    *,
    user_id: int,
    mime: str,
    storage: S3PhotoStorage,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    profile = db.get(Profile, user_id)
    if profile is None:
        raise PhotoError("Profile not found")

    mime = (mime or "").lower().strip()
    extension = ALLOWED_MIME.get(mime)
    if extension is None:
        raise PhotoError("Unsupported image type")

    if _photo_count(db, user_id) + _active_ticket_count(db, user_id, now) >= MAX_PHOTOS:
        raise PhotoLimitReached(f"Maximum {MAX_PHOTOS} photos")

    secret = secrets.token_urlsafe(32)
    object_key = f"users/{user_id}/{uuid.uuid4().hex}{extension}"
    ticket = PhotoUploadTicket(
        user_id=user_id,
        object_key=object_key,
        mime=mime,
        secret_hash=_sha256(secret),
        status="PREPARED",
        expires_at=now + UPLOAD_TTL,
        created_at=now,
    )
    db.add(ticket)
    db.flush()

    signed = storage.presign_upload(
        object_key,
        mime,
        expires_seconds=int(UPLOAD_TTL.total_seconds()),
    )
    return {
        "ticket": f"{ticket.id}.{secret}",
        "object_key": object_key,
        "upload": signed,
        "expires_at": ticket.expires_at,
        "max_bytes": MAX_FILE_BYTES,
        "allowed_mime": sorted(ALLOWED_MIME),
    }


def _load_ticket_for_update(
    db: Session,
    *,
    user_id: int,
    ticket_token: str,
    now: datetime,
) -> PhotoUploadTicket:
    ticket_id, secret = _parse_ticket(ticket_token)
    ticket = db.execute(
        select(PhotoUploadTicket)
        .where(PhotoUploadTicket.id == ticket_id)
        .with_for_update()
    ).scalar_one_or_none()
    if ticket is None or ticket.user_id != user_id:
        raise UploadTicketError("Invalid upload ticket")
    if ticket.status != "PREPARED":
        raise UploadTicketError("Upload ticket is no longer active")
    if ticket.expires_at <= now:
        ticket.status = "EXPIRED"
        db.flush()
        raise UploadTicketError("Upload ticket expired")
    if not hmac.compare_digest(ticket.secret_hash, _sha256(secret)):
        raise UploadTicketError("Invalid upload ticket")
    return ticket


def finalize_upload(
    db: Session,
    *,
    user_id: int,
    ticket_token: str,
    storage: S3PhotoStorage,
    now: datetime | None = None,
) -> Photo:
    now = now or utcnow()
    ticket = _load_ticket_for_update(
        db,
        user_id=user_id,
        ticket_token=ticket_token,
        now=now,
    )

    if _photo_count(db, user_id) >= MAX_PHOTOS:
        ticket.status = "CANCELLED"
        db.flush()
        raise PhotoLimitReached(f"Maximum {MAX_PHOTOS} photos")

    try:
        metadata = storage.head(ticket.object_key)
    except Exception as exc:
        raise UploadTicketError("Uploaded object is not available") from exc

    if metadata.content_length <= 0 or metadata.content_length > MAX_FILE_BYTES:
        ticket.status = "CANCELLED"
        db.flush()
        try:
            storage.delete(ticket.object_key)
        finally:
            raise PhotoError("Image file size is invalid")

    if metadata.content_type.lower().strip() != ticket.mime:
        ticket.status = "CANCELLED"
        db.flush()
        try:
            storage.delete(ticket.object_key)
        finally:
            raise PhotoError("Uploaded image type does not match the ticket")

    max_order = db.scalar(
        select(func.max(Photo.sort_order)).where(Photo.user_id == user_id)
    )
    any_main = db.execute(
        select(Photo.id).where(Photo.user_id == user_id, Photo.is_main.is_(True))
    ).first() is not None

    photo = Photo(
        user_id=user_id,
        storage_key=ticket.object_key,
        mime=ticket.mime,
        byte_size=metadata.content_length,
        object_etag=metadata.etag,
        is_main=not any_main,
        sort_order=int(max_order if max_order is not None else -1) + 1,
        moderation_status="PENDING",
        created_at=now,
    )
    db.add(photo)
    ticket.status = "CONSUMED"
    ticket.consumed_at = now
    db.flush()
    recompute_photo_completion(db, user_id=user_id)
    track_event(
        db,
        event_type=EVENT_PHOTO_UPLOADED,
        user_id=user_id,
        metadata={"photo_id": photo.id},
        now=now,
    )
    return photo


def list_owner_photos(db: Session, *, user_id: int) -> list[Photo]:
    return list(
        db.execute(
            select(Photo)
            .where(Photo.user_id == user_id)
            .order_by(Photo.sort_order, Photo.id)
        ).scalars()
    )


def visible_photos(db: Session, *, user_id: int) -> list[Photo]:
    return list(
        db.execute(
            select(Photo)
            .where(
                Photo.user_id == user_id,
                Photo.moderation_status == "APPROVED",
                Photo.storage_key.is_not(None),
            )
            .order_by(Photo.is_main.desc(), Photo.sort_order, Photo.id)
        ).scalars()
    )


def primary_photo(db: Session, *, user_id: int) -> Photo | None:
    rows = visible_photos(db, user_id=user_id)
    return rows[0] if rows else None


def visible_photo_payloads(
    db: Session,
    *,
    user_id: int,
    storage: S3PhotoStorage,
    expires_seconds: int = 900,
) -> list[dict[str, Any]]:
    output = []
    for photo in visible_photos(db, user_id=user_id):
        output.append(
            {
                "id": photo.id,
                "is_main": photo.is_main,
                "sort_order": photo.sort_order,
                "mime": photo.mime,
                "url": storage.presign_download(
                    photo.storage_key,
                    expires_seconds=expires_seconds,
                ),
            }
        )
    return output


def set_main_photo(db: Session, *, user_id: int, photo_id: int) -> Photo:
    target = db.get(Photo, photo_id)
    if target is None or target.user_id != user_id:
        raise PhotoNotFound("Photo not found")
    if target.moderation_status == "REJECTED":
        raise PhotoError("Rejected photo cannot be main")

    photos = list(
        db.execute(select(Photo).where(Photo.user_id == user_id)).scalars()
    )
    for photo in photos:
        photo.is_main = False
    db.flush()
    target.is_main = True
    db.flush()
    recompute_photo_completion(db, user_id=user_id)
    return target


def reorder_photos(db: Session, *, user_id: int, ordered_photo_ids: list[int]) -> list[Photo]:
    photos = list_owner_photos(db, user_id=user_id)
    current_ids = [photo.id for photo in photos]
    if len(ordered_photo_ids) != len(set(ordered_photo_ids)):
        raise PhotoError("Photo order contains duplicates")
    if set(ordered_photo_ids) != set(current_ids):
        raise PhotoError("Photo order must contain all current photos exactly once")

    by_id = {photo.id: photo for photo in photos}
    for position, photo_id in enumerate(ordered_photo_ids):
        by_id[photo_id].sort_order = position
    db.flush()
    return [by_id[photo_id] for photo_id in ordered_photo_ids]


def _ensure_approved_main(db: Session, user_id: int) -> None:
    approved = list(
        db.execute(
            select(Photo)
            .where(
                Photo.user_id == user_id,
                Photo.moderation_status == "APPROVED",
            )
            .order_by(Photo.is_main.desc(), Photo.sort_order, Photo.id)
        ).scalars()
    )
    if not approved:
        return
    approved_main = next((photo for photo in approved if photo.is_main), None)
    if approved_main is not None:
        return

    all_photos = list(
        db.execute(select(Photo).where(Photo.user_id == user_id)).scalars()
    )
    for photo in all_photos:
        photo.is_main = False
    db.flush()
    approved[0].is_main = True
    db.flush()


def recompute_photo_completion(db: Session, *, user_id: int) -> bool:
    profile = db.get(Profile, user_id)
    if profile is None:
        raise PhotoError("Profile not found")

    _ensure_approved_main(db, user_id)
    approved_count = int(
        db.scalar(
            select(func.count())
            .select_from(Photo)
            .where(
                Photo.user_id == user_id,
                Photo.moderation_status == "APPROVED",
            )
        )
        or 0
    )
    approved_main = db.execute(
        select(Photo.id).where(
            Photo.user_id == user_id,
            Photo.moderation_status == "APPROVED",
            Photo.is_main.is_(True),
        )
    ).first() is not None

    profile.photos_completed = approved_count >= MIN_PHOTOS and approved_main
    db.flush()
    return profile.photos_completed


def moderate_photo(
    db: Session,
    *,
    photo_id: int,
    status: str,
    actor: str,
    reason: str = "",
    now: datetime | None = None,
) -> Photo:
    now = now or utcnow()
    status = (status or "").upper()
    if status not in {"APPROVED", "REJECTED"}:
        raise ModerationError("Moderation status must be APPROVED or REJECTED")
    if not (actor or "").strip():
        raise ModerationError("Moderation actor is required")

    photo = db.get(Photo, photo_id)
    if photo is None:
        raise PhotoNotFound("Photo not found")

    photo.moderation_status = status
    photo.moderation_reason = (reason or "").strip()[:255] or None
    photo.moderated_at = now
    if status == "REJECTED":
        photo.is_main = False

    db.add(
        ModerationAction(
            actor=actor.strip(),
            target_type="photo",
            target_id=str(photo.id),
            action=f"PHOTO_{status}",
            metadata_json={"reason": photo.moderation_reason or ""},
            created_at=now,
        )
    )
    db.flush()
    recompute_photo_completion(db, user_id=photo.user_id)
    return photo


def delete_photo(db: Session, *, user_id: int, photo_id: int) -> None:
    photo = db.get(Photo, photo_id)
    if photo is None or photo.user_id != user_id:
        raise PhotoNotFound("Photo not found")

    storage_key = photo.storage_key
    was_main = photo.is_main
    db.delete(photo)
    db.flush()

    if storage_key:
        existing = db.execute(
            select(PhotoObjectDeletion).where(PhotoObjectDeletion.object_key == storage_key)
        ).scalar_one_or_none()
        if existing is None:
            db.add(PhotoObjectDeletion(object_key=storage_key, status="PENDING"))

    if was_main:
        _ensure_approved_main(db, user_id)
    recompute_photo_completion(db, user_id=user_id)
    db.flush()


def process_deletion_outbox(
    db: Session,
    *,
    storage: S3PhotoStorage,
    limit: int = 25,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or utcnow()
    rows = list(
        db.execute(
            select(PhotoObjectDeletion)
            .where(PhotoObjectDeletion.status.in_(("PENDING", "FAILED")))
            .order_by(PhotoObjectDeletion.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    done = 0
    failed = 0
    for row in rows:
        row.attempts += 1
        try:
            storage.delete(row.object_key)
            row.status = "DONE"
            row.deleted_at = now
            row.last_error = None
            done += 1
        except Exception as exc:
            row.status = "FAILED"
            row.last_error = str(exc)[:1000]
            failed += 1
    db.flush()
    return {"processed": len(rows), "done": done, "failed": failed}


def photo_progress(db: Session, *, user_id: int) -> dict[str, Any]:
    photos = list_owner_photos(db, user_id=user_id)
    approved = [p for p in photos if p.moderation_status == "APPROVED"]
    pending = [p for p in photos if p.moderation_status == "PENDING"]
    rejected = [p for p in photos if p.moderation_status == "REJECTED"]
    profile = db.get(Profile, user_id)
    return {
        "total": len(photos),
        "approved": len(approved),
        "pending": len(pending),
        "rejected": len(rejected),
        "minimum": MIN_PHOTOS,
        "recommended_min": RECOMMENDED_PHOTOS[0],
        "recommended_max": RECOMMENDED_PHOTOS[1],
        "maximum": MAX_PHOTOS,
        "complete": bool(profile and profile.photos_completed),
    }
