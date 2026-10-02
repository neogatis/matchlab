# Phase 10 — Interest and mutual match

## Goal

Replace swipe-like behavior with two explicit candidate decisions:

- `INTERESTED` — “Интересен человек”
- `SKIPPED` — “Пока пропустить”

A conversation is **not** created here. Phase 11 owns chat.

## Pre-launch safety

Candidate actions fail closed.

- If `PRE_LAUNCH_MODE=true`, actions are disabled unless `PRELAUNCH_MATCHING_ENABLED=true`.
- If the settings are absent, the service behaves as if pre-launch is enabled and candidate actions are disabled.
- When `PRE_LAUNCH_MODE=false`, candidate actions are enabled.

This check lives in the service layer, not only in UI routing, so a direct API call cannot bypass it after HTTP cutover.

## Eligibility

Every action reuses the Phase 7 mutual eligibility pipeline.

A user cannot express interest or skip if the pair is currently unavailable because of:
- age/status/readiness requirements;
- missing completed profile/questionnaire/preferences/photos;
- mutual gender direction;
- HARD criteria;
- blocking.

## Interest

A unilateral interest stores only the sender's decision. It does not create a match or reveal whether the other person has already expressed interest.

When both users have `INTERESTED`:
1. the pair is re-evaluated while a PostgreSQL advisory lock is held;
2. exactly one canonical match is created;
3. compatibility and final mutual-fit scores are snapshotted;
4. score components are stored;
5. both users receive an in-app match notification;
6. a mutual-match analytics event is recorded.

Match pairs are always stored as `user1 < user2`.

## Skip

`SKIPPED` means “not now”, not a permanent rejection.

The current v1 cooldown is 30 days. While the cooldown is active, the candidate is excluded from ranking for that user. After it expires, the candidate may be considered again if both profiles are still eligible.

Changing SKIPPED to INTERESTED clears the cooldown.

## Idempotency and concurrency

The pair is serialized with `pg_advisory_xact_lock`.

Repeated interest after a match:
- returns the existing match;
- does not create duplicate matches;
- does not send duplicate match notifications;
- does not emit duplicate mutual-match events.

The database also enforces:
- no self-interest;
- state is INTERESTED or SKIPPED;
- canonical match ordering.

## Candidate ranking

Phase 7 ranking now excludes:
- candidates already marked INTERESTED by the viewer;
- candidates currently under an active SKIPPED cooldown;
- already matched candidates.

There is still no endless feed: ranking defaults to a small candidate set.

## Legacy migration

Legacy v7 likes are imported as `INTERESTED` with `legacy-v7` provenance and their original timestamps.

Legacy match rows are normalized into canonical `user1 < user2` ordering while keeping the original match id and related records.
