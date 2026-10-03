# Phases 29–31 — Android onboarding, photo moderation, pre-launch ops

## Phase 29 — resumable onboarding

Production backend now exposes:

- `GET /api/v1/profile/me`
- `GET /api/v1/onboarding`
- `POST /api/v1/profile/details`
- questionnaire responses now include saved answers for resume

Profile completion now requires:

- basic profile;
- matching-relevant self data;
- readiness answers;
- 64-question questionnaire;
- partner preferences;
- approved photos.

The Android client resumes at the first incomplete step and saves every questionnaire answer immediately.

Android flow:

1. phone/Google authentication;
2. basic profile;
3. relationship/open-to-dating status;
4. readiness;
5. matching-relevant profile details;
6. 64-question compatibility questionnaire;
7. partner criteria and importance;
8. photo upload;
9. waitlist state and own compatibility summary.

Photos use direct presigned uploads to private Neon Storage. The API server does not proxy image bodies.

## Phase 30 — photo moderation

Protected moderator UI:

`/moderation/photos`

Access requires an active MatchLab session and `MODERATOR` or higher console role.

Moderators can:

- see pending photos via short-lived private signed URLs;
- approve photos;
- reject photos with a reason.

Moderation decisions create safe push notifications:

- `PHOTO_APPROVED`
- `PHOTO_REJECTED`

No raw photo URL, user identity, reason, or sensitive profile data is included in the push body.

## Phase 31 — pre-launch operations

Protected operations dashboard:

`/ops`

Access requires `VIEWER` or higher console role.

It exposes aggregate, non-PII launch metrics:

- active users;
- new users in 24h / 7d;
- onboarding funnel;
- questionnaire completion;
- partner preference completion;
- approved-photo completion;
- profiles ready for matching;
- pending moderation volume;
- aggregate gender / relationship / market distribution.

API:

`GET /api/v1/admin/prelaunch/metrics`

## Production evidence

- Phase 29 CI: green
- Android debug APK build + APK signature verification: green
- Phase 30 CI: green
- Phase 31 CI: green
- Railway production deployment: success
- Railway healthcheck: HTTP 200
- maintenance worker: healthy

Google Android OAuth remains intentionally pending until the Android OAuth client is created with the current signing SHA-1. Apple is deferred until Apple Developer Program enrollment.
