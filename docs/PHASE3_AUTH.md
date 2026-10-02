# Phase 3 — Authentication foundation

## Goals

Build authentication on the PostgreSQL foundation before wiring it into the public application.

## Implemented in this phase branch

- Argon2id password hashing for new passwords.
- Transparent verification and upgrade of legacy MatchLab v7 PBKDF2 hashes after a successful login.
- Email normalization/validation.
- Selector + secret session tokens so the bearer secret is never stored raw in PostgreSQL.
- Explicit session expiry, revocation, last-seen timestamp and optional user-agent hash.
- Safe migration of legacy session cookies: raw legacy tokens are converted to SHA-256 hashes during SQLite import.
- PostgreSQL-backed login rate limiting.
- One-time expiring auth challenges with attempt limits.
- Email verification service.
- Phone verification service primitive.
- Password-reset service that revokes all active sessions.
- Data-model foundation for Google/Apple/phone identities.
- Transaction/outbox table for future verification-delivery workers.

## Not activated in production yet

The current public v7 HTTP handlers still use the legacy SQLite authentication code. This branch deliberately does not mix the new PostgreSQL identity system into the legacy monolith before the database cutover is available.

External delivery/provider configuration is also still required before public activation:
- transactional email provider for verification/reset;
- SMS/OTP provider for phone verification;
- Google OAuth client configuration;
- Apple Sign In configuration.

No secrets are stored in Git.

## Session format

New session cookie value:

`selector.secret`

Database:
- stores selector;
- stores SHA-256(secret);
- never stores the complete bearer cookie.

Legacy v7 cookies can be validated after migration using the hashed legacy secret without persisting the raw token.

## Password migration

Existing v7 accounts use PBKDF2-HMAC-SHA256. They are not invalidated.

On the first successful password login:
1. verify legacy PBKDF2 hash;
2. immediately replace it with Argon2id;
3. update password_updated_at.

## Rate limiting

Login attempts use a database-backed bucket keyed by a SHA-256 hash of the normalized email. This works consistently across multiple application replicas without relying on process memory.

Before public production activation, rate limiting will also be applied by route/IP/device context in the HTTP layer.
