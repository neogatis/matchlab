# Phase 26 — Privacy, account deletion, data export and retention

## Result

MatchLab now has backend-complete self-service privacy flows for the pre-launch runtime.

This phase closes the repository-level implementation blockers for:

- account deletion flow;
- user data export;
- retention policy and cleanup rules.

It does **not** mark Privacy Policy or Terms URLs as published until the public production runtime is deployed.

## Account deletion

Authenticated endpoint:

- `POST /api/v1/privacy/delete`

The request requires `{"confirmation":"DELETE"}`.

When accepted:

1. the account status becomes `DELETION_REQUESTED`;
2. the profile becomes unavailable for matching immediately;
3. all active sessions are revoked;
4. push devices are disabled;
5. a deletion request is recorded;
6. the primary privacy purge is scheduled for no later than 30 days.

The account cannot log back in after the request.

## External web deletion

Public route:

- `GET /account-deletion`

It contains a browser login + deletion flow, so Android users can initiate deletion outside the mobile app once the production runtime is publicly deployed.

## Purge behavior

`scripts/process_privacy_maintenance.py` processes due deletion requests.

At purge time it removes or detaches:

- profile data;
- relationship-status history;
- questionnaire answers;
- partner preferences;
- legacy partner criteria;
- upload tickets;
- photo database rows;
- photo objects via the deletion outbox;
- interest actions;
- matches and their conversations/messages;
- blocks and associated reports;
- auth identities/challenges/sessions;
- marketing attribution;
- entitlements;
- notifications and push devices;
- consents;
- referral links;
- direct user linkage from product analytics.

The user row becomes a pseudonymous tombstone with an unusable credential, no email/phone identity, and no profile.

Payments/subscriptions may remain linked only to that pseudonymous internal tombstone for provider reconciliation, fraud prevention and applicable accounting/legal obligations.

## Data export

Authenticated endpoint:

- `GET /api/v1/privacy/export`

The export contains the user's own account/profile/questionnaire/preferences/photo metadata, actions, sent messages, reports, marketing attribution, subscriptions/payments, notifications, consents and analytics data.

Internal identifiers belonging to other users are deliberately excluded.

Password hashes, session secrets and push token references are not exported.

## Public policy endpoints

- `GET /privacy`
- `GET /terms`
- `GET /api/v1/privacy/retention`

The legal copy documents the implemented data handling and retention behavior. Public store URLs remain incomplete until these routes are available on the production domain.

## Retention enforcement

The maintenance worker enforces these cleanup windows:

- auth rate-limit state: 1 day;
- auth challenges: 7 days;
- sent auth-outbox records: 30 days;
- completed privacy-request logs: 180 days;
- completed photo-deletion logs: 30 days;
- product analytics: 365 days;
- security audit logs: 365 days;
- moderation audit logs: 365 days.

## Store policy alignment

Apple requires apps supporting account creation to let users initiate deletion inside the app. Google Play requires both an in-app deletion path and an external web resource. The Phase 26 API + web route are designed for those requirements.

## Remaining evidence

Before marking the legal/public-runtime blockers complete:

1. deploy the PostgreSQL HTTP runtime publicly;
2. verify `/privacy`, `/terms`, and `/account-deletion` on the production HTTPS domain;
3. attach privacy maintenance and photo deletion workers to scheduled production jobs;
4. execute a production test-account export;
5. execute a production test-account deletion and confirm the purge;
6. verify the photo object is physically removed;
7. enter the final Privacy Policy, Terms and account-deletion URLs in store metadata.
