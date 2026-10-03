# Phase 25 — Production photo storage and moderation HTTP flow

## Result

The PostgreSQL pre-launch runtime now has an end-to-end private photo flow suitable for waitlist acquisition.

This phase **does not claim that the public Railway service is already cut over**. Store-readiness evidence remains fail-closed until the production deployment and smoke tests are completed.

## User flow

Authenticated users can:

1. request a short-lived private upload ticket;
2. upload JPEG, PNG or WebP directly to S3-compatible object storage;
3. finalize the ticket;
4. list their own photos, including moderation state;
5. choose the main photo;
6. reorder photos;
7. delete photos.

HTTP endpoints:

- `GET /api/v1/photos`
- `POST /api/v1/photos/prepare`
- `POST /api/v1/photos/finalize`
- `POST /api/v1/photos/main`
- `POST /api/v1/photos/reorder`
- `POST /api/v1/photos/delete`

All state-changing calls require the authenticated session, allowed Origin and CSRF token.

## Content validation and privacy

Finalization no longer trusts only the object metadata.

The server now:

- reads the uploaded object with a hard byte limit;
- decodes it with Pillow;
- checks that real image format matches the ticket MIME;
- rejects malformed and animated images;
- rejects images below 200x200;
- enforces a 40-megapixel decode ceiling;
- applies EXIF orientation;
- re-encodes the image;
- strips EXIF/GPS and other source metadata before moderation;
- writes the sanitized object back to the same private key.

A photo row is created only after sanitation succeeds.

## Moderation

Moderators with the existing `MODERATOR` RBAC role can use:

- `GET /api/v1/admin/photos/pending`
- `POST /api/v1/admin/photos/moderate`

Only approved photos count toward profile completion. Two approved photos plus an approved main photo complete the photo step.

## Object deletion

Photo deletion keeps the existing transactional deletion outbox. Database state is removed first and object deletion is processed independently so a failed S3 deletion does not roll back user-visible deletion.

`scripts/process_photo_deletions.py` is the idempotent deletion worker. It still needs to be attached to a production cron/scheduled service.

## Production configuration

Required private storage variables:

- `MATCH_PHOTO_BUCKET`
- `AWS_ENDPOINT_URL_S3`
- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

The production container now installs `requirements-photo.txt`.

## Tests

Phase 25 adds coverage for:

- EXIF stripping and orientation normalization;
- MIME/content mismatch;
- malformed non-image payloads;
- minimum dimensions;
- existing upload-ticket, moderation and deletion rules;
- HTTP runtime/security compilation.

## Remaining deployment evidence

Before closing the App Store object-storage blocker:

1. verify the production bucket is private;
2. verify Railway has all five storage variables;
3. deploy Phase 24/25 runtime;
4. complete a real signed PUT and finalize;
5. verify sanitized metadata is absent on the stored object;
6. approve two photos as a moderator;
7. verify the waitlist profile changes to photo-complete;
8. attach `scripts/process_photo_deletions.py` to a production schedule and exercise deletion end-to-end.
