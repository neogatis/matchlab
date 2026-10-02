# Phase 9 — Photos

## Goal

Move profile photos out of SQLite/base64 and into private object storage, with explicit upload ownership, ordering, primary-photo behavior and moderation.

## Production storage

A private Neon Object Storage bucket is provisioned:

- bucket: `matchlab-profile-photos`
- public access: disabled
- browser uploads use short-lived presigned PUT URLs
- downloads use short-lived presigned GET URLs
- storage credentials remain server-side only

Railway has the storage endpoint, access key, secret, region and bucket name configured as secrets. The current public v7 runtime has not been redeployed to use them yet.

## Upload flow

1. Authenticated user requests an upload ticket for JPEG, PNG or WebP.
2. Server creates a random user-scoped object key and a one-time secret upload ticket.
3. Server returns a 10-minute presigned upload URL.
4. Browser uploads directly to private object storage.
5. Client finalizes the ticket.
6. Server verifies the object exists, its content type matches and its size is within the v1 limit.
7. A `photos` row is created as `PENDING`.

The bearer ticket secret is stored only as SHA-256.

## Limits

- minimum approved photos for matching: 2
- recommended: 3–5
- v1 maximum: 5
- v1 file-size maximum: 12 MiB
- accepted: JPEG, PNG, WebP

The five-photo v1 cap is an implementation guardrail and can be changed centrally later.

## Moderation

Statuses:
- PENDING
- APPROVED
- REJECTED

Every moderation decision creates a moderation audit row.

Only `APPROVED` photos can be returned by public/candidate photo helpers. A PENDING or REJECTED image can never become a visible candidate image simply because it has `is_main=true`.

If the current main photo is rejected, another approved photo becomes main automatically when one exists.

## Profile readiness

`profiles.photos_completed` is true only when:
- at least two photos are APPROVED; and
- there is an APPROVED main photo.

The normalized matching eligibility check now requires `photos_completed=true`.

## Ordering and main photo

Users can:
- reorder all current photos;
- choose a non-rejected photo as main;
- delete a photo.

There is a partial unique database index enforcing at most one main photo per user.

## Deletion

Database deletion and object deletion are decoupled with `photo_object_deletions`.

Deleting a photo:
1. removes it from the user-visible database state transactionally;
2. queues its storage key in the deletion outbox;
3. a worker deletes the object idempotently and marks the outbox row DONE.

This avoids keeping a database record that points at an object already removed before the transaction commits.

## Future selfie verification

The schema intentionally does not mark ordinary gallery photos as identity verification. Selfie/liveness verification remains a separate future feature and must not be inferred from normal uploaded images.
