# Phase 12 — Safety

## Goal

Make blocking, reporting and moderation enforceable in the service layer instead of relying on UI-only controls.

## User actions

Users can:
- block / unblock;
- report a user;
- report a photo;
- report a message;
- request account deletion.

Reports use a controlled reason list and are placed into a moderation queue.

## Report workflow

Statuses:
- OPEN
- IN_REVIEW
- RESOLVED
- DISMISSED

Each report must target exactly one object: a user, photo or message.

A message report is accepted only from a participant in the matched conversation that contains that message.

## Moderation

Supported user actions:
- SOFT_BAN
- BAN
- UNBAN

Photo moderation supports approve/reject.

User moderation is written to both moderation_actions and audit_logs.

## Enforcement

Matching requires both users to have status ACTIVE.

SOFT_BANNED users can still authenticate for account/settings/appeal flows, but are excluded from matching and cannot send chat messages.

BANNED and DELETION_REQUESTED accounts are not eligible for normal authentication.

Existing chat history remains readable after blocking/moderation, while new messages are prevented where safety requires it.

## Account deletion

The user can create an idempotent DELETE data request. The account immediately enters DELETION_REQUESTED and leaves matching/chat.

Retention-aware export and physical purge are completed later with the privacy/security work so moderation and legally required records are not silently destroyed.

## Database guarantees

PostgreSQL enforces:
- valid user safety status;
- valid report workflow status;
- exactly one report target;
- queue index by report status and creation time.
