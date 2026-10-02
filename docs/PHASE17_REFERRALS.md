# Phase 17 — Referral system

## Goal

Give every user a unique referral code and measure the path from invitation to useful completed profile.

The product specification requires tracking:

- invite
- registration
- completed_profile

The invitation copy remains “Пригласить друга пройти тест совместимости”.

## Referral code

Every user already has a unique `users.referral_code`.

`referral_link` adds the code as the `ref` query parameter while preserving existing UTM parameters.

## Registration attribution

Email registration now accepts an optional referral code.

If the code belongs to an eligible referrer:
- `users.referred_by` is set;
- a normalized `referrals` row is created;
- the literal input is stored in `marketing_attribution.referral_input`;
- a `REFERRAL_REGISTRATION` event is emitted.

An invalid or expired referral code does not block registration. It is still retained in marketing attribution for diagnosis.

A referred user can only be attributed once. Re-attribution to another referrer is rejected.

Self-referral is rejected.

## Invite tracking

Calling `record_invite`:
- increments `users.invites_sent`;
- records `REFERRAL_INVITE`;
- stores only the coarse share channel, not recipient contact data.

## Completed profile

When a referred user's profile reaches the product's completed-profile state, `mark_referred_profile_completed` records the first completion timestamp and emits `REFERRAL_COMPLETED_PROFILE` exactly once.

The profile-completion workflow can call this helper during the HTTP cutover.

## Metrics

Per referrer:
- invites_sent
- registrations
- completed_profiles
- registration_rate
- completion_rate

These metrics measure useful acquired profiles rather than clicks alone.

## Privacy

The referral subsystem does not require address-book upload, phone contacts or email recipient lists.

## Existing database

The normalized `referrals` and `marketing_attribution` tables were part of the production PostgreSQL foundation, so Phase 17 requires no new schema migration.
